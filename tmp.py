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


poco(textMatches="Oui, me connecter en tant.*").click()

Profil, onglet poco(textMatches="Profil, onglet *").click()
poco(desc="Profil, onglet 6 sur 6").click()
poco(desc="Accueil, onglet 1 sur 6").click()

poco("android.widget.FrameLayout").offspring("android:id/content").child("android.widget.LinearLayout").child("com.facebook.katana:id/(name removed)").child("android.widget.LinearLayout").child("com.facebook.katana:id/(name removed)")[1].child("com.facebook.katana:id/(name removed)").child("com.facebook.katana:id/(name removed)").click()
poco("android:id/button2").click()
Template(r"images/fr/facebook/autoriser.png", record_pos=(0.001, 0.366), resolution=(1080, 2340))

touch(Template(r"tpl1772825378560.png", record_pos=(0.006, 0.369), resolution=(1080, 2340)))


wait(Template(r"tpl1772824226308.png", record_pos=(0.418, -0.942), resolution=(1080, 2340)),timeout=20, interval=3)

if exists(Template(r"tpl1772824044265.png", record_pos=(0.416, -0.839), resolution=(1080, 2340))):
    touch(Template(r"tpl1772824044265.png", record_pos=(0.416, -0.839), resolution=(1080, 2340)))


poco(desc="Retour").click()
poco(desc="Retour").click()
poco("Retour").click()
poco("Retour").click()
poco("android:id/button1").click()

poco("Photo de profil").click()




poco("Autoriser l’accès").click()

poco("android:id/button1").click()


poco("com.android.permissioncontroller:id/permission_allow_button").click()



poco("Paramètres").click()


打开设置
start_app("com.android.settings")


滑动到最底部
```
swipe(v1, v2=None, vector=None, **kwargs)[源代码]
在当前设备画面上进行一次滑动操作。

有两种传入参数的方式
swipe(v1, v2=Template(...)) # 从 v1 滑动到 v2

swipe(v1, vector=(x, y)) # 从 v1 开始滑动，沿着vector方向。

参数
:
v1 – 滑动的起点，可以是一个Template图片实例，或是绝对坐标 (x, y)

v2 – 滑动的终点，可以是一个Template图片实例，或是绝对坐标 (x, y)

vector – 滑动动作的矢量坐标，可以是绝对坐标 (x,y) 或是屏幕百分比，例如 (0.5, 0.5)

**kwargs – 平台相关的参数 kwargs，请参考对应的平台接口文档

抛出
:
Exception – 当没有足够的参数来执行滑动时引发异常

返回
:
原点位置和目标位置

支持平台
:
Android, Windows, iOS

示例
:

swipe((100, 100), (200, 200))
自定义滑动持续时间和经过几步到达终点:

# swiping lasts for 1 second, divided into 6 steps
swipe((100, 100), (200, 200), duration=1, steps=6)
Use relative coordinates to swipe, such as swiping from the center right to the left of the screen:

swipe((0.7, 0.5), (0.2, 0.5))
```

点击 Mots de passe et comptes
poco(text="Mots de passe et comptes").click()


开始循环，依次循环删除
查找 Facebook 有就点击没有就跳出结束
poco(text="Facebook").click()


sleep(1)
poco("Parcourir vers le haut").click()
sleep(1)
poco("com.android.settings:id/button").click()

sleep(1)

poco("android:id/button1").click()


写个新的对象方法 setting_clean_fb ，这个放到卸载，/Users/admin/go/src/autovt/autovt/tasks/open_settings.py

调用这个方法写到 /Users/admin/go/src/autovt/autovt/tasks/open_settings.py         # todo 清理设置 fb 634 行 ,调用这个清理需要根据 setting_fb_del_num 需要 t_config 加这个参数，逻辑和fb_delete_num 一样出发逻辑

多语言定义到 /Users/admin/go/src/autovt/autovt/desc.py

SETTING_ 开头吧


不确定跟我确定





# 获取当前设备实例
dev = device()

# 获取当前顶层的 Activity 信息
# 它会返回一个元组：(package_name, activity_name, pid)
top_activity = dev.get_top_activity()

print(f"当前包名: {top_activity[0]}")
print(f"当前Activity: {top_activity[1]}")


poco("android.widget.FrameLayout").child("android.widget.LinearLayout").child("android:id/content").child("com.facebook.katana:id/(name removed)").child("com.facebook.katana:id/(name removed)").child("android.widget.LinearLayout").child("android.widget.FrameLayout").child("com.facebook.katana:id/(name removed)").child("com.facebook.katana:id/(name removed)")[1].offspring("android:id/content").child("com.facebook.katana:id/(name removed)").child("com.facebook.katana:id/(name removed)").child("android.view.ViewGroup").child("com.facebook.katana:id/(name removed)").child("android.view.ViewGroup").child("com.facebook.katana:id/(name removed)").child("com.facebook.katana:id/(name removed)").child("android.view.ViewGroup")[0].child("android.view.ViewGroup")[1].child("android.view.ViewGroup").offspring("Profile Picture").child("android.view.ViewGroup").click()
poco("votre photo de profil").click()

poco("votre photo de profil").click()
poco("Ajouter une photo de profil").click()

poco("Choisir une photo de profil").click()


poco("ARRÊTER").click()

poco("android:id/button1").click()
poco(desc="Profil, onglet 4 sur 4").click()
poco(desc="Notifications, onglet 3 sur 4, 1 nouveau").click()


poco(desc="Profil, onglet 6 sur 6").click()

     
     
     







