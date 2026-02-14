import re
import subprocess
from urllib.parse import urlencode

from autovt.logs import get_logger
from autovt.settings import ADB_BIN, ADB_SERVER_ADDR, CAP_METHOD, TOUCH_METHOD

log = get_logger("adb")


def list_online_serials() -> list[str]:
    """读取 adb 在线设备 serial 列表。"""
    try:
        # 调用 `adb devices` 获取设备清单。
        result = subprocess.run(
            [ADB_BIN, "devices"],
            capture_output=True,
            text=True,
            check=True,
        )
        log.debug("执行 adb devices 成功")
    except FileNotFoundError as exc:
        # 机器上没装 adb 或 PATH 里找不到 adb 时，给出清晰报错。
        log.exception("未找到 adb 命令")
        raise RuntimeError(f"未找到 adb 命令，请确认 {ADB_BIN} 已安装并在 PATH 中。") from exc

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
