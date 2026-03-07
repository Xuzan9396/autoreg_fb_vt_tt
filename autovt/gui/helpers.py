"""GUI 共享常量、数据类和工具函数。"""

from __future__ import annotations

import time
from dataclasses import dataclass

import flet as ft


# ── 常量 ─────────────────────────────────────────────────────────────────

LOGIN_USERNAME = "admin"
LOGIN_PASSWORD = "123456"
# 设备列表自动监控刷新间隔（秒），调大到 5 秒降低 adb 轮询压力。
DEVICE_MONITOR_INTERVAL_SEC = 5.0
# 账号列表每页条数（固定 20，和需求保持一致）。
ACCOUNT_PAGE_SIZE = 20
MOJIWANG_RUN_NUM_KEY = "mojiwang_run_num"
MOJIWANG_RUN_NUM_DESC = "抹机玩抹机次数: 1 到 100 填写值"
STATUS_23_RETRY_MAX_KEY = "status_23_retry_max_num"
STATUS_23_RETRY_MAX_DESC = "账号 status=2/3 时同账号重试次数: 0=不重试，1=重试一次（范围 0 到 5）"
# 定义全局 vinted 密码配置 key。
VT_PWD_KEY = "vt_pwd"
# 定义全局 vinted 密码配置描述文案。
VT_PWD_DESC = "Vinted 全局密码配置（为空时表示不启用全局密码）"
# 定义 Facebook 删除控制配置 key。
FB_DELETE_NUM_KEY = "fb_delete_num"
# 定义 Facebook 删除控制描述文案。
FB_DELETE_NUM_DESC = "0 不删除，其他数字每隔第几次重装"
# 定义设置页 Facebook 账号清理控制配置 key。
SETTING_FB_DEL_NUM_KEY = "setting_fb_del_num"
# 定义设置页 Facebook 账号清理控制描述文案。
SETTING_FB_DEL_NUM_DESC = "0 不清理，其他数字每隔第几次执行设置页 Facebook 账号清理"
# 定义代理开始位置配置 key。
PROXYIP_START_NUM_KEY = "proxyip_start_num"
# 定义代理开始位置配置描述文案。
PROXYIP_START_NUM_DESC = "代理开始位置：范围 1 到 5，填写 1 表示索引 0"
# 定义代理结束位置配置 key。
PROXYIP_END_NUM_KEY = "proxyip_end_num"
# 定义代理结束位置配置描述文案。
PROXYIP_END_NUM_DESC = "代理结束位置：范围 1 到 5，且必须大于等于代理开始位置"


# ── 数据类 ────────────────────────────────────────────────────────────────

@dataclass(slots=True)
class DeviceViewModel:
    """设备列表每一行展示所需的数据模型。"""
    serial: str
    online: bool
    pid: int
    alive: str
    state: str
    detail: str
    email_account: str
    updated_at: float


# ── 工具函数 ──────────────────────────────────────────────────────────────

def state_color(state: str) -> str:
    """根据设备状态返回标签颜色。"""
    color_map = {
        "ready": ft.Colors.BLUE_700,
        "running": ft.Colors.GREEN_700,
        "paused": ft.Colors.AMBER_700,
        "recovering": ft.Colors.DEEP_ORANGE_500,
        "warning": ft.Colors.ORANGE_600,
        "error": ft.Colors.RED_700,
        "fatal": ft.Colors.RED_900,
        "stopping": ft.Colors.BLUE_GREY_700,
        "stopped": ft.Colors.GREY_600,
        "waiting": ft.Colors.AMBER_700,
        "unknown": ft.Colors.GREY_700,
        "idle": ft.Colors.GREY_600,
        "starting": ft.Colors.LIGHT_BLUE_600,
    }
    return color_map.get(state, ft.Colors.GREY_600)


def state_text(state: str) -> str:
    """把设备状态英文值转为中文文案。"""
    # 读取原始状态并清理空白字符，避免异常值影响展示。
    raw_state = str(state or "").strip()
    # 统一转小写做映射匹配，兼容状态值大小写差异。
    state_key = raw_state.lower()
    # 状态文案映射表（英文状态 -> 中文展示）。
    text_map = {
        # 初始化完成。
        "ready": "就绪",
        # 正在执行任务。
        "running": "运行中",
        # 已暂停。
        "paused": "暂停中",
        # 正在恢复运行时。
        "recovering": "恢复中",
        # 业务可恢复警告态。
        "warning": "警告",
        # 普通错误态。
        "error": "异常",
        # 致命错误态。
        "fatal": "致命错误",
        # 正在停止。
        "stopping": "停止中",
        # 已停止。
        "stopped": "已停止",
        # 无可用账号，等待新数据。
        "waiting": "等待账号",
        # 未知状态。
        "unknown": "未知",
        # 空闲未执行。
        "idle": "空闲",
        # 启动过程中。
        "starting": "启动中",
    }
    # 命中已知状态映射时直接返回中文文案。
    if state_key in text_map:
        return text_map[state_key]
    # 空状态时返回占位符，避免显示空白标签。
    if raw_state == "":
        return "-"
    # 非空但未知状态时原样返回，便于排查新状态值。
    return raw_state


def register_status_text(value: int) -> str:
    """把 fb/vt/tt 的注册状态数值转为中文文案。"""
    mapping = {0: "未注册", 1: "成功", 2: "失败"}
    return mapping.get(int(value), f"未知({int(value)})")


def register_status_color(value: int) -> str:
    """根据 fb/vt/tt 的注册状态返回标签颜色。"""
    mapping = {0: ft.Colors.BLUE_GREY_600, 1: ft.Colors.GREEN_700, 2: ft.Colors.RED_700}
    return mapping.get(int(value), ft.Colors.GREY_700)


def account_status_text(value: int) -> str:
    """把账号 status 数值转为中文文案。"""
    mapping = {0: "未使用", 1: "正在使用", 2: "已经使用", 3: "账号问题"}
    return mapping.get(int(value), f"未知({int(value)})")


def account_status_color(value: int) -> str:
    """根据账号 status 返回标签颜色。"""
    mapping = {
        0: ft.Colors.BLUE_GREY_600,
        1: ft.Colors.LIGHT_BLUE_700,
        2: ft.Colors.GREEN_700,
        3: ft.Colors.RED_700,
    }
    return mapping.get(int(value), ft.Colors.GREY_700)


def mask_access_key(raw_value: str) -> str:
    """对 email_access_key 做前 10 位展示，后续以省略号隐藏。"""
    clean_value = str(raw_value or "")
    if clean_value == "":
        return "-"
    if len(clean_value) <= 10:
        return clean_value
    return f"{clean_value[:10]}..."


def format_timestamp(ts_value: int) -> str:
    """把秒级时间戳格式化为文本。"""
    if ts_value <= 0:
        return "-"
    try:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(int(ts_value)))
    except Exception:
        return str(ts_value)
