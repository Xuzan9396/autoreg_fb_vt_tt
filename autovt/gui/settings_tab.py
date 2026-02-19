"""全局设置 Tab 模块。"""

from __future__ import annotations

from typing import Callable

import flet as ft

from autovt.gui.helpers import (
    MOJIWANG_RUN_NUM_DESC,
    MOJIWANG_RUN_NUM_KEY,
    STATUS_23_RETRY_MAX_DESC,
    STATUS_23_RETRY_MAX_KEY,
    format_timestamp,
)
from autovt.logs import get_logger
from autovt.userdb import UserDB

log = get_logger("gui.settings")


class SettingsTab:
    """封装全局设置 Tab 的构建、刷新和保存逻辑。"""

    def __init__(
        self,
        page: ft.Page,
        user_db: UserDB,
        show_snack: Callable[[str], None],
    ) -> None:
        self.page = page
        self.user_db = user_db
        self._show_snack = show_snack

        self.mojiwang_value_input: ft.TextField | None = None
        self.status_23_retry_value_input: ft.TextField | None = None
        self.mojiwang_desc_text: ft.Text | None = None
        self.status_23_retry_desc_text: ft.Text | None = None
        self.config_last_refresh_text: ft.Text | None = None

    def build(self) -> ft.Control:
        """构建全局设置 Tab 内容。"""
        self.mojiwang_value_input = ft.TextField(
            label=MOJIWANG_RUN_NUM_KEY,
            hint_text="请输入 1 到 100 的整数",
            width=320,
            keyboard_type=ft.KeyboardType.NUMBER,
            on_submit=self.save_config,
        )
        self.status_23_retry_value_input = ft.TextField(
            label=STATUS_23_RETRY_MAX_KEY,
            hint_text="请输入 0 到 5 的整数",
            width=320,
            keyboard_type=ft.KeyboardType.NUMBER,
            on_submit=self.save_config,
        )
        self.mojiwang_desc_text = ft.Text(value=MOJIWANG_RUN_NUM_DESC, size=13, color=ft.Colors.BLUE_GREY_700)
        self.status_23_retry_desc_text = ft.Text(value=STATUS_23_RETRY_MAX_DESC, size=13, color=ft.Colors.BLUE_GREY_700)
        self.config_last_refresh_text = ft.Text(value="最近刷新: -", size=12, color=ft.Colors.BLUE_GREY_600)

        actions = ft.Row(
            controls=[
                ft.FilledButton("保存配置", icon=ft.Icons.SAVE, on_click=self.save_config),
                ft.OutlinedButton("刷新配置", icon=ft.Icons.REFRESH, on_click=lambda e: self.refresh(source="manual", show_toast=True)),
            ],
            spacing=8,
        )

        return ft.Column(
            controls=[
                ft.Container(
                    expand=True,
                    padding=16,
                    border_radius=12,
                    border=ft.border.all(1, ft.Colors.BLUE_GREY_100),
                    bgcolor=ft.Colors.WHITE,
                    content=ft.Column(
                        controls=[
                            ft.Text("全局设置", size=22, weight=ft.FontWeight.W_700),
                            self.mojiwang_desc_text,
                            self.mojiwang_value_input,
                            self.status_23_retry_desc_text,
                            self.status_23_retry_value_input,
                            actions,
                            self.config_last_refresh_text,
                        ],
                        spacing=10,
                    ),
                ),
            ],
            spacing=10,
            expand=True,
        )

    def refresh(self, source: str, show_toast: bool) -> None:
        """刷新设置 Tab 数据。"""
        if (
            not self.mojiwang_value_input
            or not self.status_23_retry_value_input
            or not self.mojiwang_desc_text
            or not self.status_23_retry_desc_text
            or not self.config_last_refresh_text
        ):
            return
        try:
            # 先触发默认配置补齐，确保两个 key 都存在。
            self.user_db.get_config_map()
            # 读取抹机王轮次配置。
            mojiwang_row = self.user_db.get_config(MOJIWANG_RUN_NUM_KEY)
            # 读取 status=2/3 最大重试次数配置。
            retry_row = self.user_db.get_config(STATUS_23_RETRY_MAX_KEY)
            if mojiwang_row is None:
                raise RuntimeError(f"读取配置失败：{MOJIWANG_RUN_NUM_KEY} 不存在")
            if retry_row is None:
                raise RuntimeError(f"读取配置失败：{STATUS_23_RETRY_MAX_KEY} 不存在")

            # 回填抹机王轮次值。
            self.mojiwang_value_input.value = str(mojiwang_row.get("val", "3"))
            # 回填 status=2/3 最大重试次数值。
            self.status_23_retry_value_input.value = str(retry_row.get("val", "0"))
            # 回填抹机王配置描述文案。
            self.mojiwang_desc_text.value = str(mojiwang_row.get("desc", MOJIWANG_RUN_NUM_DESC))
            # 回填重试配置描述文案。
            self.status_23_retry_desc_text.value = str(retry_row.get("desc", STATUS_23_RETRY_MAX_DESC))

            # 取两个配置中较新的更新时间展示在页面。
            latest_update_at = max(int(mojiwang_row.get("update_at", 0)), int(retry_row.get("update_at", 0)))
            self.config_last_refresh_text.value = f"最近刷新: {format_timestamp(latest_update_at)}"

            if source == "manual" and show_toast:
                self._show_snack("配置已刷新。")
            self.page.update()
        except Exception as exc:
            log.exception("刷新设置失败", source=source)
            self._show_snack(f"刷新设置失败: {exc}")

    def save_config(self, _e: ft.ControlEvent | None = None) -> None:
        """保存 mojiwang_run_num 与 status_23_retry_max_num 配置值。"""
        if not self.mojiwang_value_input or not self.status_23_retry_value_input:
            return
        # 读取抹机王轮次输入值。
        mojiwang_raw_value = str(self.mojiwang_value_input.value or "").strip()
        # 读取 status=2/3 最大重试次数输入值。
        retry_raw_value = str(self.status_23_retry_value_input.value or "").strip()
        if mojiwang_raw_value == "":
            self._show_snack("mojiwang_run_num 不能为空，请输入 1 到 100 的整数。")
            return
        if retry_raw_value == "":
            self._show_snack("status_23_retry_max_num 不能为空，请输入 0 到 5 的整数。")
            return
        try:
            # 保存抹机王轮次配置。
            self.user_db.set_config(key=MOJIWANG_RUN_NUM_KEY, val=mojiwang_raw_value, desc=MOJIWANG_RUN_NUM_DESC)
            # 保存 status=2/3 最大重试次数配置。
            self.user_db.set_config(key=STATUS_23_RETRY_MAX_KEY, val=retry_raw_value, desc=STATUS_23_RETRY_MAX_DESC)
            self.refresh(source="save", show_toast=False)
            self._show_snack("配置保存成功。")
        except Exception as exc:
            log.exception(
                "保存配置失败",
                mojiwang_key=MOJIWANG_RUN_NUM_KEY,
                mojiwang_raw_value=mojiwang_raw_value,
                retry_key=STATUS_23_RETRY_MAX_KEY,
                retry_raw_value=retry_raw_value,
            )
            self._show_snack(f"保存配置失败: {exc}")
