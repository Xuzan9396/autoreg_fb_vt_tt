import os
import platform
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parents[1]
# 图片资源根目录
IMAGES_DIR = PROJECT_ROOT / "images"


def _env_bool(name: str, default: bool) -> bool:
    """读取布尔环境变量：支持 1/true/yes/on。"""
    # 读取环境变量原始字符串。
    raw_value = os.getenv(name)
    # 环境变量不存在时返回默认值。
    if raw_value is None:
        return default
    # 统一按真值集合解析。
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def _resolve_runtime_data_dir() -> Path:
    """解析运行期数据目录（日志等），确保打包后也有稳定可写路径。"""
    # 读取当前系统名称，便于分平台处理目录规则。
    system_name = platform.system().lower()
    # macOS：统一放到用户 Application Support。
    if system_name == "darwin":
        return Path.home() / "Library" / "Application Support" / "AutoVT"
    # Windows：优先用 APPDATA，兜底 LOCALAPPDATA。
    if system_name.startswith("win"):
        appdata = os.environ.get("APPDATA", "").strip()
        if appdata:
            return Path(appdata) / "AutoVT"
        local_appdata = os.environ.get("LOCALAPPDATA", "").strip()
        if local_appdata:
            return Path(local_appdata) / "AutoVT"
        # 再兜底常见 Roaming 路径。
        return Path.home() / "AppData" / "Roaming" / "AutoVT"
    # Linux/其他：优先 XDG_STATE_HOME，兜底 ~/.local/state。
    xdg_state_home = os.environ.get("XDG_STATE_HOME", "").strip()
    if xdg_state_home:
        return Path(xdg_state_home) / "autovt"
    return Path.home() / ".local" / "state" / "autovt"


# 运行期数据根目录（日志等写到这里，不写到代码目录）。
RUNTIME_DATA_DIR = _resolve_runtime_data_dir()
# 日志目录（跨平台可写，适合源码和打包两种运行方式）。
LOG_DIR = RUNTIME_DATA_DIR / "log"
# JSON 日志目录（manager/worker 都写这里）。
JSON_LOG_DIR = LOG_DIR / "json"

# 当前运行语言（例如 fr、en、zh）
LOCALE = "fr"
# 当前业务模块名称（可按你的业务继续拆分）
FEATURE_NAME = "抹机王"

# ADB 配置
# ADB 可执行命令名（默认直接用系统 PATH 里的 adb）。
ADB_BIN = "adb"
# ADB Server 地址（本机一般是 127.0.0.1:5037）。
ADB_SERVER_ADDR = "127.0.0.1:5037"
# Airtest 截图方式（JAVACAP 更稳定，通常可避免 MINICAP 初始化报错）。
CAP_METHOD = "JAVACAP"
# Airtest 触控方式（MAXTOUCH 比较常用）。
TOUCH_METHOD = "MAXTOUCH"

# 多进程任务循环间隔（秒）
WORKER_LOOP_INTERVAL_SEC = 2.0
# worker 在“无可用账号/等待任务”状态下的低频轮询间隔（秒）。
WORKER_WAITING_POLL_INTERVAL_SEC = 8.0
# worker 在“暂停状态”下的低频轮询间隔（秒）。
WORKER_PAUSED_POLL_INTERVAL_SEC = 0.5
# 单设备优雅停止等待超时（秒）：超时后进入强制终止。
WORKER_STOP_GRACE_TIMEOUT_SEC = 2.0
# 强制终止后再次等待进程退出的超时（秒）。
WORKER_STOP_FORCE_TIMEOUT_SEC = 1.0
# worker 初始化失败后的重试等待（秒）
WORKER_INIT_RETRY_DELAY_SEC = 3.0
# worker 运行中发生可恢复错误后的重试等待（秒）
WORKER_RECOVER_RETRY_DELAY_SEC = 2.0
# 连续未知错误达到该阈值后，触发一次完整重初始化
WORKER_MAX_CONSECUTIVE_UNKNOWN_ERRORS = 3
# 初始化最大重试次数（0 表示无限重试，避免进程直接退出）
WORKER_MAX_INIT_RETRIES = 0
# 日志级别（DEBUG/INFO/WARNING/ERROR）
LOG_LEVEL = "INFO"
# 是否开启 Airtest/Poco 第三方 DEBUG 日志
ENABLE_AIRTEST_DEBUG = False
# 是否保存 Airtest 截图文件（False 时不再生成一堆 *.jpg 调试图）。
AIRTEST_SAVE_IMAGE = _env_bool("AUTOVT_AIRTEST_SAVE_IMAGE", False)
# 是否在每次 Poco 动作后自动截图（False 可显著减少图片落盘和磁盘占用）。
POCO_SCREENSHOT_EACH_ACTION = _env_bool("AUTOVT_POCO_SCREENSHOT_EACH_ACTION", False)

# 当前任务图片目录：images/<语言>/<业务模块>/
FEATURE_IMAGE_DIR = IMAGES_DIR / LOCALE / FEATURE_NAME

# 本任务用到的模板图
SETTINGS_ICON_TEMPLATE = FEATURE_IMAGE_DIR / "tpl1770223525363.png"
TARGET_ENTRY_TEMPLATE = FEATURE_IMAGE_DIR / "tpl1770225509350.png"

# 临时调试开关：True 时执行 HOME 后立即结束
DEBUG_STOP_AFTER_HOME = False
