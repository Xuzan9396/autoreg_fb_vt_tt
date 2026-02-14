import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlencode

from autovt.logs import get_logger
from autovt.settings import ADB_BIN, ADB_SERVER_ADDR, CAP_METHOD, TOUCH_METHOD

log = get_logger("adb")
# 缓存一次已解析的 adb 绝对路径，避免每次刷新设备都重复探测。
_RESOLVED_ADB_BIN: str | None = None


def _adb_executable_name() -> str:
    """根据当前操作系统返回 adb 可执行文件名。"""
    # Windows 平台可执行文件后缀是 .exe。
    if platform.system().lower().startswith("win"):
        return "adb.exe"
    # macOS / Linux 等类 Unix 平台统一用 adb。
    return "adb"


def _prepend_to_path(dir_path: str) -> None:
    """把目录放到 PATH 最前面，确保子进程优先命中我们确认过的 adb。"""
    # 读取当前 PATH；Finder 启动的 .app 场景下这里通常很短。
    current_path = os.environ.get("PATH", "")
    # 解析现有 PATH 为列表，顺便过滤空字符串。
    parts = [item for item in current_path.split(os.pathsep) if item]
    if dir_path in parts:
        # 已存在就不重复插入，避免 PATH 越来越长。
        return
    # 放到最前面，保证 `adb` 命令优先解析到目标目录。
    os.environ["PATH"] = os.pathsep.join([dir_path, *parts]) if parts else dir_path


def _hidden_subprocess_kwargs() -> dict:
    """返回子进程启动参数（Windows 下隐藏 adb 命令窗口）。"""
    # 仅 Windows 需要处理“命令窗闪烁”问题。
    if not platform.system().lower().startswith("win"):
        return {}

    # 优先使用 Python 提供的 CREATE_NO_WINDOW 常量；旧环境兜底硬编码值。
    create_no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    startupinfo = subprocess.STARTUPINFO()  # 构造 Windows 启动信息对象。
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW  # 告诉系统使用窗口显示控制标志。
    startupinfo.wShowWindow = 0  # SW_HIDE：隐藏窗口。
    return {
        "creationflags": create_no_window,
        "startupinfo": startupinfo,
    }


def _bundled_adb_candidates() -> list[str]:
    """返回项目内置 adb 候选路径（优先用于打包后运行）。"""
    # 统一读取系统标识，用于区分 mac / windows 目录。
    system_name = platform.system().lower()
    # 统一读取可执行文件名（adb 或 adb.exe）。
    adb_name = _adb_executable_name()

    # 候选目录集合：包含源码运行目录和打包运行目录。
    roots: list[Path] = []

    # 普通源码/venv 运行：autovt/adb.py 的上两级就是项目根目录。
    roots.append(Path(__file__).resolve().parents[1])

    # 打包运行（如 PyInstaller）会把资源解压到 _MEIPASS，补充该目录做兜底。
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        roots.append(Path(str(meipass)))

    # 根据平台拼接内置 adb 路径。
    candidates: list[str] = []
    for root in roots:
        if system_name == "darwin":
            candidates.append(str(root / "adb" / "mac" / "platform-tools" / adb_name))
        elif system_name.startswith("win"):
            candidates.append(str(root / "adb" / "windows" / "platform-tools" / adb_name))
    return candidates


def _candidate_adb_paths() -> list[tuple[str, str]]:
    """收集 adb 候选路径（按优先级从高到低），并记录来源标签。"""
    # 用列表保存候选及来源，后面会按顺序尝试。
    candidates: list[tuple[str, str]] = []

    # 1) 用户显式覆盖：优先级最高（适合打包后手动指定）。
    env_override = os.environ.get("AUTOVT_ADB_BIN", "").strip()
    if env_override:
        candidates.append((env_override, "AUTOVT_ADB_BIN"))

    # 2) 项目内置 adb（你仓库的 adb/mac 与 adb/windows）优先使用。
    candidates.extend((path, "BUNDLED_ADB") for path in _bundled_adb_candidates())

    # 3) 项目配置项：默认是 "adb"，也支持你改成绝对路径。
    if ADB_BIN:
        candidates.append((ADB_BIN, "SETTINGS_ADB_BIN"))

    # 4) 当前 PATH 命中的 adb（终端运行通常会命中）。
    which_adb = shutil.which("adb")
    if which_adb:
        candidates.append((which_adb, "PATH_WHICH_ADB"))

    # 统一可执行文件名（Windows: adb.exe，其他平台: adb）。
    adb_name = _adb_executable_name()

    # 5) Android SDK 环境变量里的 adb。
    for sdk_var in ("ANDROID_SDK_ROOT", "ANDROID_HOME"):
        sdk_root = os.environ.get(sdk_var, "").strip()
        if not sdk_root:
            continue
        candidates.append((str(Path(sdk_root) / "platform-tools" / adb_name), sdk_var))

    # 6) 平台常见安装位置兜底（打包后最常用）。
    home_dir = Path.home()
    system_name = platform.system().lower()
    if system_name == "darwin":
        # macOS：兼容 Homebrew 与 Android Studio 默认目录。
        candidates.extend(
            [
                ("/opt/homebrew/bin/adb", "PLATFORM_DEFAULT"),
                ("/usr/local/bin/adb", "PLATFORM_DEFAULT"),
                (str(home_dir / "Library/Android/sdk/platform-tools" / adb_name), "PLATFORM_DEFAULT"),
                (str(home_dir / "Android/Sdk/platform-tools" / adb_name), "PLATFORM_DEFAULT"),
            ]
        )
    elif system_name.startswith("win"):
        # Windows：兼容 Android Studio 默认 SDK 目录与常见自定义目录。
        local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
        user_profile = os.environ.get("USERPROFILE", "").strip()
        program_files = os.environ.get("ProgramFiles", "").strip()
        if local_app_data:
            candidates.append((str(Path(local_app_data) / "Android/Sdk/platform-tools" / adb_name), "PLATFORM_DEFAULT"))
        if user_profile:
            candidates.append((str(Path(user_profile) / "AppData/Local/Android/Sdk/platform-tools" / adb_name), "PLATFORM_DEFAULT"))
        if program_files:
            candidates.append((str(Path(program_files) / "Android/Android Studio/sdk/platform-tools" / adb_name), "PLATFORM_DEFAULT"))
        candidates.append((str(Path("C:/Android/Sdk/platform-tools") / adb_name), "PLATFORM_DEFAULT"))
    else:
        # Linux：兼容常见 SDK 目录与系统级安装位置。
        candidates.extend(
            [
                (str(home_dir / "Android/Sdk/platform-tools" / adb_name), "PLATFORM_DEFAULT"),
                (str(home_dir / "Android/sdk/platform-tools" / adb_name), "PLATFORM_DEFAULT"),
                ("/usr/bin/adb", "PLATFORM_DEFAULT"),
                ("/usr/local/bin/adb", "PLATFORM_DEFAULT"),
            ]
        )

    # 7) Airtest 内置 adb 路径（最后兜底，跨环境可用）。
    try:
        # 延迟导入，避免主进程启动早期无谓加载 airtest 大依赖。
        from airtest.core.android.adb import ADB as AirtestADB

        builtin_adb = AirtestADB.get_adb_path()
        if builtin_adb:
            candidates.append((str(builtin_adb), "AIRTEST_BUILTIN"))
    except Exception:
        # 兜底失败不影响主流程，后续继续尝试其他候选。
        pass

    # 去重并保持原有顺序，避免同一路径重复探测。
    deduped: list[tuple[str, str]] = []
    seen: set[str] = set()
    for item, source in candidates:
        normalized = str(item).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append((normalized, source))
    return deduped


def resolve_adb_bin() -> str:
    """解析可用 adb 可执行文件路径，并写回当前进程环境。"""
    global _RESOLVED_ADB_BIN
    # 命中缓存直接返回，减少频繁 IO/探测。
    if _RESOLVED_ADB_BIN:
        return _RESOLVED_ADB_BIN

    # 保存探测轨迹，失败时用于报错提示，帮助快速定位问题。
    probe_traces: list[str] = []
    for candidate, source in _candidate_adb_paths():
        # 判断是否是纯命令名（例如 adb / adb.exe）。
        # 这里不能只判断 "/"，因为 Windows 绝对路径一般用 "\"。
        candidate_path = Path(candidate)
        is_command_name = (candidate_path.name == candidate) and (not candidate_path.is_absolute())
        if is_command_name:
            resolved = shutil.which(candidate)
            probe_traces.append(f"[{source}] {candidate} -> {resolved or 'NOT_FOUND'}")
            if not resolved:
                continue
            candidate = resolved

        adb_path = Path(candidate).expanduser()
        probe_traces.append(f"[{source}] {adb_path}")

        # 必须先存在且是文件，才能继续可执行性判断。
        if not (adb_path.exists() and adb_path.is_file()):
            continue

        # 非 Windows 平台，如果内置 adb 丢失执行权限，尝试自动补 +x。
        if platform.system().lower() != "windows" and not os.access(adb_path, os.X_OK):
            try:
                # 保留原权限位并加上用户可执行位。
                adb_path.chmod(adb_path.stat().st_mode | 0o111)
            except Exception:
                # chmod 失败则继续按原状态判断，避免中断主流程。
                pass

        # 最终仍不可执行则跳过该候选。
        if not os.access(adb_path, os.X_OK):
            continue

        # 确认目录进入 PATH，确保后续子进程也能直接调用 `adb`。
        _prepend_to_path(str(adb_path.parent))

        # 如果是 SDK 路径，顺手补齐 ANDROID_HOME / ANDROID_SDK_ROOT。
        # 例如 /Users/xx/Library/Android/sdk/platform-tools/adb -> sdk 根目录是上两级。
        try:
            if adb_path.parent.name == "platform-tools":
                sdk_root = str(adb_path.parent.parent)
                os.environ.setdefault("ANDROID_HOME", sdk_root)
                os.environ.setdefault("ANDROID_SDK_ROOT", sdk_root)
        except Exception:
            # 环境变量写入失败时不阻断主流程。
            pass

        _RESOLVED_ADB_BIN = str(adb_path)
        log.info(
            "已解析 adb 路径",
            adb_bin=_RESOLVED_ADB_BIN,
            adb_source=source,
            env_autovt_adb_bin=os.environ.get("AUTOVT_ADB_BIN", "").strip(),
            env_android_sdk_root=os.environ.get("ANDROID_SDK_ROOT", "").strip(),
            env_android_home=os.environ.get("ANDROID_HOME", "").strip(),
        )
        return _RESOLVED_ADB_BIN

    # 全部候选都失败时，给出可读性更强的诊断信息。
    path_value = os.environ.get("PATH", "")
    debug_detail = "; ".join(probe_traces) if probe_traces else "NO_CANDIDATES"
    raise RuntimeError(
        "未找到可用 adb。"
        f" ADB_BIN={ADB_BIN!r};"
        f" 探测轨迹={debug_detail};"
        f" 当前PATH={path_value!r};"
        " 可设置环境变量 AUTOVT_ADB_BIN=/绝对路径/adb 后重试；"
        " 也可检查项目内 adb/mac 或 adb/windows 是否完整。"
    )


def ensure_adb_environment() -> str:
    """对外暴露的 adb 环境初始化入口。"""
    # 直接复用解析逻辑；返回值是最终 adb 绝对路径。
    return resolve_adb_bin()


def list_online_serials() -> list[str]:
    """读取 adb 在线设备 serial 列表。"""
    try:
        # 先解析 adb 绝对路径，兼容 Finder 启动的 .app 环境。
        adb_bin = resolve_adb_bin()
        # 调用 `adb devices` 获取设备清单。
        result = subprocess.run(
            [adb_bin, "devices"],
            capture_output=True,
            text=True,
            check=True,
            **_hidden_subprocess_kwargs(),  # Windows 下隐藏 adb 子进程窗口，避免界面闪烁。
        )
        log.debug("执行 adb devices 成功")
    except FileNotFoundError as exc:
        # 机器上没装 adb 或 PATH 里找不到 adb 时，给出清晰报错。
        log.exception("未找到 adb 命令")
        raise RuntimeError(
            f"未找到 adb 命令，请确认 {ADB_BIN} 已安装并在 PATH 中，"
            "或设置 AUTOVT_ADB_BIN=/绝对路径/adb。"
        ) from exc

    # 最终返回的在线设备 serial 列表。
    serials: list[str] = []
    # 第一行是标题（List of devices attached），从第二行开始解析。
    for line in result.stdout.splitlines()[1:]:
        # 去掉行首尾空白，便于统一处理。
        line = line.strip()
        if not line:
            # 跳过空行。
            continue

        # 典型格式：<serial>\t<status>
        parts = line.split()
        if len(parts) < 2:
            # 非标准行直接跳过，避免异常中断。
            continue

        serial, status = parts[0], parts[1]
        if status == "device":
            # 只接收状态为 device 的设备（offline/unauthorized 不加入）。
            serials.append(serial)

    # 把在线 serial 列表交给上层。
    # log.info("读取在线设备完成", count=len(serials), serials=serials)
    return serials


def build_device_uri(serial: str) -> str:
    # 按 Airtest 官方格式组装设备 URI（包含截图/触控参数）。
    # 示例：Android://127.0.0.1:5037/<serial>?cap_method=javacap&touch_method=maxtouch
    query = urlencode(
        {
            # 显式指定截图方式，避免默认先尝试 MINICAP 产生噪音日志。
            "cap_method": CAP_METHOD.lower(),
            # 显式指定触控方式，便于在不同机型稳定复现。
            "touch_method": TOUCH_METHOD.lower(),
        }
    )
    uri = f"android://{ADB_SERVER_ADDR}/{serial}?{query}"
    log.debug("组装设备 URI", serial=serial, uri=uri)
    return uri


def safe_path_part(raw: str) -> str:
    # 把 serial 里的特殊字符替换成 `_`，避免作为目录名时出问题。
    return re.sub(r"[^0-9A-Za-z._-]+", "_", raw)
