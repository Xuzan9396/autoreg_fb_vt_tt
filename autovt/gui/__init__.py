# 声明本包用途，便于其他模块快速理解。
"""GUI 包入口定义。"""

# 导出 GUI 启动函数，供 main.py 复用。
from autovt.gui.app import run_gui

# 显式声明公开符号，避免星号导入带入无关对象。
__all__ = ["run_gui"]
