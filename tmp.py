# -*- coding: utf-8 -*-
# 声明脚本作者。
__author__ = "admin"

# 导入日志模块，用于记录调试过程和错误信息。
import logging
# 导入随机模块，用于随机选择图片索引。
import random
# 导入路径模块，用于构造日志目录和项目根目录。
from pathlib import Path

# 导入 Airtest 命令行初始化函数。
from airtest.cli.parser import cli_setup
# 导入 Airtest 自动初始化函数。
from airtest.core.api import auto_setup
# 导入 Poco Android 驱动。
from poco.drivers.android.uiautomation import AndroidUiautomationPoco

# 计算当前脚本目录。
BASE_DIR = Path(__file__).resolve().parent
# 定义日志目录路径。
LOG_DIR = BASE_DIR / "log"
# 创建日志目录，若已存在则忽略。
LOG_DIR.mkdir(parents=True, exist_ok=True)
# 定义当前脚本日志文件路径。
LOG_FILE = LOG_DIR / "tmp_random_photo.log"

# 创建当前脚本专用日志器。
logger = logging.getLogger("tmp_random_photo")
# 设置日志级别为 INFO。
logger.setLevel(logging.INFO)
# 关闭向上级日志器传播，避免重复输出。
logger.propagate = False

# 当日志器还没有处理器时再初始化，避免重复添加 handler。
if not logger.handlers:
    # 创建文件日志处理器。
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    # 创建终端日志处理器。
    stream_handler = logging.StreamHandler()
    # 定义统一日志格式。
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    # 给文件处理器设置格式。
    file_handler.setFormatter(formatter)
    # 给终端处理器设置格式。
    stream_handler.setFormatter(formatter)
    # 把文件处理器挂到日志器。
    logger.addHandler(file_handler)
    # 把终端处理器挂到日志器。
    logger.addHandler(stream_handler)

# 使用异常保护整个调试流程。
    # 判断是否由 Airtest CLI 启动。
if not cli_setup():
    # 非 CLI 场景时手动执行 Airtest 初始化。
    auto_setup(
        # 传入当前脚本路径。
        __file__,
        # 打开 Airtest 运行日志目录。
        logdir=True,
        # 指定安卓设备连接 URI。
        devices=["android://127.0.0.1:5037/64fb07e2?touch_method=MAXTOUCH&"],
        # 指定项目根目录为当前脚本目录。
        project_root=str(BASE_DIR),
    )

# 创建 Poco 驱动对象。
poco = AndroidUiautomationPoco(use_airtest_input=True, screenshot_each_action=False)


snapshot(msg="请填写测试点.")


bools = poco("Cette Page n’est pas disponible pour le moment").exists()
print(f"当前状态是: {bools}")


bools = poco(text="La Page n’est pas disponible pour le moment").exists()

print(f"当前状态是v2: {bools}")


     
poco("android.view.View").click()
poco("Application prédite : Facebook").click()
poco("android.widget.Button").click()
poco("android.view.View").click()

poco(text="Create new account").click()







