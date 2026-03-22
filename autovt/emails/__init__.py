# 导出主入口方法，方便外部直接 `from autovt.emails import getfackbook_code`。
from autovt.emails.emails import getfackbook_code
# 导出 Vinted 取码入口，方便外部直接 `from autovt.emails import getvinted_code`。
from autovt.emails.emails import getvinted_code

# 定义对外导出列表，限制包级暴露符号范围。
__all__ = ["getfackbook_code", "getvinted_code"]
