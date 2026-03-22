"""Vinted 注册任务模块。"""

from __future__ import annotations
# 导入数学模块，用于生成贝塞尔滑动轨迹。
import math
# 导入随机模块，用于生成用户名随机尾号。
import random
# 导入 Any 类型，便于标注 Poco 节点列表。
from typing import Any

# 导入 Airtest 全局设备对象，便于执行多点滑动。
from airtest.core.api import G
# 导入图片查找方法，便于识别滑块起点坐标。
from airtest.core.api import loop_find
# 导入失败截图方法，便于异常排查页面状态。
from airtest.core.api import snapshot
# 导入设置系统剪贴板方法，便于配合界面“粘贴”按钮使用。
from airtest.core.api import set_clipboard
# 导入等待方法，便于页面稳定后继续执行。
from airtest.core.api import sleep
# 导入启动应用方法。
from airtest.core.api import start_app

# 导入 Vinted 邮箱验证码获取入口。
from autovt.emails import getvinted_code
# 导入 Vinted 多语言常量配置。
from autovt.fr_desc import VINTED_ACCEPT_ALL_BUTTON
from autovt.fr_desc import VINTED_EMAIL_ACTION_BUTTON_ID
from autovt.fr_desc import VINTED_EMAIL_INPUT
from autovt.fr_desc import VINTED_EMAIL_REGISTER_SIGN_UP_BUTTON_ID
from autovt.fr_desc import VINTED_PASSWORD_INPUT
from autovt.fr_desc import VINTED_PASTE_BUTTON
from autovt.fr_desc import VINTED_PASTE_BUTTON_UPPER
from autovt.fr_desc import VINTED_SHOW_REGISTRATION_OPTIONS_BUTTON_ID
from autovt.fr_desc import VINTED_TERMS_AND_CONDITIONS_CHECKBOX_ID
from autovt.fr_desc import VINTED_USERNAME_INPUT
from autovt.fr_desc import VINTED_VERIFY_CODE_INPUT_ID
from autovt.fr_desc import VINTED_VERIFY_CODE_SUBMIT_BUTTON_ID
# 导入基础任务类，复用公共前置流程和安全方法。
from autovt.tasks.open_settings import OpenSettingsTask
# 导入任务上下文类型，供模块级入口标注使用。
from autovt.tasks.task_context import TaskContext


# 定义 Vinted 注册任务类，复用 OpenSettingsTask 的公共能力。
class VintedTask(OpenSettingsTask):
    # 定义“统一记录 Vinted 失败原因并返回失败”的方法。
    def _vinted_fail(self, reason: str, target_status: int = 3) -> bool:
        # 标准化失败原因文本，避免写入空字符串。
        safe_reason = str(reason or "").strip()
        # 失败原因为空时补统一兜底文案。
        if safe_reason == "":
            # 使用统一兜底失败原因。
            safe_reason = "Vinted 注册失败：未知原因"
        # 记录错误日志，便于后续排查步骤失败位置。
        self.log.error("Vinted 步骤失败", user_email=self.user_email, reason=safe_reason, target_status=target_status)
        # 同步记录任务失败原因，供 run_once 收尾时回写数据库。
        self._set_task_result_failure(reason=safe_reason, target_status=target_status)
        # 返回 False，便于上层流程直接短路退出。
        return False

    # 定义“构建 Vinted 用户名”的方法。
    def _build_vinted_username(self) -> str | None:
        # 读取 t_user.email_pwd 作为用户名前缀来源。
        email_pwd = str(self.user_info.get("email_pwd", "")).strip()
        # 当前账号未配置 email_pwd 时直接返回空。
        if email_pwd == "":
            # 记录错误日志，便于排查账号数据缺失。
            self.log.error("Vinted 用户名生成失败：email_pwd 为空", user_email=self.user_email)
            # 返回 None 表示无法生成用户名。
            return None
        # 生成 1000 到 9999 的随机四位尾号。
        random_suffix = random.randint(1000, 9999)
        # 拼接最终用户名。
        username = f"{email_pwd}{random_suffix}"
        # 定义 Vinted 用户名允许的最大长度。
        max_username_length = 18
        # 当前用户名超长时执行尾部截断。
        if len(username) > max_username_length:
            # 记录截断前的原始长度，便于日志排查。
            original_length = len(username)
            # 按最大长度截断最终用户名，保证不超过限制。
            username = username[:max_username_length]
            # 记录用户名发生截断的日志，便于后续定位长度问题。
            self.log.info(
                "Vinted 用户名超长，已按上限截断",
                user_email=self.user_email,
                original_length=original_length,
                truncated_length=len(username),
            )
        # 记录生成完成日志，但不打印完整敏感前缀。
        self.log.info(
            "已生成 Vinted 用户名",
            username=username,
        )
        # 返回拼接后的用户名。
        return username

    # 定义“构建多语言精确文本节点列表”的方法。
    def _build_vinted_text_nodes(self, poco: Any, value_map: dict[str, str]) -> list[Any]:
        # 初始化节点列表。
        nodes: list[Any] = []
        # 收集当前语言优先的多语言文案列表。
        texts = self._collect_locale_values(value_map)
        # 遍历全部候选文案并构建节点。
        for text_value in texts:
            # 标准化当前文案。
            safe_text = str(text_value or "").strip()
            # 空文案直接跳过，避免构造无效选择器。
            if safe_text == "":
                continue
            # 追加按文本精确匹配的节点。
            nodes.append(poco(text=safe_text))
        # 返回构建好的节点列表。
        return nodes

    # 定义“构建多语言正则文本节点列表”的方法。
    def _build_vinted_regex_nodes(self, poco: Any, value_map: dict[str, str]) -> list[Any]:
        # 初始化节点列表。
        nodes: list[Any] = []
        # 收集当前语言优先的多语言文案列表。
        texts = self._collect_locale_values(value_map)
        # 遍历全部候选文案并构建节点。
        for text_value in texts:
            # 标准化当前正则文案。
            safe_text = str(text_value or "").strip()
            # 空文案直接跳过，避免构造无效选择器。
            if safe_text == "":
                continue
            # 追加按 textMatches 正则匹配的节点。
            nodes.append(poco(textMatches=safe_text))
        # 返回构建好的节点列表。
        return nodes

    # 定义“尝试给 Vinted 输入框点击界面粘贴按钮”的方法。
    def _try_click_vinted_paste(self, poco: Any, value: str, desc: str) -> bool:
        # 标准化待输入文本。
        safe_value = str(value or "")
        # 输入值为空时无需准备粘贴。
        if safe_value == "":
            # 返回 False 表示未执行粘贴点击。
            return False
        # 尝试提前把文本写入系统剪贴板。
        try:
            # 把当前值写入系统剪贴板，供界面“粘贴”按钮使用。
            set_clipboard(safe_value)
            # 记录剪贴板写入成功日志，但不输出实际敏感值。
            self.log.info("Vinted 输入值已写入剪贴板", target=desc, value_length=len(safe_value))
        # 剪贴板写入异常时仅记录日志，不中断主流程。
        except Exception as exc:
            # 连接异常走统一恢复逻辑。
            if self._is_poco_disconnect_error(exc):
                # 统一记录异常并尝试恢复连接。
                self._handle_safe_action_exception("vinted_set_clipboard", desc, exc)
                # 当前步骤若仍为连接异常，则抛给 worker 做重建。
                self._raise_runtime_disconnect_to_worker("vinted_set_clipboard", desc, exc)
            # 非连接异常记录告警并回退到焦点输入。
            self.log.warning("Vinted 写入剪贴板失败，回退焦点输入", target=desc, error=str(exc))
            # 返回 False 表示未执行粘贴点击。
            return False
        # 初始化粘贴按钮候选节点列表。
        paste_nodes: list[Any] = []
        # 追加常规大小写的粘贴按钮节点。
        paste_nodes.extend(self._build_vinted_text_nodes(poco, VINTED_PASTE_BUTTON))
        # 追加大写文案的粘贴按钮节点。
        paste_nodes.extend(self._build_vinted_text_nodes(poco, VINTED_PASTE_BUTTON_UPPER))
        # 当前没有任何候选节点时直接返回。
        if not paste_nodes:
            # 记录无候选节点日志。
            self.log.info("Vinted 未配置粘贴按钮文案，跳过界面粘贴点击", target=desc)
            # 返回 False 表示未执行粘贴点击。
            return False
        # 尝试静默点击第一个存在的粘贴按钮节点。
        if self._try_click_first_existing_node(nodes=paste_nodes, desc=f"{desc}-粘贴按钮", sleep_interval=0.3):
            # 给界面一点时间完成文本粘贴。
            sleep(0.3)
            # 记录粘贴按钮点击成功日志。
            self.log.info("Vinted 已点击界面粘贴按钮", target=desc)
            # 返回 True 表示已点击界面粘贴按钮。
            return True
        # 记录未出现粘贴按钮日志，后续继续走焦点输入。
        self.log.info("Vinted 粘贴按钮未出现，继续执行焦点输入", target=desc)
        # 返回 False 表示未点击界面粘贴按钮。
        return False

    # 定义“聚焦并输入 Vinted 文本字段”的方法。
    def _focus_and_input_vinted_field(
        self,
        poco: Any,
        nodes: list[Any],
        value: str,
        desc: str,
        wait_seconds: float = 5.0,
    ) -> bool:
        # 标准化待输入文本。
        safe_value = str(value or "").strip()
        # 输入值为空时直接返回失败。
        if safe_value == "":
            # 记录当前字段值为空的失败原因。
            return self._vinted_fail(f"Vinted {desc} 为空，无法继续注册")
        # 先查找并点击目标输入框。
        if not self.poco_find_or_click(nodes=nodes, desc=f"{desc}-输入框", sleep_interval=wait_seconds):
            # 输入框未命中时记录失败原因并返回。
            return self._vinted_fail(f"Vinted {desc} 输入框未找到")
        # 给输入框一点时间完成聚焦。
        sleep(0.5)
        # 尝试优先点击界面粘贴按钮。
        pasted_by_button = self._try_click_vinted_paste(poco=poco, value=safe_value, desc=desc)
        # 已通过界面粘贴按钮完成输入时直接返回成功。
        if pasted_by_button:
            # 记录当前字段通过界面粘贴完成输入。
            self.log.info("Vinted 字段已通过界面粘贴完成输入", target=desc)
            # 返回 True 表示输入成功。
            return True
        # 未命中界面粘贴按钮时回退到焦点输入。
        if not self._safe_input_on_focused(safe_value, f"{desc}-当前焦点"):
            # 焦点输入失败时记录失败原因并返回。
            return self._vinted_fail(f"Vinted {desc} 输入失败")
        # 给界面一点时间更新输入值。
        sleep(0.3)
        # 记录字段输入完成日志。
        self.log.info("Vinted 字段输入完成", target=desc, mode="focused_input")
        # 返回 True 表示输入成功。
        return True

    # 定义“获取 Vinted 邮箱验证码”的复用方法（带重试）。
    def _fetch_vinted_code(self, retry_times: int = 5, wait_seconds: int = 15) -> str | None:
        # 初始化成功标记，默认失败。
        ok = False
        # 初始化验证码变量，默认空。
        vinted_code: str | None = None
        # 按重试次数循环拉取验证码。
        for attempt in range(retry_times):
            # 每次重试前等待固定秒数，给邮件系统同步时间。
            sleep(wait_seconds)
            # 使用异常保护邮箱验证码拉取，避免接口异常导致流程崩溃。
            try:
                # 调用邮箱接口拉取 Vinted 验证码。
                ok, vinted_code = getvinted_code(
                    # 传入当前账号 client_id。
                    client_id=str(self.user_info.get("client_id", "")),
                    # 传入当前账号邮箱。
                    email_name=self.user_email,
                    # 传入当前账号 refresh_token。
                    refresh_token=str(self.user_info.get("email_access_key", "")),
                )
            # 捕获接口异常并按失败处理。
            except Exception as exc:
                # 记录接口异常日志。
                self.log.exception(
                    "获取 Vinted 验证码接口异常",
                    user_email=self.user_email,
                    attempt=attempt + 1,
                    error=str(exc),
                )
                # 当前轮次按失败处理。
                ok, vinted_code = False, None
            # 当拉取成功且验证码非空时结束重试。
            if ok and str(vinted_code or "").strip():
                # 记录本次命中重试轮次。
                self.log.info("获取 Vinted 验证码成功", attempt=attempt + 1, retry_times=retry_times)
                # 退出重试循环。
                break
            # 记录当前轮拉取失败日志。
            self.log.warning("获取 Vinted 验证码失败，准备重试", attempt=attempt + 1, retry_times=retry_times)
        # 当最终仍失败时返回空。
        if not ok or not str(vinted_code or "").strip():
            # 记录最终失败日志。
            self.log.error("获取 Vinted 验证码失败，无法继续", user_email=self.user_email)
            # 记录失败原因，供外层写入 t_user.msg。
            self._vinted_fail("获取 Vinted 验证码失败：邮箱未收到验证码或解析失败")
            # 返回空值表示失败。
            return None
        # 返回验证码字符串给调用方复用。
        return str(vinted_code).strip()

    # 定义“处理 Vinted 邮箱验证码提交流程”的复用方法。
    def _finish_vinted_email_verify(self, poco: Any) -> bool:
        # 构建“接受全部”按钮候选节点。
        accept_nodes = self._build_vinted_text_nodes(poco, VINTED_ACCEPT_ALL_BUTTON)
        # 当前存在候选节点时尝试等待并点击。
        if accept_nodes:
            # 使用安全点击尝试处理可能出现的弹层。
            accepted = self.poco_find_or_click(
                nodes=accept_nodes,
                desc="Vinted-接受全部按钮",
                sleep_interval=70,
            )
            # 命中弹层时记录成功日志。
            if accepted:
                # 记录当前已处理接受弹层。
                self.log.info("Vinted 验证码流程已点击接受全部", user_email=self.user_email)
            # 未命中弹层时记录非阻断日志。
            else:
                # 记录弹层未出现，继续执行后续验证码步骤。
                self.log.info("Vinted 验证码流程未出现接受全部弹层，继续后续步骤", user_email=self.user_email)
        # 点击验证码输入框，准备后续输入。
        if not self.poco_find_or_click(
            nodes=[poco(VINTED_VERIFY_CODE_INPUT_ID)],
            desc="Vinted-验证码输入框",
            sleep_interval=10,
        ):
            # 输入框未命中时记录失败原因并返回。
            return self._vinted_fail("Vinted 验证码流程失败：未找到验证码输入框")
        # 给输入框一点时间完成聚焦。
        sleep(0.5)
        # 拉取最新 Vinted 邮箱验证码。
        vinted_code = self._fetch_vinted_code()
        # 未取到验证码时直接返回失败。
        if not vinted_code:
            # 直接返回 False，失败原因已在取码 helper 中记录。
            return False

        # 再次聚焦防止没有聚焦
        self.poco_find_or_click(
            nodes=[poco(VINTED_VERIFY_CODE_INPUT_ID)],
            desc="Vinted-验证码输入框v2",
            sleep_interval=2,
        )
        # 优先尝试使用界面粘贴按钮输入验证码。
        pasted_by_button = self._try_click_vinted_paste(
            poco=poco,
            value=vinted_code,
            desc="Vinted-验证码",
        )
        # 已通过界面粘贴完成输入时记录日志。
        if pasted_by_button:
            # 记录当前验证码已通过界面粘贴完成输入。
            self.log.info("Vinted 验证码已通过界面粘贴完成输入", user_email=self.user_email)
        # 未命中粘贴按钮时回退到焦点输入。
        else:
            # 尝试向当前焦点输入验证码。
            if not self._safe_input_on_focused(vinted_code, "Vinted-验证码-当前焦点"):
                # 焦点输入失败时记录失败原因并返回。
                return self._vinted_fail("Vinted 验证码流程失败：输入验证码失败")
            # 给界面一点时间刷新输入值。
            sleep(0.3)
            # 记录当前验证码已通过焦点输入完成。
            self.log.info("Vinted 验证码已通过焦点输入完成", user_email=self.user_email)
        # 点击提交验证码按钮。
        if not self._safe_wait_click(
            poco(VINTED_VERIFY_CODE_SUBMIT_BUTTON_ID),
            10,
            "Vinted-提交验证码按钮",
            sleep_interval=1,
        ):
            # 提交按钮未命中时记录失败原因并返回。
            return self._vinted_fail("Vinted 验证码流程失败：未找到提交验证码按钮")
        # 记录验证码已提交日志。
        self.log.info("Vinted 验证码流程已提交", user_email=self.user_email)
        # 返回 True 表示验证码流程执行完成。
        return True

    # 定义“执行 Vinted 滑块识别”的独立方法。
    def vinted_slider(self) -> bool:
        # 记录当前将开始执行滑块识别。
        self.log.info("开始执行 Vinted 滑块识别", user_email=self.user_email)
        # 使用异常保护整个滑块识别流程。
        try:
            # 构建 Vinted 滑块模板对象。
            slider_template = self._build_asset_template("images", "fr", "vinted", "slider.png")
            # 记录当前使用的滑块模板路径，便于排查打包资源问题。
            self.log.info("已构建 Vinted 滑块模板", target="Vinted-滑块模板", image_path=slider_template.filename)
            # 使用异常保护 10 秒找图过程，便于区分未命中和轨迹执行失败。
            try:
                # 最多等待 10 秒识别滑块起点。
                slider_start = loop_find(slider_template, timeout=40, interval=1)
                sleep(5)
            # 捕获找图阶段异常并按“未命中”处理。
            except Exception as exc:
                # 连接异常走统一恢复链路。
                if self._is_poco_disconnect_error(exc):
                    # 统一记录异常并尝试恢复连接。
                    self._handle_safe_action_exception("vinted_slider_find", "Vinted-滑块识别", exc)
                    # 当前步骤若仍为连接异常，则抛给 worker 做重建。
                    self._raise_runtime_disconnect_to_worker("vinted_slider_find", "Vinted-滑块识别", exc)
                # 记录滑块未命中日志。
                self.log.warning("Vinted 滑块未找到", target="Vinted-滑块识别", error=str(exc), timeout_sec=10)
                # 返回 False 表示当前未识别到滑块。
                return False
            # 读取当前设备屏幕分辨率，便于后续计算滑动终点。
            screen_width, screen_height = G.DEVICE.get_current_resolution()
            # 记录当前命中的滑块起点和屏幕分辨率。
            self.log.info(
                "Vinted 滑块识别成功",
                target="Vinted-滑块识别",
                slider_start=slider_start,
                screen_width=screen_width,
                screen_height=screen_height,
            )
            # 计算滑块终点横坐标，尽量逼近右侧安全边界。
            slider_end_x = max(int(slider_start[0]) + 20, screen_width - random.randint(12, 24))
            # 计算滑块终点纵坐标，只保留极小抖动避免脱离滑道。
            slider_end_y = int(slider_start[1]) + random.randint(-4, 4)
            # 计算第一控制点横坐标，模拟起手加速。
            control_1_x = int(slider_start[0]) + int((slider_end_x - int(slider_start[0])) * random.uniform(0.20, 0.30))
            # 计算第一控制点纵坐标，模拟轻微向下偏移。
            control_1_y = int(slider_start[1]) + random.randint(4, 16)
            # 计算第二控制点横坐标，模拟中段稳定推进。
            control_2_x = int(slider_start[0]) + int((slider_end_x - int(slider_start[0])) * random.uniform(0.72, 0.84))
            # 计算第二控制点纵坐标，模拟末段轻微回正。
            control_2_y = int(slider_start[1]) + random.randint(-14, 8)
            # 生成轨迹采样点数量，保持快速但不生硬。
            curve_point_count = random.randint(5, 7)
            # 初始化滑动轨迹点列表。
            swipe_points: list[tuple[int, int]] = []
            # 逐个生成贝塞尔曲线采样点。
            for index in range(curve_point_count):
                # 计算当前采样点的时间参数。
                t = index / float(curve_point_count)
                # 计算曲线补余参数。
                one_minus_t = 1 - t
                # 计算当前采样点横坐标。
                point_x = int(
                    (one_minus_t ** 3) * int(slider_start[0])
                    + 3 * (one_minus_t ** 2) * t * control_1_x
                    + 3 * one_minus_t * (t ** 2) * control_2_x
                    + (t ** 3) * slider_end_x
                )
                # 计算当前采样点纵坐标并加入轻微波动。
                point_y = int(
                    (one_minus_t ** 3) * int(slider_start[1])
                    + 3 * (one_minus_t ** 2) * t * control_1_y
                    + 3 * one_minus_t * (t ** 2) * control_2_y
                    + (t ** 3) * slider_end_y
                    + math.sin(t * math.pi) * random.uniform(-2.0, 2.0)
                )
                # 把纵坐标限制在屏幕安全区域内。
                point_y = max(20, min(screen_height - 20, point_y))
                # 追加当前曲线点到轨迹列表。
                swipe_points.append((point_x, point_y))
            # 生成轻微过冲点，模拟真实手势惯性。
            overshoot_point = (
                screen_width - random.randint(4, 10),
                max(20, min(screen_height - 20, slider_end_y + random.randint(-2, 2))),
            )
            # 生成回拉修正点，模拟人手最终稳定动作。
            settle_point = (
                screen_width - random.randint(10, 18),
                max(20, min(screen_height - 20, slider_end_y + random.randint(-2, 2))),
            )
            # 追加过冲点到轨迹末尾。
            swipe_points.append(overshoot_point)
            # 追加回拉修正点到轨迹末尾。
            swipe_points.append(settle_point)
            # 生成本次滑动持续时间。
            swipe_duration = round(random.uniform(0.42, 0.62), 2)
            # 生成本次滑动步数。
            swipe_steps = random.randint(8, 12)
            # 记录当前生成的轨迹点信息。
            self.log.info(
                "Vinted 滑块轨迹已生成",
                target="Vinted-滑块轨迹",
                point_count=len(swipe_points),
                swipe_points=swipe_points,
                swipe_duration=swipe_duration,
                swipe_steps=swipe_steps,
            )
            # 使用多点滑动执行拟人化轨迹。
            G.DEVICE.swipe_along(swipe_points, duration=swipe_duration, steps=swipe_steps)
            # 记录滑块执行完成日志。
            self.log.info("Vinted 滑块执行完成", target="Vinted-滑块执行", slider_start=slider_start)
            # 返回 True 表示当前滑块方法执行成功。
            return True
        # 捕获滑块识别中的全部异常。
        except Exception as exc:
            # 连接异常走统一恢复链路。
            if self._is_poco_disconnect_error(exc):
                # 统一记录异常并尝试恢复连接。
                self._handle_safe_action_exception("vinted_slider_run", "Vinted-滑块执行", exc)
                # 当前步骤若仍为连接异常，则抛给 worker 做重建。
                self._raise_runtime_disconnect_to_worker("vinted_slider_run", "Vinted-滑块执行", exc)
            # 记录滑块执行失败的完整异常日志。
            self.log.exception("Vinted 滑块执行失败", target="Vinted-滑块执行", error=str(exc))
            # 使用异常保护执行失败截图，避免截图再抛错覆盖原异常。
            try:
                # 记录失败截图，便于排查当前页面状态。
                snapshot(msg="Vinted 滑块执行失败")
            # 截图失败仅记录告警，不影响主失败返回值。
            except Exception as snapshot_exc:
                # 记录截图失败日志，便于排查设备状态。
                self.log.warning("Vinted 滑块失败截图保存失败", target="Vinted-滑块执行", error=str(snapshot_exc))
            # 返回 False 表示当前滑块执行失败。
            return False

    # 定义 Vinted 注册主流程方法。
    def vinted_run_all(self) -> bool:
        # 启动 Vinted 应用。
        start_app(self.vinted_package)
        # 给应用首屏一点启动时间，避免刚启动就查找控件。
        sleep(3)
        # 获取当前可用的 Poco 实例。
        poco = self._require_poco()
        # 读取当前账号邮箱。
        email_account = str(self.user_email or "").strip()
        # 读取当前账号密码。
        password = str(self.pwd or "").strip()
        # 构建当前注册使用的用户名。
        username = self._build_vinted_username()
        # 用户名生成失败时立即结束。
        if username is None:
            # 记录失败原因并返回。
            return self._vinted_fail("Vinted 用户名生成失败：email_pwd 为空")
        # 当前账号邮箱为空时直接失败。
        if email_account == "":
            # 记录失败原因并返回。
            return self._vinted_fail("Vinted 注册失败：email_account 为空")
        # 当前业务密码为空时直接失败。
        if password == "":
            # 记录失败原因并返回。
            return self._vinted_fail("Vinted 注册失败：pwd 为空")
        # 记录 Vinted 主流程开始日志。
        self.log.info("开始执行 Vinted 注册主流程", user_email=self.user_email, package=self.vinted_package)
        # 点击注册入口按钮。
        if not self.poco_find_or_click(
            nodes=[poco(VINTED_SHOW_REGISTRATION_OPTIONS_BUTTON_ID)],
            desc="Vinted-注册入口按钮",
            sleep_interval=70,
        ):
            # 注册入口未命中时记录失败并返回。
            return self._vinted_fail("Vinted 注册失败：未找到注册入口按钮")
        # 给下一页一点加载时间。
        sleep(1)
        # 点击邮箱注册入口按钮。
        if not self.poco_find_or_click(
            nodes=[poco(VINTED_EMAIL_ACTION_BUTTON_ID)],
            desc="Vinted-邮箱注册按钮",
            sleep_interval=5,
        ):
            # 邮箱入口未命中时记录失败并返回。
            return self._vinted_fail("Vinted 注册失败：未找到邮箱注册按钮")
        # 构建用户名输入框候选节点。
        username_nodes = self._build_vinted_regex_nodes(poco, VINTED_USERNAME_INPUT)
        # 输入用户名。
        if not self._focus_and_input_vinted_field(
            poco=poco,
            nodes=username_nodes,
            value=username,
            desc="Vinted-用户名",
            wait_seconds=5,
        ):
            # 用户名输入失败时直接返回。
            return False
        # 构建邮箱输入框候选节点。
        # email_nodes = self._build_vinted_text_nodes(poco, VINTED_EMAIL_INPUT)
        email_nodes = self._build_vinted_regex_nodes(poco, VINTED_EMAIL_INPUT)
        # 输入邮箱。
        if not self._focus_and_input_vinted_field(
            poco=poco,
            nodes=email_nodes,
            value=email_account,
            desc="Vinted-邮箱",
            wait_seconds=5,
        ):
            # 邮箱输入失败时直接返回。
            return False
        # 构建密码输入框候选节点。
        password_nodes = self._build_vinted_regex_nodes(poco, VINTED_PASSWORD_INPUT)
        # 输入密码。
        if not self._focus_and_input_vinted_field(
            poco=poco,
            nodes=password_nodes,
            value=password,
            desc="Vinted-密码",
            wait_seconds=5,
        ):
            # 密码输入失败时直接返回。
            return False
        # 点击条款勾选框。
        if not self._safe_wait_click(
            poco(VINTED_TERMS_AND_CONDITIONS_CHECKBOX_ID),
            2,
            "Vinted-条款勾选框",
            sleep_interval=0.5,
        ):
            # 条款勾选失败时记录失败原因并返回。
            return self._vinted_fail("Vinted 注册失败：未能勾选条款复选框")
        # 点击提交注册按钮。
        if not self._safe_wait_click(
            poco(VINTED_EMAIL_REGISTER_SIGN_UP_BUTTON_ID),
            2,
            "Vinted-提交注册按钮",
            sleep_interval=1,
        ):
            # 提交按钮未命中时记录失败原因并返回。
            return self._vinted_fail("Vinted 注册失败：未找到提交注册按钮")
        # 记录表单提交成功日志。
        self.log.info("Vinted 注册表单已提交", user_email=self.user_email)
        # 记录当前将开始执行注册后的滑块处理。
        self.log.info("Vinted 注册提交成功，开始处理注册后滑块", user_email=self.user_email)
        # 提交后执行滑块方法，失败则按注册失败处理。
        if not self.vinted_slider(): # 非必须可能也不存在
            # 滑块处理失败时记录失败原因并返回。
            # return self._vinted_fail("Vinted 注册失败：提交后滑块处理失败")
            self.log.error("Vinted 注册后滑块处理失败，但不影响注册结果", user_email=self.user_email)
        # 记录当前将开始执行邮箱验证码流程。
        self.log.info("Vinted 注册提交成功，开始处理邮箱验证码", user_email=self.user_email)
        # 提交后继续执行邮箱验证码流程。
        if not self._finish_vinted_email_verify(poco=poco):
            # 验证码流程失败时直接返回失败结果。
            return False
        # 记录当前注册流程已完成验证码提交。
        self.log.info("Vinted 注册流程已完成邮箱验证码提交", user_email=self.user_email)
        # 返回 True 表示本次流程成功完成。
        return True

    # 定义“执行一轮完整 Vinted 任务”的公开方法。
    def run_once(self) -> None:
        # 重置本轮任务结果缓存，避免串到下一轮任务。
        self._reset_task_result_state()
        # 重置本轮设备连接异常标记，避免串到下一轮任务。
        self._runtime_disconnect_detected = False
        # 初始化 Vinted 成功标记，默认失败。
        vinted_ok = False
        # 标记本轮是否需要把异常继续抛出给 worker 做运行时重建。
        should_reraise = False
        # 保存需要继续抛出的原始异常对象。
        reraised_exc: Exception | None = None
        # 使用异常保护整轮任务，避免异常导致进程崩溃。
        try:
            # 记录当前将执行“无 Facebook 副作用”的公共前置流程。
            self.log.info(
                "Vinted 任务开始执行无 Facebook 副作用的公共前置流程",
                user_email=self.user_email,
                vt_delete_num=self.vt_delete_num,
            )
            # 执行所有任务共用的前置准备流程。
            self._run_common_setup_flow()
            # 执行 Vinted 独立应用清理，必要时按周期执行重装。
            self._run_vinted_cleanup_flow()
            # 执行共享设备准备流程（抹机王 + 代理）。
            self._run_shared_device_prepare_flow()
            # 执行 Vinted 主流程，并返回是否成功完成。
            vinted_ok = self.vinted_run_all()
        # 捕获所有异常并转换为可落库的失败原因。
        except Exception as exc:
            # 记录完整异常日志，便于排查真实堆栈。
            self.log.exception("Vinted run_once 执行异常", error=str(exc))
            # 生成具体失败原因文本，供写入 t_user.msg。
            self._set_task_result_failure(reason=self._build_failure_msg(exc, prefix="Vinted run_once 异常"), target_status=self.task_result_status)
            # 标记本轮 Vinted 结果为失败。
            vinted_ok = False
            # 连接类异常让 worker 触发 reinit_runtime，避免任务层吞错后带病继续。
            if self._is_poco_disconnect_error(exc) or isinstance(exc, (BrokenPipeError, ConnectionResetError, TimeoutError, OSError)):
                # 标记本轮检测到设备连接异常，供收尾阶段跳过失败回写。
                self._runtime_disconnect_detected = True
                # 记录将要升级处理的异常类型。
                self.log.warning("检测到 Vinted 运行时连接异常，准备抛给 worker 进行重建", error_type=type(exc).__name__)
                # 打开继续抛出标记。
                should_reraise = True
                # 保存要继续抛出的异常对象。
                reraised_exc = exc
        # 无论是否异常都执行状态回写，保证账号状态有结果。
        finally:
            # Vinted 成功时写入 status=2, vinted_status=1。
            if vinted_ok:
                # 回写成功状态并清空 msg。
                self._update_result_to_db(
                    success=True,
                    reason="",
                    status_field="vinted_status",
                    success_status_value=1,
                    failure_status_value=2,
                    log_label="Vinted",
                )
            # Vinted 失败时写入 status=3/4, vinted_status=2, msg=具体错误原因。
            else:
                # 设备连接异常场景下，不把账号打成失败状态，避免误判账号问题。
                if self._runtime_disconnect_detected:
                    # 记录跳过失败落库日志，便于后续排查。
                    self.log.warning(
                        "检测到设备连接异常，跳过 Vinted 失败状态回写",
                        user_email=self.user_email,
                        reason=str(self.task_result_reason or "").strip(),
                    )
                # 非连接异常仍按原逻辑写入失败状态。
                else:
                    # 组装最终失败原因（优先使用流程内记录的具体原因）。
                    final_reason = str(self.task_result_reason or "").strip()
                    # 失败原因为空时给出统一兜底文案。
                    if final_reason == "":
                        # 使用兜底失败原因，避免 msg 为空。
                        final_reason = "Vinted 注册失败：流程未完成，未命中成功条件"
                    # 复用通用回写逻辑，把当前模式小状态显式写成失败。
                    self._update_result_to_db(
                        success=False,
                        reason=final_reason,
                        status_field="vinted_status",
                        success_status_value=1,
                        failure_status_value=2,
                        increment_vt_fail_num=True,
                        log_label="Vinted",
                    )
            # 关闭任务内数据库连接，避免每轮 run_once 产生连接堆积。
            try:
                # 主动关闭当前任务实例持有的 UserDB 连接。
                self.user_db.close()
            # 关闭失败只记日志，不影响主流程。
            except Exception as exc:
                # 记录关闭异常，便于后续排查。
                self.log.exception("关闭 Vinted 任务内 user_db 失败", error=str(exc))
            # 非连接类异常时保留尾部等待；连接类异常由 worker 立即接管恢复。
            if (not should_reraise) and (not self._runtime_disconnect_detected):
                # 任务尾部等待 30 秒，给外部观察或下轮衔接留时间。
                from airtest.core.api import sleep

                # 调用 Airtest 的等待方法，保持与现有任务节奏一致。
                sleep(30)
        # 当流程未成功且本轮检测到设备连接异常，但没有显式异常抛出时，也主动抛给 worker 做重建。
        if (not vinted_ok) and self._runtime_disconnect_detected and not should_reraise:
            # 打开继续抛出标记，触发 worker 侧 reinit_runtime。
            should_reraise = True
            # 构造可重试的连接异常对象，确保 worker 立即走重建分支。
            reraised_exc = ConnectionResetError(
                "TransportDisconnected: 检测到设备连接异常，已跳过 Vinted 失败回写并请求 worker 重建运行时"
            )
        # 连接类异常在任务收尾后继续抛出给 worker，触发统一恢复流程。
        if should_reraise and reraised_exc is not None:
            # 继续抛出原始异常，保留完整类型和错误上下文。
            raise reraised_exc


# 保留模块级函数入口，统一通过 task_context 透传设备信息。
def run_once(task_context: TaskContext) -> None:
    # 创建任务类实例并执行一轮完整流程。
    VintedTask(task_context=task_context).run_once()
