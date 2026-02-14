from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parents[1]
# 日志目录
LOG_DIR = PROJECT_ROOT / "log"
# JSON 日志目录
JSON_LOG_DIR = LOG_DIR / "json"
# 图片资源根目录
IMAGES_DIR = PROJECT_ROOT / "images"

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

# 当前任务图片目录：images/<语言>/<业务模块>/
FEATURE_IMAGE_DIR = IMAGES_DIR / LOCALE / FEATURE_NAME

# 本任务用到的模板图
SETTINGS_ICON_TEMPLATE = FEATURE_IMAGE_DIR / "tpl1770223525363.png"
TARGET_ENTRY_TEMPLATE = FEATURE_IMAGE_DIR / "tpl1770225509350.png"

# 临时调试开关：True 时执行 HOME 后立即结束
DEBUG_STOP_AFTER_HOME = False
