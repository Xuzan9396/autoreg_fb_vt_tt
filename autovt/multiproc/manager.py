from __future__ import annotations

import multiprocessing as mp
import os
import queue
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

# 尝试导入 psutil，用于实现进程级“即时暂停/恢复”。
try:
    # 导入 psutil，便于直接挂起/恢复 worker 进程。
    import psutil
# psutil 不可用时降级回原有命令队列模式。
except Exception:
    # 标记为 None，后续分支里自动走兼容逻辑。
    psutil = None

from autovt.adb import list_online_serials, resolve_adb_bin
from autovt.logs import get_logger
from autovt.multiproc.process_guard import cleanup_autovt_helper_processes, collect_autovt_helper_processes
from autovt.multiproc.worker import worker_main
from autovt.settings import ADB_SERVER_ADDR, WORKER_STOP_FORCE_TIMEOUT_SEC, WORKER_STOP_GRACE_TIMEOUT_SEC
from autovt.userdb import UserDB

log = get_logger("manager")
# 启动探针等待秒数：用于识别“启动即退出”的秒退进程。
WORKER_STARTUP_PROBE_SEC = 0.4
# Facebook 应用包名（卸载时使用）。
FACEBOOK_PACKAGE_NAME = "com.facebook.katana"
# Facebook 安装包相对路径（安装时使用）。
FACEBOOK_APK_RELATIVE_PATH = Path("apks") / "facebook.apk"
# Vinted 应用包名（卸载时使用）。
VINTED_PACKAGE_NAME = "fr.vinted"
# Vinted 安装包相对路径（安装时使用）。
VINTED_APK_RELATIVE_PATH = Path("apks") / "vinted.apk"
# Yosemite 输入法包名（安装后用于识别应用）。
YOSEMITE_PACKAGE_NAME = "com.netease.nie.yosemite"
# Yosemite 安装包相对路径（airtest 资源目录）。
YOSEMITE_APK_RELATIVE_PATH = Path("airtest") / "core" / "android" / "static" / "apks" / "Yosemite.apk"
# 允许启动任务使用的注册方式集合。
VALID_REGISTER_MODES = {"facebook", "vinted"}


def _normalize_register_mode(register_mode: str) -> str:
    """标准化注册方式文本，统一做空白清理和小写化。"""
    # 把输入值转成字符串并清理前后空白。
    normalized_value = str(register_mode or "").strip().lower()
    # 返回标准化后的注册方式。
    return normalized_value


def _hidden_subprocess_kwargs() -> dict:
    """返回子进程启动参数（Windows 下隐藏 adb 命令窗口）。"""
    # 非 Windows 平台无需额外参数。
    if not sys.platform.lower().startswith("win"):
        return {}
    # 优先使用 Python 常量，旧环境兜底硬编码值。
    create_no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    # 构造 Windows 启动信息对象。
    startupinfo = subprocess.STARTUPINFO()
    # 使用窗口显示控制标志。
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    # SW_HIDE：隐藏窗口。
    startupinfo.wShowWindow = 0
    # 返回窗口隐藏参数。
    return {
        "creationflags": create_no_window,
        "startupinfo": startupinfo,
    }


def _ensure_spawn_pythonpath() -> None:
    """确保 spawn 子进程可导入 autovt 包。"""
    # 解析应用根目录（包含 autovt 包的上一级）。
    app_root = Path(__file__).resolve().parents[2]
    # 转成字符串，便于写入环境变量。
    app_root_text = str(app_root)
    # 读取当前 PYTHONPATH（可能为空）。
    old_pythonpath = os.environ.get("PYTHONPATH", "")
    # 拆分并清洗已有路径列表。
    parts = [part for part in old_pythonpath.split(os.pathsep) if part.strip()]
    # 已存在时无需重复写入。
    if app_root_text in parts:
        return
    # 把应用根目录放在最前面，保证优先导入本项目代码。
    new_parts = [app_root_text, *parts]
    # 回写新的 PYTHONPATH，供后续 spawn 子进程继承。
    os.environ["PYTHONPATH"] = os.pathsep.join(new_parts)
    log.info("已补齐 spawn PYTHONPATH", app_root=app_root_text)


@dataclass
class WorkerHandle:
    # 设备序列号。
    serial: str
    # 子进程对象。
    process: mp.Process
    # 主进程用于通知子进程停止的事件。
    stop_event: mp.Event
    # 主进程发给子进程的命令队列。
    command_queue: mp.Queue
    # 最近一次状态（starting/running/paused/...）。
    last_state: str = "starting"
    # 最近一次状态详情。
    last_detail: str = ""
    # 最近一次状态更新时间。
    updated_at: float = field(default_factory=time.time)


class DeviceProcessManager:
    def __init__(self, loop_interval_sec: float) -> None:
        # 先保证子进程 import 路径可用，避免打包态 worker 秒退。
        _ensure_spawn_pythonpath()

        # 预先解析当前项目使用的 adb 路径，供后续辅助进程清理复用。
        self._adb_bin = resolve_adb_bin()
        # 强制使用 spawn：多平台行为更一致，尤其是 macOS。
        self._ctx = mp.get_context("spawn")
        # 子进程自动轮询间隔。
        self._loop_interval_sec = loop_interval_sec
        # 子进程 -> 主进程 的事件队列。
        self._event_queue: mp.Queue = self._ctx.Queue()
        # 当前所有运行中的 worker 句柄。
        self._workers: dict[str, WorkerHandle] = {}
        # 为跨线程 GUI 操作准备递归锁，避免后台动作和前台刷新并发改状态表。
        self._state_lock = threading.RLock()
        # 为 close 幂等控制准备独立锁，避免 GUI/window/signal 重复收口。
        self._close_lock = threading.RLock()
        # 标记当前 manager 是否已经执行过最终 close。
        self._closed = False
        # 缓存数据库文件路径，后续按需创建短连接，避免跨线程复用同一 SQLite 连接。
        self._user_db_path = UserDB().path
        # manager 初始化完成后先清一次历史孤儿辅助进程，避免新 GUI 接上旧残留。
        self._cleanup_helper_processes(reason="manager_init_orphan_cleanup", orphan_only=True)
        log.info("DeviceProcessManager 初始化完成", loop_interval_sec=loop_interval_sec, user_db_path=str(self._user_db_path))

    def close(self) -> None:
        # 使用幂等锁保护 close，避免多个退出入口重复回收。
        with self._close_lock:
            # 已执行过 close 时直接返回，避免重复清理同一批进程。
            if self._closed:
                # 记录幂等命中日志，便于排查重复退出链路。
                log.debug("DeviceProcessManager.close 重复调用，已跳过")
                # 结束本次 close。
                return
            # 标记 close 已执行，后续调用直接走幂等返回。
            self._closed = True
        # close 作为最终兜底入口，再做一次全局辅助进程清理。
        self._cleanup_helper_processes(reason="manager_close_final_cleanup", orphan_only=False)
        # 记录 close 完成日志，便于排查最终收口是否执行。
        log.debug("DeviceProcessManager.close 调用完成（当前无常驻 SQLite 连接）")

    def _format_helper_processes_for_log(self, processes: list[dict[str, object]]) -> list[str]:
        """把辅助进程列表压缩成稳定可读的日志片段。"""
        # 初始化压缩结果列表。
        items: list[str] = []
        # 逐个拼接关键信息，方便日志快速定位残留来源。
        for process in processes:
            # 读取当前进程 pid。
            pid = int(process.get("pid", 0) or 0)
            # 读取当前进程父 pid。
            ppid = int(process.get("ppid", 0) or 0)
            # 读取当前进程 serial。
            serial = str(process.get("serial", "") or "").strip()
            # 读取当前进程命中关键字列表。
            matched_tokens = ",".join(str(token) for token in process.get("matched_tokens", []) if str(token).strip())
            # 读取命令行文本。
            cmdline_text = str(process.get("cmdline_text", "") or "").strip()
            # 组装当前进程摘要。
            items.append(f"pid={pid} ppid={ppid} serial={serial or '-'} tokens={matched_tokens or '-'} cmd={cmdline_text}")
        # 返回压缩后的进程摘要列表。
        return items

    def _collect_helper_processes(self, serial: str = "", orphan_only: bool = False) -> list[dict[str, object]]:
        """读取当前 autovt 辅助进程快照，供启动前诊断和停机后复检复用。"""
        # 调用公共守卫模块扫描辅助进程。
        return collect_autovt_helper_processes(
            adb_bin=self._adb_bin,
            serial=serial,
            orphan_only=orphan_only,
        )

    def _log_helper_cleanup_result(self, result: dict[str, object]) -> None:
        """统一记录辅助进程清理结果。"""
        # 读取命中的辅助进程数量。
        matched = int(result.get("matched", 0) or 0)
        # 读取 kill 后仍残留的进程列表。
        remaining = list(result.get("remaining", []) or [])
        # 没有命中且没有残留时无需刷日志。
        if matched <= 0 and not remaining:
            return
        # 把命中进程压缩成日志友好的文本。
        process_items = self._format_helper_processes_for_log(list(result.get("processes", []) or []))
        # 命中时先记录一次清理结果摘要。
        log.warning(
            "辅助进程清理已执行",
            reason=str(result.get("reason", "") or "").strip(),
            serial=str(result.get("serial", "") or "").strip(),
            orphan_only=bool(result.get("orphan_only", False)),
            matched=matched,
            terminated=int(result.get("terminated", 0) or 0),
            killed=int(result.get("killed", 0) or 0),
            failed=int(result.get("failed", 0) or 0),
            processes=process_items,
        )
        # kill 后仍有残留时升级为错误日志，便于快速定位。
        if remaining:
            # 记录剩余残留进程详情。
            log.error(
                "辅助进程清理后仍有残留",
                reason=str(result.get("reason", "") or "").strip(),
                serial=str(result.get("serial", "") or "").strip(),
                remaining=self._format_helper_processes_for_log(remaining),
            )

    def _cleanup_helper_processes(self, serial: str = "", orphan_only: bool = False, reason: str = "") -> dict[str, object]:
        """清理 autovt 自有辅助进程，并统一记录结果日志。"""
        # 调用公共守卫模块执行辅助进程清理。
        result = cleanup_autovt_helper_processes(
            adb_bin=self._adb_bin,
            log=log,
            serial=serial,
            orphan_only=orphan_only,
            reason=reason,
        )
        # 统一输出清理结果日志。
        self._log_helper_cleanup_result(result)
        # 返回清理结果给调用方继续决策。
        return result

    def _merge_helper_cleanup_results(
        self,
        first: dict[str, object] | None,
        second: dict[str, object] | None,
    ) -> dict[str, object]:
        """合并同一阶段两次辅助进程清理结果，便于 stop 路径汇总展示。"""
        # 统一把空值转成空字典，简化后续读取。
        first_result = dict(first or {})
        # 统一把空值转成空字典，简化后续读取。
        second_result = dict(second or {})
        # 读取第二次复检残留，优先以更晚结果为准。
        final_remaining = list(second_result.get("remaining", []) or first_result.get("remaining", []) or [])
        # 返回汇总后的清理结果。
        return {
            "reason": str(second_result.get("reason", "") or first_result.get("reason", "") or "").strip(),
            "serial": str(second_result.get("serial", "") or first_result.get("serial", "") or "").strip(),
            "matched": int(first_result.get("matched", 0) or 0) + int(second_result.get("matched", 0) or 0),
            "terminated": int(first_result.get("terminated", 0) or 0) + int(second_result.get("terminated", 0) or 0),
            "killed": int(first_result.get("killed", 0) or 0) + int(second_result.get("killed", 0) or 0),
            "failed": int(first_result.get("failed", 0) or 0) + int(second_result.get("failed", 0) or 0),
            "remaining": final_remaining,
        }

    def _open_user_db(self, connect_timeout_sec: float = 1.2, busy_timeout_ms: int = 1200) -> UserDB:
        """创建一个短生命周期数据库连接，避免跨线程复用同一 SQLite 连接。"""
        # 基于缓存的数据库路径创建独立连接对象。
        user_db = UserDB(
            db_path=self._user_db_path,
            connect_timeout_sec=connect_timeout_sec,
            busy_timeout_ms=busy_timeout_ms,
        )
        # 建立 SQLite 连接，供当前调用链短时使用。
        user_db.connect()
        # 返回已连接的数据库对象。
        return user_db

    def _get_user_rows_by_devices(self, user_db: UserDB, serials: list[str]) -> dict[str, dict[str, object]]:
        """按设备 serial 读取占用账号信息。"""
        # 预留批量查询接口位，当前仍逐设备回查，避免影响兼容性。
        user_rows: dict[str, dict[str, object]] = {}
        # 逐个设备读取当前账号占用关系。
        for serial in serials:
            user_row = user_db.get_user_by_device(serial)
            # 命中记录时写入映射，供状态组装阶段复用。
            if user_row:
                user_rows[str(serial)] = dict(user_row)
        # 返回设备到账号行的映射结果。
        return user_rows

    def _get_worker(self, serial: str) -> WorkerHandle | None:
        """在线程锁保护下读取单个 worker 句柄。"""
        # 使用状态锁保护共享 worker 表读取。
        with self._state_lock:
            # 返回指定设备的 worker 句柄。
            return self._workers.get(serial)

    def _snapshot_worker_serials(self) -> list[str]:
        """在线程锁保护下快照当前 worker serial 列表。"""
        # 使用状态锁保护共享 worker 表遍历。
        with self._state_lock:
            # 返回当前全部 worker serial 快照。
            return sorted(self._workers.keys())

    def _snapshot_workers(self) -> list[tuple[str, WorkerHandle]]:
        """在线程锁保护下快照当前 worker 列表。"""
        # 使用状态锁保护共享 worker 表遍历。
        with self._state_lock:
            # 返回排序后的 worker 快照列表。
            return list(sorted(self._workers.items()))

    def list_online_devices(self, force_refresh: bool = False, source: str = "") -> list[str]:
        # 从 adb 读取当前在线设备列表，并把缓存策略和来源透传到底层。
        serials = list_online_serials(force_refresh=force_refresh, source=source)
        return serials

    def _build_adb_server_args(self) -> list[str]:
        """构建 adb server 参数，保证命令与运行时使用同一 server。"""
        # 读取 server 地址配置并清理空白。
        raw_addr = str(ADB_SERVER_ADDR or "").strip()
        # 配置为空时回退本地默认 server。
        if raw_addr == "":
            return ["-H", "127.0.0.1", "-P", "5037"]
        # 配置为 host:port 时解析 host 和 port。
        if ":" in raw_addr:
            host_part, port_part = raw_addr.rsplit(":", 1)
            host_value = host_part.strip() or "127.0.0.1"
            port_value = port_part.strip() or "5037"
            return ["-H", host_value, "-P", port_value]
        # 仅配置 host 时，端口回退 5037。
        return ["-H", raw_addr, "-P", "5037"]

    def _run_adb_for_serial(self, serial: str, args: list[str], timeout_sec: float) -> subprocess.CompletedProcess[str]:
        """执行 adb 子命令并返回结果（不抛 check 异常，由调用方解析）。"""
        # 解析当前可用 adb 绝对路径。
        adb_bin = resolve_adb_bin()
        # 组装完整命令：adb + server 参数 + 设备 serial + 子命令。
        cmd = [adb_bin, *self._build_adb_server_args(), "-s", str(serial), *args]
        # 执行命令并返回结果对象。
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=max(1.0, float(timeout_sec)),
            **_hidden_subprocess_kwargs(),
        )

    def _resolve_facebook_apk_path(self) -> Path:
        """解析 facebook.apk 路径，优先使用“可执行文件同级 apks”外置目录。"""
        # 保存候选路径，按优先级依次尝试。
        candidates: list[Path] = []
        # 解析当前可执行文件所在目录（源码模式通常是 Python 所在目录，打包模式是 exe/app 内部目录）。
        exe_dir = Path(sys.executable).resolve().parent
        # 候选 1：可执行文件同级目录下的 apks/facebook.apk（用户要求的主路径）。
        candidates.append(exe_dir / FACEBOOK_APK_RELATIVE_PATH)
        # 候选 2：可执行文件上一级目录下的 apks/facebook.apk（部分打包目录结构兜底）。
        candidates.append(exe_dir.parent / FACEBOOK_APK_RELATIVE_PATH)
        # 候选 3：macOS .app 场景下，app 包外层目录同级 apks/facebook.apk。
        try:
            candidates.append(exe_dir.parents[2] / FACEBOOK_APK_RELATIVE_PATH)
        except Exception:
            # 非 .app 目录结构时忽略该候选。
            pass
        # 候选 4：当前工作目录下的 apks/facebook.apk（命令行切目录运行兜底）。
        candidates.append(Path.cwd() / FACEBOOK_APK_RELATIVE_PATH)
        # 候选 5：源码运行路径（项目根目录）下的 apks/facebook.apk。
        candidates.append(Path(__file__).resolve().parents[2] / FACEBOOK_APK_RELATIVE_PATH)
        # 逐个候选检查文件是否存在。
        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                return candidate
        # 全部候选失效时，抛出明确错误，便于用户定位。
        raise FileNotFoundError(
            "未找到 facebook.apk（期望外置在可执行文件同级 apks 目录），请确认文件存在："
            + " / ".join(str(path) for path in candidates)
        )

    def _resolve_vinted_apk_path(self) -> Path:
        """解析 vinted.apk 路径，优先使用“可执行文件同级 apks”外置目录。"""
        # 保存候选路径，按优先级依次尝试。
        candidates: list[Path] = []
        # 解析当前可执行文件所在目录（源码模式通常是 Python 所在目录，打包模式是 exe/app 内部目录）。
        exe_dir = Path(sys.executable).resolve().parent
        # 候选 1：可执行文件同级目录下的 apks/vinted.apk。
        candidates.append(exe_dir / VINTED_APK_RELATIVE_PATH)
        # 候选 2：可执行文件上一级目录下的 apks/vinted.apk。
        candidates.append(exe_dir.parent / VINTED_APK_RELATIVE_PATH)
        # 候选 3：macOS .app 场景下，app 包外层目录同级 apks/vinted.apk。
        try:
            candidates.append(exe_dir.parents[2] / VINTED_APK_RELATIVE_PATH)
        except Exception:
            # 非 .app 目录结构时忽略该候选。
            pass
        # 候选 4：当前工作目录下的 apks/vinted.apk。
        candidates.append(Path.cwd() / VINTED_APK_RELATIVE_PATH)
        # 候选 5：源码运行路径（项目根目录）下的 apks/vinted.apk。
        candidates.append(Path(__file__).resolve().parents[2] / VINTED_APK_RELATIVE_PATH)
        # 逐个候选检查文件是否存在。
        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                return candidate
        # 全部候选失效时，抛出明确错误，便于用户定位。
        raise FileNotFoundError(
            "未找到 vinted.apk（期望外置在可执行文件同级 apks 目录），请确认文件存在："
            + " / ".join(str(path) for path in candidates)
        )

    def _resolve_yosemite_apk_path(self) -> Path:
        """解析 Yosemite.apk 路径，兼容源码运行与打包运行。"""
        # 保存候选路径，按优先级依次尝试。
        candidates: list[Path] = []
        # 优先使用 airtest 包当前安装目录，避免写死 Python 版本路径。
        try:
            # 延迟导入 airtest，避免启动阶段不必要依赖。
            import airtest

            # 解析 airtest 包目录。
            airtest_root = Path(str(getattr(airtest, "__file__", ""))).resolve().parent
            # 拼接 Yosemite.apk 绝对路径。
            candidates.append(airtest_root / "core" / "android" / "static" / "apks" / "Yosemite.apk")
        except Exception:
            # 导入失败不阻断流程，继续尝试其他候选路径。
            log.warning("导入 airtest 失败，继续尝试其他 Yosemite.apk 路径")
        # 源码运行兜底路径：项目内 .venv/site-packages/airtest/.../Yosemite.apk。
        candidates.append(
            Path(__file__).resolve().parents[2]
            / ".venv"
            / "lib"
            / f"python{sys.version_info.major}.{sys.version_info.minor}"
            / "site-packages"
            / YOSEMITE_APK_RELATIVE_PATH
        )
        # 打包运行路径：PyInstaller 解包目录下 airtest/.../Yosemite.apk。
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(Path(str(meipass)) / YOSEMITE_APK_RELATIVE_PATH)
        # 逐个候选检查文件是否存在。
        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                return candidate
        # 全部候选失效时，抛出明确错误，便于用户定位。
        raise FileNotFoundError(
            "未找到 Yosemite.apk，请确认文件存在："
            + " / ".join(str(path) for path in candidates)
        )

    @staticmethod
    def _compact_adb_output(result: subprocess.CompletedProcess[str]) -> str:
        """压缩 adb 命令输出为单行文本，便于提示与日志展示。"""
        # 合并 stdout 与 stderr。
        merged = f"{str(result.stdout or '').strip()} {str(result.stderr or '').strip()}".strip()
        # 压成单行，避免 GUI 提示换行过长。
        return " ".join(merged.split())

    def _is_package_installed_for_device(self, serial: str, package_name: str, timeout_sec: float = 12.0) -> bool:
        """根据包名判断设备上是否已安装应用。"""
        # 执行包路径查询命令（已安装时会返回 package:xxx.apk）。
        try:
            result = self._run_adb_for_serial(
                serial=serial,
                args=["shell", "pm", "path", package_name],
                timeout_sec=timeout_sec,
            )
        except Exception as exc:
            # 查询失败时记录日志并按“未安装”处理，避免阻塞主流程。
            log.warning("查询包安装状态失败，按未安装处理", serial=serial, package_name=package_name, error=str(exc))
            return False
        # 压缩输出文本便于规则判断。
        output_text = self._compact_adb_output(result)
        output_lower = output_text.lower()
        # 命中 package: 视为已安装。
        if "package:" in output_lower:
            return True
        # 常见未安装关键词，直接判定未安装。
        if "not found" in output_lower or "unknown package" in output_lower:
            return False
        # 兜底日志：便于追踪非常见系统输出。
        log.info(
            "包安装状态判定为未安装",
            serial=serial,
            package_name=package_name,
            returncode=int(result.returncode),
            output=output_text,
        )
        return False

    def _is_worker_running(self, serial: str) -> bool:
        """判断指定设备 worker 是否仍在运行。"""
        # 先清理一次已退出 worker，避免使用陈旧句柄误判。
        self._cleanup_dead(serial)
        # 读取设备对应 worker 句柄。
        worker = self._get_worker(serial)
        # 无句柄时判定未运行。
        if not worker:
            return False
        # 返回进程存活状态。
        return bool(worker.process.is_alive())

    def uninstall_facebook_for_device(self, serial: str) -> str:
        """卸载指定设备上的 Facebook 应用。"""
        # 设备正在执行任务时，拒绝卸载以避免和 worker 争用设备。
        if self._is_worker_running(serial):
            return f"{serial}: 设备任务运行中，请先停止该设备后再执行一键删除FB"
        # 先尝试停止 Facebook 进程，降低卸载失败概率。
        try:
            self._run_adb_for_serial(serial=serial, args=["shell", "am", "force-stop", FACEBOOK_PACKAGE_NAME], timeout_sec=8.0)
        except Exception:
            log.warning("卸载前停止 Facebook 进程失败，继续执行卸载", serial=serial)
        # 执行卸载命令。
        try:
            result = self._run_adb_for_serial(serial=serial, args=["uninstall", FACEBOOK_PACKAGE_NAME], timeout_sec=35.0)
        except Exception as exc:
            log.exception("卸载 Facebook 执行异常", serial=serial, error=str(exc))
            return f"{serial}: 卸载失败（执行异常）{exc}"
        # 解析命令输出。
        output_text = self._compact_adb_output(result)
        output_lower = output_text.lower()
        # 命中 success 时判定成功。
        if "success" in output_lower:
            log.info("Facebook 卸载成功", serial=serial, output=output_text)
            return f"{serial}: Facebook 卸载成功"
        # 未安装场景按可接受结果返回。
        if "unknown package" in output_lower or "not installed" in output_lower:
            log.info("Facebook 未安装，按成功处理", serial=serial, output=output_text)
            return f"{serial}: Facebook 未安装"
        # 非 success 视为失败并返回简化原因。
        log.error(
            "Facebook 卸载失败",
            serial=serial,
            returncode=int(result.returncode),
            output=output_text,
        )
        return f"{serial}: Facebook 卸载失败（{output_text or f'returncode={result.returncode}'})"

    def install_facebook_for_device(self, serial: str) -> str:
        """为指定设备安装 Facebook（外置 apks/facebook.apk）。"""
        # 设备正在执行任务时，拒绝安装以避免和 worker 争用设备。
        if self._is_worker_running(serial):
            return f"{serial}: 设备任务运行中，请先停止该设备后再执行一键安装FB"
        # 解析安装包路径，支持源码和打包运行。
        try:
            apk_path = self._resolve_facebook_apk_path()
        except Exception as exc:
            log.exception("解析 Facebook 安装包路径失败", serial=serial, error=str(exc))
            return f"{serial}: 安装失败（找不到 facebook.apk）"
        # 执行安装命令（-r 覆盖安装，-d 允许降级）。
        try:
            result = self._run_adb_for_serial(
                serial=serial,
                args=["install", "-r", "-d", str(apk_path)],
                timeout_sec=200.0,
            )
        except Exception as exc:
            log.exception("安装 Facebook 执行异常", serial=serial, apk_path=str(apk_path), error=str(exc))
            return f"{serial}: 安装失败（执行异常）{exc}"
        # 解析命令输出。
        output_text = self._compact_adb_output(result)
        output_lower = output_text.lower()
        # 命中 success 时判定成功。
        if "success" in output_lower:
            log.info("Facebook 安装成功", serial=serial, apk_path=str(apk_path), output=output_text)
            return f"{serial}: Facebook 安装成功"
        # 非 success 视为失败并返回简化原因。
        log.error(
            "Facebook 安装失败",
            serial=serial,
            apk_path=str(apk_path),
            returncode=int(result.returncode),
            output=output_text,
        )
        return f"{serial}: Facebook 安装失败（{output_text or f'returncode={result.returncode}'})"

    def uninstall_vinted_for_device(self, serial: str) -> str:
        """卸载指定设备上的 Vinted 应用。"""
        # 设备正在执行任务时，拒绝卸载以避免和 worker 争用设备。
        if self._is_worker_running(serial):
            return f"{serial}: 设备任务运行中，请先停止该设备后再执行一键删除VT"
        # 先尝试停止 Vinted 进程，降低卸载失败概率。
        try:
            self._run_adb_for_serial(serial=serial, args=["shell", "am", "force-stop", VINTED_PACKAGE_NAME], timeout_sec=8.0)
        except Exception:
            log.warning("卸载前停止 Vinted 进程失败，继续执行卸载", serial=serial)
        # 执行卸载命令。
        try:
            result = self._run_adb_for_serial(serial=serial, args=["uninstall", VINTED_PACKAGE_NAME], timeout_sec=35.0)
        except Exception as exc:
            log.exception("卸载 Vinted 执行异常", serial=serial, error=str(exc))
            return f"{serial}: 卸载失败（执行异常）{exc}"
        # 解析命令输出。
        output_text = self._compact_adb_output(result)
        output_lower = output_text.lower()
        # 命中 success 时判定成功。
        if "success" in output_lower:
            log.info("Vinted 卸载成功", serial=serial, output=output_text)
            return f"{serial}: Vinted 卸载成功"
        # 未安装场景按可接受结果返回。
        if "unknown package" in output_lower or "not installed" in output_lower:
            log.info("Vinted 未安装，按成功处理", serial=serial, output=output_text)
            return f"{serial}: Vinted 未安装"
        # 非 success 视为失败并返回简化原因。
        log.error(
            "Vinted 卸载失败",
            serial=serial,
            returncode=int(result.returncode),
            output=output_text,
        )
        return f"{serial}: Vinted 卸载失败（{output_text or f'returncode={result.returncode}'})"

    def install_vinted_for_device(self, serial: str) -> str:
        """为指定设备安装 Vinted（外置 apks/vinted.apk）。"""
        # 设备正在执行任务时，拒绝安装以避免和 worker 争用设备。
        if self._is_worker_running(serial):
            return f"{serial}: 设备任务运行中，请先停止该设备后再执行一键安装VT"
        # 解析安装包路径，支持源码和打包运行。
        try:
            apk_path = self._resolve_vinted_apk_path()
        except Exception as exc:
            log.exception("解析 Vinted 安装包路径失败", serial=serial, error=str(exc))
            return f"{serial}: 安装失败（找不到 vinted.apk）"
        # 执行安装命令（-r 覆盖安装，-d 允许降级）。
        try:
            result = self._run_adb_for_serial(
                serial=serial,
                args=["install", "-r", "-d", str(apk_path)],
                timeout_sec=200.0,
            )
        except Exception as exc:
            log.exception("安装 Vinted 执行异常", serial=serial, apk_path=str(apk_path), error=str(exc))
            return f"{serial}: 安装失败（执行异常）{exc}"
        # 解析命令输出。
        output_text = self._compact_adb_output(result)
        output_lower = output_text.lower()
        # 命中 success 时判定成功。
        if "success" in output_lower:
            log.info("Vinted 安装成功", serial=serial, apk_path=str(apk_path), output=output_text)
            return f"{serial}: Vinted 安装成功"
        # 非 success 视为失败并返回简化原因。
        log.error(
            "Vinted 安装失败",
            serial=serial,
            apk_path=str(apk_path),
            returncode=int(result.returncode),
            output=output_text,
        )
        return f"{serial}: Vinted 安装失败（{output_text or f'returncode={result.returncode}'})"

    def uninstall_facebook_all(self) -> list[str]:
        """一键卸载全部在线设备上的 Facebook。"""
        # 读取在线设备列表。
        serials = self.list_online_devices()
        # 无在线设备时返回友好提示。
        if not serials:
            return ["未检测到在线设备（adb devices 为空）"]
        # 逐台执行卸载并汇总结果。
        return [self.uninstall_facebook_for_device(serial) for serial in serials]

    def install_facebook_all(self) -> list[str]:
        """一键安装全部在线设备上的 Facebook。"""
        # 读取在线设备列表。
        serials = self.list_online_devices()
        # 无在线设备时返回友好提示。
        if not serials:
            return ["未检测到在线设备（adb devices 为空）"]
        # 逐台执行安装并汇总结果。
        return [self.install_facebook_for_device(serial) for serial in serials]

    def uninstall_vinted_all(self) -> list[str]:
        """一键卸载全部在线设备上的 Vinted。"""
        # 读取在线设备列表。
        serials = self.list_online_devices()
        # 无在线设备时返回友好提示。
        if not serials:
            return ["未检测到在线设备（adb devices 为空）"]
        # 逐台执行卸载并汇总结果。
        return [self.uninstall_vinted_for_device(serial) for serial in serials]

    def install_vinted_all(self) -> list[str]:
        """一键安装全部在线设备上的 Vinted。"""
        # 读取在线设备列表。
        serials = self.list_online_devices()
        # 无在线设备时返回友好提示。
        if not serials:
            return ["未检测到在线设备（adb devices 为空）"]
        # 逐台执行安装并汇总结果。
        return [self.install_vinted_for_device(serial) for serial in serials]

    def install_yosemite_for_device(self, serial: str) -> str:
        """为指定设备安装 Yosemite 输入法（手动设为默认）。"""
        # 先按包名判断是否已安装，已安装则直接跳过。
        if self._is_package_installed_for_device(serial=serial, package_name=YOSEMITE_PACKAGE_NAME):
            return f"{serial}: 输入法已安装，跳过（{YOSEMITE_PACKAGE_NAME}）"
        # 设备正在执行任务时，拒绝安装以避免和 worker 争用设备。
        if self._is_worker_running(serial):
            return f"{serial}: 设备任务运行中，请先停止该设备后再执行安装输入法"
        # 解析安装包路径，支持源码和打包运行。
        try:
            apk_path = self._resolve_yosemite_apk_path()
        except Exception as exc:
            log.exception("解析 Yosemite 安装包路径失败", serial=serial, error=str(exc))
            return f"{serial}: 安装失败（找不到 Yosemite.apk）"
        # 执行安装命令（-r 覆盖安装，-d 允许降级）。
        try:
            result = self._run_adb_for_serial(
                serial=serial,
                args=["install", "-r", "-d", str(apk_path)],
                timeout_sec=200.0,
            )
        except Exception as exc:
            log.exception("安装 Yosemite 输入法执行异常", serial=serial, apk_path=str(apk_path), error=str(exc))
            return f"{serial}: 输入法安装失败（执行异常）{exc}"
        # 解析命令输出。
        output_text = self._compact_adb_output(result)
        output_lower = output_text.lower()
        # 命中 success 时判定成功。
        if "success" in output_lower:
            log.info(
                "Yosemite 输入法安装成功",
                serial=serial,
                apk_path=str(apk_path),
                package_name=YOSEMITE_PACKAGE_NAME,
                output=output_text,
            )
            return f"{serial}: 输入法安装成功（请手动设为默认）"
        # 非 success 视为失败并返回简化原因。
        log.error(
            "Yosemite 输入法安装失败",
            serial=serial,
            apk_path=str(apk_path),
            package_name=YOSEMITE_PACKAGE_NAME,
            returncode=int(result.returncode),
            output=output_text,
        )
        return f"{serial}: 输入法安装失败（{output_text or f'returncode={result.returncode}'})"

    def install_yosemite_all(self) -> list[str]:
        """一键安装全部在线设备上的 Yosemite 输入法。"""
        # 读取在线设备列表。
        serials = self.list_online_devices()
        # 无在线设备时返回友好提示。
        if not serials:
            return ["未检测到在线设备（adb devices 为空）"]
        # 逐台执行安装并汇总结果。
        return [self.install_yosemite_for_device(serial) for serial in serials]

    def _update_state(self, serial: str, state: str, detail: str, event_time: float) -> None:
        # 把事件同步到内存中的 worker 状态。
        with self._state_lock:
            # 读取目标设备 worker 句柄。
            worker = self._workers.get(serial)
            # worker 不存在时直接返回。
            if not worker:
                return
            # 更新最近状态。
            worker.last_state = state
            # 更新最近详情。
            worker.last_detail = detail
            # 更新时间戳。
            worker.updated_at = event_time

    def _release_device_account(self, serial: str, reason: str) -> None:
        # 释放设备占用账号：status=1 回退 0；status=2/3/4 保持不变，仅清空 device。
        user_db: UserDB | None = None
        try:
            # 打开短连接，避免后台线程复用主线程连接。
            user_db = self._open_user_db(connect_timeout_sec=0.8, busy_timeout_ms=800)
            # 释放当前设备占用账号。
            released = user_db.release_user_for_device(serial)
            if released > 0:
                log.info("已释放设备占用账号", serial=serial, released=released, reason=reason)
        except Exception as exc:
            log.exception("释放设备占用账号失败", serial=serial, reason=reason, error=str(exc))
        finally:
            # 短连接使用后立即关闭，避免连接泄漏。
            if user_db is not None:
                try:
                    # 关闭本次释放动作使用的数据库连接。
                    user_db.close()
                except Exception:
                    # 关闭失败仅记录日志，不影响主流程。
                    log.exception("关闭释放设备占用账号连接失败", serial=serial, reason=reason)

    # 定义“全局释放所有运行中账号”方法，供应用退出时兜底调用。
    def reset_all_running_accounts(self, reason: str) -> int:
        # 初始化影响行数，异常时回退 0。
        released = 0
        # 准备数据库短连接占位，便于 finally 统一关闭。
        user_db: UserDB | None = None
        try:
            # 打开短连接，避免跨线程复用连接导致异常。
            user_db = self._open_user_db(connect_timeout_sec=1.0, busy_timeout_ms=1000)
            # 执行全局重置：把所有 status=1 的账号回退为 0，并清空设备绑定。
            released = user_db.reset_all_running_users()
            # 记录本次全局释放结果，便于排查退出后账号残留问题。
            log.info("已全局释放运行中账号", released=released, reason=reason)
        except Exception as exc:
            # 记录异常但不向上抛，避免退出链路被中断。
            log.exception("全局释放运行中账号失败", reason=reason, error=str(exc))
        finally:
            # 短连接使用后立即关闭，避免连接泄漏。
            if user_db is not None:
                try:
                    # 关闭本次全局释放使用的数据库连接。
                    user_db.close()
                except Exception:
                    # 关闭失败仅记录日志，不再中断调用方。
                    log.exception("关闭全局释放账号连接失败", reason=reason)
        # 返回影响行数，供上层日志展示。
        return released

    def _finalize_worker_stop(
        self,
        *,
        serial: str,
        worker: WorkerHandle,
        release_account: bool,
        release_reason: str,
    ) -> dict[str, object]:
        # 先清理一次当前设备辅助进程，尽量在删句柄前回收可见残留。
        helper_cleanup_before = self._cleanup_helper_processes(
            serial=serial,
            orphan_only=False,
            reason=f"{release_reason}_helper_pre_finalize",
        )
        # 回收句柄资源并从管理表中删除，避免内存和句柄泄漏。
        try:
            worker.command_queue.close()
        except Exception:
            pass
        if release_account:
            self._release_device_account(serial=serial, reason=release_reason)
        # 使用状态锁保护 worker 表删除，避免和状态刷新并发冲突。
        with self._state_lock:
            # 从 worker 管理表移除当前设备句柄。
            self._workers.pop(serial, None)
        # 句柄删除后再复检一次辅助进程，覆盖已脱离父子关系的孤儿进程。
        helper_cleanup_after = self._cleanup_helper_processes(
            serial=serial,
            orphan_only=False,
            reason=f"{release_reason}_helper_post_finalize",
        )
        # 返回合并后的辅助进程清理结果，供 stop 路径汇总展示。
        return self._merge_helper_cleanup_results(helper_cleanup_before, helper_cleanup_after)

    def _cleanup_dead(self, serial: str) -> None:
        # 清理已经退出的子进程句柄，避免状态污染。
        worker = self._get_worker(serial)
        if not worker:
            return
        if worker.process.is_alive():
            return
        self._finalize_worker_stop(
            serial=serial,
            worker=worker,
            release_account=True,
            release_reason="worker_dead",
        )

    def _cleanup_all_dead(self) -> None:
        # 批量清理所有已退出 worker。
        for serial in self._snapshot_worker_serials():
            self._cleanup_dead(serial)

    def drain_events(self) -> list[dict[str, str | float]]:
        # 把事件队列里积压的消息一次性取完。
        events: list[dict[str, str | float]] = []
        while True:
            try:
                event = self._event_queue.get_nowait()
            except queue.Empty:
                break

            # 收集事件，供 CLI/GUI 直接输出。
            events.append(event)
            # 同步更新内部状态快照。
            self._update_state(
                serial=str(event["serial"]),
                state=str(event["state"]),
                detail=str(event["detail"]),
                event_time=float(event["time"]),
            )

        # 不在 drain_events 里自动删除 dead worker。
        # 原因：GUI 需要看到“刚退出”的状态（pid/详情/exit_code），否则会回退成“未启动”误导用户。
        return events

    def start_worker(self, serial: str, register_mode: str = "") -> str:
        # 先刷新状态，避免重复启动僵尸条目。
        self.drain_events()
        self._cleanup_dead(serial)
        # 标准化注册方式参数，避免大小写和空格影响判断。
        normalized_register_mode = _normalize_register_mode(register_mode)
        # 注册方式非法时直接返回明确错误，避免启动出错后才暴露问题。
        if normalized_register_mode not in VALID_REGISTER_MODES:
            # 记录非法启动请求，便于排查 GUI/CLI 调用链问题。
            log.warning("启动 worker 失败：注册方式非法", serial=serial, register_mode=register_mode)
            # 返回可直接展示给界面的错误文案。
            return f"{serial}: 启动失败，请先选择注册方式"

        old = self._get_worker(serial)
        if old and old.process.is_alive():
            # 已有运行中 worker 时仅读取当前辅助进程快照，帮助排查状态混乱。
            helper_snapshot = self._collect_helper_processes(serial=serial, orphan_only=False)
            log.warning("设备已在运行", serial=serial, pid=old.process.pid)
            # 命中辅助进程快照时补一条诊断日志，便于排查多进程错乱。
            if helper_snapshot:
                log.warning(
                    "设备已在运行，当前辅助进程快照",
                    serial=serial,
                    pid=old.process.pid,
                    helper_processes=self._format_helper_processes_for_log(helper_snapshot),
                )
            return f"{serial}: 已在运行 pid={old.process.pid}"

        # 新 worker 拉起前先清理当前设备历史残留辅助进程，避免新旧运行时串线。
        self._cleanup_helper_processes(serial=serial, orphan_only=False, reason="start_worker_preflight_cleanup")
        # 为新子进程创建 stop 事件和命令队列。
        stop_event = self._ctx.Event()
        command_queue: mp.Queue = self._ctx.Queue()
        # 创建并启动子进程。
        process = self._ctx.Process(
            target=worker_main,
            args=(serial, normalized_register_mode, self._loop_interval_sec, stop_event, command_queue, self._event_queue),
            name=f"autovt-{serial}",
            daemon=False,
        )
        process.start()
        log.info("子进程已启动", serial=serial, pid=process.pid, register_mode=normalized_register_mode)

        # 保存句柄，供后续 stop/restart/status 使用。
        # 使用状态锁保护 worker 句柄写入，避免后台动作与状态刷新并发冲突。
        with self._state_lock:
            # 保存新启动的 worker 句柄，供后续 stop/restart/status 使用。
            self._workers[serial] = WorkerHandle(
                serial=serial,
                process=process,
                stop_event=stop_event,
                command_queue=command_queue,
                last_state="starting",
                last_detail=f"子进程已启动 pid={process.pid}",
                updated_at=time.time(),
            )
        # 启动后做一次短探针：如果子进程“秒退”，直接返回失败原因，避免 GUI 误显示“已启动”。
        process.join(WORKER_STARTUP_PROBE_SEC)
        if not process.is_alive():
            # 读取退出码，便于定位秒退原因。
            exit_code = process.exitcode if process.exitcode is not None else -1
            # 构造统一失败详情文案。
            detail = f"子进程启动后立即退出 exit_code={exit_code}"
            # 回读句柄，更新状态快照给 GUI 展示。
            worker = self._get_worker(serial)
            if worker:
                # 秒退统一标记为 fatal，方便前端颜色和文案突出显示。
                with self._state_lock:
                    # 秒退统一标记为 fatal，方便前端颜色和文案突出显示。
                    worker.last_state = "fatal"
                    # 写入失败详情。
                    worker.last_detail = detail
                    # 更新时间戳，确保 UI 立即刷新到最新状态。
                    worker.updated_at = time.time()
            log.error("子进程启动探针失败", serial=serial, pid=process.pid, exit_code=exit_code)
            return f"{serial}: 启动失败，{detail}"
        return f"{serial}: 启动成功 pid={process.pid}"

    def start_all(self, register_mode: str = "") -> list[str]:
        # 启动所有在线设备对应的子进程。
        serials = self.list_online_devices(force_refresh=False, source="start_all")
        if not serials:
            return ["未检测到在线设备（adb devices 为空）"]
        # 批量启动时统一把注册方式透传给每一台设备。
        return [self.start_worker(serial, register_mode=register_mode) for serial in serials]

    def _try_realtime_pause_resume(self, serial: str, worker: WorkerHandle, command: str) -> str | None:
        # 尝试使用进程级 suspend/resume 实现“尽量即时”的暂停与恢复。
        # 只处理 pause/resume，其它命令走原有队列逻辑。
        if command not in {"pause", "resume"}:
            return None
        # psutil 不可用时不做即时控制，回退到队列命令模式。
        if psutil is None:
            return None

        # 读取 worker 进程 PID。
        pid = int(worker.process.pid or -1)
        # PID 无效时直接回退到队列命令模式。
        if pid <= 0:
            return None

        # 获取目标进程对象，后续执行 suspend/resume。
        try:
            # 构造 psutil 进程句柄。
            proc = psutil.Process(pid)
            # 即时暂停分支：直接挂起进程。
            if command == "pause":
                # 挂起 worker 进程，当前执行步骤会立即冻结。
                proc.suspend()
                # 使用状态锁保护内存状态更新，避免和状态刷新并发冲突。
                with self._state_lock:
                    # 立即更新状态快照，UI 可立刻看到暂停态。
                    worker.last_state = "paused"
                    # 更新状态详情文案。
                    worker.last_detail = "已即时暂停（进程挂起）"
                    # 更新时间戳用于状态列表显示。
                    worker.updated_at = time.time()
                # 记录即时暂停日志。
                log.info("即时暂停成功", serial=serial, pid=pid)
                return f"{serial}: 已即时暂停"

            # 即时恢复分支：恢复被挂起的进程继续执行。
            proc.resume()
            # 使用状态锁保护内存状态更新，避免和状态刷新并发冲突。
            with self._state_lock:
                # 立即更新状态快照为运行中。
                worker.last_state = "running"
                # 更新状态详情文案。
                worker.last_detail = "已即时恢复（进程继续）"
                # 更新时间戳用于状态列表显示。
                worker.updated_at = time.time()
            # 记录即时恢复日志。
            log.info("即时恢复成功", serial=serial, pid=pid)
            return f"{serial}: 已即时恢复"
        # 即时控制失败时记录告警并回退到队列命令模式。
        except Exception as exc:
            log.warning("即时暂停/恢复失败，回退命令队列模式", serial=serial, command=command, error=str(exc))
            return None

    def send_command(self, serial: str, command: str) -> str:
        # 给指定设备子进程发送控制命令。
        self.drain_events()
        self._cleanup_dead(serial)
        worker = self._get_worker(serial)
        if not worker or not worker.process.is_alive():
            log.warning("发送命令失败，设备未运行", serial=serial, command=command)
            return f"{serial}: 未运行"

        # 优先尝试进程级即时暂停/恢复。
        fast_result = self._try_realtime_pause_resume(serial=serial, worker=worker, command=command)
        # 命中即时暂停/恢复分支时直接返回结果。
        if fast_result is not None:
            return fast_result

        worker.command_queue.put(command)
        log.info("命令已发送", serial=serial, command=command)
        return f"{serial}: 已发送命令 {command}"

    def send_command_all(self, command: str) -> list[str]:
        # 广播命令给所有运行中的设备。
        return [self.send_command(serial, command) for serial in self._snapshot_worker_serials()]

    def _try_send_stop(self, worker: WorkerHandle, serial: str) -> None:
        # 给子进程发送 stop 命令并设置 stop_event，使用双保险提高退出成功率。
        try:
            worker.command_queue.put("stop")
        except Exception as exc:
            log.warning("发送 stop 命令失败，改用 stop_event", serial=serial, error=str(exc))
        worker.stop_event.set()

    def _kill_worker_process_tree(self, worker: WorkerHandle, serial: str, reason: str) -> None:
        # psutil 不可用时无法做进程树清理，直接跳过。
        if psutil is None:
            return
        # 读取 worker 主进程 PID。
        pid = int(worker.process.pid or -1)
        # PID 无效时直接跳过，避免 psutil 抛异常。
        if pid <= 0:
            return
        try:
            # 构造 worker 主进程句柄。
            proc = psutil.Process(pid)
        except Exception as exc:
            # 主进程句柄不存在时记录调试日志即可。
            log.debug("构造 worker 进程句柄失败，跳过进程树清理", serial=serial, pid=pid, reason=reason, error=str(exc))
            return
        try:
            # 先读取当前仍存活的全部子孙进程。
            children = proc.children(recursive=True)
        except Exception as exc:
            # 读取子进程树失败时记录告警，不影响主流程。
            log.warning("读取 worker 子进程树失败", serial=serial, pid=pid, reason=reason, error=str(exc))
            return
        # 没有子孙进程时直接返回。
        if not children:
            return
        # 逐个尝试终止子孙进程。
        for child in children:
            try:
                # 先发送 terminate，给子进程一点优雅退出机会。
                child.terminate()
            except Exception:
                # 单个子进程 terminate 失败时忽略，后续统一 kill 兜底。
                continue
        try:
            # 等待子孙进程短时间退出。
            _, alive_children = psutil.wait_procs(children, timeout=1.2)
        except Exception as exc:
            # wait_procs 失败时回退到“全部视为仍存活”。
            log.warning("等待 worker 子进程退出失败，准备直接 kill", serial=serial, pid=pid, reason=reason, error=str(exc))
            alive_children = children
        # 对仍存活的子孙进程执行 kill 兜底。
        for child in alive_children:
            try:
                # 强制杀掉残留子进程，避免 adb/pocoservice 宿主进程泄露。
                child.kill()
            except Exception:
                # 单个子进程 kill 失败时继续处理其余进程。
                continue
        # 记录本次进程树清理结果日志。
        log.info("worker 子进程树清理完成", serial=serial, pid=pid, reason=reason, child_count=len(children), alive_after_terminate=len(alive_children))
        # 进程树清理后再做一次签名级复检，覆盖已脱离父子关系的孤儿辅助进程。
        self._cleanup_helper_processes(serial=serial, orphan_only=False, reason=f"{reason}_signature_cleanup")

    def stop_worker(self, serial: str, timeout_sec: float | None = None) -> str:
        # 停止指定设备子进程：先优雅停止，超时再强杀。
        self.drain_events()
        worker = self._get_worker(serial)
        if not worker:
            # 即使进程句柄不存在，也尝试做一次账号释放，防止残留绑定。
            self._release_device_account(serial=serial, reason="stop_worker_without_handle")
            log.warning("停止失败，设备未运行", serial=serial)
            return f"{serial}: 未运行"

        grace_timeout_sec = (
            max(0.0, float(timeout_sec)) if timeout_sec is not None else WORKER_STOP_GRACE_TIMEOUT_SEC
        )
        if worker.process.is_alive():
            # 先优雅停止：发 stop 命令并等待短超时。
            self._try_send_stop(worker, serial=serial)
            worker.process.join(grace_timeout_sec)

        if worker.process.is_alive():
            # 主进程仍未退出时，先清理其子进程树，避免 adb/pocoservice 残留。
            self._kill_worker_process_tree(worker=worker, serial=serial, reason="stop_worker_before_terminate")
            # 超时还没退就强制 terminate。
            worker.process.terminate()
            worker.process.join(WORKER_STOP_FORCE_TIMEOUT_SEC)
            if worker.process.is_alive():
                # terminate 后再次清理一轮子进程树，避免孤儿进程残留。
                self._kill_worker_process_tree(worker=worker, serial=serial, reason="stop_worker_before_kill")
                # terminate 仍未退出时，最后使用 kill 兜底。
                worker.process.kill()
                worker.process.join(WORKER_STOP_FORCE_TIMEOUT_SEC)
                msg = f"{serial}: 超时，已强制 kill"
                log.error(
                    "子进程 terminate 后仍未退出，已 kill",
                    serial=serial,
                    grace_timeout_sec=grace_timeout_sec,
                    force_timeout_sec=WORKER_STOP_FORCE_TIMEOUT_SEC,
                )
            else:
                msg = f"{serial}: 超时，已强制终止"
                log.error(
                    "子进程停止超时，已强制终止",
                    serial=serial,
                    grace_timeout_sec=grace_timeout_sec,
                    force_timeout_sec=WORKER_STOP_FORCE_TIMEOUT_SEC,
                )
        else:
            msg = f"{serial}: 已停止"
            log.info("子进程已停止", serial=serial)

        # 回收资源并删除句柄。
        helper_cleanup = self._finalize_worker_stop(
            serial=serial,
            worker=worker,
            release_account=True,
            release_reason="stop_worker",
        )
        # 还有残留时返回明确提示，避免界面误以为完全收口。
        if list(helper_cleanup.get("remaining", []) or []):
            msg = f"{serial}: 已停止，但仍检测到残留辅助进程"
        # 命中过残留但已清理干净时，明确告知已做额外收口。
        elif int(helper_cleanup.get("matched", 0) or 0) > 0 and msg.endswith("已停止"):
            msg = f"{serial}: 已停止并清理残留"
        return msg

    def stop_all(self, timeout_sec: float | None = None) -> list[str]:
        # 停止全部子进程：并发发 stop + 统一等待，避免多设备串行超时导致总耗时过长。
        self.drain_events()
        serials = self._snapshot_worker_serials()
        if not serials:
            # 没有可停止进程时返回明确提示，避免 GUI 侧看起来“无反应”。
            return ["当前无运行中的设备进程"]

        grace_timeout_sec = (
            max(0.0, float(timeout_sec)) if timeout_sec is not None else WORKER_STOP_GRACE_TIMEOUT_SEC
        )

        # 第一阶段：并发发送 stop 请求。
        for serial in serials:
            worker = self._get_worker(serial)
            if not worker:
                continue
            if worker.process.is_alive():
                self._try_send_stop(worker, serial=serial)

        # 第二阶段：统一等待优雅退出。
        deadline = time.time() + grace_timeout_sec
        # 初始化“优雅等待后仍存活”的设备集合。
        alive_serials: set[str] = set()
        # 首轮扫描当前仍存活的 worker。
        for serial in serials:
            # 读取当前设备 worker 句柄。
            worker = self._get_worker(serial)
            # 仅把仍存活的 worker 加入等待集合。
            if worker and worker.process.is_alive():
                alive_serials.add(serial)
        while alive_serials and time.time() < deadline:
            for serial in list(alive_serials):
                worker = self._get_worker(serial)
                if not worker or not worker.process.is_alive():
                    alive_serials.discard(serial)
            if alive_serials:
                time.sleep(0.05)

        # 第三阶段：并发 terminate 仍存活的进程，并统一等待。
        # 初始化“优雅等待后仍存活”的设备集合。
        alive_after_grace: set[str] = set()
        # 再次扫描当前仍存活的 worker。
        for serial in serials:
            # 读取当前设备 worker 句柄。
            worker = self._get_worker(serial)
            # 仅把仍存活的 worker 加入 terminate 阶段集合。
            if worker and worker.process.is_alive():
                alive_after_grace.add(serial)
        for serial in alive_after_grace:
            worker = self._get_worker(serial)
            if worker and worker.process.is_alive():
                # terminate 前先清理 worker 子进程树，避免 adb/pocoservice 残留。
                self._kill_worker_process_tree(worker=worker, serial=serial, reason="stop_all_before_terminate")
                worker.process.terminate()
        terminate_deadline = time.time() + WORKER_STOP_FORCE_TIMEOUT_SEC
        alive_after_terminate = set(alive_after_grace)
        while alive_after_terminate and time.time() < terminate_deadline:
            for serial in list(alive_after_terminate):
                worker = self._get_worker(serial)
                if not worker or not worker.process.is_alive():
                    alive_after_terminate.discard(serial)
            if alive_after_terminate:
                time.sleep(0.05)

        # 第四阶段：并发 kill terminate 后仍存活的进程，并统一等待。
        for serial in alive_after_terminate:
            worker = self._get_worker(serial)
            if worker and worker.process.is_alive():
                # kill 前再次清理 worker 子进程树，避免孤儿 adb 进程残留。
                self._kill_worker_process_tree(worker=worker, serial=serial, reason="stop_all_before_kill")
                worker.process.kill()
        kill_deadline = time.time() + WORKER_STOP_FORCE_TIMEOUT_SEC
        alive_after_kill = set(alive_after_terminate)
        while alive_after_kill and time.time() < kill_deadline:
            for serial in list(alive_after_kill):
                worker = self._get_worker(serial)
                if not worker or not worker.process.is_alive():
                    alive_after_kill.discard(serial)
            if alive_after_kill:
                time.sleep(0.05)

        # 第五阶段：回收资源并产出每个设备的停止结果。
        messages: list[str] = []
        for serial in serials:
            worker = self._get_worker(serial)
            if not worker:
                continue

            if serial in alive_after_kill:
                msg = f"{serial}: 超时，kill 后仍未退出"
                log.error(
                    "stop_all kill 后仍未退出",
                    serial=serial,
                    grace_timeout_sec=grace_timeout_sec,
                    force_timeout_sec=WORKER_STOP_FORCE_TIMEOUT_SEC,
                )
            elif serial in alive_after_terminate:
                msg = f"{serial}: 超时，已强制 kill"
                log.error(
                    "stop_all terminate 后仍未退出，已 kill",
                    serial=serial,
                    grace_timeout_sec=grace_timeout_sec,
                    force_timeout_sec=WORKER_STOP_FORCE_TIMEOUT_SEC,
                )
            elif serial in alive_after_grace:
                msg = f"{serial}: 超时，已强制终止"
                log.error(
                    "stop_all 停止超时，已强制终止",
                    serial=serial,
                    grace_timeout_sec=grace_timeout_sec,
                    force_timeout_sec=WORKER_STOP_FORCE_TIMEOUT_SEC,
                )
            else:
                msg = f"{serial}: 已停止"
                log.info("stop_all 子进程已停止", serial=serial)

            helper_cleanup = self._finalize_worker_stop(
                serial=serial,
                worker=worker,
                release_account=True,
                release_reason="stop_all",
            )
            # 还有残留时把结果升级为明确异常提示。
            if list(helper_cleanup.get("remaining", []) or []):
                msg = f"{serial}: 已停止，但仍检测到残留辅助进程"
            # 命中过残留且已清理干净时，给界面返回更准确文案。
            elif int(helper_cleanup.get("matched", 0) or 0) > 0 and msg.endswith("已停止"):
                msg = f"{serial}: 已停止并清理残留"
            messages.append(msg)
        return messages

    def restart_worker(self, serial: str, timeout_sec: float | None = None, register_mode: str = "") -> list[str]:
        # 重启：先停再启，返回两条结果信息。
        return [self.stop_worker(serial, timeout_sec=timeout_sec), self.start_worker(serial, register_mode=register_mode)]

    def status(self) -> list[dict[str, str | int | float]]:
        # 返回当前所有子进程状态快照，供 CLI/GUI 展示。
        status_started_at = time.monotonic()
        # 预置各阶段耗时指标，便于失败时也能输出诊断日志。
        drain_events_elapsed_ms = 0
        db_open_elapsed_ms = 0
        device_lookup_elapsed_ms = 0
        row_build_elapsed_ms = 0
        # 先把 worker 事件队列清空到内存快照。
        step_started_at = time.monotonic()
        self.drain_events()
        drain_events_elapsed_ms = int((time.monotonic() - step_started_at) * 1000)
        # 打开短连接，避免后台线程复用同一 SQLite 连接导致异常。
        user_db: UserDB | None = None
        rows: list[dict[str, str | int | float]] = []
        try:
            # 打开短连接，供状态快照阶段读取设备占用邮箱。
            step_started_at = time.monotonic()
            user_db = self._open_user_db(connect_timeout_sec=0.6, busy_timeout_ms=600)
            db_open_elapsed_ms = int((time.monotonic() - step_started_at) * 1000)
            # 先快照当前 worker 列表，避免后续多次加锁遍历。
            worker_items = self._snapshot_workers()
            # 抽取当前全部 serial，供设备占用关系统一查询。
            serials = [serial for serial, _ in worker_items]
            # 读取设备绑定账号关系。
            step_started_at = time.monotonic()
            user_rows = self._get_user_rows_by_devices(user_db=user_db, serials=serials)
            device_lookup_elapsed_ms = int((time.monotonic() - step_started_at) * 1000)
            # 组装最终状态行。
            step_started_at = time.monotonic()
            for serial, worker in worker_items:
                # 从设备到账号映射中读取当前邮箱绑定。
                user_row = user_rows.get(serial, {})
                email_account = str(user_row.get("email_account", "")).strip() if user_row else ""
                rows.append(
                    {
                        # 设备序列号。
                        "serial": serial,
                        # 进程 PID。
                        "pid": worker.process.pid or -1,
                        # 是否存活。
                        "alive": "yes" if worker.process.is_alive() else "no",
                        # 最近状态。
                        "state": worker.last_state,
                        # 最近详情。
                        "detail": worker.last_detail,
                        # 当前设备占用邮箱。
                        "email_account": email_account,
                        # 最近更新时间戳。
                        "updated_at": worker.updated_at,
                    }
                )
            row_build_elapsed_ms = int((time.monotonic() - step_started_at) * 1000)
        finally:
            # 短连接使用后立即关闭，避免连接泄漏。
            if user_db is not None:
                try:
                    # 关闭状态快照读取连接。
                    user_db.close()
                except Exception:
                    # 关闭失败只记日志，不影响状态返回。
                    log.exception("关闭状态快照数据库连接失败")
        # 计算本轮状态快照总耗时。
        total_elapsed_ms = int((time.monotonic() - status_started_at) * 1000)
        # 状态快照耗时较长时升级为告警日志，便于继续压缩卡顿来源。
        level_method = log.warning if total_elapsed_ms >= 1000 else log.debug
        level_method(
            "manager.status 快照完成",
            total_elapsed_ms=total_elapsed_ms,
            drain_events_elapsed_ms=drain_events_elapsed_ms,
            db_open_elapsed_ms=db_open_elapsed_ms,
            device_lookup_elapsed_ms=device_lookup_elapsed_ms,
            row_build_elapsed_ms=row_build_elapsed_ms,
            row_count=len(rows),
        )
        return rows
