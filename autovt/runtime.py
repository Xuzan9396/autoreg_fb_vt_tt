from pathlib import Path
import sys
from typing import Any

from autovt.adb import build_device_uri
from autovt.logs import apply_third_party_log_policy, get_logger
from autovt.settings import LOG_DIR, PROJECT_ROOT

log = get_logger("runtime")
# 进程内共享的 Poco 单例（每个 worker 进程各自一份，互不影响）。
_POCO_INSTANCE: Any | None = None


def setup_device(serial: str, script_file: str, log_subdir: str) -> None:
    """
    在当前进程内初始化一台设备。
    多进程模式下每个子进程只调用一次，互不干扰。
    """
    # 延迟导入：只在子进程真正初始化设备时才加载 airtest。
    # 这样主控层（只做进程管理）不会被 airtest 依赖强绑定。
    from airtest.cli.parser import cli_setup
    from airtest.core.api import auto_setup, set_current

    # Airtest import 时会改动 logger 级别，这里导入后立即重置一次策略。
    airtest_debug = apply_third_party_log_policy()
    log.info("已应用第三方日志策略", airtest_debug=airtest_debug)

    if len(sys.argv) > 1:
        # 当前脚本携带了自定义参数（例如 test.py clear_all），直接跳过 Airtest CLI 解析。
        log.debug("检测到自定义参数，跳过 cli_setup 解析", argv=list(sys.argv))
    else:
        try:
            if cli_setup():
                # 如果通过 airtest 命令行启动，环境已初始化，直接返回。
                log.info("检测到 Airtest CLI 场景，跳过 setup_device")
                return
        except SystemExit:
            # 当参数解析触发退出时，忽略该退出并继续执行我们自己的初始化流程。
            log.debug("cli_setup 解析触发退出，忽略并继续初始化", argv=list(sys.argv))

    # 按设备划分日志目录，避免多设备并发写同一个日志目录。
    log_dir = Path(LOG_DIR) / log_subdir
    log_dir.mkdir(parents=True, exist_ok=True)

    # 初始化 Airtest：
    # 1) 指定当前脚本文件
    # 2) 指定日志目录
    # 3) 只连接本进程负责的这一台设备
    # 4) 指定项目根目录（便于资源定位）
    auto_setup(
        script_file,
        logdir=str(log_dir),
        devices=[build_device_uri(serial)],
        project_root=str(PROJECT_ROOT),
    )
    # 当前进程内只连一台设备，索引固定是 0。
    set_current(0)
    log.info("设备初始化完成", serial=serial, log_dir=str(log_dir))


def create_poco() -> Any:
    # 延迟导入：避免主控阶段提前加载移动端自动化依赖。
    from poco.drivers.android.uiautomation import AndroidUiautomationPoco

    global _POCO_INSTANCE
    # 创建 Poco 驱动实例，后续任务里就能进行控件级操作。
    _POCO_INSTANCE = AndroidUiautomationPoco(
        use_airtest_input=True,
        screenshot_each_action=True,
    )
    log.info("Poco 初始化完成", poco_type=type(_POCO_INSTANCE).__name__)
    return _POCO_INSTANCE


def get_poco() -> Any:
    """
    获取当前进程已初始化的 Poco 实例。
    任务层在 run_once 里直接调用这个函数即可拿到 Poco。
    """
    if _POCO_INSTANCE is None:
        log.error("获取 Poco 实例失败", reason="Poco 尚未初始化")
        raise RuntimeError("Poco 尚未初始化，请先调用 create_poco()")
    return _POCO_INSTANCE
