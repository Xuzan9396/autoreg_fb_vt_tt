"""账号列表 Tab 模块。"""

from __future__ import annotations

import re
import time
from typing import Any, Callable

import flet as ft

from autovt.gui.account_importer import AccountFileImporter, NAME_COUNTRY_OPTIONS
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
        self._editing_device_value = ""

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
            # 使用占位提示，避免浮动 label 与描边边框重叠导致显示异常。
            hint_text="选择姓名国家",
            # 默认使用法国姓名。
            value="fr_FR",
            # 控件宽度。
            width=180,
            # 选项列表（法国、英国等）。
            options=[ft.dropdown.Option(locale, label) for label, locale in NAME_COUNTRY_OPTIONS],
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
                self.import_country_dropdown,
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
        if self._refreshing or not self.list_column:
            return
        self._refreshing = True
        try:
            email_kw, status_f, fb_f, vinted_f, titok_f = self._get_filter_values()
            total_count = self.user_db.count_users_filtered(
                email_keyword=email_kw, status=status_f,
                fb_status=fb_f, vinted_status=vinted_f, titok_status=titok_f,
            )
            total_pages = max((int(total_count) + ACCOUNT_PAGE_SIZE - 1) // ACCOUNT_PAGE_SIZE, 1)
            self._total = int(total_count)
            self._total_pages = int(total_pages)

            if self._page_index > self._total_pages:
                self._page_index = self._total_pages
            if self._page_index < 1:
                self._page_index = 1

            rows = self.user_db.list_users_page_filtered(
                page=self._page_index, page_size=ACCOUNT_PAGE_SIZE,
                email_keyword=email_kw, status=status_f,
                fb_status=fb_f, vinted_status=vinted_f, titok_status=titok_f,
            )
            self._render_rows(rows)
            self._update_summary(self._total, len(rows))
            self._update_pagination()
            if source == "manual" and show_toast:
                self._show_snack(f"账号列表已刷新，第 {self._page_index} 页共 {len(rows)} 条。")
            self.page.update()
        except Exception as exc:
            log.exception("刷新账号列表失败", source=source)
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

    # ═══════════════════════════════════════════════════════════════════
    # 表单弹窗 (新增 / 编辑)
    # ═══════════════════════════════════════════════════════════════════

    async def _pick_import_file(self, _e: ft.ControlEvent | None = None) -> None:
        """打开文件选择器，选择要导入的文本文件。"""
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

    def _handle_import_file_result(self, picked_files: list[Any] | None) -> None:
        """处理文件选择结果并执行批量导入。"""
        # 用户取消选择时直接返回。
        if not picked_files:
            return
        # 仅取第一份文件路径。
        selected_path = str(getattr(picked_files[0], "path", "") or "").strip()
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

    def _open_edit_dialog(self, row: dict[str, Any]) -> None:
        self._open_form_dialog(dialog_title="编辑账号", row=row)

    def _open_form_dialog(self, dialog_title: str, row: dict[str, Any] | None) -> None:
        self._editing_user_id = int(row.get("id", 0)) if row else None
        v = lambda k, d="": str(row.get(k, d)) if row else d  # noqa: E731
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

        form_content = ft.Container(
            width=760,
            content=ft.Column(
                controls=[
                    ft.Text("以下字段新增/修改均不能为空：email_account, email_pwd, client_id, email_access_key, first_name, last_name, pwd, status", size=12, color=ft.Colors.BLUE_GREY_700),
                    ft.Text(
                        "一键识别说明：只支持粘贴 email----email_pwd----client_id----email_access_key",
                        size=12,
                        color=ft.Colors.BLUE_GREY_700,
                    ),
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
            title=dialog_title,
            content=form_content,
            actions=[
                ft.TextButton("取消", on_click=self._close_dialog),
                ft.FilledButton("保存", icon=ft.Icons.SAVE, on_click=self._save_form),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.show_dialog(dialog)

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
            # 给出识别结果提示。
            self._show_snack("识别成功：已填充邮箱、邮箱密码、client_id 和邮箱授权码。")
        except Exception as exc:
            self._show_snack(f"识别失败: {exc}")

    def _close_dialog(self, _e: ft.ControlEvent | None = None) -> None:
        self.page.pop_dialog()

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
            record = self._collect_form_record()
            if self._editing_user_id is None:
                new_id = self.user_db.create_user(record)
                self._page_index = 1
                self.page.pop_dialog()
                self.refresh(source="create", show_toast=False)
                self._show_snack(f"新增账号成功，ID={new_id}")
                return
            affected = self.user_db.update_user_by_id(self._editing_user_id, record)
            if affected <= 0:
                raise RuntimeError("保存失败：目标账号不存在，可能已被删除")
            self.page.pop_dialog()
            self.refresh(source="update", show_toast=False)
            self._show_snack("账号修改成功。")
        except Exception as exc:
            log.exception("保存账号失败", editing_user_id=self._editing_user_id)
            self._show_snack(f"保存账号失败: {exc}")

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
            title="删除账号",
            content=ft.Text(f"确认删除账号：{email_account}（ID={safe_id}）？"),
            actions=[
                ft.TextButton("取消", on_click=self._close_dialog),
                ft.FilledButton("确认删除", icon=ft.Icons.DELETE_FOREVER, on_click=lambda e, uid=safe_id: self._delete(uid)),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.show_dialog(dialog)

    def _delete(self, user_id: int) -> None:
        safe_id = int(user_id)
        try:
            affected = self.user_db.delete_user_by_id(safe_id)
            self.page.pop_dialog()
            if affected <= 0:
                self._show_snack("删除失败：目标账号不存在")
                return
            self.refresh(source="delete", show_toast=False)
            self._show_snack(f"账号已删除（ID={safe_id}）。")
        except Exception as exc:
            log.exception("删除账号失败", user_id=safe_id)
            self._show_snack(f"删除账号失败: {exc}")
