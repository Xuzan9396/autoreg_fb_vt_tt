"""登录页视图模块。"""

from __future__ import annotations

from typing import Callable

import flet as ft

from autovt.gui.helpers import LOGIN_PASSWORD, LOGIN_USERNAME


class LoginView:
    """封装登录页面的构建和验证逻辑。"""

    def __init__(self, page: ft.Page, on_login_success: Callable[[], None]) -> None:
        self.page = page
        self._on_login_success = on_login_success

        self.username_input: ft.TextField | None = None
        self.password_input: ft.TextField | None = None
        self.login_tip: ft.Text | None = None

    def build(self) -> None:
        """构建登录界面并挂载到页面。"""
        self.username_input = ft.TextField(
            label="账号",
            value=LOGIN_USERNAME,
            width=320,
            prefix_icon=ft.Icons.PERSON,
            autofocus=True,
        )
        self.password_input = ft.TextField(
            label="密码",
            value=LOGIN_PASSWORD,
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
                    ft.Text("默认账号：admin  默认密码：123456", color=ft.Colors.BLUE_GREY_600, size=13),
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
                bgcolor=ft.Colors.BLUE_GREY_50,  # 登录页与主控台统一背景色，避免出现“手机模式”割裂感。
                padding=ft.padding.symmetric(horizontal=24, vertical=12),  # 增加外层留白，让桌面布局更协调。
                content=ft.Column(
                    expand=True,
                    spacing=8,
                    controls=[
                        ft.Row(  # 顶部标题行样式与主控台一致，保持视觉统一。
                            controls=[
                                ft.Text("主控台", size=26, weight=ft.FontWeight.W_700, color=ft.Colors.BLUE_GREY_900),
                                ft.Text("自动注册 facebook, vinted, tiktok", size=13, color=ft.Colors.BLUE_GREY_700),
                            ],
                            alignment=ft.MainAxisAlignment.START,
                        ),
                        ft.Container(
                            expand=True,
                            alignment=ft.Alignment(0, -0.08),  # 让登录卡片略微靠上，贴近后台登录页常见布局。
                            content=login_card,
                        ),
                    ],
                ),
            )
        )
        self.page.update()

    def _handle_login(self, _e: ft.ControlEvent) -> None:
        """处理登录按钮点击或回车提交事件。"""
        username = (self.username_input.value if self.username_input else "").strip()
        password = (self.password_input.value if self.password_input else "").strip()

        if username != LOGIN_USERNAME or password != LOGIN_PASSWORD:
            if self.login_tip:
                self.login_tip.value = "账号或密码错误，请重试。"
            self.page.update()
            return

        self._on_login_success()
