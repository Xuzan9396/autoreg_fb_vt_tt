# 导出主入口方法，方便外部直接 `from autovt.emails import getfackbook_code`。
from autovt.emails.emails import getfackbook_code

# 定义对外导出列表，限制包级暴露符号范围。
__all__ = ["getfackbook_code"]
