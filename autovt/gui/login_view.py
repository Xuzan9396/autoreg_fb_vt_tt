"""登录页视图模块。"""

from __future__ import annotations

from typing import Callable

import flet as ft

# 导入登录服务，复用 Go 版加密登录协议和本地缓存能力。
from autovt.auth import LoginService


class LoginView:
    """封装登录页面的构建和验证逻辑。"""

    def __init__(self, page: ft.Page, on_login_success: Callable[[], None]) -> None:
        self.page = page
        self._on_login_success = on_login_success
        # 初始化登录服务实例。
        self.login_service = LoginService()

        self.username_input: ft.TextField | None = None
        self.password_input: ft.TextField | None = None
        self.login_tip: ft.Text | None = None

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
                    ft.FilledButton(
                        "登录",
                        icon=ft.Icons.LOGIN,
                        width=320,
                        on_click=self._handle_login,
                    ),
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

    def _handle_login(self, _e: ft.ControlEvent) -> None:
        """处理登录按钮点击或回车提交事件。"""
        # 读取当前输入账号并做 trim。
        username = (self.username_input.value if self.username_input else "").strip()
        # 读取当前输入密码（不做 trim，避免误删空格密码）。
        password = str(self.password_input.value if self.password_input else "")
        # 调用登录服务执行鉴权。
        result = self.login_service.login(account=username, password=password)

        # 登录失败时展示错误文案并返回。
        if not result.ok:
            if self.login_tip:
                self.login_tip.value = result.msg or "登录失败"
            self.page.update()
            return
        # 登录成功后保存本地账号密码缓存。
        self.login_service.save_credentials(account=username, password=password)
        # 清空错误提示文本。
        if self.login_tip:
            self.login_tip.value = ""
        # 先刷新页面状态，再进入主控台。
        self.page.update()
        # 触发上层登录成功回调。
        self._on_login_success()
