"""账号列表 Tab 模块。"""

from __future__ import annotations

import asyncio
import sqlite3
import csv
import io
import re
import inspect
import platform
import time
from pathlib import Path
from typing import Any, Callable

import flet as ft
from openpyxl import Workbook

from autovt.gui.account_importer import AccountFileImporter, IMPORT_SPLITTER, NAME_COUNTRY_OPTIONS, generate_account_name
from autovt.gui.helpers import (
    ACCOUNT_PAGE_SIZE,
    VT_PWD_KEY,
    account_status_color,
    account_status_text,
    format_timestamp,
    mask_access_key,
    register_status_color,
    register_status_text,
)
from autovt.logs import get_logger
from autovt.settings import RUNTIME_DATA_DIR
from autovt.userdb import UserDB, UserRecord

log = get_logger("gui.account")


class AccountTab:
    """封装账号列表 Tab 的构建、刷新、筛选、分页和 CRUD 逻辑。"""

    def __init__(
        self,
        page: ft.Page,
        user_db: UserDB,
        show_snack: Callable[[str], None],
    ) -> None:
        self.page = page
        self.user_db = user_db
        self._show_snack = show_snack

        self._refreshing = False
        self._page_index = 1
        self._total = 0
        self._total_pages = 1
        self._editing_user_id: int | None = None
        # 创建账号批量导入器实例。
        self._account_importer = AccountFileImporter(user_db=self.user_db, log=log)

        # ── UI 控件占位 ──
        self.summary_text: ft.Text | None = None
        self.last_refresh_text: ft.Text | None = None
        self.list_column: ft.Column | None = None
        self.search_input: ft.TextField | None = None
        self.status_filter_dropdown: ft.Dropdown | None = None
        self.fb_filter_dropdown: ft.Dropdown | None = None
        self.vinted_filter_dropdown: ft.Dropdown | None = None
        self.titok_filter_dropdown: ft.Dropdown | None = None
        self.page_text: ft.Text | None = None
        self.prev_button: ft.OutlinedButton | None = None
        self.next_button: ft.OutlinedButton | None = None
        self.import_country_dropdown: ft.Dropdown | None = None
        self.import_file_picker: ft.FilePicker | None = None

        # 表单控件占位
        self.email_account_input: ft.TextField | None = None
        self.email_pwd_input: ft.TextField | None = None
        self.email_access_key_input: ft.TextField | None = None
        self.client_id_input: ft.TextField | None = None
        self.first_name_input: ft.TextField | None = None
        self.last_name_input: ft.TextField | None = None
        self.pwd_input: ft.TextField | None = None
        self.status_dropdown: ft.Dropdown | None = None
        self.fb_status_dropdown: ft.Dropdown | None = None
        self.vinted_status_dropdown: ft.Dropdown | None = None
        self.titok_status_dropdown: ft.Dropdown | None = None
        self.msg_input: ft.TextField | None = None
        self.quick_parse_input: ft.TextField | None = None
        self.form_feedback_text: ft.Text | None = None
        self._editing_device_value = ""
        self._active_dialog: ft.AlertDialog | None = None
        self._active_dialog_title = ""
        self._active_dialog_trace_id: str | None = None
        self._dialog_open_seq = 0

    # ═══════════════════════════════════════════════════════════════════
    # 构建 Tab 内容
    # ═══════════════════════════════════════════════════════════════════

    def build(self) -> ft.Control:
        """构建账号列表 Tab 的全部 UI。"""
        self.summary_text = ft.Text(value="账号总数: 0", size=14, weight=ft.FontWeight.W_600, color=ft.Colors.BLUE_GREY_900)
        self.last_refresh_text = ft.Text(value="最近刷新: -", size=12, color=ft.Colors.BLUE_GREY_600)
        self.list_column = ft.Column(
            controls=[ft.Text("账号列表待加载...", color=ft.Colors.BLUE_GREY_600)],
            spacing=10,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )
        self.search_input = ft.TextField(label="邮箱搜索", hint_text="输入 email_account 关键字", width=280, on_submit=self._apply_filters, col={"xs": 12, "md": 2})
        self.status_filter_dropdown = ft.Dropdown(
            label="status 筛选", width=180, value="", col={"xs": 6, "md": 2},
            options=[ft.dropdown.Option("", "全部"), ft.dropdown.Option("0", "0 未使用"), ft.dropdown.Option("1", "1 正在使用"), ft.dropdown.Option("2", "2 已经使用"), ft.dropdown.Option("3", "3 账号问题")],
        )
        self.fb_filter_dropdown = ft.Dropdown(
            label="FB 筛选", width=150, value="", col={"xs": 6, "md": 2},
            options=[ft.dropdown.Option("", "全部"), ft.dropdown.Option("0", "0 未注册"), ft.dropdown.Option("1", "1 成功"), ft.dropdown.Option("2", "2 失败")],
        )
        self.vinted_filter_dropdown = ft.Dropdown(
            label="VT 筛选", width=150, value="", col={"xs": 6, "md": 2},
            options=[ft.dropdown.Option("", "全部"), ft.dropdown.Option("0", "0 未注册"), ft.dropdown.Option("1", "1 成功"), ft.dropdown.Option("2", "2 失败")],
        )
        self.titok_filter_dropdown = ft.Dropdown(
            label="TT 筛选", width=150, value="", col={"xs": 6, "md": 2},
            options=[ft.dropdown.Option("", "全部"), ft.dropdown.Option("0", "0 未注册"), ft.dropdown.Option("1", "1 成功"), ft.dropdown.Option("2", "2 失败")],
        )
        self.page_text = ft.Text(value="第 1 / 1 页（共 0 条）", size=12, color=ft.Colors.BLUE_GREY_700)
        self.prev_button = ft.OutlinedButton("上一页", icon=ft.Icons.CHEVRON_LEFT, disabled=True, on_click=self._goto_prev_page)
        self.next_button = ft.OutlinedButton("下一页", icon=ft.Icons.CHEVRON_RIGHT, disabled=True, on_click=self._goto_next_page)
        # 创建姓名国家下拉框，导入时用于 Faker 生成姓名。
        self.import_country_dropdown = ft.Dropdown(
            # 默认使用法国姓名。
            value="fr_FR",
            # 控件宽度。
            width=180,
            # 固定高度，避免不同平台字体导致控件抖动。
            height=50,
            # 使用紧凑样式，减少上下留白。
            dense=True,
            # 明确设置内边距，避免文字与边框过近。
            content_padding=ft.padding.symmetric(horizontal=12, vertical=10),
            # 选项列表（法国、英国等）。
            options=[ft.dropdown.Option(locale, label) for label, locale in NAME_COUNTRY_OPTIONS],
            # 鼠标悬停提示当前控件用途。
            tooltip="选择 Faker 姓名国家",
        )
        # 使用独立标题文本，避免 Material 浮动标签与边框重叠。
        import_country_selector = ft.Column(
            # 先展示标题，再展示下拉框。
            controls=[
                ft.Text("姓名国家", size=12, color=ft.Colors.BLUE_GREY_700),
                self.import_country_dropdown,
            ],
            # 标题与输入框间距保持紧凑。
            spacing=4,
        )
        # 创建文件选择器服务，供“一键导入文件”使用。
        self.import_file_picker = ft.FilePicker()
        # 避免重复添加到页面 services。
        if self.import_file_picker not in self.page.services:
            # 把文件选择器挂到页面级 services。
            self.page.services.append(self.import_file_picker)

        actions = ft.Row(
            controls=[
                ft.FilledButton("新增账号", icon=ft.Icons.ADD, on_click=self._open_create_dialog),
                ft.FilledButton("刷新账号", icon=ft.Icons.REFRESH, on_click=lambda e: self.refresh(source="manual", show_toast=True)),
                ft.OutlinedButton("一键导出", icon=ft.Icons.DOWNLOAD, on_click=self._handle_export_filtered_accounts),
                import_country_selector,
                ft.OutlinedButton("一键导入文件", icon=ft.Icons.UPLOAD_FILE, on_click=self._pick_import_file),
            ],
            alignment=ft.MainAxisAlignment.START,
            spacing=8,
        )
        filters = ft.ResponsiveRow(
            controls=[
                self.search_input,
                self.status_filter_dropdown,
                self.fb_filter_dropdown,
                self.vinted_filter_dropdown,
                self.titok_filter_dropdown,
                ft.FilledButton("筛选", icon=ft.Icons.SEARCH, on_click=self._apply_filters, col={"xs": 6, "md": 1.5}),
                ft.OutlinedButton("重置", icon=ft.Icons.CLEAR_ALL, on_click=self._reset_filters, col={"xs": 6, "md": 1.5}),
            ],
            spacing=8,
            run_spacing=8,
        )
        pagination = ft.Row(
            controls=[self.prev_button, self.page_text, self.next_button],
            alignment=ft.MainAxisAlignment.END,
            spacing=8,
        )

        return ft.Column(
            controls=[
                actions,
                filters,
                ft.Row([self.summary_text, self.last_refresh_text], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ft.Divider(height=1, color=ft.Colors.BLUE_GREY_100),
                ft.Container(
                    expand=True, padding=12, border_radius=12,
                    border=ft.border.all(1, ft.Colors.BLUE_GREY_100),
                    bgcolor=ft.Colors.WHITE,
                    content=self.list_column,
                ),
                pagination,
            ],
            spacing=10,
            expand=True,
        )

    # ═══════════════════════════════════════════════════════════════════
    # 刷新
    # ═══════════════════════════════════════════════════════════════════

    def refresh(self, source: str, show_toast: bool) -> None:
        """刷新账号列表数据。"""
        # 记录刷新总起点，便于输出完整耗时。
        started_at = time.monotonic()
        # 初始化 count 查询耗时（毫秒）。
        count_elapsed_ms = 0
        # 初始化列表查询耗时（毫秒）。
        list_elapsed_ms = 0
        # 初始化渲染提交耗时（毫秒）。
        render_elapsed_ms = 0
        if self._refreshing or not self.list_column:
            return
        self._refreshing = True
        try:
            # 记录 count 查询起点。
            step_started_at = time.monotonic()
            email_kw, status_f, fb_f, vinted_f, titok_f = self._get_filter_values()
            total_count = self.user_db.count_users_filtered(
                email_keyword=email_kw, status=status_f,
                fb_status=fb_f, vinted_status=vinted_f, titok_status=titok_f,
            )
            # 统计 count 查询耗时。
            count_elapsed_ms = int((time.monotonic() - step_started_at) * 1000)
            total_pages = max((int(total_count) + ACCOUNT_PAGE_SIZE - 1) // ACCOUNT_PAGE_SIZE, 1)
            self._total = int(total_count)
            self._total_pages = int(total_pages)

            if self._page_index > self._total_pages:
                self._page_index = self._total_pages
            if self._page_index < 1:
                self._page_index = 1

            # 记录列表查询起点。
            step_started_at = time.monotonic()
            rows = self.user_db.list_users_page_filtered(
                page=self._page_index, page_size=ACCOUNT_PAGE_SIZE,
                email_keyword=email_kw, status=status_f,
                fb_status=fb_f, vinted_status=vinted_f, titok_status=titok_f,
            )
            # 统计列表查询耗时。
            list_elapsed_ms = int((time.monotonic() - step_started_at) * 1000)

            # 记录渲染提交起点。
            step_started_at = time.monotonic()
            self._render_rows(rows)
            self._update_summary(self._total, len(rows))
            self._update_pagination()
            if source == "manual" and show_toast:
                self._show_snack(f"账号列表已刷新，第 {self._page_index} 页共 {len(rows)} 条。")
            self.page.update()
            # 统计渲染提交耗时。
            render_elapsed_ms = int((time.monotonic() - step_started_at) * 1000)

            # 计算本次刷新总耗时。
            total_elapsed_ms = int((time.monotonic() - started_at) * 1000)
            # 总耗时较长时输出告警日志，便于定位卡顿段。
            if total_elapsed_ms >= 1200:
                log.warning(
                    "账号页刷新耗时较长",
                    source=source,
                    total_elapsed_ms=total_elapsed_ms,
                    count_elapsed_ms=count_elapsed_ms,
                    list_elapsed_ms=list_elapsed_ms,
                    render_elapsed_ms=render_elapsed_ms,
                    page_index=self._page_index,
                    total_count=self._total,
                    page_rows=len(rows),
                )
            # 总耗时正常时输出调试日志。
            else:
                log.debug(
                    "账号页刷新完成",
                    source=source,
                    total_elapsed_ms=total_elapsed_ms,
                    count_elapsed_ms=count_elapsed_ms,
                    list_elapsed_ms=list_elapsed_ms,
                    render_elapsed_ms=render_elapsed_ms,
                    page_index=self._page_index,
                    total_count=self._total,
                    page_rows=len(rows),
                )
        except Exception as exc:
            # 数据库锁冲突时快速返回，避免卡住 GUI 线程。
            if self._is_sqlite_locked_error(exc):
                # 记录锁冲突告警，便于排查并发写压力。
                log.warning(
                    "刷新账号列表遇到 SQLite 锁冲突，已跳过本轮刷新",
                    source=source,
                    error=str(exc),
                    count_elapsed_ms=count_elapsed_ms,
                    list_elapsed_ms=list_elapsed_ms,
                    render_elapsed_ms=render_elapsed_ms,
                )
                # 手动刷新时给用户提示，自动刷新场景避免刷屏。
                if source == "manual" and show_toast:
                    self._show_snack("数据库忙，请稍后重试刷新。")
            # 非锁冲突按原逻辑记录并提示。
            else:
                log.exception(
                    "刷新账号列表失败",
                    source=source,
                    count_elapsed_ms=count_elapsed_ms,
                    list_elapsed_ms=list_elapsed_ms,
                    render_elapsed_ms=render_elapsed_ms,
                )
                self._show_snack(f"刷新账号失败: {exc}")
        finally:
            self._refreshing = False

    # ═══════════════════════════════════════════════════════════════════
    # 渲染
    # ═══════════════════════════════════════════════════════════════════

    def _render_rows(self, rows: list[dict[str, Any]]) -> None:
        if not self.list_column:
            return
        if not rows:
            self.list_column.controls = [ft.Text("当前没有账号数据，请先写入 t_user。", color=ft.Colors.BLUE_GREY_700)]
            return
        self.list_column.controls = [self._build_card(row) for row in rows]

    def _build_card(self, row: dict[str, Any]) -> ft.Control:
        row_data = dict(row)
        user_id = int(row_data.get("id", 0))
        email_account = str(row_data.get("email_account", ""))
        email_access_key = str(row_data.get("email_access_key", ""))
        device_id = str(row_data.get("device", "")).strip()
        first_name = str(row_data.get("first_name", ""))
        last_name = str(row_data.get("last_name", ""))
        msg = str(row_data.get("msg", ""))

        status_val = int(row_data.get("status", 0))
        vinted_val = int(row_data.get("vinted_status", 0))
        fb_val = int(row_data.get("fb_status", 0))
        tiktok_val = int(row_data.get("titok_status", 0))
        update_at_val = int(row_data.get("update_at", 0))

        name_text = (f"{first_name} {last_name}").strip() or "-"
        update_text = format_timestamp(update_at_val)
        masked_key = mask_access_key(email_access_key)

        a_status_text = account_status_text(status_val)
        a_status_color = account_status_color(status_val)
        fb_text = register_status_text(fb_val)
        fb_color = register_status_color(fb_val)
        vt_text = register_status_text(vinted_val)
        vt_color = register_status_color(vinted_val)
        tt_text = register_status_text(tiktok_val)
        tt_color = register_status_color(tiktok_val)

        def _pill(label: str, bg: str) -> ft.Container:
            return ft.Container(
                content=ft.Text(label, color=ft.Colors.WHITE, size=11),
                bgcolor=bg, border_radius=999,
                padding=ft.padding.symmetric(horizontal=10, vertical=4),
                col={"xs": 6, "md": 3},
            )

        return ft.Container(
            padding=12,
            border=ft.border.all(1, ft.Colors.BLUE_GREY_100),
            border_radius=12,
            bgcolor=ft.Colors.BLUE_GREY_50,
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[ft.Text(f"ID:{user_id} | {email_account or '-'}", size=15, weight=ft.FontWeight.W_600, expand=True)],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    ft.ResponsiveRow(
                        controls=[
                            _pill(f"账号: {a_status_text}", a_status_color),
                            _pill(f"FB: {fb_text}", fb_color),
                            _pill(f"VT: {vt_text}", vt_color),
                            _pill(f"TT: {tt_text}", tt_color),
                        ],
                        spacing=6, run_spacing=6,
                    ),
                    ft.Text(f"姓名: {name_text} | 更新时间: {update_text}", size=12, color=ft.Colors.BLUE_GREY_700),
                    ft.Text(f"设备ID: {device_id or '-'}", size=12, color=ft.Colors.BLUE_GREY_700),
                    ft.Text(f"email_access_key: {masked_key}", size=12, color=ft.Colors.BLUE_GREY_800),
                    ft.Text(f"备注: {msg or '-'}", size=12, color=ft.Colors.BLUE_GREY_700, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                    ft.Row(
                        controls=[
                            ft.OutlinedButton("编辑", icon=ft.Icons.EDIT, on_click=lambda e, r=row_data: self._open_edit_dialog(r)),
                            ft.OutlinedButton(
                                "删除", icon=ft.Icons.DELETE_OUTLINE,
                                on_click=lambda e, uid=user_id, em=email_account: self._confirm_delete(uid, em),
                                style=ft.ButtonStyle(color=ft.Colors.RED_700),
                            ),
                        ],
                        spacing=8,
                    ),
                ],
                spacing=8,
            ),
        )

    # ═══════════════════════════════════════════════════════════════════
    # 摘要 & 分页
    # ═══════════════════════════════════════════════════════════════════

    def _update_summary(self, total_count: int, current_rows: int) -> None:
        if self.summary_text:
            self.summary_text.value = f"账号总数: {int(total_count)} | 当前页数量: {int(current_rows)} | 每页: {ACCOUNT_PAGE_SIZE}"
        if self.last_refresh_text:
            self.last_refresh_text.value = f"最近刷新: {time.strftime('%H:%M:%S', time.localtime())}"

    def _update_pagination(self) -> None:
        if self.page_text:
            self.page_text.value = f"第 {self._page_index} / {self._total_pages} 页（共 {self._total} 条）"
        if self.prev_button:
            self.prev_button.disabled = self._page_index <= 1
        if self.next_button:
            self.next_button.disabled = self._page_index >= self._total_pages

    def _goto_prev_page(self, _e: ft.ControlEvent | None = None) -> None:
        if self._page_index <= 1:
            return
        self._page_index -= 1
        self.refresh(source="page_prev", show_toast=False)

    def _goto_next_page(self, _e: ft.ControlEvent | None = None) -> None:
        if self._page_index >= self._total_pages:
            return
        self._page_index += 1
        self.refresh(source="page_next", show_toast=False)

    # ═══════════════════════════════════════════════════════════════════
    # 筛选
    # ═══════════════════════════════════════════════════════════════════

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

    @staticmethod
    def _parse_optional_int(raw_value: str | None) -> int | None:
        clean = str(raw_value or "").strip()
        if clean == "":
            return None
        try:
            return int(clean)
        except Exception:
            return None

    def _get_filter_values(self) -> tuple[str, int | None, int | None, int | None, int | None]:
        email_kw = str(self.search_input.value if self.search_input else "").strip()
        status_f = self._parse_optional_int(self.status_filter_dropdown.value if self.status_filter_dropdown else None)
        fb_f = self._parse_optional_int(self.fb_filter_dropdown.value if self.fb_filter_dropdown else None)
        vinted_f = self._parse_optional_int(self.vinted_filter_dropdown.value if self.vinted_filter_dropdown else None)
        titok_f = self._parse_optional_int(self.titok_filter_dropdown.value if self.titok_filter_dropdown else None)
        return email_kw, status_f, fb_f, vinted_f, titok_f

    def _apply_filters(self, _e: ft.ControlEvent | None = None) -> None:
        self._page_index = 1
        self.refresh(source="filter", show_toast=False)

    def _reset_filters(self, _e: ft.ControlEvent | None = None) -> None:
        if self.search_input:
            self.search_input.value = ""
        if self.status_filter_dropdown:
            self.status_filter_dropdown.value = ""
        if self.fb_filter_dropdown:
            self.fb_filter_dropdown.value = ""
        if self.vinted_filter_dropdown:
            self.vinted_filter_dropdown.value = ""
        if self.titok_filter_dropdown:
            self.titok_filter_dropdown.value = ""
        self._page_index = 1
        self.refresh(source="filter_reset", show_toast=False)

    # 定义“导出按钮点击入口”方法。
    def _handle_export_filtered_accounts(self, _e: ft.ControlEvent | None = None) -> None:
        # 在 Flet 事件线程调度异步导出任务。
        try:
            # 调度“按当前筛选导出账号”任务。
            self.page.run_task(self._export_filtered_accounts_async)
        # 调度失败时记录异常并提示。
        except Exception as exc:
            # 打印完整异常栈，便于定位事件线程问题。
            log.exception("调度账号导出任务失败", error=str(exc))
            # 给用户可读错误提示。
            self._show_snack(f"导出任务启动失败: {exc}")

    # 定义“按当前筛选条件拉取导出数据”方法。
    def _list_filtered_rows_for_export(self) -> list[dict[str, Any]]:
        # 读取当前筛选控件值（邮箱关键字 + 4 种状态）。
        email_kw, status_f, fb_f, vinted_f, titok_f = self._get_filter_values()
        # 查询当前筛选命中的总条数。
        total_count = self.user_db.count_users_filtered(
            # 传入邮箱关键字筛选参数。
            email_keyword=email_kw,
            # 传入账号状态筛选参数。
            status=status_f,
            # 传入 FB 状态筛选参数。
            fb_status=fb_f,
            # 传入 VT 状态筛选参数。
            vinted_status=vinted_f,
            # 传入 TT 状态筛选参数。
            titok_status=titok_f,
        )
        # 没有命中数据时返回空列表。
        if int(total_count) <= 0:
            return []
        # 查询全部命中数据用于导出（不走分页）。
        return self.user_db.list_users_filtered(
            # 使用筛选总数作为导出上限。
            limit=int(total_count),
            # 从第 0 条开始导出。
            offset=0,
            # 传入邮箱关键字筛选参数。
            email_keyword=email_kw,
            # 传入账号状态筛选参数。
            status=status_f,
            # 传入 FB 状态筛选参数。
            fb_status=fb_f,
            # 传入 VT 状态筛选参数。
            vinted_status=vinted_f,
            # 传入 TT 状态筛选参数。
            titok_status=titok_f,
        )

    # 定义“组装 outlook 导出字段”的方法。
    @staticmethod
    def _build_outlook_export_field(row: dict[str, Any]) -> str:
        # 读取邮箱账号字段。
        email_account = str(row.get("email_account", ""))
        # 读取邮箱密码字段。
        email_pwd = str(row.get("email_pwd", ""))
        # 读取微软 OAuth client_id 字段。
        client_id = str(row.get("client_id", ""))
        # 读取邮箱授权码字段。
        email_access_key = str(row.get("email_access_key", ""))
        # 按导入同款分隔符拼回 outlook 一整段字段。
        return IMPORT_SPLITTER.join([email_account, email_pwd, client_id, email_access_key])

    # 定义“构建导出二维表格数据”的方法。
    def _build_export_table_rows(self, rows: list[dict[str, Any]]) -> list[list[str | int]]:
        # 初始化导出二维表数组。
        export_table_rows: list[list[str | int]] = []
        # 先写入表头行。
        export_table_rows.append(["id", "账号", "账号状态", "FB状态", "VT状态", "TT状态", "pwd", "msg", "outlook"])
        # 逐行写入数据。
        for row in rows:
            # 读取账号状态值。
            status_val = int(row.get("status", 0))
            # 读取 FB 状态值。
            fb_val = int(row.get("fb_status", 0))
            # 读取 VT 状态值。
            vinted_val = int(row.get("vinted_status", 0))
            # 读取 TT 状态值。
            titok_val = int(row.get("titok_status", 0))
            # 追加当前账号导出行。
            export_table_rows.append(
                [
                    # 账号主键 ID。
                    int(row.get("id", 0)),
                    # 邮箱账号。
                    str(row.get("email_account", "")),
                    # 账号状态（数值 + 文案）。
                    f"{status_val} {account_status_text(status_val)}",
                    # FB 状态（数值 + 文案）。
                    f"{fb_val} {register_status_text(fb_val)}",
                    # VT 状态（数值 + 文案）。
                    f"{vinted_val} {register_status_text(vinted_val)}",
                    # TT 状态（数值 + 文案）。
                    f"{titok_val} {register_status_text(titok_val)}",
                    # vinted 密码。
                    str(row.get("pwd", "")),
                    # 备注信息。
                    str(row.get("msg", "")),
                    # 微软账号拼接字段。
                    self._build_outlook_export_field(row),
                ]
            )
        # 返回导出二维表。
        return export_table_rows

    # 定义“把导出二维表转为 TSV 剪贴板文本”的方法。
    @staticmethod
    def _build_export_tsv(export_table_rows: list[list[str | int]]) -> str:
        # 创建内存文本缓冲区，避免手写转义逻辑。
        buffer = io.StringIO()
        # 创建 TSV 写入器（使用制表符分隔）。
        writer = csv.writer(buffer, delimiter="\t", lineterminator="\n")
        # 逐行写入二维表。
        writer.writerows(export_table_rows)
        # 返回最终 TSV 文本。
        return buffer.getvalue()

    # 定义“保存导出数据到 xlsx 文件”的方法。
    @staticmethod
    def _save_export_file(export_table_rows: list[list[str | int]]) -> Path:
        # 读取当前系统名称并转小写，便于分平台处理。
        system_name = platform.system().lower()
        # macOS 默认导出到下载目录。
        if system_name == "darwin":
            # 指定 macOS 导出目录为用户 Downloads。
            export_dir = Path.home() / "Downloads"
        # Windows 默认导出到当前用户桌面目录。
        elif system_name.startswith("win"):
            # 指定 Windows 导出目录为用户 Desktop。
            export_dir = Path.home() / "Desktop"
        # 其他系统走运行期目录兜底。
        else:
            # 指定兜底导出目录为运行期 exports 目录。
            export_dir = Path(RUNTIME_DATA_DIR) / "exports"
        # 尝试创建导出目录。
        try:
            # 创建导出目录（不存在则自动创建）。
            export_dir.mkdir(parents=True, exist_ok=True)
        # 创建目录失败时回退到运行期目录兜底。
        except Exception as exc:
            # 记录目录创建失败日志，便于定位权限问题。
            log.exception("创建导出目录失败，回退运行期目录", export_dir=str(export_dir), error=str(exc))
            # 回退导出目录到运行期 exports。
            export_dir = Path(RUNTIME_DATA_DIR) / "exports"
            # 确保兜底目录存在。
            export_dir.mkdir(parents=True, exist_ok=True)
        # 生成当前时间戳字符串作为文件名后缀。
        time_text = time.strftime("%Y%m%d_%H%M%S", time.localtime())
        # 组装导出文件完整路径。
        export_path = export_dir / f"accounts_export_{time_text}.xlsx"
        # 创建 Excel 工作簿对象。
        workbook = Workbook()
        # 获取默认工作表对象。
        worksheet = workbook.active
        # 设置工作表名称。
        worksheet.title = "accounts"
        # 写入导出二维表到工作表。
        for export_row in export_table_rows:
            # 按行追加到 Excel。
            worksheet.append(export_row)
        # 冻结首行，方便查看表头。
        worksheet.freeze_panes = "A2"
        # 保存 xlsx 文件到目标路径。
        workbook.save(str(export_path))
        # 关闭工作簿句柄，释放文件资源。
        workbook.close()
        # 返回导出文件路径给调用方。
        return export_path

    # 定义“异步执行导出并复制剪贴板”的方法。
    async def _export_filtered_accounts_async(self) -> None:
        # 使用异常保护导出流程，保证界面不崩溃。
        try:
            # 按当前筛选读取全部命中数据。
            rows = self._list_filtered_rows_for_export()
            # 无数据时直接提示并结束。
            if len(rows) == 0:
                self._show_snack("当前筛选条件下没有可导出的账号。")
                return
            # 构建导出二维表数据。
            export_table_rows = self._build_export_table_rows(rows)
            # 构建导出文本内容。
            export_text = self._build_export_tsv(export_table_rows)
            # 保存导出文件到运行期目录。
            export_path = self._save_export_file(export_table_rows)
            # 先标记剪贴板复制是否成功。
            clipboard_ok = False
            # 尝试把导出文本复制到系统剪贴板。
            try:
                # 调用 Flet Clipboard 服务写入文本。
                await self.page.clipboard.set(export_text)
                # 标记复制成功。
                clipboard_ok = True
            # 复制失败时记录日志并继续保留文件导出结果。
            except Exception as exc:
                # 打印异常栈，便于排查系统剪贴板权限问题。
                log.exception("账号导出复制到剪贴板失败", error=str(exc))
            # 复制成功时提示“文件+剪贴板”都可用。
            if clipboard_ok:
                self._show_snack(f"导出成功：{len(rows)} 条，已复制剪贴板，文件: {export_path}")
                return
            # 复制失败时提示用户文件路径仍可用。
            self._show_snack(f"导出成功：{len(rows)} 条，剪贴板失败，文件: {export_path}")
        # 捕获导出主流程异常并提示。
        except Exception as exc:
            # 记录完整异常栈，满足“每个错误记录日志”要求。
            log.exception("账号导出失败", error=str(exc))
            # 给用户可读错误提示。
            self._show_snack(f"导出失败: {exc}")

    # ═══════════════════════════════════════════════════════════════════
    # 表单弹窗 (新增 / 编辑)
    # ═══════════════════════════════════════════════════════════════════

    def _pick_import_file(self, _e: ft.ControlEvent | None = None) -> None:
        """同步点击入口：调度异步文件选择任务。"""
        # 文件选择器未初始化时直接提示。
        if not self.import_file_picker:
            self._show_snack("文件选择器未初始化，请重试。")
            return
        # 在 Flet 事件线程中调度异步任务，避免把协程对象误当成结果。
        try:
            # 调度真正的异步文件选择逻辑。
            self.page.run_task(self._pick_import_file_async)
        # 调度失败时记录日志并提示。
        except Exception as exc:
            # 记录异常详情，满足错误必记录要求。
            log.exception("调度文件选择任务失败", error=str(exc))
            # 给用户提示失败原因。
            self._show_snack(f"打开文件选择器失败: {exc}")

    async def _pick_import_file_async(self) -> None:
        """异步打开文件选择器并处理返回文件列表。"""
        # 文件选择器未初始化时直接提示。
        if not self.import_file_picker:
            self._show_snack("文件选择器未初始化，请重试。")
            return
        # 打开系统文件选择窗口（不限制后缀，只要是文本内容即可）。
        try:
            # pick_files 在当前 Flet 版本是协程方法，需要 await。
            picked_files = await self.import_file_picker.pick_files(
                allow_multiple=False,
                dialog_title="选择账号导入文件（任意后缀，内容需为文本）",
                file_type=ft.FilePickerFileType.ANY,
            )
        # 文件选择器调用失败时提示错误。
        except Exception as exc:
            # 记录异常详情。
            log.exception("打开文件选择器失败", error=str(exc))
            # 给用户提示失败原因。
            self._show_snack(f"打开文件选择器失败: {exc}")
            return
        # 处理文件选择结果并执行导入。
        self._handle_import_file_result(picked_files)

    async def _resolve_picked_files_async(self, picked_files_awaitable: Any) -> None:
        """兼容兜底：把误传的 awaitable 结果解析成文件列表。"""
        # 等待 awaitable 真正返回文件列表。
        try:
            # 解析协程返回值。
            resolved_picked_files = await picked_files_awaitable
        # 解析失败时记录并提示。
        except Exception as exc:
            # 记录兜底解析失败异常。
            log.exception("解析文件选择协程结果失败", error=str(exc))
            # 给用户提示失败原因。
            self._show_snack(f"读取文件选择结果失败: {exc}")
            return
        # 把解析后的文件列表交给统一处理逻辑。
        self._handle_import_file_result(resolved_picked_files)

    def _handle_import_file_result(self, picked_files: Any) -> None:
        """处理文件选择结果并执行批量导入。"""
        # 兼容历史路径：若误传协程对象，自动异步解析后再继续。
        if inspect.isawaitable(picked_files):
            # 记录告警，便于后续追踪事件链路。
            log.warning("检测到未 await 的文件选择结果，自动转为异步解析")
            try:
                # 调度 awaitable 解析任务，避免当前同步函数崩溃。
                self.page.run_task(self._resolve_picked_files_async, picked_files)
            # 调度兜底任务失败时记录并提示。
            except Exception as exc:
                # 记录调度失败异常。
                log.exception("调度文件选择结果解析任务失败", error=str(exc))
                # 给用户提示失败原因。
                self._show_snack(f"读取文件选择结果失败: {exc}")
            return
        # 用户取消选择时直接返回。
        if not picked_files:
            return
        # 统一转为列表，兼容 tuple/list 等序列类型。
        picked_file_list = list(picked_files)
        # 列表为空时视为未选择文件。
        if len(picked_file_list) == 0:
            return
        # 仅取第一份文件路径。
        selected_path = str(getattr(picked_file_list[0], "path", "") or "").strip()
        # 兼容极端场景：桌面端路径为空。
        if selected_path == "":
            self._show_snack("读取文件路径失败，请重新选择文件。")
            return
        # 读取全局 vt_pwd 配置。
        vt_pwd_row = self.user_db.get_config(VT_PWD_KEY)
        # 提取全局密码值。
        vt_pwd_value = str(vt_pwd_row.get("val", "") if vt_pwd_row else "").strip()
        # 未设置全局密码时禁止导入。
        if vt_pwd_value == "":
            self._show_snack("请先到“全局设置”填写 vt_pwd，再执行批量导入。")
            return
        # 读取姓名国家 locale；未选择时回退法国。
        selected_locale = str(self.import_country_dropdown.value if self.import_country_dropdown else "fr_FR").strip() or "fr_FR"
        # 记录导入启动日志。
        log.info("开始批量导入账号", file_path=selected_path, name_locale=selected_locale)
        try:
            # 执行“先校验后写库”的导入逻辑。
            result = self._account_importer.import_from_file(
                file_path=selected_path,
                vt_pwd=vt_pwd_value,
                name_locale=selected_locale,
            )
        # 捕获导入主流程异常并提示。
        except Exception as exc:
            log.exception("批量导入执行异常", file_path=selected_path, name_locale=selected_locale, error=str(exc))
            self._show_snack(f"批量导入失败: {exc}")
            return
        # 命中格式错误时直接提示，不执行刷新。
        if result.has_validation_error():
            # 取前 3 条错误做提示摘要。
            preview = "；".join(result.validation_errors[:3])
            # 给出“未写库”明确提示。
            self._show_snack(f"导入失败：发现 {len(result.validation_errors)} 条格式错误，未写入 t_user。{preview}")
            return
        # 构造成功统计文案。
        success_msg = (
            f"导入完成：总行 {result.total_non_empty_lines}，"
            f"有效 {result.valid_line_count}，"
            f"新增 {result.inserted_count}，"
            f"已存在跳过 {result.skipped_existing_count}，"
            f"文件内重复跳过 {result.skipped_duplicate_in_file_count}"
        )
        # 写库阶段仍可能存在单条异常，单独补充提示。
        if len(result.insert_errors) > 0:
            # 取前 2 条错误做摘要。
            insert_error_preview = "；".join(result.insert_errors[:2])
            # 拼接错误统计文案。
            success_msg = f"{success_msg}，写库失败 {len(result.insert_errors)}。{insert_error_preview}"
        # 输出导入结果日志。
        log.info(
            "批量导入完成",
            file_path=selected_path,
            total_non_empty_lines=result.total_non_empty_lines,
            valid_line_count=result.valid_line_count,
            inserted_count=result.inserted_count,
            skipped_existing_count=result.skipped_existing_count,
            skipped_duplicate_in_file_count=result.skipped_duplicate_in_file_count,
            insert_error_count=len(result.insert_errors),
        )
        # 刷新账号列表展示。
        self._page_index = 1
        self.refresh(source="import_file", show_toast=False)
        # 给出导入完成提示。
        self._show_snack(success_msg)

    def _open_create_dialog(self, _e: ft.ControlEvent | None = None) -> None:
        self._open_form_dialog(dialog_title="新增账号", row=None)

    def _get_selected_name_locale(self) -> str:
        # 读取顶部“姓名国家”当前值。
        selected_locale = str(self.import_country_dropdown.value if self.import_country_dropdown else "fr_FR").strip()
        # 未选择时回退法国 locale。
        return selected_locale or "fr_FR"

    def _get_global_vt_pwd_value(self) -> str:
        # 尝试读取全局 vt_pwd 配置。
        try:
            # 获取 vt_pwd 配置行。
            vt_pwd_row = self.user_db.get_config(VT_PWD_KEY)
        # 读取异常时记录日志并返回空字符串，避免新增弹窗直接崩溃。
        except Exception as exc:
            # 记录配置读取异常。
            log.exception("读取全局 vt_pwd 配置失败", error=str(exc))
            # 返回空字符串作为安全兜底。
            return ""
        # 提取配置值并清理空白。
        return str(vt_pwd_row.get("val", "") if vt_pwd_row else "").strip()

    def _build_create_form_defaults(self) -> dict[str, str]:
        # 读取当前顶部“姓名国家”的 locale。
        selected_locale = self._get_selected_name_locale()
        # 根据当前 locale 生成默认姓名。
        generated_first_name, generated_last_name = generate_account_name(selected_locale)
        # 读取全局 vt_pwd 作为默认业务密码。
        vt_pwd_value = self._get_global_vt_pwd_value()
        # 记录新增弹窗默认值生成结果，便于排查“为什么名字不一样”。
        log.info(
            "已生成新增账号默认值",
            name_locale=selected_locale,
            has_vt_pwd=vt_pwd_value != "",
            first_name=generated_first_name,
            last_name=generated_last_name,
        )
        # 返回新增弹窗需要预填的字段。
        return {
            "first_name": generated_first_name,
            "last_name": generated_last_name,
            "pwd": vt_pwd_value,
        }

    def _open_edit_dialog(self, row: dict[str, Any]) -> None:
        # 提取 user_id，便于日志定位慢点。
        user_id = int(row.get("id", 0))
        # 记录“编辑弹窗”打开起点。
        started_at = time.monotonic()
        # 记录点击编辑按钮请求日志。
        log.info("收到编辑账号请求", user_id=user_id)
        try:
            # 打开编辑弹窗。
            self._open_form_dialog(dialog_title="编辑账号", row=row)
            # 计算打开编辑弹窗总耗时。
            elapsed_ms = int((time.monotonic() - started_at) * 1000)
            # 打开耗时较长时输出告警。
            if elapsed_ms >= 500:
                log.warning("打开编辑账号弹窗耗时较长", user_id=user_id, elapsed_ms=elapsed_ms)
            # 打开耗时正常时输出调试日志。
            else:
                log.debug("打开编辑账号弹窗完成", user_id=user_id, elapsed_ms=elapsed_ms)
        except Exception as exc:
            # 记录打开编辑弹窗失败异常栈。
            log.exception("打开编辑账号弹窗失败", user_id=user_id, error=str(exc))
            # 给用户可读提示，避免“点了没反应”。
            self._show_snack(f"打开编辑弹窗失败: {exc}")

    def _open_form_dialog(self, dialog_title: str, row: dict[str, Any] | None) -> None:
        # 记录构建弹窗起点时间。
        started_at = time.monotonic()
        self._editing_user_id = int(row.get("id", 0)) if row else None
        # 新增账号时预先生成姓名和默认 vt_pwd，编辑账号时保持原记录不变。
        initial_row = dict(row) if row else self._build_create_form_defaults()
        v = lambda k, d="": str(initial_row.get(k, d)) if initial_row else d  # noqa: E731
        self._editing_device_value = v("device", "")

        self.quick_parse_input = ft.TextField(
            label="一键识别（固定 4 段）",
            hint_text="格式: email----email_pwd----client_id----email_access_key",
            multiline=True,
            min_lines=2,
            max_lines=4,
            width=700,
        )
        self.email_account_input = ft.TextField(label="email_account（邮箱账号，唯一）", value=v("email_account"), width=340)
        self.email_pwd_input = ft.TextField(label="email_pwd（邮箱密码）", value=v("email_pwd"), width=340)
        self.client_id_input = ft.TextField(label="client_id（微软 OAuth 应用 ID）", value=v("client_id"), width=340)
        self.email_access_key_input = ft.TextField(label="email_access_key（邮箱授权码）", value=v("email_access_key"), multiline=True, min_lines=3, max_lines=6, width=700)
        self.first_name_input = ft.TextField(label="first_name（姓）", value=v("first_name"), width=340)
        self.last_name_input = ft.TextField(label="last_name（名）", value=v("last_name"), width=340)
        self.pwd_input = ft.TextField(label="pwd（vinted 密码）", value=v("pwd"), width=340)

        def _dropdown(label: str, value: str, width: int, options: list[tuple[str, str]]) -> ft.Dropdown:
            return ft.Dropdown(label=label, value=value, width=width, options=[ft.dropdown.Option(k, t) for k, t in options])

        self.status_dropdown = _dropdown("status（账号状态）", v("status", "0"), 340, [("0", "0 未使用"), ("1", "1 正在使用"), ("2", "2 已经使用"), ("3", "3 账号问题")])
        self.fb_status_dropdown = _dropdown("fb_status（fb 注册状态）", v("fb_status", "0"), 220, [("0", "0 未注册"), ("1", "1 成功"), ("2", "2 失败")])
        self.vinted_status_dropdown = _dropdown("vinted_status（vt 注册状态）", v("vinted_status", "0"), 220, [("0", "0 未注册"), ("1", "1 成功"), ("2", "2 失败")])
        self.titok_status_dropdown = _dropdown("titok_status（tt 注册状态）", v("titok_status", "0"), 220, [("0", "0 未注册"), ("1", "1 成功"), ("2", "2 失败")])
        self.msg_input = ft.TextField(label="msg（备注）", value=v("msg"), multiline=True, min_lines=2, max_lines=4, width=700)
        self.form_feedback_text = ft.Text(value="", size=12, color=ft.Colors.RED_700, visible=False)

        form_content = ft.Container(
            width=760,
            content=ft.Column(
                controls=[
                    ft.Text("以下字段新增/修改均不能为空：email_account, email_pwd, client_id, email_access_key, first_name, last_name, pwd, status", size=12, color=ft.Colors.BLUE_GREY_700),
                    ft.Text(
                        "新增账号会按顶部“姓名国家”自动生成姓名，并自动带入全局 vt_pwd；打开弹窗后可直接查看和修改。",
                        size=12,
                        color=ft.Colors.BLUE_GREY_700,
                    ) if row is None else ft.Container(),
                    ft.Text(
                        "一键识别说明：只支持粘贴 email----email_pwd----client_id----email_access_key",
                        size=12,
                        color=ft.Colors.BLUE_GREY_700,
                    ),
                    self.form_feedback_text,
                    self.quick_parse_input,
                    ft.Row(
                        [ft.FilledButton("识别并填充", icon=ft.Icons.AUTO_FIX_HIGH, on_click=self._recognize_and_fill_form)],
                        alignment=ft.MainAxisAlignment.END,
                    ),
                    ft.Row([self.email_account_input, self.email_pwd_input], spacing=10),
                    ft.Row([self.client_id_input], spacing=10),
                    self.email_access_key_input,
                    ft.Row([self.first_name_input, self.last_name_input], spacing=10),
                    ft.Row([self.pwd_input, self.status_dropdown], spacing=10),
                    ft.Row([self.fb_status_dropdown, self.vinted_status_dropdown, self.titok_status_dropdown], spacing=10),
                    self.msg_input,
                ],
                spacing=10,
                scroll=ft.ScrollMode.AUTO,
                height=450,
            ),
        )

        dialog = ft.AlertDialog(
            modal=True,
            title=self._build_dialog_title(dialog_title),
            content=form_content,
            actions=[
                ft.TextButton("取消", on_click=lambda e: self._close_dialog(e, source="cancel_button")),
                ft.FilledButton("保存", icon=ft.Icons.SAVE, on_click=self._save_form),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            on_dismiss=self._on_dialog_dismiss,
        )
        # 生成本次弹窗追踪 ID，便于串联打开/点击/关闭日志。
        dialog_trace_id = self._next_dialog_trace_id()
        # 保存当前活动弹窗引用，便于后续显式关闭。
        self._active_dialog = dialog
        # 保存当前活动弹窗标题，便于日志定位。
        self._active_dialog_title = dialog_title
        # 保存当前活动弹窗追踪 ID。
        self._active_dialog_trace_id = dialog_trace_id
        # 调起弹窗显示。
        self.page.show_dialog(dialog)
        # 强制刷新页面，避免“点击后无反应直到下一次 update”。
        self.page.update()
        # 记录弹窗构建和展示耗时。
        elapsed_ms = int((time.monotonic() - started_at) * 1000)
        log.info(
            "账号弹窗已展示",
            dialog_title=dialog_title,
            dialog_trace_id=dialog_trace_id,
            dialog_instance_id=hex(id(dialog)),
            editing_user_id=self._editing_user_id,
            elapsed_ms=elapsed_ms,
        )

    @staticmethod
    def _normalize_access_key(raw_key: str) -> str:
        """把授权码中的换行和空白去掉，兼容复制时自动换行。"""
        # 去掉所有空白字符，避免长密钥粘贴后被换行或空格污染。
        return re.sub(r"\s+", "", str(raw_key or "").strip())

    def _parse_quick_text(self, raw_text: str) -> tuple[str, str, str, str]:
        """解析一键识别字符串，返回邮箱、邮箱密码、client_id、邮箱授权码。"""
        # 先做基础清洗，避免空输入。
        clean_text = str(raw_text or "").strip()
        if not clean_text:
            raise ValueError("识别文本不能为空")

        # 最多按 3 次分割，确保后半段密钥里即使出现 ---- 也不会继续被拆。
        parts = [part.strip() for part in clean_text.split("----", 3)]
        if len(parts) != 4:
            raise ValueError("格式错误：必须是 4 段 email----email_pwd----client_id----email_access_key")

        # 固定前两段：邮箱账号 + 邮箱密码。
        email_account = parts[0]
        email_pwd = parts[1]
        # 第三段固定是 client_id。
        client_id = parts[2]
        # 第四段固定是邮箱授权码。
        access_key = parts[3]

        # 授权码清洗，去掉复制带来的换行和空格。
        access_key = self._normalize_access_key(access_key)

        # 核心字段必须有值，避免把空值写入数据库。
        if not email_account or not email_pwd or not client_id or not access_key:
            raise ValueError("格式错误：email_account、email_pwd、client_id、email_access_key 不能为空")
        return email_account, email_pwd, client_id, access_key

    def _recognize_and_fill_form(self, _e: ft.ControlEvent | None = None) -> None:
        """执行一键识别并把结果写入表单控件。"""
        try:
            # 读取原始识别文本。
            raw_text = str(self.quick_parse_input.value if self.quick_parse_input else "").strip()
            email_account, email_pwd, client_id, access_key = self._parse_quick_text(raw_text)

            # 自动填充邮箱账号。
            if self.email_account_input:
                self.email_account_input.value = email_account
            # 自动填充邮箱密码。
            if self.email_pwd_input:
                self.email_pwd_input.value = email_pwd
            # 自动填充 client_id。
            if self.client_id_input:
                self.client_id_input.value = client_id
            # 自动填充邮箱授权码。
            if self.email_access_key_input:
                self.email_access_key_input.value = access_key

            # 刷新弹窗 UI，让用户立即看到填充结果。
            self.page.update()
            # 记录识别填充成功日志，避免在账号弹窗上方再压一个 SnackBar 干扰后续关闭。
            log.info(
                "识别填充账号表单成功",
                dialog_trace_id=self._active_dialog_trace_id,
                dialog_title=self._active_dialog_title,
                editing_user_id=self._editing_user_id,
            )
            # 在弹窗内部展示识别结果，避免底部提示条遮挡“取消”按钮。
            self._set_form_feedback("识别成功：已填充邮箱、邮箱密码、client_id 和邮箱授权码。", is_error=False)
        except Exception as exc:
            # 识别失败时在弹窗内部展示错误，避免底部提示条遮挡操作区。
            self._set_form_feedback(f"识别失败: {exc}", is_error=True)

    def _next_dialog_trace_id(self) -> str:
        """生成递增的弹窗追踪 ID。"""
        # 递增弹窗打开序号，便于和日志串联。
        self._dialog_open_seq += 1
        # 返回带前缀的追踪 ID，方便搜索。
        return f"dialog-{self._dialog_open_seq}"

    @staticmethod
    def _get_event_control_name(_e: ft.ControlEvent | None) -> str:
        """提取事件来源控件名，便于日志查看。"""
        # 没有事件对象时返回 unknown。
        if _e is None:
            # 返回默认值，避免日志字段为空。
            return "unknown"
        # 提取事件关联控件。
        control = getattr(_e, "control", None)
        # 控件不存在时返回 unknown。
        if control is None:
            # 返回默认值，避免访问空对象。
            return "unknown"
        # 返回控件类型名称，方便快速判断点击来源。
        return control.__class__.__name__

    def _set_form_feedback(self, message: str, is_error: bool) -> None:
        """在账号弹窗内部展示提示文本。"""
        # 弹窗提示控件未初始化时直接返回，避免在非表单场景误调用。
        if self.form_feedback_text is None:
            return
        # 清洗提示文本，避免 None 混入 UI。
        safe_message = str(message).strip()
        # 写入提示文本内容。
        self.form_feedback_text.value = safe_message
        # 有提示文本时才展示控件，避免空白占位。
        self.form_feedback_text.visible = safe_message != ""
        # 根据成功或失败切换颜色，方便用户快速区分。
        self.form_feedback_text.color = ft.Colors.RED_700 if is_error else ft.Colors.BLUE_GREY_700
        try:
            # 优先只刷新表单提示控件，减少整页闪动。
            self.form_feedback_text.update()
        except Exception as exc:
            # 记录局部刷新失败日志，并回退整页刷新。
            log.exception(
                "刷新账号弹窗提示文本失败，准备回退整页刷新",
                dialog_trace_id=self._active_dialog_trace_id,
                dialog_title=self._active_dialog_title,
                error=str(exc),
            )
            try:
                # 回退整页刷新，保证提示内容尽量可见。
                self.page.update()
            except Exception:
                # 整页刷新失败时继续记录异常，避免吞掉真正错误。
                log.exception(
                    "整页刷新账号弹窗提示文本失败",
                    dialog_trace_id=self._active_dialog_trace_id,
                    dialog_title=self._active_dialog_title,
                )

    def _close_dialog(self, _e: ft.ControlEvent | None = None, source: str = "manual_close") -> None:
        # 记录收到关闭请求的日志，先确认点击事件是否进入 Python 层。
        log.info(
            "收到关闭账号弹窗请求",
            source=source,
            dialog_trace_id=self._active_dialog_trace_id,
            dialog_title=self._active_dialog_title,
            dialog_instance_id=hex(id(self._active_dialog)) if self._active_dialog is not None else "",
            event_control=self._get_event_control_name(_e),
            editing_user_id=self._editing_user_id,
        )
        # 调用统一弹窗关闭方法，确保不同 Flet 版本都能稳定关闭。
        self._dismiss_active_dialog(reason=source)

    def _build_dialog_title(self, dialog_title: str) -> ft.Control:
        """构建带关闭按钮的弹窗标题栏。"""
        # 使用标题栏右上角关闭按钮，方便保存失败后手动关闭弹窗。
        return ft.Row(
            controls=[
                # 左侧展示标题文本，并占满剩余宽度。
                ft.Text(dialog_title, size=18, weight=ft.FontWeight.W_600, expand=True),
                # 右侧提供显式关闭按钮，避免只能依赖取消按钮关闭。
                ft.IconButton(
                    icon=ft.Icons.CLOSE,
                    tooltip="关闭弹窗",
                    on_click=lambda e: self._close_dialog(e, source="title_close_button"),
                ),
            ],
            # 标题和关闭按钮左右分布。
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            # 垂直居中对齐，避免标题和图标上下跳动。
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            # 标题栏本身不额外撑开高度。
            tight=True,
        )

    def _on_dialog_dismiss(self, _e: ft.ControlEvent | None = None) -> None:
        """处理弹窗实际关闭后的状态清理。"""
        # 从事件中提取被关闭的弹窗实例，便于和当前活动弹窗做一致性判断。
        dismissed_dialog = _e.control if (_e is not None and isinstance(getattr(_e, "control", None), ft.AlertDialog)) else None
        # 提前记录 dismiss 回调日志，确认关闭事件是否真正到达框架层。
        log.info(
            "收到账号弹窗 on_dismiss 回调",
            dialog_trace_id=self._active_dialog_trace_id,
            dialog_title=self._active_dialog_title,
            dialog_instance_id=hex(id(dismissed_dialog)) if dismissed_dialog is not None else "",
            active_dialog_instance_id=hex(id(self._active_dialog)) if self._active_dialog is not None else "",
            editing_user_id=self._editing_user_id,
        )
        # 当回调来自旧弹窗且当前已有新弹窗时，跳过清理，避免把新弹窗引用误清空。
        if dismissed_dialog is not None and self._active_dialog is not None and dismissed_dialog is not self._active_dialog:
            # 记录“忽略旧回调”的调试日志，辅助定位偶发关闭失效问题。
            log.debug(
                "忽略非活动弹窗的关闭回调",
                dialog_trace_id=self._active_dialog_trace_id,
                dialog_title=self._active_dialog_title,
                editing_user_id=self._editing_user_id,
                has_active_dialog=True,
            )
            return
        # 弹窗真正关闭后清空活动弹窗引用，避免残留旧实例。
        self._active_dialog = None
        # 清空活动弹窗标题，避免旧值污染下一次日志。
        self._active_dialog_title = ""
        # 清空活动弹窗追踪 ID，避免旧值污染下一次日志。
        self._active_dialog_trace_id = None
        # 记录关闭完成日志，便于排查“为何弹窗没有消失”。
        log.debug("账号弹窗已完成关闭", editing_user_id=self._editing_user_id)

    def _dismiss_active_dialog(self, reason: str) -> None:
        # 优先关闭当前账号弹窗实例本身，避免 SnackBar 仍在栈顶时误关掉提示条而不是表单。
        # 先保存当前活动弹窗引用，供后续定向关闭和异常兜底使用。
        current_dialog = self._active_dialog
        # 先保存当前弹窗标题，避免后面清空引用后日志丢上下文。
        dialog_title = self._active_dialog_title
        # 先保存当前弹窗追踪 ID，避免后面清空引用后日志丢上下文。
        dialog_trace_id = self._active_dialog_trace_id
        # 记录开始执行关闭动作的日志。
        log.info(
            "开始关闭账号弹窗",
            reason=reason,
            dialog_trace_id=dialog_trace_id,
            dialog_title=dialog_title,
            dialog_instance_id=hex(id(current_dialog)) if current_dialog is not None else "",
            editing_user_id=self._editing_user_id,
        )
        # 先标记是否已成功触发定向关闭。
        targeted_close_done = False
        # 持有活动弹窗引用时，优先对该实例执行定向关闭。
        if current_dialog is not None:
            # 把当前弹窗 open 状态置为 False。
            current_dialog.open = False
            try:
                # 刷新当前弹窗控件，触发关闭。
                current_dialog.update()
                # 标记定向关闭已执行完成。
                targeted_close_done = True
                # 记录定向关闭成功日志。
                log.info(
                    "定向关闭账号弹窗已执行",
                    reason=reason,
                    dialog_trace_id=dialog_trace_id,
                    dialog_title=dialog_title,
                    dialog_instance_id=hex(id(current_dialog)),
                    editing_user_id=self._editing_user_id,
                )
            # 兜底刷新失败时记录异常，但继续尝试刷新整页。
            except Exception as exc:
                # 记录定向关闭失败日志，后续继续尝试关闭栈顶弹窗兜底。
                log.exception(
                    "定向关闭账号弹窗失败，准备回退到 pop_dialog",
                    reason=reason,
                    dialog_trace_id=dialog_trace_id,
                    dialog_title=dialog_title,
                    error=str(exc),
                )

        # 定向关闭未执行成功时，再回退到关闭栈顶弹窗。
        if not targeted_close_done:
            try:
                # 关闭当前最上层弹窗，兼容活动引用丢失或实例更新失败的场景。
                popped_dialog = self.page.pop_dialog()
                # 记录官方弹窗栈关闭结果。
                log.info(
                    "page.pop_dialog 执行完成",
                    reason=reason,
                    dialog_trace_id=dialog_trace_id,
                    dialog_title=dialog_title,
                    popped_dialog_instance_id=hex(id(popped_dialog)) if popped_dialog is not None else "",
                    editing_user_id=self._editing_user_id,
                )
            # 关闭失败时记录异常，避免吞掉真正错误。
            except Exception as exc:
                # 记录弹窗栈关闭异常日志。
                log.exception(
                    "关闭账号弹窗失败，pop_dialog 也执行异常",
                    reason=reason,
                    dialog_trace_id=dialog_trace_id,
                    dialog_title=dialog_title,
                    error=str(exc),
                )
                # 标记当前没有拿到官方关闭结果。
                popped_dialog = None
            # 栈顶关闭未命中时记录告警，便于继续排查异常时序。
            if popped_dialog is None:
                log.warning(
                    "关闭账号弹窗未命中：定向关闭失败且弹窗栈为空",
                    reason=reason,
                    dialog_trace_id=dialog_trace_id,
                    dialog_title=dialog_title,
                    editing_user_id=self._editing_user_id,
                )
        else:
            # 定向关闭成功时，不再额外 pop 栈顶，避免误关闭仍在展示的 SnackBar。
            log.info(
                "账号弹窗已通过定向关闭完成，无需继续 pop_dialog",
                reason=reason,
                dialog_trace_id=dialog_trace_id,
                dialog_title=dialog_title,
                editing_user_id=self._editing_user_id,
            )

        # 清空当前活动弹窗引用，避免后续仍指向旧实例。
        self._active_dialog = None
        # 清空当前活动弹窗标题，避免旧值影响下一次日志。
        self._active_dialog_title = ""
        # 清空当前活动弹窗追踪 ID，避免旧值影响下一次日志。
        self._active_dialog_trace_id = None
        try:
            # 再刷新整页一次，确保关闭状态及时反映到界面。
            self.page.update()
            # 记录整页刷新成功，确认关闭链路走完。
            log.info(
                "关闭账号弹窗后页面刷新完成",
                reason=reason,
                dialog_trace_id=dialog_trace_id,
                dialog_title=dialog_title,
                editing_user_id=self._editing_user_id,
            )
        # 整页刷新失败时仅记录日志，不阻断后续逻辑。
        except Exception as exc:
            # 记录页面刷新失败日志。
            log.exception(
                "关闭账号弹窗后刷新页面失败",
                reason=reason,
                dialog_trace_id=dialog_trace_id,
                dialog_title=dialog_title,
                error=str(exc),
            )

    async def _refresh_after_dialog_close(self, source: str, success_message: str) -> None:
        """在弹窗关闭后异步刷新列表，避免关闭动作被立即重绘打断。"""
        try:
            # 让出一个事件循环周期，优先完成弹窗关闭渲染。
            await asyncio.sleep(0)
            # 刷新账号列表，展示最新数据。
            self.refresh(source=source, show_toast=False)
            # 刷新成功后提示用户操作完成。
            self._show_snack(success_message)
        except Exception as exc:
            # 记录异步刷新失败日志，便于排查关闭后的后续问题。
            log.exception("弹窗关闭后刷新账号列表失败", source=source, error=str(exc))
            # 即便刷新失败，也把主操作结果反馈给用户。
            self._show_snack(f"{success_message}（列表刷新失败: {exc}）")

    def _collect_form_record(self) -> UserRecord:
        g = lambda ctrl: str(ctrl.value if ctrl else "").strip()  # noqa: E731
        return UserRecord(
            email_account=g(self.email_account_input),
            email_pwd=g(self.email_pwd_input),
            client_id=g(self.client_id_input),
            email_access_key=g(self.email_access_key_input),
            status=g(self.status_dropdown),
            first_name=g(self.first_name_input),
            last_name=g(self.last_name_input),
            pwd=g(self.pwd_input),
            fb_status=g(self.fb_status_dropdown) or "0",
            vinted_status=g(self.vinted_status_dropdown) or "0",
            titok_status=g(self.titok_status_dropdown) or "0",
            device=self._editing_device_value,
            msg=g(self.msg_input),
        )

    def _save_form(self, _e: ft.ControlEvent | None = None) -> None:
        try:
            # 清空上一次表单提示，避免旧错误残留影响本次判断。
            self._set_form_feedback("", is_error=False)
            # 记录保存按钮点击，便于和关闭按钮日志对比事件是否进入 Python。
            log.info(
                "收到保存账号请求",
                dialog_trace_id=self._active_dialog_trace_id,
                dialog_title=self._active_dialog_title,
                dialog_instance_id=hex(id(self._active_dialog)) if self._active_dialog is not None else "",
                event_control=self._get_event_control_name(_e),
                editing_user_id=self._editing_user_id,
            )
            record = self._collect_form_record()
            if self._editing_user_id is None:
                new_id = self.user_db.create_user(record)
                self._page_index = 1
                self._dismiss_active_dialog(reason="create_save_success")
                self.page.run_task(self._refresh_after_dialog_close, "create", f"新增账号成功，ID={new_id}")
                return
            affected = self.user_db.update_user_by_id(self._editing_user_id, record)
            if affected <= 0:
                raise RuntimeError("保存失败：目标账号不存在，可能已被删除")
            self._dismiss_active_dialog(reason="update_save_success")
            self.page.run_task(self._refresh_after_dialog_close, "update", "账号修改成功。")
        except Exception as exc:
            log.exception("保存账号失败", editing_user_id=self._editing_user_id)
            # 保存失败时在弹窗内部展示错误，避免底部提示条遮挡“取消”按钮。
            self._set_form_feedback(f"保存账号失败: {exc}", is_error=True)

    # ═══════════════════════════════════════════════════════════════════
    # 删除
    # ═══════════════════════════════════════════════════════════════════

    def _confirm_delete(self, user_id: int, email_account: str) -> None:
        safe_id = int(user_id)
        if safe_id <= 0:
            self._show_snack("删除失败：无效的账号 ID")
            return
        dialog = ft.AlertDialog(
            modal=True,
            title=self._build_dialog_title("删除账号"),
            content=ft.Text(f"确认删除账号：{email_account}（ID={safe_id}）？"),
            actions=[
                ft.TextButton("取消", on_click=lambda e: self._close_dialog(e, source="delete_cancel_button")),
                ft.FilledButton("确认删除", icon=ft.Icons.DELETE_FOREVER, on_click=lambda e, uid=safe_id: self._delete(uid)),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            on_dismiss=self._on_dialog_dismiss,
        )
        # 生成删除弹窗追踪 ID，便于日志串联。
        dialog_trace_id = self._next_dialog_trace_id()
        # 保存当前活动弹窗引用，便于后续显式关闭。
        self._active_dialog = dialog
        # 保存删除弹窗标题，便于日志定位。
        self._active_dialog_title = "删除账号"
        # 保存删除弹窗追踪 ID。
        self._active_dialog_trace_id = dialog_trace_id
        # 调起删除确认弹窗显示。
        self.page.show_dialog(dialog)
        # 强制刷新页面，避免“点击删除后弹窗延迟显示”。
        self.page.update()
        # 记录删除弹窗打开日志。
        log.info(
            "删除账号弹窗已展示",
            dialog_trace_id=dialog_trace_id,
            dialog_title="删除账号",
            dialog_instance_id=hex(id(dialog)),
            user_id=safe_id,
            email_account=email_account,
        )

    def _delete(self, user_id: int) -> None:
        safe_id = int(user_id)
        try:
            affected = self.user_db.delete_user_by_id(safe_id)
            self._dismiss_active_dialog(reason="delete_success")
            if affected <= 0:
                self._show_snack("删除失败：目标账号不存在")
                return
            self.page.run_task(self._refresh_after_dialog_close, "delete", f"账号已删除（ID={safe_id}）。")
        except Exception as exc:
            log.exception("删除账号失败", user_id=safe_id)
            self._show_snack(f"删除账号失败: {exc}")
