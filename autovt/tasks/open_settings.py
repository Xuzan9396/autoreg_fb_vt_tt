# 导入 Any 类型，方便给 Poco 节点做类型标注。
from typing import Any
# 导入随机模块，用于头像相册随机选图。
import random
# 导入时间模块，用于精确统计轮询超时。
import time

# 导入清理应用数据方法。
from airtest.core.api import clear_app
# 导入回到桌面方法。
from airtest.core.api import home
# 导入按键事件方法，用于切换输入焦点。
from airtest.core.api import keyevent
# 导入粘贴事件方法，用于向当前焦点粘贴文本。
from airtest.core.api import paste
# 导入设置剪贴板方法，配合 paste 做输入兜底。
from airtest.core.api import set_clipboard
# 导入休眠方法，避免轮询过快。
from airtest.core.api import sleep
# 导入启动应用方法。
from airtest.core.api import start_app
# 导入停止应用方法。
from airtest.core.api import stop_app
# 导入输入事件方法，用于给当前焦点输入文本。
from airtest.core.api import text
# 导入唤醒屏幕方法。
from airtest.core.api import wake

# 导入项目日志工厂。
from autovt.logs import get_logger
# 导入获取当前进程 Poco 实例的方法。
from autovt.runtime import create_poco
from autovt.runtime import get_poco
# 导入任务上下文对象，统一承载设备信息。
from autovt.tasks.task_context import TaskContext
# 导入用户数据库封装，供任务结束后回写账号状态。
from autovt.userdb.user_db import UserDB
from autovt.desc import  *
import json
from datetime import datetime

from autovt.emails import getfackbook_code

# 定义“打开设置并执行清理流程”的任务类。
class OpenSettingsTask:
    # 定义任务类的初始化方法，强制要求传入完整上下文。
    def __init__(self, task_context: TaskContext) -> None:
        # 创建当前任务专用日志对象。
        self.log = get_logger("task.open_settings")
        # 保存当前任务实例使用的 Poco 对象（先置空，后续再获取）。
        self.poco: Any | None = None
        # 保存任务上下文对象，后续字段统一从这里取值。
        self.task_context = task_context
        # 强制校验 serial/locale/lang 必填字段，缺失则立即抛错阻断执行。
        self.task_context.ensure_required()
        # 保存设备 serial，便于日志和分支判断使用。
        self.device_serial = self.task_context.serial
        # 保存设备语言区域码（例如 en-US / zh-CN）。
        self.device_locale = self.task_context.device_locale
        # 保存设备语言主码（例如 en / zh）。
        self.device_lang = self.task_context.device_lang
        # 读取当前设备绑定的一条 t_user 数据（完整账号信息)
        self.user_info = dict(self.task_context.user_info or {})

        print(f"DEBUG DATA: {json.dumps(self.user_info, indent=4, ensure_ascii=False)}")

        # 读取 t_config 全量 key->val 映射。
        self.config_map = {str(k): str(v) for k, v in dict(self.task_context.config_map or {}).items()}
        # 缓存当前账号邮箱，便于日志追踪。
        self.user_email = str(self.user_info.get("email_account", "")).strip()
        # 缓存 first_name，供 Facebook 表单输入。
        self.user_first_name = str(self.user_info.get("first_name", "")).strip()
        # 缓存 last_name，供 Facebook 表单输入。
        self.user_last_name = str(self.user_info.get("last_name", "")).strip()
        # 缓存密码，供 Facebook 表单输入。
        self.pwd = str(self.user_info.get("pwd", "")).strip()
        # 缓存全局 vt_pwd，供账号密码缺失时兜底使用。
        self.vt_pwd = str(self.config_map.get("vt_pwd", "")).strip()
        # 当账号 pwd 为空且配置了全局 vt_pwd 时，自动使用全局密码兜底。
        if self.pwd == "" and self.vt_pwd != "":
            # 使用全局 vt_pwd 作为当前任务密码。
            self.pwd = self.vt_pwd
            # 记录兜底日志，便于排查密码来源。
            self.log.warning("账号 pwd 为空，已使用全局 vt_pwd 兜底", user_email=self.user_email)
        # 保存需要先清理数据的业务应用包名。
        self.vinted_package = "fr.vinted"
        # 保存插件应用包名。
        self.mojiwang_packge = "com.yztc.studio.plugin"
        # Facebook 应用包名
        self.facebook_package = "com.facebook.katana"
        # 代理
        self.nekobox_package = "moe.nb4a"
        # 保存“清理按钮”资源 ID。
        self.mojiwang_wipe_button_id = "com.yztc.studio.plugin:id/wipedev_btn_wipe"
        # 保存“任务结束提示”资源 ID。
        self.mojiwang_done_msg_id = "com.yztc.studio.plugin:id/wipe_task_tv_msg"
        # 保存“任务结束提示”文本内容。
        self.mojiwang_done_msg_text = "任务结束-点击返回"
        # 从 t_config 读取抹机王轮次，默认值回退到 3。
        self.mojiwang_loop_count = self._read_mojiwang_loop_count()
        # 保存每次等待控件出现的最大秒数。
        self.mojiwang_wait_timeout_sec = 5.0
        # 创建用户数据库对象，供注册成功/失败后统一更新状态。
        self.user_db = UserDB()
        # 初始化 Facebook 失败原因缓存，失败时会写入 t_user.msg。
        self.facebook_error_reason = ""

    # 定义“读取抹机王轮次配置”的方法。
    def _read_mojiwang_loop_count(self) -> int:
        # 从配置映射读取 mojiwang_run_num，缺失时回退 3。
        raw_value = str(self.config_map.get("mojiwang_run_num", "3")).strip()
        # 尝试把配置值解析为整数。
        try:
            # 转成整数做边界校验。
            parsed_value = int(raw_value)
        # 非法值（非整数）时回退默认值。
        except Exception:
            # 返回默认轮次 3。
            return 3
        # 小于最小值时回退默认值。
        if parsed_value < 1:
            # 返回默认轮次 3。
            return 3
        # 大于最大值时截断到 100，避免异常大值拖慢流程。
        if parsed_value > 100:
            # 返回上限值 100。
            return 100
        # 返回合法轮次配置值。
        return parsed_value

    # 定义“获取并校验 Poco 实例”的方法。
    def _require_poco(self) -> Any:
        # 如果当前实例已经保存了 Poco，就直接复用。
        if self.poco is not None:
            # 返回已缓存的 Poco 对象。
            return self.poco
        # 开始尝试从运行时获取 Poco。
        try:
            # 从 runtime 获取当前进程中的 Poco 实例。
            self.poco = get_poco()
        # 如果获取过程中抛异常，先记录日志。
        except Exception as exc:
            # 打印异常日志，方便排查。
            self.log.exception("获取 Poco 实例失败", error=str(exc))
            # 尝试自动重建 Poco 连接，尽量避免流程直接崩溃。
            if self._try_recover_poco("require_poco"):
                # 重建成功后返回当前可用 Poco。
                return self.poco
            # 抛出更明确的业务异常。
            raise RuntimeError("Poco 实例不存在或未初始化，请先检查 worker 初始化日志") from exc
        # 双保险：即便没抛异常，也要防止拿到空对象。
        if self.poco is None:
            # 打印错误日志。
            self.log.error("获取 Poco 实例失败", reason="实例为空")
            # 主动抛错阻断后续流程。
            raise RuntimeError("Poco 实例为空，请先执行 create_poco()")
        # 记录成功拿到 Poco 的日志。
        self.log.info("已获取 Poco 实例", poco_type=type(self.poco).__name__)
        # 返回可用的 Poco 对象。
        return self.poco

    # 定义“判断是否为 Poco/ADB 连接异常”的方法。
    def _is_poco_disconnect_error(self, exc: Exception) -> bool:
        # 把异常转成小写字符串，便于统一关键字匹配。
        detail = str(exc).lower()
        # 空异常文本时直接判定为非连接异常。
        if not detail:
            # 返回 False 表示不是连接异常。
            return False
        # 定义连接中断相关关键字集合。
        keywords = (
            "transportdisconnected",
            "connection refused",
            "max retries exceeded",
            "failed to establish a new connection",
            "device not found",
            "adb: device",
            "adberror",
            "adbshellerror",
            "pocoservice",
            "127.0.0.1",
        )
        # 只要命中任意关键字就判定为连接异常。
        return any(keyword in detail for keyword in keywords)

    # 定义“尝试重建 Poco 连接”的方法。
    def _try_recover_poco(self, reason: str) -> bool:
        # 使用异常保护重建流程，避免二次异常导致崩溃。
        try:
            # 先清空当前缓存 Poco，避免复用失效对象。
            self.poco = None
            # 重新创建当前进程的 Poco 实例。
            create_poco()
            # 重新读取并缓存新 Poco 对象。
            self.poco = get_poco()
            # 记录重建成功日志。
            self.log.warning("Poco 连接已重建", reason=reason, poco_type=type(self.poco).__name__)
            # 返回 True 表示重建成功。
            return True
        # 捕获重建中的全部异常并记录日志。
        except Exception as exc:
            # 记录重建失败详情，便于排查设备连接问题。
            self.log.exception("Poco 连接重建失败", reason=reason, error=str(exc))
            # 返回 False 表示重建失败。
            return False

    # 定义“统一处理安全动作异常”的方法。
    def _handle_safe_action_exception(self, action: str, desc: str, exc: Exception) -> None:
        # 先记录原始异常堆栈，便于定位真实报错点。
        self.log.exception("动作执行异常，按失败处理", action=action, target=desc, error=str(exc))
        # 如果识别到 Poco/ADB 连接异常，则尝试自动重建连接。
        if self._is_poco_disconnect_error(exc):
            # 记录连接异常告警日志。
            self.log.warning("检测到 Poco/ADB 连接异常，尝试重建连接", action=action, target=desc)
            # 执行重建，不论成功失败都不再抛异常。
            self._try_recover_poco(reason=f"{action}:{desc}")

    def clear_all(self) -> None:
        # 这个方法目前没用到，但保留作为“如果需要在循环外做一次性清理”的预留。
        # 停止业务应用，确保可执行清理数据。
        stop_app(self.vinted_package)
        # 记录业务应用停止成功。
        self.log.info("已停止应用", package=self.vinted_package)
        sleep(0.5)
        # 清理业务应用数据，确保环境干净。
        clear_app(self.vinted_package)
        # 记录业务应用清理成功。
        self.log.info("已清理应用数据", package=self.vinted_package)
        # 先停止插件应用，避免脏状态残留。
        stop_app(self.mojiwang_packge)
        # 记录插件应用停止成功。
        self.log.info("已停止应用", package=self.mojiwang_packge)
        # stop_app(self.nekobox_package)
        # 记录插件应用停止成功。
        # self.log.info("已停止应用", package=self.nekobox_package)
        #
        stop_app(self.facebook_package)
        # 记录插件
        self.log.info("已停止应用", package=self.facebook_package)
        sleep(0.5)
        clear_app(self.facebook_package)
        #清理
        self.log.info("已清理应用数据", package=self.facebook_package)

    # 定义“等待节点可点击并点击”的通用方法。
    def _wait_and_click_node(self, node: Any, desc: str) -> bool:
        # 尝试执行“等待 + 点击”动作。
        try:
            # 使用你原来的 wait 逻辑：先等待，再判断是否存在。
            if node.wait(self.mojiwang_wait_timeout_sec).exists():
                # 节点在超时前出现后直接点击。
                node.click()
                # 记录点击成功日志，方便排查。
                self.log.info("点击成功", target=desc)
                # 返回 True 表示本次点击已经成功完成。
                return True
            # 超时后记录警告日志。
            self.log.error("等待超时，未点击", target=desc, timeout_sec=self.mojiwang_wait_timeout_sec)
            # 返回 False 表示本次没有点到目标控件。
            return False
        # 捕获异常并按失败处理，保证流程不会崩溃。
        except Exception as exc:
            # 统一记录异常并尝试恢复连接。
            self._handle_safe_action_exception("wait_and_click", desc, exc)
            # 返回 False 表示本次动作失败。
            return False

    # 定义“安全等待并判断存在”的方法，避免 UI 查询异常直接中断流程。
    def _safe_wait_exists(self, node: Any, wait_seconds: float, desc: str) -> bool:
        # 尝试执行等待和存在判断。
        try:
            # 成功时返回布尔值，统一给调用方使用。
            bools =  bool(node.wait(wait_seconds).exists())
            if not bools:
                self.log.error("查找失败", target=desc, wait_seconds=wait_seconds)

            return bools
        # 任意异常都在这里兜底，避免流程直接崩溃。
        except Exception as exc:
            # 统一记录异常并尝试恢复连接。
            self._handle_safe_action_exception("wait_exists", desc, exc)
            # 发生异常时按不存在处理，让主流程安全退出。
            return False

    # 定义“安全点击”的方法，避免点击异常中断流程。
    def _safe_click(self, node: Any, desc: str, sleep_interval: float | None = None) -> bool:
        # 尝试执行点击动作。
        try:
            # 仅使用关键字参数传递 sleep_interval，避免参数歧义。
            node.click(sleep_interval=sleep_interval)
            # 记录点击成功日志。
            self.log.info("点击成功", target=desc, sleep_interval=sleep_interval)
            # 返回 True 表示点击成功。
            return True
        # 任意点击异常都在这里兜底。
        except Exception as exc:
            # 统一记录异常并尝试恢复连接。
            self._handle_safe_action_exception("click", desc, exc)
            # 返回 False 表示点击失败。
            return False
    def _safe_wait_click(self, node: Any, wait_seconds: float, desc: str,sleep_interval: float | None = None ) -> bool:
        ok = self._safe_wait_exists(node,wait_seconds,desc)
        if not ok:
            return False

        return self._safe_click(node,desc,sleep_interval=sleep_interval)

    # 定义“安全点击 Facebook 深层 next 节点”的方法。
    def _safe_click_facebook_next_v2_deep(self, poco: Any) -> bool:
        # 使用异常保护构建深层节点，避免索引越界导致流程崩溃。
        try:
            # 根据固定层级链路定位 next 按钮节点。
            deep_next_node = (
                # 从页面 content 根节点开始向下查找。
                poco("android:id/content")
                # 进入 Facebook 页面第一层容器。
                .child("com.facebook.katana:id/(name removed)")
                # 进入 Facebook 页面第二层容器。
                .child("com.facebook.katana:id/(name removed)")
                # 进入第一层 FrameLayout。
                .child("android.widget.FrameLayout")
                # 进入第二层 FrameLayout。
                .child("android.widget.FrameLayout")
                # 选择第三层 FrameLayout 的索引 1。
                .child("android.widget.FrameLayout")[1]
                # 继续选择下一层 FrameLayout 的索引 1。
                .child("android.widget.FrameLayout")[1]
                # 逐层进入 ViewGroup 容器。
                .child("android.view.ViewGroup")
                # 逐层进入 ViewGroup 容器。
                .child("android.view.ViewGroup")
                # 逐层进入 ViewGroup 容器。
                .child("android.view.ViewGroup")
                # 逐层进入 ViewGroup 容器。
                .child("android.view.ViewGroup")
                # 在当前层级向下查找 RecyclerView。
                .offspring("androidx.recyclerview.widget.RecyclerView")[0]
                # 进入 RecyclerView 的第 2 个子节点。
                .child("android.view.ViewGroup")[1]
                # 继续进入下一层 ViewGroup。
                .child("android.view.ViewGroup")
                # 继续进入下一层 ViewGroup。
                .child("android.view.ViewGroup")
                # 进入最终目标 ViewGroup 的第 1 个子节点。
                .child("android.view.ViewGroup")[0]
            )
        # 捕获深层节点构建异常并按失败处理。
        except Exception as exc:
            # 统一记录异常并尝试恢复连接。
            self._handle_safe_action_exception("build_facebook_next_v2_deep", "next输入点v2-深层路径", exc)
            # 返回 False 表示本次定位失败。
            return False
        # 等待深层 next 节点出现。
        if not self._safe_wait_exists(deep_next_node, 2, "next输入点v2-深层路径"):
            # 返回 False 表示节点不存在。
            return False
        # 点击深层 next 节点并返回点击结果。
        if  self._safe_click(deep_next_node, "next输入点v2-深层路径点击", sleep_interval=2):
            return self._safe_click(poco(text=FACEBOOK_FIRST_LAST_NAME_NEXT[self.device_lang]), "重命名名称了", sleep_interval=1)
        return False

    # 定义“安全输入事件”的方法，避免使用 set_text 造成不可编辑异常。
    def _safe_input_by_event(self, node: Any, value: str, desc: str) -> bool:
        # 先点击目标节点尝试聚焦输入框。
        if not self._safe_click(node, f"{desc}-聚焦", sleep_interval=0.3):
            # 如果直接点击失败，再尝试点击父节点作为兜底。
            try:
                # 获取当前节点父节点，某些页面点击父容器才会聚焦输入框。
                parent = node.parent()
            # 父节点获取失败时直接返回失败。
            except Exception:
                # 标记父节点不可用。
                parent = None
            # 如果没有可用父节点。
            if parent is None:
                # 记录无法聚焦原因。
                self.log.info("输入框节点不可点击，无法触发输入事件", target=desc, value=value)
                # 返回 False 表示无法继续输入。
                return False
            # 尝试点击父节点聚焦输入框。
            if not self._safe_click(parent, f"{desc}-父节点聚焦", sleep_interval=0.3):
                # 记录兜底失败原因。
                self.log.info("输入框及父节点都不可点击，无法触发输入事件", target=desc, value=value)
                # 返回 False 表示输入失败。
                return False
        # 节点聚焦后执行输入事件。
        try:
            # 使用 Airtest 输入事件把文本打到当前焦点输入框。
            text(value, enter=False)
            # 记录输入事件成功日志。
            self.log.info("输入事件成功", target=desc, value=value)
            # 返回 True 表示输入成功。
            return True
        # 输入事件异常时兜底，不中断流程。
        except Exception as exc:
            # 如果识别到连接异常，走统一恢复逻辑并直接返回失败。
            if self._is_poco_disconnect_error(exc):
                # 统一记录异常并尝试恢复连接。
                self._handle_safe_action_exception("input_event", desc, exc)
                # 返回 False，避免继续执行后续输入动作。
                return False
            # 记录 text 输入失败原因，并进入 adb shell 输入兜底。
            self.log.error("输入事件失败，尝试 adb shell 输入", target=desc, value=value, error=str(exc))
            # 尝试使用 adb shell 对当前焦点输入文本。
            if self._safe_input_by_adb_shell(value=value, desc=desc, enter=False):
                # adb 输入成功则返回 True。
                return True
            # adb 兜底也失败时返回 False。
            return False

    # 定义“把文本转换为 adb input text 安全参数”的方法。
    def _build_adb_input_text_arg(self, value: str) -> str:
        # 先把入参标准化为字符串，避免 None 引发异常。
        raw_value = str(value or "")
        # 准备字符片段列表，后续逐字符拼接安全文本。
        pieces: list[str] = []
        # 逐个字符进行转换。
        for char in raw_value:
            # 空格转换为 %s，兼容 adb input text 语法。
            if char == " ":
                pieces.append("%s")
                continue
            # 常见 shell 特殊字符前补反斜杠，避免命令被解释。
            if char in {'\\', '"', "'", "&", "|", "<", ">", ";", "(", ")", "$", "`", "!", "*", "?", "[", "]", "{", "}", "#"}:
                pieces.append(f"\\{char}")
                continue
            # 普通字符按原样保留。
            pieces.append(char)
        # 返回转换后的安全参数字符串。
        return "".join(pieces)

    # 定义“使用 adb shell input text 输入当前焦点文本”的方法。
    def _safe_input_by_adb_shell(self, value: str, desc: str, enter: bool = False) -> bool:
        # 标准化输入文本，避免 None 透传到 adb。
        safe_value = str(value or "")
        # 空值输入没有业务意义，直接返回失败。
        if safe_value == "":
            # 记录空值失败原因，便于调用方定位。
            self.log.error("ADB Shell 输入失败：值为空", target=desc)
            # 返回 False 表示输入失败。
            return False
        # 把输入值转换成 adb input text 可接受格式。
        adb_text_arg = self._build_adb_input_text_arg(safe_value)
        # 转换后为空时直接返回失败。
        if adb_text_arg == "":
            # 记录转换失败日志。
            self.log.error("ADB Shell 输入失败：参数为空", target=desc, value=safe_value)
            # 返回 False 表示输入失败。
            return False
        # 延迟导入 device，避免主流程初始化阶段提前绑定 airtest。
        try:
            # 导入当前设备对象获取方法。
            from airtest.core.api import device
        # 导入失败时记录日志并返回失败。
        except Exception as exc:
            # 记录导入异常。
            self.log.error("ADB Shell 输入失败：导入 device 失败", target=desc, value=safe_value, error=str(exc))
            # 返回 False，避免异常扩散。
            return False
        # 尝试执行 adb shell 输入命令。
        try:
            # 获取当前 Airtest 绑定的设备对象。
            current_device = device()
            # 读取当前设备的 adb 客户端。
            adb_client = current_device.adb
            # 使用 adb input text 向当前焦点输入文本。
            adb_client.shell(["input", "text", adb_text_arg])
            # 当调用方要求回车时，补发 ENTER 键。
            if enter:
                # KEYCODE_ENTER 对应值是 66。
                adb_client.shell(["input", "keyevent", "66"])
            # 记录 adb 输入成功日志。
            self.log.info("焦点输入成功", target=desc, value=safe_value, mode="adb_input_text")
            # 返回 True 表示输入成功。
            return True
        # adb 输入异常时统一兜底。
        except Exception as exc:
            # 连接类异常走统一恢复流程。
            if self._is_poco_disconnect_error(exc):
                # 统一记录并尝试恢复连接。
                self._handle_safe_action_exception("focus_adb_input", desc, exc)
                # 返回 False，避免继续执行。
                return False
            # 记录 adb 输入失败原因。
            self.log.error("ADB Shell 输入失败，按跳过处理", target=desc, value=safe_value, error=str(exc))
            # 返回 False 表示输入失败。
            return False

    # 定义“对当前焦点输入文本”的方法，不依赖节点定位。
    def _safe_input_on_focused(self, value: str, desc: str,enter: bool = False) -> bool:
        # 先尝试直接发送输入事件。
        try:
            # 把文本输入到当前已聚焦的输入框。
            text(value, enter=enter)
            # 记录 text 方式输入成功。
            self.log.info("焦点输入成功", target=desc, value=value, mode="text")
            # 返回 True 表示输入成功。
            return True
        # text 失败后进入粘贴兜底流程。
        except Exception as exc:
            # 如果识别到连接异常，走统一恢复逻辑并直接返回失败。
            if self._is_poco_disconnect_error(exc):
                # 统一记录异常并尝试恢复连接。
                self._handle_safe_action_exception("focus_text_input", desc, exc)
                # 返回 False，避免继续执行粘贴动作。
                return False
            # 记录 text 失败原因，并进入 adb shell 输入兜底。
            self.log.error("text 输入失败，尝试 adb shell 输入", target=desc, value=value, error=str(exc))
        # 先尝试 adb shell 输入作为第一层兜底。
        if self._safe_input_by_adb_shell(value=value, desc=desc, enter=enter):
            # adb 输入成功时直接返回。
            return True
        # adb 失败后再尝试剪贴板粘贴。
        self.log.warning("adb shell 输入失败，尝试剪贴板粘贴", target=desc, value=value)
        # 尝试剪贴板粘贴作为兜底方案。
        try:
            # 先把要输入的值写入系统剪贴板。
            set_clipboard(value)
            # 向当前焦点执行粘贴动作。
            paste()
            # 记录 paste 方式输入成功。
            self.log.info("焦点粘贴成功", target=desc, value=value, mode="paste")
            # 返回 True 表示输入成功。
            return True
        # 粘贴也失败则返回失败，不抛异常。
        except Exception as exc:
            # 如果识别到连接异常，走统一恢复逻辑并返回失败。
            if self._is_poco_disconnect_error(exc):
                # 统一记录异常并尝试恢复连接。
                self._handle_safe_action_exception("focus_paste_input", desc, exc)
                # 返回 False，避免异常扩散。
                return False
            # 记录最终失败原因。
            self.log.error("焦点输入失败，已跳过", target=desc, value=value, error=str(exc))
            # 返回 False 表示输入失败。
            return False

    # 定义“安全按键事件”方法，用于焦点切换。
    def _safe_keyevent(self, key: str, desc: str) -> bool:
        # 尝试发送按键事件。
        try:
            # 发送指定按键（例如 KEYCODE_TAB）。
            keyevent(key)
            # 记录按键成功日志。
            self.log.info("按键事件成功", target=desc, key=key)
            # 返回 True 表示按键发送成功。
            return True
        # 按键异常时兜底，不中断主流程。
        except Exception as exc:
            # 如果识别到连接异常，走统一恢复逻辑并返回失败。
            if self._is_poco_disconnect_error(exc):
                # 统一记录异常并尝试恢复连接。
                self._handle_safe_action_exception("keyevent", desc, exc)
                # 返回 False，避免异常扩散。
                return False
            # 记录按键失败原因。
            self.log.error("按键事件失败，按跳过处理", target=desc, key=key, error=str(exc))
            # 返回 False 表示按键失败。
            return False

    # 定义“清空 Facebook 失败原因缓存”的方法。
    def _reset_facebook_error_reason(self) -> None:
        # 把失败原因重置为空字符串，避免串到下一轮任务。
        self.facebook_error_reason = ""

    # 定义“记录 Facebook 失败原因并返回 False”的方法。
    def _facebook_fail(self, reason: str) -> bool:
        # 标准化失败原因字符串，避免空值落库不可读。
        safe_reason = str(reason or "").strip()
        # 当调用方传空原因时，回退统一文案。
        if safe_reason == "":
            # 使用兜底错误文案。
            safe_reason = "Facebook 注册失败：未知原因"
        # 保存失败原因，供 run_once 统一写入 t_user.msg。
        self.facebook_error_reason = safe_reason
        # 记录错误日志，确保失败链路可追踪。
        self.log.error("Facebook 注册流程失败", reason=safe_reason, user_email=self.user_email)
        # 返回 False，便于调用方直接 `return self._facebook_fail(...)`。
        return False

    # 定义“格式化异常文本”的方法，供 msg 字段落库复用。
    def _build_failure_msg(self, exc: Exception, prefix: str = "") -> str:
        # 提取异常类型名，提升可读性。
        exc_type = type(exc).__name__
        # 提取异常明细文本。
        exc_detail = str(exc).strip()
        # 当异常文本为空时回退为类型名。
        if exc_detail == "":
            # 用类型名作为兜底详情。
            exc_detail = exc_type
        # 组装“前缀 + 类型 + 详情”格式文本。
        base_message = f"{prefix} | {exc_type}: {exc_detail}" if prefix else f"{exc_type}: {exc_detail}"
        # 控制 msg 长度，避免异常文本过长影响列表查看。
        return base_message[:300]

    # 定义“回写 Facebook 结果到 t_user”的方法。
    def _update_fb_result_to_db(self, success: bool, reason: str = "") -> None:
        # 邮箱为空时无法按账号更新，直接记录错误并返回。
        if self.user_email == "":
            # 记录无法更新的根因。
            self.log.error("更新 t_user 失败：email_account 为空", success=success)
            # 直接返回，避免无意义 SQL。
            return
        # 成功时账号状态写 2（已完成）。
        target_status = 2 if success else 3
        # 成功时 Facebook 状态写 1，失败写 0。
        target_fb_status = 1 if success else 0
        # 成功时清空 msg，失败时写入具体错误原因。
        target_msg = "" if success else str(reason or "Facebook 注册失败：未知原因").strip()
        # 控制 msg 长度，避免写入过长异常字符串。
        target_msg = target_msg[:300]
        # 使用异常保护数据库更新，确保任务流程不崩溃。
        try:
            # 执行按邮箱更新状态（status/fb_status/msg）。
            affected_rows = self.user_db.update_status(
                # 目标邮箱账号。
                email_account=self.user_email,
                # 目标账号状态。
                status=target_status,
                # 目标 Facebook 注册状态。
                fb_status=target_fb_status,
                # 目标备注信息。
                msg=target_msg,
            )
            # 记录落库结果，便于后续排查是否命中记录。
            self.log.info(
                "Facebook 结果已回写 t_user",
                email_account=self.user_email,
                status=target_status,
                fb_status=target_fb_status,
                msg=target_msg,
                affected_rows=affected_rows,
            )
        # 捕获数据库更新异常并记录，不向外抛出。
        except Exception as exc:
            # 记录完整异常栈，便于定位 DB 层问题。
            self.log.exception(
                "回写 Facebook 结果到 t_user 失败",
                email_account=self.user_email,
                status=target_status,
                fb_status=target_fb_status,
                msg=target_msg,
                error=str(exc),
            )

    # 定义“按轮询查找并点击”的通用方法，支持传入 Poco 节点列表。
    def poco_find_or_click(
        self,
        nodes: list[Any],
        desc: str,
        sleep_interval: float | None = None,
    ) -> bool:
        # 当调用方未传节点时直接返回失败。
        if not nodes:
            # 记录参数错误日志，方便排查调用点问题。
            self.log.error("poco_find_or_click 未传入节点", target=desc)
            # 返回 False 表示本次调用失败。
            return False

        # 解析总超时秒数：未传时默认最多等待 5 秒。
        timeout_sec = 5.0 if sleep_interval is None else float(sleep_interval)
        # 兜底修正非法超时值，避免负数造成死循环。
        if timeout_sec < 0:
            # 负数超时重置为 0。
            timeout_sec = 0.0
        # 记录轮询开始时间，后续计算总耗时与剩余时间。
        started_at = time.monotonic()
        # 计算本次轮询截止时间点。
        deadline_at = started_at + timeout_sec
        # 初始化轮询计数器，便于日志排查。
        attempt = 0

        # 在超时前持续按 1 秒间隔轮询。
        while True:
            # 进入新一轮轮询时递增计数。
            attempt += 1
            # 逐个遍历传入的候选节点。
            for node_index, node in enumerate(nodes):
                # 使用异常保护 exists 查询，避免查询异常导致流程中断。
                try:
                    # 当前节点存在时尝试立即点击。
                    if bool(node.exists()):
                        # 调用统一安全点击方法，命中后直接返回。
                        if self._safe_click(node, f"{desc}-候选{node_index}", sleep_interval=None):
                            # 计算当前总耗时毫秒，包含查询与轮询等待。
                            elapsed_ms = int((time.monotonic() - started_at) * 1000)
                            # 记录命中日志，包含命中轮次和节点索引。
                            self.log.info(
                                "poco_find_or_click 命中并点击成功",
                                target=desc,
                                timeout_sec=timeout_sec,
                                attempt=attempt,
                                elapsed_ms=elapsed_ms,
                                node_index=node_index,
                            )
                            # 点击成功后立即返回 True。
                            return True
                # 捕获 exists 查询异常并统一处理。
                except Exception as exc:
                    # 记录异常并尝试恢复 Poco 连接。
                    self._handle_safe_action_exception("poco_find_or_click", f"{desc}-候选{node_index}", exc)
            # 计算当前距离截止时间的剩余秒数。
            remaining_sec = deadline_at - time.monotonic()
            # 超时后退出轮询循环。
            if remaining_sec <= 0:
                break
            # 每次最多等待 1 秒，确保“每秒查一次”且不超过总超时。
            sleep(min(1.0, remaining_sec))
        # 计算最终总耗时毫秒，包含查询与等待时间。
        elapsed_ms = int((time.monotonic() - started_at) * 1000)
        # 所有轮次都未命中时记录失败日志。
        self.log.error(
            "poco_find_or_click 未命中",
            target=desc,
            timeout_sec=timeout_sec,
            attempt=attempt,
            elapsed_ms=elapsed_ms,
            candidates=len(nodes),
        )
        # 返回 False 表示未找到可点击节点。
        return False

    # 定义单次循环逻辑，封装每轮清理动作。
    def mojiwang_run_one_loop(self, loop_index: int) -> None:
        sleep(1)
        # 从当前任务实例中拿到可用的 Poco 对象。
        poco = self._require_poco()
        # 把从 0 开始的索引转换成人类可读的轮次编号。
        round_no = loop_index + 1
        # 记录循环开始日志。
        self.log.info("开始执行清理循环", round_no=round_no, total_rounds=self.mojiwang_loop_count)
        # 定位“清理按钮”控件节点。
        wipe_button = poco(self.mojiwang_wipe_button_id)
        # 如果 5 秒内都没点到清理按钮。
        if not self._wait_and_click_node(wipe_button, f"清理按钮-第{round_no}轮"):
            # 记录跳过日志并结束本轮。
            self.log.error("未找到清理按钮，跳过本轮", round_no=round_no)
            # 直接返回，避免继续找“任务结束提示”。
            return

        # 中文模式：按 ID + 文本定位。
        done_msg = poco(self.mojiwang_done_msg_id, text=self.mojiwang_done_msg_text)

        # 若在超时前成功点击“任务结束提示”。
        if self._wait_and_click_node(done_msg, f"任务结束返回提示-第{round_no}轮"):
            # 记录成功日志。
            self.log.info("已点击任务结束返回提示", round_no=round_no)
            # 点击成功后结束本轮。
            return
        # 若没出现则记录警告，继续下一轮。
        self.log.error("未出现任务结束返回提示", round_no=round_no)
        
    # 定义“抹机王全部循环动作”的方法。
    def mojiwang_run_all(self) -> None:
        # 短暂等待 1 秒，让系统完成进程状态切换。
        sleep(1)
        # 重新启动插件应用，进入待操作页面。
        start_app(self.mojiwang_packge)
        # 记录插件应用启动成功。
        self.log.info("已启动应用,循环次数", package=self.mojiwang_packge, num=self.mojiwang_loop_count)
        # 按设定次数循环执行清理流程。
        for loop_index in range(self.mojiwang_loop_count):
            # 短暂等待 1 秒
            sleep(1)
            # 调用单轮方法执行“清理并返回”动作。
            self.mojiwang_run_one_loop(loop_index)

        # 等待操作完
        sleep(3)
        # 全部循环结束后停止插件应用。
        stop_app(self.mojiwang_packge)
        # 记录任务结束日志。
        self.log.info("任务结束，已停止应用", package=self.mojiwang_packge)

    # 定义 Nekobox 全流程方法（带 defer 风格收尾）。
    def nekobox_run_all(self, mode_index: int) -> None:
        """
        :param mode_index: 0=动态，1=移动
        """
        # 从当前任务实例中拿到可用的 Poco 对象。
        poco = self._require_poco()
        # 稍等 1 秒，避免紧接上一步操作导致界面状态不稳定。
        sleep(1)
        # 启动 Nekobox 应用。
        start_app(self.nekobox_package)
        # 记录启动成功日志。
        self.log.info("已启动应用", package=self.nekobox_package)
        # 用 try/finally 模拟 Go defer：主流程在 try，收尾放 finally。
        try:
            # 等待页面加载完成，避免节点还没出现就查找。
            sleep(1)
            # 定位顶部分组容器的直接子项。
            parent = poco("moe.nb4a:id/group_tab").child("android.widget.LinearLayout")
            # 先安全等待父节点出现，避免直接 exists/click 触发连接异常中断。
            if not self._safe_wait_exists(parent, 3, "Nekobox 模式选择父节点"):
                # 记录错误日志。
                self.log.error("未找到 Nekobox 模式选择父节点，无法继续", package=self.nekobox_package)
                # 本轮提前结束，finally 仍会执行收尾。
                return
            # 取到 group_tab 下一层所有可点击子节点（订阅/移动等）。
            tab_children = parent.children()
            # 至少需要两个分组节点才满足后续点击。
            if len(tab_children) < 2:
                # 记录错误日志。
                self.log.error("Nekobox 订阅和代理找不到,至少 2 个分组，订阅放第一个，移动和动态放第二个分组", package=self.nekobox_package)
                # 本轮提前结束，finally 仍会执行收尾。
                return
            # 点击第二个分组（索引从 0 开始，1 表示第二个）。
            if not self._safe_click(tab_children[1], "Nekobox 第二分组", sleep_interval=1):
                # 点击失败时记录错误并结束本轮，避免后续链路连锁失败。
                self.log.error("点击 Nekobox 第二分组失败，结束本轮", package=self.nekobox_package)
                # 本轮提前结束，finally 仍会执行收尾。
                return
            # 定位配置列表容器。
            parent = poco("android.widget.FrameLayout").child("android.widget.LinearLayout").offspring("moe.nb4a:id/fragment_holder").offspring("moe.nb4a:id/configuration_list").child("moe.nb4a:id/content")
            # 安全等待配置列表父节点，避免连接波动时直接崩溃。
            if not self._safe_wait_exists(parent, 3, "Nekobox 配置列表父节点"):
                # 记录错误日志。
                self.log.error("未找到 Nekobox 配置列表父节点，无法继续", package=self.nekobox_package)
                # 本轮提前结束，finally 仍会执行收尾。
                return
            # 取配置列表下一层的模式节点集合。
            mode_children = parent.children()
            # 校验入参索引不越界（支持 0/1 或更多模式）。
            if len(mode_children) <= mode_index:
                # 记录越界错误日志。
                self.log.error("Nekobox 模式索引越界", package=self.nekobox_package, mode_index=mode_index, total=len(mode_children))
                # 本轮提前结束，finally 仍会执行收尾。
                return
            # 按入参索引点击目标模式节点。
            if not self._safe_click(mode_children[mode_index], f"Nekobox 模式节点-{mode_index}", sleep_interval=1):
                # 点击失败时记录错误并结束本轮。
                self.log.error("点击 Nekobox 模式节点失败，结束本轮", package=self.nekobox_package, mode_index=mode_index)
                # 本轮提前结束，finally 仍会执行收尾。
                return
            # 判断 stats 节点是否存在。
            start_button_node = poco("android.widget.FrameLayout").child("android.widget.LinearLayout").offspring("moe.nb4a:id/stats")
            # 使用安全等待判断代理是否已经启动。
            start_button_bool = self._safe_wait_exists(start_button_node, 1.5, "Nekobox 运行状态节点")
            # stats 存在时认为代理已在运行。
            if start_button_bool:
                # 记录已运行状态。
                self.log.info("代理已经启动了", package=self.nekobox_package)
            # stats 不存在时尝试点击启动按钮。
            else:
                # 记录准备启动日志。
                self.log.info("代理未启动，正在启动", package=self.nekobox_package)
                # 先定位启动按钮节点，避免重复查询。
                fab = poco("moe.nb4a:id/fab")
                # 按钮存在才执行点击。
                if self._safe_wait_exists(fab, 2, "Nekobox 启动按钮"):
                    # 点击启动代理按钮。
                    self._safe_click(fab, "Nekobox 启动按钮", sleep_interval=0.5)
                # 启动按钮不存在时记录警告。
                else:
                    # 记录按钮缺失日志。
                    self.log.error("未找到代理启动按钮", package=self.nekobox_package)
            # 预留观察/生效等待时间，后续可按需要调整。
            sleep(2)
        # 无论 try 内成功、return 或抛异常，都会执行这里。
        finally:
            # 强制停止 Nekobox，保证流程收尾一致。
            # stop_app(self.nekobox_package)
            home()
            # 记录收尾停止日志。
            # self.log.info("任务结束，已停止应用", package=self.nekobox_package)

    # 定义“获取 Facebook 验证码”的复用方法（带重试）。
    def _fetch_facebook_code(self, retry_times: int = 3, wait_seconds: int = 25) -> str | None:
        # 校验 client_id 是否存在，缺失时直接返回失败。
        if not self.user_info.get("client_id"):
            # 记录 client_id 缺失错误。
            self.log.error("client_id 为空，无法获取验证码", user_email=self.user_email)
            # 记录失败原因，供外层写入 t_user.msg。
            self._facebook_fail("client_id 为空，无法获取验证码")
            # 返回空值表示获取失败。
            return None

        # 校验 email_access_key 是否存在，缺失时直接返回失败。
        if not self.user_info.get("email_access_key"):
            # 记录 email_access_key 缺失错误。
            self.log.error("email_access_key 为空，无法获取验证码", user_email=self.user_email)
            # 记录失败原因，供外层写入 t_user.msg。
            self._facebook_fail("email_access_key 为空，无法获取验证码")
            # 返回空值表示获取失败。
            return None

        # 初始化成功标记，默认失败。
        ok = False
        # 初始化验证码变量，默认空。
        fb_code = None
        # 按重试次数循环拉取验证码。
        for attempt in range(retry_times):
            # 每次重试前等待固定秒数，给邮件系统同步时间。
            sleep(wait_seconds)
            # 使用异常保护邮箱验证码拉取，避免接口异常导致流程崩溃。
            try:
                # 调用邮箱接口拉取验证码。
                ok, fb_code = getfackbook_code(
                    # 传入当前账号 client_id。
                    client_id=self.user_info["client_id"],
                    # 传入当前账号邮箱。
                    email_name=self.user_email,
                    # 传入当前账号 refresh_token。
                    refresh_token=self.user_info["email_access_key"],
                )
            # 捕获接口异常并按失败处理。
            except Exception as exc:
                # 记录接口异常日志。
                self.log.exception("获取验证码接口异常", user_email=self.user_email, attempt=attempt + 1, error=str(exc))
                # 当前轮次按失败处理。
                ok, fb_code = False, None
            # 当拉取成功且验证码非空时结束重试。
            if ok and fb_code:
                # 记录本次命中重试轮次。
                self.log.info("获取验证码成功", attempt=attempt + 1, retry_times=retry_times)
                # 退出重试循环。
                break
            # 记录当前轮拉取失败日志。
            self.log.warning("获取验证码失败，准备重试", attempt=attempt + 1, retry_times=retry_times)

        # 当最终仍失败时返回空。
        if not ok or not fb_code:
            # 记录最终失败日志。
            self.log.error("获取验证码失败，无法继续", user_email=self.user_email)
            # 记录失败原因，供外层写入 t_user.msg。
            self._facebook_fail("获取验证码失败：邮箱未收到验证码或解析失败")
            # 返回空值表示失败。
            return None

        # 返回验证码字符串给调用方复用。
        return str(fb_code)

    # 定义 Facebook 全流程方法，包含节点查询和点击的安全兜底。
    def facebook_run_all(self) -> bool:
        # 重置本轮 Facebook 失败原因，避免串到历史失败信息。
        self._reset_facebook_error_reason()
        # 稍等 1 秒，避免紧接上一步导致页面状态不稳定。
        sleep(1)
        # 先清理相关应用状态，保证流程从干净环境开始。 调试
        # self.clear_all()
        # 获取当前任务实例中的 Poco 对象。
        poco = self._require_poco()
        # 启动 Facebook 应用。
        start_app(self.facebook_package)
        # 记录启动成功日志。
        self.log.info("已启动应用", package=self.facebook_package)
        # 按设备语言读取“开始按钮”文案。
        start_desc = FACEBOOK_START_UP.get(self.device_lang)
        # 如果当前语言没有配置启动文案。
        if not start_desc:
            # 记录跳过原因。
            self.log.info("当前语言不支持 Facebook 自动化操作，跳过", device_lang=self.device_lang)
            # 返回失败并记录具体错误原因。
            return self._facebook_fail(f"当前语言不支持 Facebook 自动化操作: {self.device_lang}")
        # 初始化“创建账号候选按钮”列表（兼容 v1/v2 文案）。
        create_user_nodes: list[Any] = []
        # 读取 v1 按钮文案并清理空白字符。
        create_user_text_v1 = str(FACEBOOK_CREATE_USER_BUTTON.get(self.device_lang, "")).strip()
        # v1 文案非空时加入候选列表。
        if create_user_text_v1:
            create_user_nodes.append(poco(text=create_user_text_v1))
        # 读取 v2 按钮文案并清理空白字符。
        create_user_text_v2 = str(FACEBOOK_CREATE_USER_BUTTONV2.get(self.device_lang, "")).strip()
        # v2 文案非空时加入候选列表。
        if create_user_text_v2:
            create_user_nodes.append(poco(text=create_user_text_v2))

        # 记录是否已经进入“创建账号”分支。
        entered_create_user_flow = False
        # 候选按钮列表非空时执行 or 逻辑查找点击。
        if create_user_nodes:
            # 最多等待 30 秒，命中任一按钮就点击并返回 True。
            entered_create_user_flow = self.poco_find_or_click(
                nodes=create_user_nodes,
                desc="Create New Facebook Account 按钮(v1/v2)",
                sleep_interval=30,
            )
        # 候选按钮列表为空时记录提示。
        else:
            # 记录当前语言未配置 v1/v2 文案。
            self.log.error("创建账号按钮文案为空，跳过 v1/v2 匹配", device_lang=self.device_lang)
            # 返回失败并记录具体错误原因。
            return self._facebook_fail("创建账号按钮文案为空（v1/v2 均未配置）")

        # 命中创建账号分支后继续执行下一页流程。
        if entered_create_user_flow:
            # 某些机型点了 v2 后还会出现一次创建账号按钮，这里做一次短时二次确认点击。
            # self.poco_find_or_click(
            #     nodes=create_user_nodes,
            #     desc="Create New Facebook Account 按钮二次确认(v1/v2)",
            #     sleep_interval=3,
            # )
            # 定位“创建账号第 2 页”按钮。
            create_user_page2_node = poco(FACEBOOK_CREATE_USER_BUTTON_PAGE2[self.device_lang])
            # 等待第 2 页按钮出现。
            if not self._safe_wait_exists(create_user_page2_node, 35, "Create New Facebook Account 按钮2"):
                # 返回失败并记录具体错误原因。
                return self._facebook_fail("未找到 Create New Facebook Account 按钮2")
            # 点击第 2 页按钮。
            self._safe_click(create_user_page2_node, "Create New Facebook Account 按钮2", sleep_interval=2)
        # 未命中创建账号按钮时走启动按钮分支。
        else:
            # 定位“Get started / Démarrer”按钮节点。
            start_node = poco(text=start_desc)
            # 安全等待启动按钮出现。
            if self._safe_wait_exists(start_node, 2, "Facebook 启动按钮"):
                # 点击启动按钮并记录日志。
                self._safe_click(start_node, "Facebook 启动按钮")
                # 按钮未出现时记录信息。
            else:
                # 记录跳过启动按钮。
                self.log.info("未找到启动按钮，跳过点击", start_desc=start_desc)



        # 定位系统权限允许按钮。
        allow_button = poco("com.android.permissioncontroller:id/permission_allow_button")
        # 安全等待权限按钮。
        if self._safe_wait_exists(allow_button, 2, "系统权限允许按钮"):
            # 点击权限按钮后等待 1 秒。
            self._safe_click(allow_button, "系统权限允许按钮", sleep_interval=1)
        # 给页面一个短暂缓冲，确保你手动或前序动作已把焦点放到 first name。
        sleep(1)
        # 如果 first name 为空或缺失。
        if not self.user_first_name:
            # 记录错误日志，包含账号信息
            self.log.error("First name 为空，无法输入", user_email=self.user_email)
            # 返回失败并记录具体错误原因。
            return self._facebook_fail("First name 为空，无法输入")

        # 直接向当前焦点输入 first name（不依赖节点）。
        if not self._safe_input_on_focused(self.user_first_name, "First name-当前焦点"):
            # 记录失败并结束流程。
            self.log.info("First name 焦点输入失败，跳过后续操作")
            # 输入失败时返回失败并记录原因。
            return self._facebook_fail("First name 焦点输入失败")
        # 读取当前语言的 last name 占位文案，用于点击聚焦输入框。
        last_name_desc = FACEBOOK_LAST_NAME_INPUT.get(self.device_lang)
        
        # 聚焦 Last name 输入框
        # 记录是否已成功把焦点切到 last name 输入框。
        focused_last_name = False
        # 只有配置了文案才尝试节点点击聚焦。
        if last_name_desc:
            # 根据占位文案定位 last name 区域节点。
            last_name_node = poco(text=last_name_desc)
            # 等待 last name 节点出现。
            if self._safe_wait_exists(last_name_node, 2, "Last name 输入框节点"):
                # 先点击 last name 节点聚焦。
                if self._safe_click(last_name_node, "Last name 输入框-点击聚焦", sleep_interval=0.6):
                    # 标记聚焦成功。
                    focused_last_name = True

        # 如果还没成功聚焦 last name。
        if not focused_last_name:
            # 记录尝试按键切换。
            self.log.error("Last name 输入框节点不可点击，尝试按键切换聚焦")
            # 返回失败并记录具体错误原因。
            return self._facebook_fail("Last name 输入框节点不可点击")

        # 无论哪种聚焦方式都额外等待一会儿，确保焦点稳定后再输入。
        sleep(0.8)
        # 如果 last name 为空或缺失。
        if not self.user_last_name:
            # 记录错误日志，包含账号信息
            self.log.error("Last name 为空，无法输入", user_email=self.user_email)
            # 返回失败并记录具体错误原因。
            return self._facebook_fail("Last name 为空，无法输入")
        # 继续向当前焦点输入 last name（不依赖节点）。
        if not self._safe_input_on_focused(self.user_last_name, "Last name-当前焦点"):
            # 记录失败并结束流程。
            self.log.info("Last name 焦点输入失败，结束本轮输入")
            # 输入失败时返回失败并记录原因。
            return self._facebook_fail("Last name 焦点输入失败")
        # 输入完成后稍等，确保输入事件处理完毕
        sleep(0.5)




        # 根据占位文案定位 last name 区域节点。
        next_node = poco(text=FACEBOOK_FIRST_LAST_NAME_NEXT[self.device_lang])
        # 等待 last name 节点出现。
        if not self._safe_wait_exists(next_node, 1, "next输入点"):
            # 返回失败并记录具体错误原因。
            return self._facebook_fail("未找到 next 输入点")

        # 先点击 last name 节点聚焦
        self._safe_click(next_node, "next输入点点击", sleep_interval=2)

        if  self._safe_wait_exists(poco(text=FACEBOOK_FIRST_LAST_NAME_NEXT[self.device_lang]), 2, "输入名字后继续找到 next 说明需要确认名称了"):
            if not self._safe_click_facebook_next_v2_deep(poco):
                # 返回失败并记录具体错误原因。
                return self._facebook_fail("未找到 next 输入点v2（深层路径）或点击失败")



        year = datetime.now().year

        # 根据占位文案定位 last name 区域节点
        year_node = poco(text=str(year))
        # 等待 last name 节点出现。
        if not self._safe_wait_exists(year_node, 5, "year输入点:" + str(year)):
            # 返回失败并记录具体错误原因。
            return self._facebook_fail(f"未找到年份输入点: {year}")
        # 先点击 last name 节点聚焦
        self._safe_click(year_node, "year输入点点击", sleep_interval=2)


        # 继续向当前焦点输入 last name（不依赖节点）。
        if not self._safe_input_on_focused("1996", "年份",True):
            # 输入失败时返回失败并记录原因。
            return self._facebook_fail("年份输入失败")

        # 先点击 last name 节点聚焦
        self._safe_click(poco(text=FACEBOOK_YEAR_SET[self.device_lang]), "年份 set 点击", sleep_interval=2)

        self._safe_click(poco(text=FACEBOOK_FIRST_LAST_NAME_NEXT[self.device_lang]), "年份 set后下一页", sleep_interval=4)  #


        # 根据占位文案定位 男性 输入节点
        gender_node = poco(text=FACEBOOK_GENDER_MALE[self.device_lang])
        # 等待 男性 输入节点 出现。
        if not self._safe_wait_exists(gender_node, 2, "性别找不到"):
            # 返回失败并记录具体错误原因。
            return self._facebook_fail("未找到性别选择节点（男性）")

        # 点击 男性 输入节点 聚焦并选择
        self._safe_click(gender_node, "性别-男性-点击", sleep_interval=2)


        self._safe_click(poco(text=FACEBOOK_FIRST_LAST_NAME_NEXT[self.device_lang]), "设置性别后下一页", sleep_interval=2)


        email_node = poco(text=FACEBOOK_SELECT_EMAIL_SIGN_UP[self.device_lang])
        # 等待选择邮箱注册按钮出现。
        if not self._safe_wait_exists(email_node, 30, "选择邮箱注册按钮"):
            # 返回失败并记录具体错误原因。
            return self._facebook_fail("未找到选择邮箱注册按钮")
        # 点击选择邮箱注册按钮
        self._safe_click(email_node, "选择邮箱注册按钮", sleep_interval=2)
        # 定位邮箱输入框
        email_input_node = poco(text=FACEBOOK_EMAIL_INPUT[self.device_lang])
        # 等待邮箱输入框出现。
        if not self._safe_wait_exists(email_input_node, 4, "邮箱输入框"):
            # 记录错误日志，包含账号信息
            self.log.error("邮箱输入框未出现，无法继续输入", user_email=self.user_email)
            # 返回失败并记录具体错误原因。
            return self._facebook_fail("邮箱输入框未出现")

        # 点击邮箱输入框聚焦
        self._safe_click(email_input_node,"邮箱输入框-点击聚焦", sleep_interval=1)

        # 向当前焦点输入邮箱地址。
        if not self._safe_input_on_focused(self.user_email, "邮箱输入框-当前焦点",True):
            # 输入失败时返回失败并记录原因。
            return self._facebook_fail("邮箱输入失败")


        self._safe_click(poco(text=FACEBOOK_FIRST_LAST_NAME_NEXT[self.device_lang]), "提交邮箱下一页", sleep_interval=2)


        # 定位密码输入框
        facebook_input_password_node = poco(text=FACEBOOK_INPUT_PASSWORD[self.device_lang])
        # 等待密码输入框出现。
        if not self._safe_wait_exists(facebook_input_password_node, 7, "密码输入框"):
            # 记录错误日志，包含账号信息
            self.log.error("密码输入框未出现，无法继续输入", user_email=self.user_email)
            # 返回失败并记录具体错误原因。
            return self._facebook_fail("密码输入框未出现")

        # 点击密码输入框聚焦
        self._safe_click(facebook_input_password_node,"密码输入框-点击聚焦", sleep_interval=1)
        # 向当前焦点输入密码。
        if not self._safe_input_on_focused(self.pwd, "密码输入框-当前焦点",True):
            # 输入失败时返回失败并记录原因。
            return self._facebook_fail("密码输入失败")

        self._safe_click(poco(text=FACEBOOK_FIRST_LAST_NAME_NEXT[self.device_lang]), "提交密码下一页", sleep_interval=2)

        # 先判断接受按钮防止等待太久
        access_node = poco(text=FACEBOOK_FINAL_CREATE_USER_BUTTON[self.device_lang])

        if not self._safe_wait_exists(access_node, 7, "创建接受账号按钮v0"):
            # 这块有个弹框稍后处理
            facebook_later_node = poco(text=FACEBOOK_LATER_BUTTON[self.device_lang])
            if  self._safe_wait_exists(facebook_later_node, 20, "稍后按钮0"):
                self._safe_click(facebook_later_node, "稍后按钮0", sleep_interval=2)

            # 确认最后信息

            access_node = poco(text=FACEBOOK_FINAL_CREATE_USER_BUTTON[self.device_lang])
            if not self._safe_wait_exists(access_node, 5, "创建接受账号按钮"):
                # 返回失败并记录具体错误原因。
                return self._facebook_fail("未找到创建接受账号按钮")

            self._safe_click(access_node, "创建账号按钮", sleep_interval=5)
        else:
            self._safe_click(access_node, "创建账号按钮v0", sleep_interval=5)


        if  self._safe_wait_exists(poco(text=FACEBOOK_REFRESH_FONT_BUTTON[self.device_lang]), 70, "再次刷新按钮"):
            self._safe_click(poco(text=FACEBOOK_REFRESH_FONT_BUTTON[self.device_lang]), "刷新验证码按钮", sleep_interval=3)

        # 初始化验证码缓存变量，供不同分支共用。
        cached_fb_code: str | None = None

        # 这里判断是否注册了了
        # match_reg_node = poco(textMatches=FACEBOOK_IS_REGISTERED_BUTTON[self.device_lang])
        # if  self._safe_wait_exists(match_reg_node, 5, "已注册按钮"):
        #     self._safe_click(match_reg_node, "已注册按钮", sleep_interval=3)
        #
        #     # 继续邮箱登录
        #     if not self._safe_wait_exists(poco(FACEBOOK_CONTINUE_EMAIL_SIGN_UP_BUTTON[self.device_lang]), 5, "选择邮箱登录按钮"):
        #         return
        #
        #     self._safe_click(poco(FACEBOOK_CONTINUE_EMAIL_SIGN_UP_BUTTON[self.device_lang]), "选择邮箱登录按钮", sleep_interval=2)
        #
        #     # 已注册的聚焦验证码
        #     if not self._safe_wait_exists(poco(FACEBOOK_FOCUS_EMAIL_CODE_INPUT[self.device_lang]), 15, "验证码输入框-已注册"):
        #         return
        #
        #     self._safe_click(poco(FACEBOOK_FOCUS_EMAIL_CODE_INPUT[self.device_lang]), "验证码输入框-已注册-点击聚焦", sleep_interval=2)
        #
        #     # 在已注册分支先拉取验证码，后续步骤可直接复用。
        #     cached_fb_code = self._fetch_facebook_code()
        #     # 拉取失败时结束当前流程。
        #     if not cached_fb_code:
        #         return
        #
        #
        #     if not self._safe_input_on_focused(cached_fb_code, "输入 fb code-注册的",False):
        #     # 输入失败时结束流程，避免误操作。
        #         return
        #
        #     sleep(1)
        #     # 继续邮箱登录
        #     if not self._safe_wait_exists(poco(FACEBOOK_CONTINUE_EMAIL_SIGN_UP_BUTTON[self.device_lang]), 5, "继续选择邮箱登录按钮V2"):
        #         return
        #
        #     self._safe_click(poco(FACEBOOK_CONTINUE_EMAIL_SIGN_UP_BUTTON[self.device_lang]), "继续选择邮箱登录按钮V2", sleep_interval=2)
        #     return





        if  self._safe_wait_exists(poco(text=FACEBOOK_REFRESH_FONT_BUTTON[self.device_lang]), 5, "再次刷新按钮v2"):
            self._safe_click(poco(text=FACEBOOK_REFRESH_FONT_BUTTON[self.device_lang]), "刷新验证码按钮v2", sleep_interval=3)

        # 验证码输入
        email_node = poco(text=FACEBOOK_EMAIL_CODE_INPUT[self.device_lang])
        if not self._safe_wait_exists(email_node, 15, "验证码输入框"):
            # 返回失败并记录具体错误原因。
            return self._facebook_fail("未找到验证码输入框")

        self._safe_click(email_node, "验证码输入框-点击聚焦", sleep_interval=1)

        # 如果当前分支还没有缓存验证码，则走统一获取方法。
        if not cached_fb_code:
            # 调用复用方法拉取验证码。
            cached_fb_code = self._fetch_facebook_code()
        # 拉取失败时结束流程。
        if not cached_fb_code:
            # 返回失败并记录具体错误原因。
            return self._facebook_fail("获取验证码失败")

        if not self._safe_input_on_focused(cached_fb_code, "输入 fb code",False):
            # 输入失败时返回失败并记录原因。
            return self._facebook_fail("输入验证码失败")



        self._safe_click(poco(text=FACEBOOK_FIRST_LAST_NAME_NEXT[self.device_lang]), "提交验证码确认", sleep_interval=3)

        # 进入“忽略/稍后/下一步”连续处理循环。
        for i in range(10):
            # 第 0 轮给更长等待时间，后续轮次使用常规等待时间。
            current_sleep_interval = 10 if i == 0 else 5
            # 每轮按候选顺序尝试：命中任一节点就点击，并进入下一轮。
            matched = self.poco_find_or_click(
                nodes=[
                    poco(text=FACEBOOK_IGNORE_BUTTON[self.device_lang]),
                    poco(text=FACEBOOK_LATER_BUTTON[self.device_lang]),
                    poco(text=FACEBOOK_POPUP_IGNORE_BUTTON[self.device_lang]),
                    poco(text=FACEBOOK_FIRST_LAST_NAME_NEXT[self.device_lang]),
                    poco(text=FACEBOOK_CONTINUE_EMAIL_SIGN_UP_BUTTON[self.device_lang]),
                ],
                desc=f"忽略链路候选all-{i}",
                sleep_interval=current_sleep_interval,
            )
            # 当前轮一个都没命中时，结束忽略链路循环。
            if not matched:
                break




        allow_button = poco("com.android.permissioncontroller:id/permission_allow_button")
    # 安全等待权限按钮。
        if self._safe_wait_exists(allow_button, 10, "系统权限允许按钮v2"):
        # 点击权限按钮后等待 1 秒。
            self._safe_click(allow_button, "系统权限允许按钮", sleep_interval=2)


        # 执行头像相册随机选图逻辑（跳过索引 0，随机范围 1..min(9, x)）。
        if not self.facebook_select_img():
            # 返回失败并记录具体错误原因（优先复用选图方法内已设置原因）。
            return self._facebook_fail(self.facebook_error_reason or "头像相册随机选图失败")



        # 循环 5 次，处理“下一步 + 忽略”弹层。
        for i in range(10):
            # 每轮先尝试点击“上传了图片下一步了”按钮：每 1 秒查一次，最多 5 次。
            sleep_interval = 20 if i == 0 else 3
            if not self.poco_find_or_click(
                nodes=[poco(text=FACEBOOK_FIRST_LAST_NAME_NEXT[self.device_lang]),poco(text=FACEBOOK_IGNORE_BUTTON[self.device_lang]),poco(text=FACEBOOK_FINAL_CONFIRM_BUTTON[self.device_lang]),poco(text=FACEBOOK_FINAL_CONFIRM_BUTTONV2[self.device_lang])],
                desc=f"上传了图片下一步了-{i}",
                sleep_interval=sleep_interval,
            ):
                break

        # 走到这里表示 Facebook 主流程已完成关键步骤。
        return True





    # 定义“Facebook 头像相册随机选图”的方法。
    def facebook_select_img(self) -> bool:
        # 获取当前任务实例中的 Poco 对象。
        poco = self._require_poco()
        # 用 try/except 保护整个选图流程，确保异常可追踪。
        try:

            # 接受所有 cookie
            cookie_button = poco(text=FACEBOOK_ACCEPT_ALL_COOKIE_BUTTON[self.device_lang])
            if self._safe_wait_exists(cookie_button, 5, "接受 cookie 按钮"):
                self._safe_click(cookie_button, "接受 cookie 按钮", sleep_interval=5)


            menu_tab_node = poco(desc=FACEBOOK_MENU_TAB_DESC[self.device_lang])
            if not self._safe_wait_exists(menu_tab_node,5,"三条杆菜单"):
                # 返回失败并记录具体错误原因。
                return self._facebook_fail("未找到 Facebook 三条杆菜单入口")

            self._safe_click(menu_tab_node, "三条杆菜单", sleep_interval=5)

            # 查找头像
            avatar_node = poco(FACEBOOK_PROFILE_PHOTO_BUTTON[self.device_lang])
            if not self._safe_wait_exists(avatar_node, 5, "首页头像按钮"):
                # 返回失败并记录具体错误原因。
                return self._facebook_fail("未找到首页头像按钮")

            self._safe_click(avatar_node, "首页头像按钮", sleep_interval=3)

            # 这里可能弹出忽略按钮和添加 photo 按钮

            # 初始化“是否已通过弹框直接进入相册页面”的标记。
            opened_album_directly = False
            # 定位“添加图片”弹框按钮节点。
            facebook_add_photo_popup_node = poco(text=FACEBOOK_ADD_PHOTO_POPUP[self.device_lang])
            # 如果弹框按钮出现，则点击后直接进入相册授权流程。
            if self._safe_wait_exists(facebook_add_photo_popup_node, 5, "弹框跳转添加图片"):
                self._safe_click(facebook_add_photo_popup_node, "弹框跳转添加图片", sleep_interval=2)
                # 标记当前已通过弹框进入相册。
                opened_album_directly = True
                # 记录直达分支日志，方便后续排查页面分支。
                self.log.info("命中添加图片弹框，直接进入相册授权流程")

            # 如果没有命中弹框直达，则走常规头像二级入口流程。
            if not opened_album_directly:
                # 判断有没有忽略，有就排除
                facebook_ignore_button_node = poco(text=FACEBOOK_IGNORE_BUTTON[self.device_lang])
                if self._safe_wait_exists(facebook_ignore_button_node, 3, "头像入口忽略按钮"):
                    # 返回记录
                    pass

                # 定位头像二级入口节点。
                avatar_nodev2 = poco(FACEBOOK_PROFILE_PHOTO_BUTTON_2[self.device_lang])
                # 等待头像二级入口出现。
                if not self._safe_wait_exists(avatar_nodev2, 5, "首页头像按钮v2"):
                    # 返回失败并记录具体错误原因。
                    return self._facebook_fail("未找到首页头像按钮v2")

                # 点击头像二级入口。
                self._safe_click(avatar_nodev2, "首页头像按钮v2", sleep_interval=3)

                # 点了头像后，有个打开相册的按钮。
                facebook_profile_photo_bottom_node = poco(text=FACEBOOK_PROFILE_PHOTO_BOTTOM_BUTTON[self.device_lang])
                # 等待打开底部相册按钮出现。
                if not self._safe_wait_exists(facebook_profile_photo_bottom_node, 5, "打开底部相册找不到"):
                    # 返回失败并记录具体错误原因。
                    return self._facebook_fail("未找到打开底部相册按钮")

                # 点击打开底部相册按钮。
                self._safe_click(facebook_profile_photo_bottom_node, "点击首页头像按钮", sleep_interval=2)

            facebook_album_auth_button_node = poco(text=FACEBOOK_ALBUM_AUTH_BUTTON[self.device_lang])
            if self._safe_wait_exists(facebook_album_auth_button_node, 5, "相册权限授权按钮"):
                self._safe_click(facebook_album_auth_button_node, "相册权限授权按钮", sleep_interval=2)

            if self._safe_wait_exists(poco("android:id/button1"), 3, "系统弹框允许按钮"):
                self._safe_click(poco("android:id/button1"), "系统弹框允许按钮", sleep_interval=2)

            allow_button = poco("com.android.permissioncontroller:id/permission_allow_button")
            # 安全等待权限按钮。
            if self._safe_wait_exists(allow_button, 2, "系统权限允许按钮v3"):
            # 点击权限按钮后等待 1 秒。
                self._safe_click(allow_button, "系统权限允许按钮v3", sleep_interval=2)

            # 查找 Facebook 图库页面内的 GridView 节点。
            grid_nodes = poco("com.facebook.katana:id/(name removed)").offspring("android.widget.GridView")
            # 当没有找到 GridView 时记录错误并返回失败。
            if len(grid_nodes) == 0:
                # 记录节点缺失，便于排查页面结构变化。
                self.log.error("未找到 Facebook 图库 GridView 节点")
                # 返回失败并记录具体错误原因。
                return self._facebook_fail("未找到 Facebook 图库 GridView 节点")
            # 取第一个 GridView 作为图片列表容器。
            grid_view = grid_nodes[0]
            # 读取 GridView 的全部直接子节点。
            all_items = grid_view.children()
            # 计算当前子节点总数。
            total_items = len(all_items)
            # 记录节点统计信息，便于问题回溯。
            self.log.info("Facebook 图库节点统计", total_items=total_items)
            # 当总节点数小于等于 1 时，表示没有可选图片。
            if total_items <= 1:
                # 记录错误信息，说明只有索引 0 这个非图片节点。
                self.log.error("当前 GridView 中除了索引 0 以外没有照片可供选择", total_items=total_items)
                # 返回失败并记录具体错误原因。
                return self._facebook_fail(f"图库可选照片不足：total_items={total_items}")
            # 计算真实图片数量（排除索引 0）。
            photo_count = total_items - 1
            # 计算最大可随机索引（最多为 9）。
            max_random_index = min(9, photo_count)
            # 在 1 到最大可选索引之间随机生成一个索引。
            random_index = random.randint(1, max_random_index)
            # 根据随机索引拿到目标图片节点。
            target_item = all_items[random_index]
            # 记录本次随机范围和命中索引。
            self.log.info(
                "Facebook 随机命中图片索引",
                photo_count=photo_count,
                random_index=random_index,
                selectable_range=f"1..{max_random_index}",
            )
            # 优先直接点击随机命中的图片节点。
            if not self._safe_click(target_item, f"Facebook 随机图片节点-索引{random_index}", sleep_interval=1):
                # 返回失败并记录具体错误原因。
                return self._facebook_fail(f"点击随机图片失败：index={random_index}")


            self.log.info("Facebook 随机图片点击完成", random_index=random_index)

            facebook_confirm_photo_button_node = poco(FACEBOOK_CONFIRM_PHOTO_BUTTON[self.device_lang])
            if  self._safe_wait_exists(facebook_confirm_photo_button_node, 5, "注册确认相片"):
                self._safe_click(facebook_confirm_photo_button_node, "注册确认相片", sleep_interval=2)

            # 返回 True 表示选图成功。
            return True
        # 捕获任意异常并记录堆栈。
        except Exception as exc:
            # 记录异常详情，满足“每个错误需要日志记录”要求。
            self.log.exception("Facebook 选图异常", error=str(exc))
            # 返回失败并记录具体错误原因。
            return self._facebook_fail(self._build_failure_msg(exc, prefix="Facebook 选图异常"))


    # 定义“执行一轮完整任务”的公开方法。
    def run_once(self) -> None:
        # 重置本轮 Facebook 失败原因缓存。
        self._reset_facebook_error_reason()
        # 初始化 Facebook 成功标记，默认失败。
        facebook_ok = False
        # 标记本轮是否需要把异常继续抛出给 worker 做运行时重建。
        should_reraise = False
        # 保存需要继续抛出的原始异常对象。
        reraised_exc: Exception | None = None
        # 使用异常保护整轮任务，避免异常导致进程崩溃。
        try:
            # 获取并校验当前 worker 进程初始化好的 Poco 实例。
            self._require_poco()
            # 记录当前任务感知到的上下文信息。
            self.log.info(
                "任务开始",
                serial=self.device_serial,
                device_locale=self.device_locale,
                device_lang=self.device_lang,
                email_account=self.user_email,
                mojiwang_run_num=self.mojiwang_loop_count,
            )
            # 唤醒设备屏幕，避免黑屏导致后续操作失败。
            wake()
            # 回到系统桌面，保证任务从一致状态开始。
            home()
            # 记录回桌面动作完成。
            self.log.info("已回到桌面")
            # 清理所有业务应用数据。
            self.clear_all()
            # 执行抹机王完整循环动作。
            self.mojiwang_run_all()
            # 执行代理流程（0=动态，1=移动）。
            self.nekobox_run_all(0)
            # 执行 Facebook 全流程，并返回是否成功完成。
            facebook_ok = self.facebook_run_all()
        # 捕获所有异常并转换为可落库的失败原因。
        except Exception as exc:
            # 记录完整异常日志，便于排查真实堆栈。
            self.log.exception("run_once 执行异常", error=str(exc))
            # 生成具体失败原因文本，供写入 t_user.msg。
            self.facebook_error_reason = self._build_failure_msg(exc, prefix="run_once 异常")
            # 标记本轮 Facebook 结果为失败。
            facebook_ok = False
            # 连接类异常让 worker 触发 reinit_runtime，避免任务层吞错后带病继续。
            if self._is_poco_disconnect_error(exc) or isinstance(exc, (BrokenPipeError, ConnectionResetError, TimeoutError, OSError)):
                # 记录将要升级处理的异常类型。
                self.log.warning("检测到运行时连接异常，准备抛给 worker 进行重建", error_type=type(exc).__name__)
                # 打开继续抛出标记。
                should_reraise = True
                # 保存要继续抛出的异常对象。
                reraised_exc = exc
        # 无论是否异常都执行状态回写，保证账号状态有结果。
        finally:
            # Facebook 成功时写入 status=2, fb_status=1。
            if facebook_ok:
                # 回写成功状态并清空 msg。
                self._update_fb_result_to_db(success=True, reason="")
            # Facebook 失败时写入 status=3, fb_status=0, msg=具体错误原因。
            else:
                # 组装最终失败原因（优先使用流程内记录的具体原因）。
                final_reason = str(self.facebook_error_reason or "").strip()
                # 失败原因为空时给出统一兜底文案。
                if final_reason == "":
                    # 使用兜底失败原因，避免 msg 为空。
                    final_reason = "Facebook 注册失败：流程未完成，未命中成功条件"
                # 回写失败状态和详细错误原因。
                self._update_fb_result_to_db(success=False, reason=final_reason)
            # 关闭任务内数据库连接，避免每轮 run_once 产生连接堆积。
            try:
                # 主动关闭当前任务实例持有的 UserDB 连接。
                self.user_db.close()
            # 关闭失败只记日志，不影响主流程。
            except Exception as exc:
                # 记录关闭异常，便于后续排查。
                self.log.exception("关闭任务内 user_db 失败", error=str(exc))
            # 非连接类异常时保留尾部等待；连接类异常由 worker 立即接管恢复。
            if not should_reraise:
                # 任务尾部等待 30 秒，给外部观察或下轮衔接留时间。
                sleep(30)
        # 连接类异常在任务收尾后继续抛出给 worker，触发统一恢复流程。
        if should_reraise and reraised_exc is not None:
            # 继续抛出原始异常，保留完整类型和错误上下文。
            raise reraised_exc


# 保留模块级函数入口，统一通过 task_context 透传设备信息。
def run_once(task_context: TaskContext) -> None:
    # 创建任务类实例并执行一轮完整流程。
    OpenSettingsTask(task_context=task_context).run_once()
