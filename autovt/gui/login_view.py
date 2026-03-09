"""登录页视图模块。"""

from __future__ import annotations

import asyncio
from typing import Callable

import flet as ft

# 导入登录服务，复用 Go 版加密登录协议和本地缓存能力。
from autovt.auth import LoginService
from autovt.logs import get_logger

# 创建登录页日志对象，便于记录异步登录调度异常。
log = get_logger("gui.login")


class LoginView:
    """封装登录页面的构建和验证逻辑。"""

    def __init__(self, page: ft.Page, on_login_success: Callable[[], None]) -> None:
        self.page = page
        self._on_login_success = on_login_success
        # 初始化登录服务实例。
        self.login_service = LoginService()

        self.username_input: ft.TextField | None = None
        self.password_input: ft.TextField | None = None
        self.login_button: ft.FilledButton | None = None
        self.login_tip: ft.Text | None = None
        self._logging_in = False

    def build(self) -> None:
        """构建登录界面并挂载到页面。"""
        # 读取本地上次登录缓存，作为默认回填值。
        saved_username, saved_password = self.login_service.load_saved_credentials()
        # 根据环境变量决定当前是否是调试跳过登录模式。
        skip_login_mode = self.login_service.is_skip_api_login()
        # 组装登录页底部提示文案。
        mode_tip_text = "调试模式：GITXUZAN_LOGIN=1，当前已跳过 API 登录校验" if skip_login_mode else "账号/密码登录"
        self.username_input = ft.TextField(
            label="账号",
            value=saved_username,
            width=320,
            prefix_icon=ft.Icons.PERSON,
            autofocus=True,
        )
        self.password_input = ft.TextField(
            label="密码",
            value=saved_password,
            width=320,
            password=True,
            can_reveal_password=True,
            prefix_icon=ft.Icons.LOCK,
            on_submit=self._handle_login,
        )
        self.login_tip = ft.Text(value="", color=ft.Colors.RED_700, size=12)

        # 创建登录按钮引用，便于异步登录期间禁用重复提交。
        self.login_button = ft.FilledButton(
            "登录",
            icon=ft.Icons.LOGIN,
            width=320,
            on_click=self._handle_login,
        )

        login_card = ft.Container(
            width=460,
            padding=24,
            border_radius=16,
            bgcolor=ft.Colors.WHITE,
            border=ft.border.all(1, ft.Colors.BLUE_GREY_100),
            shadow=ft.BoxShadow(
                spread_radius=1,
                blur_radius=18,
                color=ft.Colors.with_opacity(0.08, ft.Colors.BLACK),
                offset=ft.Offset(0, 8),
            ),
            content=ft.Column(
                controls=[
                    ft.Text("AutoVT 登录", size=26, weight=ft.FontWeight.W_700),
                    ft.Text(mode_tip_text, color=ft.Colors.BLUE_GREY_600, size=13),
                    self.username_input,
                    self.password_input,
                    self.login_button,
                    self.login_tip,
                ],
                spacing=12,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

        self.page.clean()
        self.page.add(
            ft.Container(
                expand=True,
                # 登录页与主控台统一背景色，避免出现“手机模式”割裂感。
                bgcolor=ft.Colors.BLUE_GREY_50,
                # 增加外层留白，让桌面布局更协调。
                padding=ft.padding.symmetric(horizontal=24, vertical=12),
                content=ft.Column(
                    expand=True,
                    spacing=8,
                    controls=[
                        # 顶部标题行样式与主控台一致，保持视觉统一。
                        ft.Row(
                            controls=[
                                ft.Text("主控台", size=26, weight=ft.FontWeight.W_700, color=ft.Colors.BLUE_GREY_900),
                                ft.Text("自动注册 facebook, vinted, tiktok", size=13, color=ft.Colors.BLUE_GREY_700),
                            ],
                            alignment=ft.MainAxisAlignment.START,
                        ),
                        ft.Container(
                            expand=True,
                            # 让登录卡片略微靠上，贴近后台登录页常见布局。
                            alignment=ft.Alignment(0, -0.08),
                            content=login_card,
                        ),
                    ],
                ),
            )
        )
        self.page.update()

    def _set_login_busy(self, busy: bool, tip_text: str = "") -> None:
        """更新登录页提交状态，避免重复点击并给出明确反馈。"""
        # 记录当前是否正在执行登录请求。
        self._logging_in = bool(busy)
        # 登录按钮存在时同步更新禁用状态和文案。
        if self.login_button:
            # 登录中时禁用按钮，避免重复触发并发请求。
            self.login_button.disabled = bool(busy)
            # 登录中时把按钮文案切换为“登录中...”。
            self.login_button.text = "登录中..." if busy else "登录"
        # 账号输入框存在时同步更新禁用状态。
        if self.username_input:
            # 登录中时禁用账号输入，避免用户误以为可以继续编辑当前请求。
            self.username_input.disabled = bool(busy)
        # 密码输入框存在时同步更新禁用状态。
        if self.password_input:
            # 登录中时禁用密码输入，避免重复回车触发提交。
            self.password_input.disabled = bool(busy)
        # 登录提示控件存在时更新页面提示文案。
        if self.login_tip is not None:
            # 写入当前提示文案；空字符串表示清空提示。
            self.login_tip.value = str(tip_text or "")
        # 提交 UI 更新，确保控件状态立即生效。
        self.page.update()

    def _handle_login(self, _e: ft.ControlEvent) -> None:
        """处理登录按钮点击或回车提交事件。"""
        # 已有登录请求在执行时直接返回，避免并发提交。
        if self._logging_in:
            return
        # 读取当前输入账号并做 trim。
        username = (self.username_input.value if self.username_input else "").strip()
        # 读取当前输入密码（不做 trim，避免误删空格密码）。
        password = str(self.password_input.value if self.password_input else "")
        # 先切换到登录中状态，避免用户误以为按钮无响应。
        self._set_login_busy(True, "正在登录，请稍候...")
        try:
            # 调度真正的异步登录逻辑，把网络请求移出 Flet 事件线程。
            self.page.run_task(self._login_async, username, password)
        # 调度失败时立即恢复界面状态并记录日志。
        except Exception as exc:
            # 记录调度失败异常，便于排查 Flet 运行时问题。
            log.exception("调度异步登录任务失败", error=str(exc))
            # 恢复登录页控件状态并提示用户失败原因。
            self._set_login_busy(False, f"启动登录任务失败: {exc}")

    async def _login_async(self, username: str, password: str) -> None:
        """在线程池中执行登录请求，避免同步网络阻塞 GUI。"""
        try:
            # 把同步登录请求放到后台线程，避免 Flet 事件线程卡住。
            result = await asyncio.to_thread(self.login_service.login, account=username, password=password)
            # 登录失败时恢复界面状态并展示错误文案。
            if not result.ok:
                # 恢复登录页控件状态，并展示返回的失败文案。
                self._set_login_busy(False, result.msg or "登录失败")
                return
            # 登录成功后把本地账号密码缓存写入后台线程，避免文件 IO 阻塞界面。
            await asyncio.to_thread(self.login_service.save_credentials, account=username, password=password)
            # 清空登录提示并恢复按钮状态。
            self._set_login_busy(False, "")
            # 触发上层登录成功回调，进入主控台。
            self._on_login_success()
        # 捕获所有未预期异常，确保登录页不会因协程失败而失去响应。
        except Exception as exc:
            # 记录完整异常堆栈，便于排查真实失败原因。
            log.exception("异步登录执行失败", error=str(exc))
            # 恢复登录页控件状态并提示可读错误。
            self._set_login_busy(False, f"登录失败: {exc}")
