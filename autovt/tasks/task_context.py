from __future__ import annotations  # 开启前向引用支持，便于类型标注写法更简洁。

from dataclasses import dataclass, field  # 导入 dataclass/field，用于定义可扩展上下文对象。
from typing import Any  # 导入 Any 类型，支持 extras 承载动态扩展数据。


@dataclass  # 使用 dataclass 定义上下文对象，便于后续持续扩展字段。
class TaskContext:  # 定义任务运行上下文对象，统一承载设备相关信息。
    serial: str = ""  # 当前设备序列号（例如 64fb07e2）。
    device_locale: str = "unknown"  # 当前设备语言区域（例如 en-US / zh-CN）。
    device_lang: str = "unknown"  # 当前设备语言主码（例如 en / zh）。
    user_info: dict[str, Any] = field(default_factory=dict)  # 当前设备绑定的一条 t_user 数据（整条账号信息）。
    config_map: dict[str, str] = field(default_factory=dict)  # t_config 全表配置映射（key -> val）。
    extras: dict[str, Any] = field(default_factory=dict)  # 预留动态扩展字段（例如设备品牌、系统版本、自定义标记等）。

    @classmethod  # 声明类方法，便于从 serial + locale 快速构建上下文对象。
    def from_serial_locale(cls, serial: str, device_locale: str) -> "TaskContext":  # 根据设备号和区域码创建上下文。
        locale = (device_locale or "unknown").strip()  # 先规范 locale 字符串，避免空值和空格干扰。
        if not locale or locale.lower() in {"none", "null"}:  # 对无效占位值统一降级为 unknown。
            locale = "unknown"  # 使用 unknown 作为统一兜底值。
        lang = locale.split("-", 1)[0].lower() if locale != "unknown" else "unknown"  # 抽取语言主码，unknown 保持不变。
        return cls(serial=serial, device_locale=locale, device_lang=lang)  # 返回构建完成的上下文对象。

    def missing_required_fields(self) -> list[str]:  # 返回当前上下文里缺失的必填字段列表。
        missing: list[str] = []  # 初始化缺失字段列表。
        if not (self.serial or "").strip():  # serial 为空时判定为缺失。
            missing.append("serial")  # 记录缺失 serial。
        if not (self.device_locale or "").strip() or self.device_locale == "unknown":  # 语言区域为空或 unknown 时判定为缺失。
            missing.append("device_locale")  # 记录缺失 device_locale。
        if not (self.device_lang or "").strip() or self.device_lang == "unknown":  # 语言主码为空或 unknown 时判定为缺失。
            missing.append("device_lang")  # 记录缺失 device_lang。
        return missing  # 返回缺失字段列表。

    def ensure_required(self) -> None:  # 强制校验必填字段，不满足时直接抛错。
        missing = self.missing_required_fields()  # 先获取缺失字段列表。
        if missing:  # 只要有缺失字段就判定上下文无效。
            raise RuntimeError(f"TaskContext 缺少必填字段: {', '.join(missing)}")  # 抛出明确错误，供上层做 fatal 处理。

    def get_config(self, key: str, default: str = "") -> str:  # 从 config_map 按 key 读取配置值（不存在时返回 default）。
        safe_key = str(key or "").strip()  # 标准化 key 文本，避免空白字符干扰读取。
        if safe_key == "":  # 空 key 时直接返回默认值，避免误查。
            return str(default)
        return str(self.config_map.get(safe_key, default))  # 返回配置值（统一转字符串）。
