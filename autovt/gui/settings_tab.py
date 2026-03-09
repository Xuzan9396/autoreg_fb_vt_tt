"""全局设置 Tab 模块。"""

from __future__ import annotations

import asyncio
import sqlite3
import time
from pathlib import Path
from typing import Callable

import flet as ft

from autovt.gui.helpers import (
    FB_DELETE_NUM_DESC,
    FB_DELETE_NUM_KEY,
    MOJIWANG_RUN_NUM_DESC,
    MOJIWANG_RUN_NUM_KEY,
    PROXYIP_END_NUM_DESC,
    PROXYIP_END_NUM_KEY,
    PROXYIP_START_NUM_DESC,
    PROXYIP_START_NUM_KEY,
    SETTING_FB_DEL_NUM_DESC,
    SETTING_FB_DEL_NUM_KEY,
    STATUS_23_RETRY_MAX_DESC,
    STATUS_23_RETRY_MAX_KEY,
    VT_PWD_DESC,
    VT_PWD_KEY,
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
        self.vt_pwd_value_input: ft.TextField | None = None
        self.fb_delete_num_value_input: ft.TextField | None = None
        self.setting_fb_del_num_value_input: ft.TextField | None = None
        self.proxyip_start_num_value_input: ft.TextField | None = None
        self.proxyip_end_num_value_input: ft.TextField | None = None
        self.mojiwang_desc_text: ft.Text | None = None
        self.status_23_retry_desc_text: ft.Text | None = None
        self.vt_pwd_desc_text: ft.Text | None = None
        self.fb_delete_num_desc_text: ft.Text | None = None
        self.setting_fb_del_num_desc_text: ft.Text | None = None
        self.proxyip_start_num_desc_text: ft.Text | None = None
        self.proxyip_end_num_desc_text: ft.Text | None = None
        self.config_last_refresh_text: ft.Text | None = None
        # 标记“刷新任务是否进行中”，避免重复触发导致并发读库。
        self._refreshing = False

    def build(self) -> ft.Control:
        """构建全局设置 Tab 内容。"""
        self.mojiwang_value_input = ft.TextField(
            label=MOJIWANG_RUN_NUM_KEY,
            hint_text="请输入 1 到 100 的整数",
            width=420,
            keyboard_type=ft.KeyboardType.NUMBER,
            on_submit=self.save_config,
        )
        self.status_23_retry_value_input = ft.TextField(
            label=STATUS_23_RETRY_MAX_KEY,
            hint_text="请输入 0 到 5 的整数",
            width=420,
            keyboard_type=ft.KeyboardType.NUMBER,
            # 输入变化时做“可删除”的软校验，避免硬拦截导致无法清空。
            on_change=self._sanitize_status_23_retry_input,
            on_submit=self.save_config,
        )
        # 创建全局 vinted 密码输入框。
        self.vt_pwd_value_input = ft.TextField(
            # 设置输入框标签为配置 key。
            label=VT_PWD_KEY,
            # 设置输入提示文案。
            hint_text="请输入 vinted 全局密码（可为空）",
            # 统一输入框宽度。
            width=420,
            # 回车时触发保存。
            on_submit=self.save_config,
        )
        # 创建 Facebook 删除控制输入框。
        self.fb_delete_num_value_input = ft.TextField(
            # 设置输入框标签为配置 key。
            label=FB_DELETE_NUM_KEY,
            # 设置输入提示文案。
            hint_text="请输入大于等于 0 的整数（0 不删除，其他数字每隔第几次重装）",
            # 统一输入框宽度。
            width=420,
            # 使用数字键盘输入。
            keyboard_type=ft.KeyboardType.NUMBER,
            # 输入变化时做软校验。
            on_change=self._sanitize_fb_delete_num_input,
            # 回车时触发保存。
            on_submit=self.save_config,
        )
        # 创建设置页 Facebook 账号清理控制输入框。
        self.setting_fb_del_num_value_input = ft.TextField(
            # 设置输入框标签为配置 key。
            label=SETTING_FB_DEL_NUM_KEY,
            # 设置输入提示文案。
            hint_text="请输入大于等于 0 的整数（0 不清理，其他数字每隔第几次执行设置页清理）",
            # 统一输入框宽度。
            width=420,
            # 使用数字键盘输入。
            keyboard_type=ft.KeyboardType.NUMBER,
            # 输入变化时做软校验。
            on_change=self._sanitize_setting_fb_del_num_input,
            # 回车时触发保存。
            on_submit=self.save_config,
        )
        # 创建代理开始位置输入框。
        self.proxyip_start_num_value_input = ft.TextField(
            # 设置输入框标签为简洁的开始位置说明。
            label="开始位置",
            # 设置输入提示文案。
            hint_text="请输入 1 到 6 的整数",
            # 统一输入框宽度。
            width=160,
            # 使用数字键盘输入。
            keyboard_type=ft.KeyboardType.NUMBER,
            # 输入变化时做软校验。
            on_change=self._sanitize_proxyip_start_num_input,
            # 回车时触发保存。
            on_submit=self.save_config,
        )
        # 创建代理结束位置输入框。
        self.proxyip_end_num_value_input = ft.TextField(
            # 设置输入框标签为简洁的结束位置说明。
            label="结束位置",
            # 设置输入提示文案。
            hint_text="请输入 1 到 6 的整数",
            # 统一输入框宽度。
            width=160,
            # 使用数字键盘输入。
            keyboard_type=ft.KeyboardType.NUMBER,
            # 输入变化时做软校验。
            on_change=self._sanitize_proxyip_end_num_input,
            # 回车时触发保存。
            on_submit=self.save_config,
        )
        self.mojiwang_desc_text = ft.Text(value=MOJIWANG_RUN_NUM_DESC, size=13, color=ft.Colors.BLUE_GREY_700)
        self.status_23_retry_desc_text = ft.Text(value=STATUS_23_RETRY_MAX_DESC, size=13, color=ft.Colors.BLUE_GREY_700)
        # 创建全局 vinted 密码描述文本。
        self.vt_pwd_desc_text = ft.Text(value=VT_PWD_DESC, size=13, color=ft.Colors.BLUE_GREY_700)
        # 创建 Facebook 删除控制描述文本。
        self.fb_delete_num_desc_text = ft.Text(value=FB_DELETE_NUM_DESC, size=13, color=ft.Colors.BLUE_GREY_700)
        # 创建设置页 Facebook 账号清理控制描述文本。
        self.setting_fb_del_num_desc_text = ft.Text(value=SETTING_FB_DEL_NUM_DESC, size=13, color=ft.Colors.BLUE_GREY_700)
        # 创建代理开始位置描述文本。
        self.proxyip_start_num_desc_text = ft.Text(value=PROXYIP_START_NUM_DESC, size=13, color=ft.Colors.BLUE_GREY_700)
        # 创建代理结束位置描述文本。
        self.proxyip_end_num_desc_text = ft.Text(value=PROXYIP_END_NUM_DESC, size=13, color=ft.Colors.BLUE_GREY_700)
        self.config_last_refresh_text = ft.Text(value="最近刷新: -", size=12, color=ft.Colors.BLUE_GREY_600)

        # 构建双列设置行，按“每行两个设置项”排列，减少纵向占用。
        settings_rows = ft.Column(
            controls=[
                self._build_setting_row(
                    self._build_setting_item(self.mojiwang_desc_text, self.mojiwang_value_input),
                    self._build_setting_item(self.status_23_retry_desc_text, self.status_23_retry_value_input),
                ),
                self._build_setting_row(
                    self._build_setting_item(self.vt_pwd_desc_text, self.vt_pwd_value_input),
                    self._build_setting_item(self.fb_delete_num_desc_text, self.fb_delete_num_value_input),
                ),
                self._build_setting_row(
                    self._build_setting_item(self.setting_fb_del_num_desc_text, self.setting_fb_del_num_value_input),
                    self._build_proxy_range_item(),
                ),
            ],
            spacing=12,
        )

        # 构建底部固定操作栏，避免滚动过长时保存按钮丢出可视区。
        actions = ft.Row(
            controls=[
                # 左侧展示最近刷新时间，并占满剩余宽度。
                ft.Container(content=self.config_last_refresh_text, expand=True),
                # 右侧集中摆放保存与刷新操作按钮。
                ft.Row(
                    controls=[
                        ft.FilledButton("保存配置", icon=ft.Icons.SAVE, on_click=self.save_config),
                        ft.OutlinedButton("刷新配置", icon=ft.Icons.REFRESH, on_click=lambda e: self.refresh(source="manual", show_toast=True)),
                    ],
                    spacing=8,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
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
                            # 顶部放置可滚动的表单区，解决设置项超出后无法滚动的问题。
                            ft.Column(
                                controls=[
                                    ft.Text("全局设置", size=22, weight=ft.FontWeight.W_700),
                                    settings_rows,
                                ],
                                spacing=12,
                                expand=True,
                                scroll=ft.ScrollMode.ALWAYS,
                            ),
                            # 使用分隔线隔开滚动区与固定操作区，提升层次感。
                            ft.Divider(height=1, color=ft.Colors.BLUE_GREY_100),
                            # 底部固定操作区始终可见。
                            actions,
                        ],
                        spacing=12,
                        expand=True,
                    ),
                ),
            ],
            spacing=10,
            expand=True,
        )

    def _build_setting_item(self, desc_control: ft.Text, input_control: ft.TextField) -> ft.Control:
        """构建单个设置项卡片，供双列布局复用。"""
        # 使用轻量容器包裹单项设置，提升双列布局下的可读性。
        return ft.Container(
            # 给每个设置项增加内边距，避免内容贴边。
            padding=12,
            # 设置圆角，保持与后台整体风格一致。
            border_radius=10,
            # 使用浅色边框分隔不同设置项。
            border=ft.border.all(1, ft.Colors.BLUE_GREY_100),
            # 轻微着色提升分组感，但不破坏整体简洁风格。
            bgcolor=ft.Colors.BLUE_GREY_50,
            # 单项内部采用纵向布局，先描述后输入。
            content=ft.Column(
                # 描述文本与输入框按顺序展示。
                controls=[desc_control, input_control],
                # 保持紧凑但不拥挤的垂直间距。
                spacing=8,
            ),
        )

    def _build_setting_row(self, left_control: ft.Control, right_control: ft.Control | None) -> ft.Control:
        """构建一行双列设置布局。"""
        # 为奇数项场景准备右侧占位控件，保证前后列宽一致。
        safe_right_control = right_control if right_control else ft.Container()
        # 使用横向布局承载两个设置项。
        return ft.Row(
            # 左右两列都设置为等宽拉伸。
            controls=[
                ft.Container(content=left_control, expand=True),
                ft.Container(content=safe_right_control, expand=True),
            ],
            # 保持两列之间的稳定间距。
            spacing=12,
            # 顶部对齐，避免描述文本长短不同导致错位。
            vertical_alignment=ft.CrossAxisAlignment.START,
        )

    def _build_proxy_range_item(self) -> ft.Control:
        """构建代理范围合并卡片。"""
        # 代理输入框未初始化时记录日志，并返回空容器兜底。
        if not self.proxyip_start_num_value_input or not self.proxyip_end_num_value_input:
            log.warning("构建代理范围卡片时发现输入框未初始化")
            return ft.Container()
        # 使用单卡片集中展示代理开始和结束位置，便于并排查看。
        return ft.Container(
            # 为代理范围卡片增加内边距，保持和其他设置卡片一致。
            padding=12,
            # 设置圆角，保持统一视觉风格。
            border_radius=10,
            # 使用浅色边框区分卡片区域。
            border=ft.border.all(1, ft.Colors.BLUE_GREY_100),
            # 保持轻量底色，避免界面过重。
            bgcolor=ft.Colors.BLUE_GREY_50,
            # 卡片内部采用纵向结构，标题和输入区分层展示。
            content=ft.Column(
                controls=[
                    # 使用单行说明展示代理范围规则，减少卡片头部高度。
                    ft.Text(
                        "代理点击范围：范围 1 到 6，且开始位置不能大于结束位置。",
                        size=13,
                        color=ft.Colors.BLUE_GREY_700,
                    ),
                    # 使用一行两个小输入框并排展示开始和结束位置。
                    ft.Row(
                        controls=[
                            # 左侧放代理开始位置输入框。
                            ft.Container(content=self.proxyip_start_num_value_input, expand=True),
                            # 右侧放代理结束位置输入框。
                            ft.Container(content=self.proxyip_end_num_value_input, expand=True),
                        ],
                        # 设置两个小输入框之间的间距。
                        spacing=10,
                    ),
                ],
                # 控制卡片内部纵向间距，和其他设置卡片保持一致。
                spacing=8,
            ),
        )

    def _sanitize_status_23_retry_input(self, _e: ft.ControlEvent | None = None) -> None:
        """软校验 status_23_retry_max_num 输入：允许清空，限制 0~5。"""
        # 输入框未初始化时直接返回。
        if not self.status_23_retry_value_input:
            return
        # 读取当前输入框原始值。
        raw_value = str(self.status_23_retry_value_input.value or "")
        # 清理首尾空白。
        clean_value = raw_value.strip()
        # 允许用户先删除为空，便于重新输入。
        if clean_value == "":
            # 值已经是空时无需再改动。
            if self.status_23_retry_value_input.value == "":
                return
            # 把值归一化为空字符串。
            self.status_23_retry_value_input.value = ""
            # 刷新页面让 UI 立即同步。
            try:
                self.page.update()
            # 刷新失败时记录日志但不抛异常。
            except Exception as exc:
                log.exception("清空重试次数输入框时刷新页面失败", error=str(exc))
            return
        # 只保留数字字符，兼容粘贴场景。
        digit_chars = "".join(ch for ch in clean_value if ch.isdigit())
        # 没有任何数字时归一化为空。
        if digit_chars == "":
            normalized_value = ""
        else:
            # 只取首位数字，保持和 max_length=1 一致。
            normalized_value = digit_chars[0]
            # 超过 5 时自动截断到 5。
            if int(normalized_value) > 5:
                normalized_value = "5"
        # 值未变化时无需更新，避免无效刷新。
        if normalized_value == self.status_23_retry_value_input.value:
            return
        # 回填标准化后的值。
        self.status_23_retry_value_input.value = normalized_value
        # 刷新页面让 UI 立即显示标准化结果。
        try:
            self.page.update()
        # 刷新失败时记录日志，避免事件链路中断。
        except Exception as exc:
            log.exception("标准化重试次数输入框时刷新页面失败", error=str(exc))

    def _sanitize_fb_delete_num_input(self, _e: ft.ControlEvent | None = None) -> None:
        """软校验 fb_delete_num 输入：允许清空，限制为非负整数。"""
        # 复用通用非负整数输入清洗逻辑。
        self._sanitize_non_negative_int_input(self.fb_delete_num_value_input, "fb_delete_num")

    def _sanitize_setting_fb_del_num_input(self, _e: ft.ControlEvent | None = None) -> None:
        """软校验 setting_fb_del_num 输入：允许清空，限制为非负整数。"""
        # 复用通用非负整数输入清洗逻辑。
        self._sanitize_non_negative_int_input(self.setting_fb_del_num_value_input, "setting_fb_del_num")

    def _sanitize_proxyip_start_num_input(self, _e: ft.ControlEvent | None = None) -> None:
        """软校验 proxyip_start_num 输入：允许清空，限制 1~6。"""
        # 复用 16 输入清洗逻辑。
        self._sanitize_one_to_five_input(self.proxyip_start_num_value_input, "proxyip_start_num")

    def _sanitize_proxyip_end_num_input(self, _e: ft.ControlEvent | None = None) -> None:
        """软校验 proxyip_end_num 输入：允许清空，限制 1~5。"""
        self._sanitize_one_to_five_input(self.proxyip_end_num_value_input, "proxyip_end_num")

    def _sanitize_non_negative_int_input(self, input_control: ft.TextField | None, field_name: str) -> None:
        """软校验非负整数输入框：允许清空，限制为非负整数。"""
        # 输入框未初始化时直接返回。
        if not input_control:
            return
        # 读取当前输入框原始值。
        raw_value = str(input_control.value or "")
        # 清理首尾空白。
        clean_value = raw_value.strip()
        # 允许用户先删除为空，便于重新输入。
        if clean_value == "":
            # 值已经是空时无需再改动。
            if input_control.value == "":
                return
            # 把值归一化为空字符串。
            input_control.value = ""
            # 刷新页面让 UI 立即同步。
            try:
                self.page.update()
            # 刷新失败时记录日志但不抛异常。
            except Exception as exc:
                log.exception("清空非负整数输入框时刷新页面失败", field_name=field_name, error=str(exc))
            return
        # 只保留数字字符，兼容粘贴场景。
        digit_chars = "".join(ch for ch in clean_value if ch.isdigit())
        # 没有任何数字时归一化为空。
        if digit_chars == "":
            normalized_value = ""
        else:
            # 转为整数再回写，统一去除前导零。
            normalized_value = str(int(digit_chars))
        # 值未变化时无需更新，避免无效刷新。
        if normalized_value == input_control.value:
            return
        # 回填标准化后的值。
        input_control.value = normalized_value
        # 刷新页面让 UI 立即显示标准化结果。
        try:
            self.page.update()
        # 刷新失败时记录日志，避免事件链路中断。
        except Exception as exc:
            log.exception("标准化非负整数输入框时刷新页面失败", field_name=field_name, error=str(exc))

    def _sanitize_one_to_five_input(self, input_control: ft.TextField | None, field_name: str) -> None:
        """软校验 1~6 整数输入框：允许清空，限制 1 到 6。"""
        # 输入框未初始化时直接返回。
        if not input_control:
            return
        # 读取当前输入框原始值。
        raw_value = str(input_control.value or "")
        # 清理首尾空白。
        clean_value = raw_value.strip()
        # 允许用户先删除为空，便于重新输入。
        if clean_value == "":
            # 值已经是空时无需再改动。
            if input_control.value == "":
                return
            # 把值归一化为空字符串。
            input_control.value = ""
            # 刷新页面让 UI 立即同步。
            try:
                self.page.update()
            # 刷新失败时记录日志但不抛异常。
            except Exception as exc:
                log.exception("清空 1~6 输入框时刷新页面失败", field_name=field_name, error=str(exc))
            return
        # 只保留数字字符，兼容粘贴场景。
        digit_chars = "".join(ch for ch in clean_value if ch.isdigit())
        # 没有任何数字时归一化为空。
        if digit_chars == "":
            normalized_value = ""
        else:
            # 只取首位数字，避免多位数输入造成歧义。
            normalized_value = digit_chars[0]
            # 小于 1 时自动拉回到 1。
            if int(normalized_value) < 1:
                normalized_value = "1"
            # 大于 6 时自动截断到 6。
            if int(normalized_value) > 6:
                normalized_value = "6"
        # 值未变化时无需更新，避免无效刷新。
        if normalized_value == input_control.value:
            return
        # 回填标准化后的值。
        input_control.value = normalized_value
        # 刷新页面让 UI 立即显示标准化结果。
        try:
            self.page.update()
        # 刷新失败时记录日志，避免事件链路中断。
        except Exception as exc:
            log.exception("标准化 1~6 输入框时刷新页面失败", field_name=field_name, error=str(exc))

    def refresh(self, source: str, show_toast: bool) -> None:
        """刷新设置 Tab 数据。"""
        if (
            not self.mojiwang_value_input
            or not self.status_23_retry_value_input
            or not self.vt_pwd_value_input
            or not self.fb_delete_num_value_input
            or not self.setting_fb_del_num_value_input
            or not self.proxyip_start_num_value_input
            or not self.proxyip_end_num_value_input
            or not self.mojiwang_desc_text
            or not self.status_23_retry_desc_text
            or not self.vt_pwd_desc_text
            or not self.fb_delete_num_desc_text
            or not self.setting_fb_del_num_desc_text
            or not self.proxyip_start_num_desc_text
            or not self.proxyip_end_num_desc_text
            or not self.config_last_refresh_text
        ):
            return
        # 刷新任务进行中时直接返回，避免重复读库占用 UI 线程。
        if self._refreshing:
            return
        # 置位刷新标记，防止短时间重复触发。
        self._refreshing = True
        try:
            # 调度异步刷新任务，把读库操作移出 UI 事件主线程。
            self.page.run_task(self._refresh_async, source, show_toast)
        except Exception:
            # 调度失败时复位刷新标记，避免后续无法刷新。
            self._refreshing = False
            # 记录调度失败日志，便于排查 Flet 任务调度异常。
            log.exception("调度刷新配置任务失败", source=source)

    async def _refresh_async(self, source: str, show_toast: bool) -> None:
        """异步刷新设置页数据，避免同步读库阻塞界面。"""
        # 记录刷新开始时间，用于输出耗时日志。
        started_at = time.monotonic()
        try:
            # 在后台线程读取配置快照，避免 UI 主线程被 SQLite 等待阻塞。
            snapshot = await asyncio.to_thread(self._load_config_snapshot, self.user_db.path)
            # 回填抹机王轮次值。
            self.mojiwang_value_input.value = str(snapshot["mojiwang_val"])
            # 回填 status=2/3 最大重试次数值。
            self.status_23_retry_value_input.value = str(snapshot["retry_val"])
            # 回填全局 vinted 密码值。
            self.vt_pwd_value_input.value = str(snapshot["vt_pwd_val"])
            # 回填 Facebook 删除控制值。
            self.fb_delete_num_value_input.value = str(snapshot["fb_delete_num_val"])
            # 回填设置页 Facebook 账号清理控制值。
            self.setting_fb_del_num_value_input.value = str(snapshot["setting_fb_del_num_val"])
            # 回填代理开始位置配置值。
            self.proxyip_start_num_value_input.value = str(snapshot["proxyip_start_num_val"])
            # 回填代理结束位置配置值。
            self.proxyip_end_num_value_input.value = str(snapshot["proxyip_end_num_val"])
            # 回填抹机王配置描述文案。
            self.mojiwang_desc_text.value = str(snapshot["mojiwang_desc"])
            # 回填重试配置描述文案。
            self.status_23_retry_desc_text.value = str(snapshot["retry_desc"])
            # 回填全局 vinted 密码配置描述文案。
            self.vt_pwd_desc_text.value = str(snapshot["vt_pwd_desc"])
            # 回填 Facebook 删除控制配置描述文案。
            self.fb_delete_num_desc_text.value = str(snapshot["fb_delete_num_desc"])
            # 回填设置页 Facebook 账号清理控制配置描述文案。
            self.setting_fb_del_num_desc_text.value = str(snapshot["setting_fb_del_num_desc"])
            # 回填代理开始位置配置描述文案。
            self.proxyip_start_num_desc_text.value = str(snapshot["proxyip_start_num_desc"])
            # 回填代理结束位置配置描述文案。
            self.proxyip_end_num_desc_text.value = str(snapshot["proxyip_end_num_desc"])
            # 回填最近刷新时间。
            self.config_last_refresh_text.value = f"最近刷新: {format_timestamp(int(snapshot['latest_update_at']))}"

            # 手动刷新场景提示成功。
            if source == "manual" and show_toast:
                self._show_snack("配置已刷新。")
            # 提交界面更新，立即展示最新值。
            self.page.update()

            # 计算本次刷新总耗时（毫秒）。
            elapsed_ms = int((time.monotonic() - started_at) * 1000)
            # 耗时较长时记录告警日志，便于定位卡顿来源。
            if elapsed_ms >= 1000:
                log.warning("配置页刷新耗时较长", source=source, elapsed_ms=elapsed_ms)
            # 正常耗时记录调试日志，便于后续对比。
            else:
                log.debug("配置页刷新完成", source=source, elapsed_ms=elapsed_ms)
        except Exception as exc:
            # 数据库锁冲突时快速提示，避免界面长时间等待。
            if self._is_sqlite_locked_error(exc):
                # 记录锁冲突告警日志，便于排查并发写压力。
                log.warning("刷新设置遇到 SQLite 锁冲突，已跳过本轮刷新", source=source, error=str(exc))
                # 手动刷新时提示“数据库忙”，自动刷新场景避免刷屏。
                if source == "manual" and show_toast:
                    self._show_snack("数据库忙，请稍后重试刷新配置。")
            # 非锁冲突按原逻辑处理。
            else:
                # 记录完整异常堆栈，便于排查失败原因。
                log.exception("刷新设置失败", source=source)
                # 展示失败提示，避免用户误以为点击无效。
                self._show_snack(f"刷新设置失败: {exc}")
        finally:
            # 无论成功失败都复位刷新标记，保证后续可再次刷新。
            self._refreshing = False

    @staticmethod
    def _load_config_snapshot(db_path: Path) -> dict[str, str | int]:
        """使用独立短超时连接读取配置快照，降低 GUI 卡顿概率。"""
        # 创建独立读库连接，避免与主线程共享同一 SQLite 连接对象。
        reader = UserDB(db_path=db_path, connect_timeout_sec=0.5, busy_timeout_ms=500)
        try:
            # 建立 SQLite 连接。
            reader.connect()
            # 先触发默认配置补齐，确保四个 key 都存在。
            reader.get_config_map()
            # 读取抹机王轮次配置。
            mojiwang_row = reader.get_config(MOJIWANG_RUN_NUM_KEY)
            # 读取 status=2/3 最大重试次数配置。
            retry_row = reader.get_config(STATUS_23_RETRY_MAX_KEY)
            # 读取全局 vinted 密码配置。
            vt_pwd_row = reader.get_config(VT_PWD_KEY)
            # 读取 Facebook 删除控制配置。
            fb_delete_num_row = reader.get_config(FB_DELETE_NUM_KEY)
            # 读取设置页 Facebook 账号清理控制配置。
            setting_fb_del_num_row = reader.get_config(SETTING_FB_DEL_NUM_KEY)
            # 读取代理开始位置配置。
            proxyip_start_num_row = reader.get_config(PROXYIP_START_NUM_KEY)
            # 读取代理结束位置配置。
            proxyip_end_num_row = reader.get_config(PROXYIP_END_NUM_KEY)
            # 抹机王配置不存在时抛错。
            if mojiwang_row is None:
                raise RuntimeError(f"读取配置失败：{MOJIWANG_RUN_NUM_KEY} 不存在")
            # 重试配置不存在时抛错。
            if retry_row is None:
                raise RuntimeError(f"读取配置失败：{STATUS_23_RETRY_MAX_KEY} 不存在")
            # 全局密码配置不存在时抛错。
            if vt_pwd_row is None:
                raise RuntimeError(f"读取配置失败：{VT_PWD_KEY} 不存在")
            # Facebook 删除控制配置不存在时抛错。
            if fb_delete_num_row is None:
                raise RuntimeError(f"读取配置失败：{FB_DELETE_NUM_KEY} 不存在")
            # 设置页 Facebook 账号清理控制配置不存在时抛错。
            if setting_fb_del_num_row is None:
                raise RuntimeError(f"读取配置失败：{SETTING_FB_DEL_NUM_KEY} 不存在")
            # 代理开始位置配置不存在时抛错。
            if proxyip_start_num_row is None:
                raise RuntimeError(f"读取配置失败：{PROXYIP_START_NUM_KEY} 不存在")
            # 代理结束位置配置不存在时抛错。
            if proxyip_end_num_row is None:
                raise RuntimeError(f"读取配置失败：{PROXYIP_END_NUM_KEY} 不存在")

            # 计算全部配置中较新的更新时间。
            latest_update_at = max(
                int(mojiwang_row.get("update_at", 0)),
                int(retry_row.get("update_at", 0)),
                int(vt_pwd_row.get("update_at", 0)),
                int(fb_delete_num_row.get("update_at", 0)),
                int(setting_fb_del_num_row.get("update_at", 0)),
                int(proxyip_start_num_row.get("update_at", 0)),
                int(proxyip_end_num_row.get("update_at", 0)),
            )
            # 组装配置快照并返回给主线程渲染。
            return {
                "mojiwang_val": str(mojiwang_row.get("val", "3")),
                "retry_val": str(retry_row.get("val", "0")),
                "vt_pwd_val": str(vt_pwd_row.get("val", "")),
                "fb_delete_num_val": str(fb_delete_num_row.get("val", "0")),
                "setting_fb_del_num_val": str(setting_fb_del_num_row.get("val", "0")),
                "proxyip_start_num_val": str(proxyip_start_num_row.get("val", "1")),
                "proxyip_end_num_val": str(proxyip_end_num_row.get("val", "1")),
                "mojiwang_desc": str(mojiwang_row.get("desc", MOJIWANG_RUN_NUM_DESC)),
                "retry_desc": str(retry_row.get("desc", STATUS_23_RETRY_MAX_DESC)),
                "vt_pwd_desc": str(vt_pwd_row.get("desc", VT_PWD_DESC)),
                "fb_delete_num_desc": FB_DELETE_NUM_DESC,
                "setting_fb_del_num_desc": SETTING_FB_DEL_NUM_DESC,
                "proxyip_start_num_desc": PROXYIP_START_NUM_DESC,
                "proxyip_end_num_desc": PROXYIP_END_NUM_DESC,
                "latest_update_at": int(latest_update_at),
            }
        finally:
            # 独立读库连接使用后立即关闭，避免连接泄漏。
            try:
                # 关闭独立连接。
                reader.close()
            except Exception as close_exc:
                # 记录关闭失败日志，不再向上抛异常影响主流程。
                log.warning("关闭配置快照读取连接失败", error=str(close_exc))

    def save_config(self, _e: ft.ControlEvent | None = None) -> None:
        """保存全局设置中的全部配置值。"""
        if (
            not self.mojiwang_value_input
            or not self.status_23_retry_value_input
            or not self.vt_pwd_value_input
            or not self.fb_delete_num_value_input
            or not self.setting_fb_del_num_value_input
            or not self.proxyip_start_num_value_input
            or not self.proxyip_end_num_value_input
        ):
            return
        # 读取抹机王轮次输入值。
        mojiwang_raw_value = str(self.mojiwang_value_input.value or "").strip()
        # 读取 status=2/3 最大重试次数输入值。
        retry_raw_value = str(self.status_23_retry_value_input.value or "").strip()
        # 读取全局 vinted 密码输入值。
        vt_pwd_raw_value = str(self.vt_pwd_value_input.value or "")
        # 读取 Facebook 删除控制输入值。
        fb_delete_num_raw_value = str(self.fb_delete_num_value_input.value or "").strip()
        # 读取设置页 Facebook 账号清理控制输入值。
        setting_fb_del_num_raw_value = str(self.setting_fb_del_num_value_input.value or "").strip()
        # 读取代理开始位置输入值。
        proxyip_start_num_raw_value = str(self.proxyip_start_num_value_input.value or "").strip()
        # 读取代理结束位置输入值。
        proxyip_end_num_raw_value = str(self.proxyip_end_num_value_input.value or "").strip()
        if mojiwang_raw_value == "":
            self._show_snack("mojiwang_run_num 不能为空，请输入 1 到 100 的整数。")
            return
        if retry_raw_value == "":
            self._show_snack("status_23_retry_max_num 不能为空，请输入 0 到 5 的整数。")
            return
        if fb_delete_num_raw_value == "":
            self._show_snack("fb_delete_num 不能为空，请输入大于等于 0 的整数。")
            return
        if setting_fb_del_num_raw_value == "":
            self._show_snack("setting_fb_del_num 不能为空，请输入大于等于 0 的整数。")
            return
        if proxyip_start_num_raw_value == "":
            self._show_snack("代理开始位置不能为空，请输入 1 到 6 的整数。")
            return
        if proxyip_end_num_raw_value == "":
            self._show_snack("代理结束位置不能为空，请输入 1 到 6 的整数。")
            return
        # 尝试把代理范围配置解析为整数，便于保存前先做跨字段校验。
        try:
            # 解析代理开始位置。
            proxyip_start_num_value = int(proxyip_start_num_raw_value)
            # 解析代理结束位置。
            proxyip_end_num_value = int(proxyip_end_num_raw_value)
        # 非整数时给出明确提示。
        except Exception:
            # 提示用户输入合法整数。
            self._show_snack("代理开始位置和代理结束位置必须是 1 到 6 的整数。")
            return
        # 开始位置大于结束位置时禁止保存。
        if proxyip_start_num_value > proxyip_end_num_value:
            # 给出明确提示。
            self._show_snack("代理开始位置不能大于代理结束位置。")
            return
        try:
            # 保存抹机王轮次配置。
            self.user_db.set_config(key=MOJIWANG_RUN_NUM_KEY, val=mojiwang_raw_value, desc=MOJIWANG_RUN_NUM_DESC)
            # 保存 status=2/3 最大重试次数配置。
            self.user_db.set_config(key=STATUS_23_RETRY_MAX_KEY, val=retry_raw_value, desc=STATUS_23_RETRY_MAX_DESC)
            # 保存全局 vinted 密码配置。
            self.user_db.set_config(key=VT_PWD_KEY, val=vt_pwd_raw_value, desc=VT_PWD_DESC)
            # 保存 Facebook 删除控制配置。
            self.user_db.set_config(key=FB_DELETE_NUM_KEY, val=fb_delete_num_raw_value, desc=FB_DELETE_NUM_DESC)
            # 保存设置页 Facebook 账号清理控制配置。
            self.user_db.set_config(key=SETTING_FB_DEL_NUM_KEY, val=setting_fb_del_num_raw_value, desc=SETTING_FB_DEL_NUM_DESC)
            # 保存代理开始位置配置。
            self.user_db.set_config(key=PROXYIP_START_NUM_KEY, val=proxyip_start_num_raw_value, desc=PROXYIP_START_NUM_DESC)
            # 保存代理结束位置配置。
            self.user_db.set_config(key=PROXYIP_END_NUM_KEY, val=proxyip_end_num_raw_value, desc=PROXYIP_END_NUM_DESC)
            self.refresh(source="save", show_toast=False)
            self._show_snack("配置保存成功。")
        except Exception as exc:
            # 数据库锁冲突时给出友好提示，避免误判为参数格式错误。
            if self._is_sqlite_locked_error(exc):
                # 记录锁冲突告警日志。
                log.warning(
                    "保存配置遇到 SQLite 锁冲突，已跳过本次写入",
                    mojiwang_key=MOJIWANG_RUN_NUM_KEY,
                    retry_key=STATUS_23_RETRY_MAX_KEY,
                    vt_pwd_key=VT_PWD_KEY,
                    fb_delete_num_key=FB_DELETE_NUM_KEY,
                    setting_fb_del_num_key=SETTING_FB_DEL_NUM_KEY,
                    proxyip_start_num_key=PROXYIP_START_NUM_KEY,
                    proxyip_end_num_key=PROXYIP_END_NUM_KEY,
                    error=str(exc),
                )
                # 给用户提示稍后重试。
                self._show_snack("数据库忙，请稍后重试保存配置。")
            # 非锁冲突按原逻辑记录异常并提示。
            else:
                log.exception(
                    "保存配置失败",
                    mojiwang_key=MOJIWANG_RUN_NUM_KEY,
                    mojiwang_raw_value=mojiwang_raw_value,
                    retry_key=STATUS_23_RETRY_MAX_KEY,
                    retry_raw_value=retry_raw_value,
                    vt_pwd_key=VT_PWD_KEY,
                    vt_pwd_length=len(vt_pwd_raw_value),
                    fb_delete_num_key=FB_DELETE_NUM_KEY,
                    fb_delete_num_raw_value=fb_delete_num_raw_value,
                    setting_fb_del_num_key=SETTING_FB_DEL_NUM_KEY,
                    setting_fb_del_num_raw_value=setting_fb_del_num_raw_value,
                    proxyip_start_num_key=PROXYIP_START_NUM_KEY,
                    proxyip_start_num_raw_value=proxyip_start_num_raw_value,
                    proxyip_end_num_key=PROXYIP_END_NUM_KEY,
                    proxyip_end_num_raw_value=proxyip_end_num_raw_value,
                )
                self._show_snack(f"保存配置失败: {exc}")

    @staticmethod
    def _is_sqlite_locked_error(exc: Exception) -> bool:
        """判断是否为 SQLite 锁冲突异常。"""
        # 非 sqlite OperationalError 直接返回 False。
        if not isinstance(exc, sqlite3.OperationalError):
            return False
        # 提取异常文本并转小写，便于关键字匹配。
        detail = str(exc).strip().lower()
        # 命中 locked/busy 关键字时判定为锁冲突。
        return "database is locked" in detail or "database is busy" in detail or "locked" in detail
