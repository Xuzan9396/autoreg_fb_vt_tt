from __future__ import annotations

import json
import logging
import os
import re
import sys
from pathlib import Path

from loguru import logger

from autovt.settings import ENABLE_AIRTEST_DEBUG, JSON_LOG_DIR, LOG_LEVEL


def _safe_path_part(raw: str) -> str:
    return re.sub(r"[^0-9A-Za-z._-]+", "_", raw)


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _resolve_airtest_debug() -> bool:
    # 打包运行永久关闭 Airtest/Poco debug（忽略环境变量），避免线上包出现大量第三方噪音日志。
    executable_text = str(Path(sys.executable))  # 读取当前解释器或可执行文件路径。
    argv0_text = str(Path(sys.argv[0])) if sys.argv else ""  # 读取 argv[0]，兼容部分子进程场景。
    # 只要路径包含 .app/Contents/，就视为 macOS bundle 内运行（含 MacOS 与 Frameworks 子路径）。
    running_in_macos_bundle = ".app/Contents/" in executable_text or ".app/Contents/" in argv0_text
    # Windows 打包通常是 .exe；排除 python.exe/pythonw.exe，避免误伤源码调试。
    executable_name = Path(executable_text).name.lower()
    argv0_name = Path(argv0_text).name.lower()
    running_in_windows_exe = (
        (executable_text.lower().endswith(".exe") and "python" not in executable_name)
        or (argv0_text.lower().endswith(".exe") and "python" not in argv0_name)
    )
    if running_in_macos_bundle or running_in_windows_exe or bool(getattr(sys, "frozen", False)):
        return False

    # 源码运行时：环境变量优先，便于临时打开/关闭 debug：
    # AUTOVT_AIRTEST_DEBUG=1 python main.py
    env_value = os.getenv("AUTOVT_AIRTEST_DEBUG")
    if env_value is not None:  # 显式设置时按环境变量走。
        return _env_bool("AUTOVT_AIRTEST_DEBUG", ENABLE_AIRTEST_DEBUG)

    # 源码模式按 settings 默认值执行。
    return ENABLE_AIRTEST_DEBUG


def _resolve_log_level() -> str:
    # 环境变量优先，便于临时改级别：
    # AUTOVT_LOG_LEVEL=DEBUG python main.py
    return os.getenv("AUTOVT_LOG_LEVEL", LOG_LEVEL).upper()


def _configure_third_party_debug(enable_airtest_debug: bool) -> None:
    """
    控制 Airtest/Poco 的第三方日志噪音。
    默认关闭 debug（设为 WARNING），必要时可打开。
    """
    logging.captureWarnings(True)
    targets = [
        "airtest",
        "airtest.core.android.adb",
        "poco",
    ]
    level = logging.DEBUG if enable_airtest_debug else logging.WARNING
    for target in targets:
        logging.getLogger(target).setLevel(level)


def apply_third_party_log_policy() -> bool:
    """
    重新应用第三方日志策略。
    作用：应对 Airtest 在 import 时把 logger 改回 DEBUG 的行为。
    """
    enable_airtest_debug = _resolve_airtest_debug()
    level = logging.DEBUG if enable_airtest_debug else logging.WARNING

    _configure_third_party_debug(enable_airtest_debug)

    # 先处理根命名空间 logger。
    for name in ("airtest", "poco"):
        base_logger = logging.getLogger(name)
        base_logger.setLevel(level)
        for handler in base_logger.handlers:
            handler.setLevel(level)

    # 再处理已经创建出来的子 logger。
    for logger_name, logger_obj in logging.root.manager.loggerDict.items():
        if not isinstance(logger_obj, logging.Logger):
            continue
        if logger_name.startswith("airtest.") or logger_name.startswith("poco."):
            logger_obj.setLevel(level)
            for handler in logger_obj.handlers:
                handler.setLevel(level)

    return enable_airtest_debug


def _build_compact_text(record: dict) -> str:
    # 生成紧凑文本：时间 + 级别 + 文件位置 + 消息 + 额外参数。
    time_str = record["time"].strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]  # 提取毫秒级时间字符串，便于定位问题时间点。
    level = record["level"].name  # 读取日志级别名称（INFO/WARNING/ERROR 等）。
    name = record["name"]  # 读取日志记录器名字（通常是模块路径）。
    function = record["function"]  # 读取函数名，方便快速定位调用点。
    line = record["line"]  # 读取代码行号，便于直接跳转源码。
    message = record["message"]  # 读取日志主消息文本。
    extras = record.get("extra", {})  # 读取 loguru 的 extra 字段（bind 和 kwargs 都在这里）。
    extra_pairs: list[str] = []  # 初始化额外参数字符串列表。
    for key in sorted(extras):  # 按键名排序输出，保证日志顺序稳定可读。
        if key == "compact_json":  # 跳过内部使用字段，避免递归污染输出。
            continue  # 当前键处理完后直接看下一个键。
        value = extras[key]  # 读取当前额外字段的值。
        if isinstance(value, str):  # 字符串直接输出，避免二次 JSON 转义出现 \"。
            value_text = value.replace("\n", "\\n")  # 仅把换行转义成 \n，防止打断单行日志。
        elif isinstance(value, (int, float, bool)) or value is None:  # 基础标量类型用 str 即可。
            value_text = str(value)  # 基础类型转字符串，输出简洁可读。
        else:  # 复杂对象（dict/list/tuple/自定义对象）再做 JSON 兜底。
            try:  # 优先把复杂值序列化成 JSON，结构更清晰。
                value_text = json.dumps(value, ensure_ascii=False)  # 复杂对象保持 JSON 格式输出。
            except TypeError:  # 如果仍不可 JSON 序列化（例如部分自定义类）。
                value_text = str(value).replace("\n", "\\n")  # 退化成字符串，保证日志不会报错。
        extra_pairs.append(f"{key}={value_text}")  # 拼成 key=value 片段，后续统一拼接。
    if extra_pairs:  # 如果本条日志包含额外字段。
        message = f"{message} | {' '.join(extra_pairs)}"  # 把额外字段追加到消息尾部。
    return f"{time_str} | {level:<8} | {name}:{function}:{line} - {message}"  # 返回最终紧凑文本。


def _compact_json_patcher(record: dict) -> None:
    # 给每条日志注入紧凑 JSON 字符串，sink 用这个字段输出。
    text = _build_compact_text(record)
    record["extra"]["compact_json"] = json.dumps({"text": text}, ensure_ascii=False)


def setup_logging(process_role: str, serial: str | None = None) -> None:
    """
    初始化日志系统：
    - 终端 JSON 输出
    - 文件 JSON 输出
    - 自动包含 file/line/function（loguru record 自带）
    """
    JSON_LOG_DIR.mkdir(parents=True, exist_ok=True)

    level = _resolve_log_level()
    enable_airtest_debug = _resolve_airtest_debug()

    file_tag = serial if serial else process_role
    file_path = Path(JSON_LOG_DIR) / f"{_safe_path_part(file_tag)}.jsonl"

    # 重置默认 sink，避免重复输出。
    logger.remove()

    # 给所有日志添加统一上下文。
    logger.configure(
        extra={
            "process_role": process_role,
            "device_serial": serial or "",
        },
        patcher=_compact_json_patcher,
    )

    # 终端 JSON（stderr，不干扰交互输入）。
    logger.add(
        sys.stderr,
        level=level,
        format="{extra[compact_json]}",
        serialize=False,
        enqueue=True,
        backtrace=False,
        diagnose=False,
    )

    # 文件 JSON（jsonl，每行一条日志）。
    logger.add(
        str(file_path),
        level=level,
        format="{extra[compact_json]}",
        serialize=False,
        enqueue=True,
        rotation="20 MB",
        retention="14 days",
        backtrace=False,
        diagnose=False,
    )

    apply_third_party_log_policy()

    logger.bind(component="logging").info(
        "日志系统初始化完成",
        log_level=level,
        airtest_debug=enable_airtest_debug,
        log_file=str(file_path),
    )


def get_logger(component: str):
    # 统一增加 component 字段，便于过滤日志。
    return logger.bind(component=component)
