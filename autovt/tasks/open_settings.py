# 导入 Any 类型，方便给 Poco 节点做类型标注。
from typing import Any

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
from autovt.runtime import get_poco
# 导入任务上下文对象，统一承载设备信息。
from autovt.tasks.task_context import TaskContext
from autovt.desc import  *
import json
from datetime import datetime

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
            # 记录异常详情，方便排查。
            self.log.exception("节点查询异常，按不存在处理", target=desc, wait_seconds=wait_seconds, error=str(exc))
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
            # 记录点击失败详情，方便排查。
            self.log.exception("点击失败，按跳过处理", target=desc, error=str(exc))
            # 返回 False 表示点击失败。
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
            # 记录输入失败原因。
            self.log.error("输入事件失败，按跳过处理", target=desc, value=value, error=str(exc))
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
            # 记录 text 失败原因。
            self.log.error("text 输入失败，尝试剪贴板粘贴", target=desc, value=value, error=str(exc))
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
            # 记录按键失败原因。
            self.log.error("按键事件失败，按跳过处理", target=desc, key=key, error=str(exc))
            # 返回 False 表示按键失败。
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
            # 先判断父节点是否存在，避免后面直接报错。
            if not parent.exists():
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
            tab_children[1].click(focus=None, sleep_interval=1)
            # 定位配置列表容器。
            parent = poco("android.widget.FrameLayout").child("android.widget.LinearLayout").offspring("moe.nb4a:id/fragment_holder").offspring("moe.nb4a:id/configuration_list").child("moe.nb4a:id/content")
            # 先判断配置列表父节点是否存在。
            if not parent.exists():
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
            mode_children[mode_index].click(focus=None, sleep_interval=1)
            # 判断 stats 节点是否存在。
            start_button_bool = poco("android.widget.FrameLayout").child("android.widget.LinearLayout").offspring("moe.nb4a:id/stats").exists()
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
                if fab.exists():
                    # 点击启动代理按钮。
                    fab.click()
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

    # 定义 Facebook 全流程方法，包含节点查询和点击的安全兜底。
    def facebook_run_all(self) -> None:
        # 稍等 1 秒，避免紧接上一步导致页面状态不稳定。
        sleep(1)
        # 先清理相关应用状态，保证流程从干净环境开始。 调试
        self.clear_all()
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
            # 直接返回，避免 KeyError 或误操作。
            return


        if self._safe_wait_exists(poco(FACEBOOK_CREATE_USER_BUTTON[self.device_lang]), 30, "Create New Facebook Account 按钮"):
            # 默认分支 1
            self._safe_click(poco(FACEBOOK_CREATE_USER_BUTTON[self.device_lang]), "Create New Facebook Account 按钮", sleep_interval=2)
            if not self._safe_wait_exists(poco(FACEBOOK_CREATE_USER_BUTTON_PAGE2[self.device_lang]), 3, "Create New Facebook Account 按钮2"):
                return
            self._safe_click(poco(FACEBOOK_CREATE_USER_BUTTON_PAGE2[self.device_lang]), "Create New Facebook Account 按钮2", sleep_interval=2)
        else:
            # 默认分支 2
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
            return

        # 直接向当前焦点输入 first name（不依赖节点）。
        if not self._safe_input_on_focused(self.user_first_name, "First name-当前焦点"):
            # 记录失败并结束流程。
            self.log.info("First name 焦点输入失败，跳过后续操作")
            # 输入失败时结束流程，避免后续连锁误输入。
            return
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
            return

        # 无论哪种聚焦方式都额外等待一会儿，确保焦点稳定后再输入。
        sleep(0.8)
        # 如果 last name 为空或缺失。
        if not self.user_last_name:
            # 记录错误日志，包含账号信息
            self.log.error("Last name 为空，无法输入", user_email=self.user_email)
            return
        # 继续向当前焦点输入 last name（不依赖节点）。
        if not self._safe_input_on_focused(self.user_last_name, "Last name-当前焦点"):
            # 记录失败并结束流程。
            self.log.info("Last name 焦点输入失败，结束本轮输入")
            # 输入失败时结束流程。
            return
        # 输入完成后稍等，确保输入事件处理完毕
        sleep(0.5)





        # 根据占位文案定位 last name 区域节点。
        next_node = poco(text=FACEBOOK_FIRST_LAST_NAME_NEXT[self.device_lang])
        # 等待 last name 节点出现。
        if not self._safe_wait_exists(next_node, 1, "next输入点"):
            return

        # 先点击 last name 节点聚焦
        self._safe_click(next_node, "next输入点点击", sleep_interval=2)


        year = datetime.now().year

        # 根据占位文案定位 last name 区域节点
        year_node = poco(text=str(year))
        # 等待 last name 节点出现。
        if not self._safe_wait_exists(year_node, 2, "year输入点"):
            return
        # 先点击 last name 节点聚焦
        self._safe_click(year_node, "year输入点点击", sleep_interval=2)


        # 继续向当前焦点输入 last name（不依赖节点）。
        if not self._safe_input_on_focused("1996", "年份",True):
            # 输入失败时结束流程。
            return

        # 先点击 last name 节点聚焦
        self._safe_click(poco(text=FACEBOOK_YEAR_SET[self.device_lang]), "年份 set 点击", sleep_interval=2)

        self._safe_click(poco(text=FACEBOOK_FIRST_LAST_NAME_NEXT[self.device_lang]), "年份 set后下一页", sleep_interval=4)  #


        # 根据占位文案定位 男性 输入节点
        gender_node = poco(text=FACEBOOK_GENDER_MALE[self.device_lang])
        # 等待 男性 输入节点 出现。
        if not self._safe_wait_exists(gender_node, 2, "性别找不到"):
            return

        # 点击 男性 输入节点 聚焦并选择
        self._safe_click(gender_node, "性别-男性-点击", sleep_interval=2)


        self._safe_click(poco(text=FACEBOOK_FIRST_LAST_NAME_NEXT[self.device_lang]), "设置性别后下一页", sleep_interval=4)


        # 选择邮箱注册按钮
        email_node = poco(text=FACEBOOK_SELECT_EMAIL_SIGN_UP[self.device_lang])
        # 等待选择邮箱注册按钮出现。
        if not self._safe_wait_exists(email_node, 3, "选择邮箱注册按钮"):
            return
        # 点击选择邮箱注册按钮
        self._safe_click(email_node, "选择邮箱注册按钮", sleep_interval=4)
        sleep(2)
        # 定位邮箱输入框
        email_input_node = poco(text=FACEBOOK_EMAIL_INPUT[self.device_lang])
        # 等待邮箱输入框出现。
        if not self._safe_wait_exists(email_input_node, 4, "邮箱输入框"):
            # 记录错误日志，包含账号信息
            self.log.error("邮箱输入框未出现，无法继续输入", user_email=self.user_email)
            return

        # 点击邮箱输入框聚焦
        self._safe_click(email_input_node,"邮箱输入框-点击聚焦", sleep_interval=1)

        # 向当前焦点输入邮箱地址。
        if not self._safe_input_on_focused(self.user_email, "邮箱输入框-当前焦点",True):
            # 输入失败时结束流程，避免误操作。
            return



        self._safe_click(poco(text=FACEBOOK_FIRST_LAST_NAME_NEXT[self.device_lang]), "提交邮箱下一页", sleep_interval=5)


        # 定位密码输入框
        facebook_input_password_node = poco(text=FACEBOOK_INPUT_PASSWORD[self.device_lang])
        # 等待密码输入框出现。
        if not self._safe_wait_exists(facebook_input_password_node, 4, "密码输入框"):
            # 记录错误日志，包含账号信息
            self.log.error("密码输入框未出现，无法继续输入", user_email=self.user_email)
            return

        # 点击密码输入框聚焦
        self._safe_click(facebook_input_password_node,"密码输入框-点击聚焦", sleep_interval=1)
        # 向当前焦点输入密码。
        if not self._safe_input_on_focused(self.pwd, "密码输入框-当前焦点",True):
            # 输入失败时结束流程，避免误操作。
            return

        self._safe_click(poco(text=FACEBOOK_FIRST_LAST_NAME_NEXT[self.device_lang]), "提交密码下一页", sleep_interval=5)

        # 确认最后信息

        access_node = poco(text=FACEBOOK_FINAL_CREATE_USER_BUTTON[self.device_lang])
        if not self._safe_wait_exists(access_node, 2, "创建账号按钮"):
            return

        self._safe_click(access_node, "创建账号按钮", sleep_interval=5)






    # 定义“执行一轮完整任务”的公开方法。
    def run_once(self) -> None:
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
        # TODO(account-status): 账号状态收敛落点建议放在这里（任务编排层最合适）。
        # 1) 当前实现里，worker 在分配账号时已把 status 设置为 1（使用中），并写入 device。
        # 2) 本轮任务执行成功后，建议在此处把当前账号更新为 status=2（已经完成）。
        # 3) 本轮任务出现业务失败时，建议在此处把当前账号更新为 status=3（账号问题）并写入 msg。
        # 4) 更新依据建议使用 task_context.user_info['id']，避免按邮箱更新带来的歧义。
        # 5) 停机释放规则已在 release_user_for_device() 实现：status=1 回退 0；status=2/3 保持不变，仅清空 device。
        # 唤醒设备屏幕，避免黑屏导致后续操作失败。
        wake()
        # 回到系统桌面，保证任务从一致状态开始。
        home()
        # 记录回桌面动作完成。
        self.log.info("已回到桌面")

        # 清理所有的
        self.clear_all()

        # 抹机玩操作
        # 执行抹机王完整循环动作。
        self.mojiwang_run_all()

        # 代理操作
        # 0 动态 1 移动
        self.nekobox_run_all(0)


        self.facebook_run_all()


        # 任务尾部等待 30 秒，给外部观察或下轮衔接留时间。
        sleep(30)


# 保留模块级函数入口，统一通过 task_context 透传设备信息。
def run_once(task_context: TaskContext) -> None:
    # 创建任务类实例并执行一轮完整流程。
    OpenSettingsTask(task_context=task_context).run_once()
