# -*- coding: utf-8 -*-
# 声明脚本作者。
__author__ = "admin"

# 导入日志模块，用于记录调试过程和错误信息。
import logging
# 导入数学模块，用于计算贝塞尔曲线路径。
import math
# 导入随机模块，用于随机选择图片索引。
import random
# 导入路径模块，用于构造日志目录和项目根目录。
from pathlib import Path

# 导入 Airtest 命令行初始化函数。
from airtest.cli.parser import cli_setup
# 导入 Airtest 自动初始化函数和常用操作对象。
from airtest.core.api import Template, auto_setup, loop_find, snapshot
# 导入 Airtest 全局设备对象。
from airtest.core.helper import G
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






# 点击注册 self.poco_find_or_click( 等待 10s
poco("fr.vinted:id/show_registration_options_button").click()



# 点击邮箱 self.poco_find_or_click( 等待 5s
poco("fr.vinted:id/email_action_button").click()



# 输入用户Id t_user 表的 email_pwd + 4位数的随机(1000 到 9999） ,需要点击粘贴， _safe_click 和 _safe_input_on_focused
poco(textMatches="^Nom d'utilisateur.*$").click()


# 输入邮箱  t_user 表的 email_account ，需要点击粘贴， _safe_click 和 _safe_input_on_focused
poco(text="Email. ").click()





# 输入密码  t_user 表的 pwd ，需要点击粘贴 ，_safe_click 和 _safe_input_on_focused
poco(textMatches="^Mot de passe.*$").click()


# 点击勾选 self.poco_find_or_click( 等待 2s
poco("fr.vinted:id/terms_and_conditions_checkbox").click()


# 点击注册 self.poco_find_or_click( 等待 2s
poco("fr.vinted:id/email_register_sign_up").click()



# 下面滑块等待 10s 封装成一个方法  ， 返回true 和 false 


import random
# 导入日志模块，用于记录调试过程和错误信息。
import logging
# 导入数学模块，用于计算贝塞尔曲线路径。
import math
# 导入随机模块，用于随机选择图片索引。
import random
# 定义滑块模板对象，用于识别滑块当前位置。
slider_template = Template(r"tpl1774108524633.png", record_pos=(-0.25, -0.3), resolution=(1080, 2340))

# 使用异常保护滑块拖动流程，确保失败时能写入错误日志。
try:
    # 记录准备开始执行滑块拖动。
    logger.info("开始执行底部滑块贝塞尔曲线拖动测试。")
    # 识别滑块起点坐标。
    slider_start = loop_find(slider_template, timeout=10)
    # 记录识别到的滑块起点。
    logger.info("识别到滑块起点坐标：%s", slider_start)
    # 获取当前设备屏幕分辨率。
    screen_width, screen_height = G.DEVICE.get_current_resolution()
    # 记录当前设备分辨率，便于排查轨迹偏移问题。
    logger.info("当前设备分辨率：width=%s height=%s", screen_width, screen_height)
    # 计算终点横坐标，直接逼近屏幕最右侧安全边界，提升完成速度。
    slider_end_x = screen_width - random.randint(12, 24)
    # 计算终点纵坐标，只保留极小波动，避免末端偏离滑道。
    slider_end_y = slider_start[1] + random.randint(-4, 4)
    # 计算第一段贝塞尔控制点一的横坐标，模拟起手加速。
    control_1_x = slider_start[0] + int((slider_end_x - slider_start[0]) * random.uniform(0.20, 0.30))
    # 计算第一段贝塞尔控制点一的纵坐标，加入轻微向下偏移。
    control_1_y = slider_start[1] + random.randint(4, 16)
    # 计算第二段贝塞尔控制点二的横坐标，模拟中段稳定推进。
    control_2_x = slider_start[0] + int((slider_end_x - slider_start[0]) * random.uniform(0.72, 0.84))
    # 计算第二段贝塞尔控制点二的纵坐标，加入轻微向上回正。
    control_2_y = slider_start[1] + random.randint(-14, 8)
    # 生成轨迹采样点数量，减少点数以提升滑动速度。
    curve_point_count = random.randint(5, 7)
    # 初始化滑动轨迹点列表。
    swipe_points = []
    # 生成单段贝塞尔曲线点，保证持续按压并快速向右推进。
    for index in range(curve_point_count):
        # 计算当前采样点的时间参数。
        t = index / float(curve_point_count)
        # 计算曲线的补余参数。
        one_minus_t = 1 - t
        # 计算曲线点的横坐标。
        point_x = int(
            (one_minus_t ** 3) * slider_start[0]
            + 3 * (one_minus_t ** 2) * t * control_1_x
            + 3 * one_minus_t * (t ** 2) * control_2_x
            + (t ** 3) * slider_end_x
        )
        # 计算曲线点的纵坐标，并加入轻微抖动。
        point_y = int(
            (one_minus_t ** 3) * slider_start[1]
            + 3 * (one_minus_t ** 2) * t * control_1_y
            + 3 * one_minus_t * (t ** 2) * control_2_y
            + (t ** 3) * slider_end_y
            + math.sin(t * math.pi) * random.uniform(-2.0, 2.0)
        )
        # 把曲线点纵坐标限制在屏幕安全区域内。
        point_y = max(20, min(screen_height - 20, point_y))
        # 追加曲线轨迹点。
        swipe_points.append((point_x, point_y))
    # 生成轻微过冲点，模拟真实手势惯性，同时保证到达最右边。
    overshoot_point = (screen_width - random.randint(4, 10), max(20, min(screen_height - 20, slider_end_y + random.randint(-2, 2))))
    # 生成回拉修正点，模拟人手二次微调。
    settle_point = (screen_width - random.randint(10, 18), max(20, min(screen_height - 20, slider_end_y + random.randint(-2, 2))))
    # 追加过冲点到轨迹末尾。
    swipe_points.append(overshoot_point)
    # 追加回拉修正点到轨迹末尾。
    swipe_points.append(settle_point)
    # 记录本次实际生成的轨迹点。
    logger.info("本次生成滑动轨迹点数量：%s，轨迹点：%s", len(swipe_points), swipe_points)
    # 使用多点滑动执行贝塞尔拟人轨迹，并缩短整体耗时。
    G.DEVICE.swipe_along(swipe_points, duration=round(random.uniform(0.42, 0.62), 2), steps=random.randint(8, 12))
    # 记录滑块拖动执行完成。
    logger.info("底部滑块贝塞尔曲线拖动执行完成。")
# 捕获所有异常并写入错误日志，方便手动测试排查。
except Exception:
    # 记录滑块拖动失败的完整异常堆栈。
    logger.exception("底部滑块贝塞尔曲线拖动失败。")
    # 失败时截图，便于定位页面状态和滑块位置。
    snapshot(msg="底部滑块贝塞尔曲线拖动失败")





# /Users/admin/go/src/autovt/autovt/tasks/vinted.py 465 行 追加下面逻辑， 参考该文件使用的方法，下面只是大概流程，


# 点击接受 ，查找点击 最多等待 40s
poco(text="Accepter tout").click()


# 点击验证码框架 ,最多等待 10s 
poco("fr.vinted:id/view_input_value").click()


# 获取vinted 验证码 参考 /Users/admin/go/src/autovt/autovt/emails/test_vt.py, 如果没获取成功验证码成功，重试5次， 每次等待 15s ,然后输入粘贴

# 提交验证码， 等待10s
poco("fr.vinted:id/verify_code_button").click()


poco("fr.vinted:id/view_input_value").click()



poco("android.widget.LinearLayout").offspring("android.view.ViewGroup").child("android.webkit.WebView").offspring("captcha__frame__bottom").child("android.view.View")[1].child("android.widget.TextView")[0].click()



Template(r"tpl1774194537953.png", record_pos=(-0.306, -0.085), resolution=(1080, 2340))

poco("android:id/navigationBarBackground").swipe([-0.1789, -0.4832])

Template(r"tpl1774195425217.png", record_pos=(-0.255, -0.295), resolution=(1080, 2340))















