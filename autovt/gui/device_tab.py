"""设备列表 Tab 模块。"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Callable

import flet as ft

from autovt.gui.device_refresh_coordinator import (
    DEVICE_LOG_MAX_LINES,
    DeviceRefreshCoordinator,
    DeviceRefreshSnapshot,
)
from autovt.gui.helpers import DeviceViewModel, state_color, state_text
from autovt.logs import get_logger
from autovt.multiproc.manager import DeviceProcessManager

log = get_logger("gui.device")


class DeviceTab:
    """封装设备列表 Tab 的构建、刷新和渲染逻辑。"""

    def __init__(
        self,
        page: ft.Page,
        manager: DeviceProcessManager,
        coordinator: DeviceRefreshCoordinator,
        show_snack: Callable[[str], None],
        run_action: Callable[[str, Callable[[], str | list[str]]], None],
    ) -> None:
        self.page = page
        self.manager = manager
        self._coordinator = coordinator
        self._show_snack = show_snack
        self._run_action = run_action

        self._refreshing = False
        self._last_online_serials: set[str] = set()
        # 缓存当前日志框的最新消息列表，供“一键复制”直接使用。
        self._latest_log_messages: list[str] = []
        # 是否跟随最新日志到底部；用户手动上滑后会临时关闭。
        self._logs_follow_latest = True
        # 是否正在执行日志清空任务，避免重复并发改写日志文件。
        self._clearing_logs = False
        # 缓存最近一次已应用的快照，便于失败时继续维持界面稳定。
        self._last_snapshot: DeviceRefreshSnapshot | None = None

        self.summary_text: ft.Text | None = None
        self.last_refresh_text: ft.Text | None = None
        self.device_list_column: ft.Column | None = None
        self.log_list_view: ft.ListView | None = None
        # 日志区元信息文本（条数 + 最近刷新时间）。
        self.log_meta_text: ft.Text | None = None
        # 注册方式下拉框控件引用，供后续启动动作读取当前选择。
        self.register_mode_dropdown: ft.Dropdown | None = None
        # 缓存当前注册方式选择值，默认空字符串表示“未选择”。
        self.selected_register_mode = ""

    def build(self) -> ft.Control:
        """构建设备列表 Tab 的内容。"""
        self.summary_text = ft.Text(
            value="在线设备: 0 | 运行进程: 0",
            size=14,
            weight=ft.FontWeight.W_600,
            color=ft.Colors.BLUE_GREY_900,
        )
        self.last_refresh_text = ft.Text(
            value="最近刷新: -",
            size=12,
            color=ft.Colors.BLUE_GREY_600,
        )
        self.device_list_column = ft.Column(
            controls=[ft.Text("正在读取设备列表...", color=ft.Colors.BLUE_GREY_600)],
            spacing=10,
            # 设备列表滚动条常驻，避免误以为不可滚动。
            scroll=ft.ScrollMode.ALWAYS,
            expand=True,
        )
        # 创建设备日志列表容器，并切换为更适合大量行渲染的 ListView。
        self.log_list_view = ft.ListView(
            # 初始占位文本改成白字，匹配黑底日志框。
            controls=[ft.Text("日志待加载...", color=ft.Colors.WHITE70)],
            # 日志行间距设置为 4，提升可读性。
            spacing=4,
            # 日志列表滚动条常驻显示，避免“看不清是否可滚动”。
            scroll=ft.ScrollMode.ALWAYS,
            # 开启按需构建，减少大日志列表一次性创建控件的压力。
            build_controls_on_demand=True,
            # 为日志列表提供原型项，帮助 Flet 估算布局成本。
            prototype_item=ft.Container(
                padding=ft.padding.symmetric(horizontal=8, vertical=4),
                content=ft.Row(
                    controls=[
                        ft.Container(
                            width=92,
                            content=ft.Text(
                                "00:00:00.000",
                                size=11,
                                color=ft.Colors.CYAN_200,
                                font_family="monospace",
                            ),
                        ),
                        ft.Text(
                            "示例日志",
                            size=12,
                            color=ft.Colors.WHITE,
                            font_family="monospace",
                            expand=True,
                        ),
                    ],
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.START,
                ),
            ),
            # 关闭强制自动滚动，改为“默认跟随最新 + 用户上滑可查看历史”。
            auto_scroll=False,
            # 监听日志滚动位置，判断是否继续跟随最新。
            on_scroll=self._on_log_scroll,
            # 日志容器拉伸占满日志区域高度。
            expand=True,
        )
        # 初始化日志区的右上角元信息文案。
        self.log_meta_text = ft.Text(
            # 默认显示 0 条和空更新时间。
            "0 条 | 最近更新: -",
            # 使用较小字号，避免与标题抢视觉层级。
            size=11,
            # 黑底场景下使用半透明白字。
            color=ft.Colors.WHITE70,
        )
        # 创建设备页顶部“注册方式”下拉框，默认保持空值等待用户显式选择。
        self.register_mode_dropdown = ft.Dropdown(
            # 使用标签明确说明该控件用途。
            label="注册方式",
            # 默认空字符串，对应“选择注册方式”。
            value="",
            # 控件宽度固定，避免随窗口伸缩影响按钮布局。
            width=180,
            # 下拉选项固定为“空 / Facebook / Vinted”三种。
            options=[
                # 空值选项作为默认占位提示。
                ft.dropdown.Option("", "选择注册方式"),
                # Facebook 注册模式选项。
                ft.dropdown.Option("facebook", "facebook注册"),
                # Vinted 注册模式选项。
                ft.dropdown.Option("vinted", "vinted注册"),
            ],
        )
        # 顶部操作区改为可换行 Row，按钮按内容宽度展示，避免被网格拉得过长。
        top_actions = ft.Row(
            controls=[
                # 刷新设备按钮（按内容宽度显示）。
                ft.FilledButton("刷新设备", icon=ft.Icons.REFRESH, on_click=lambda e: self.refresh(source="manual", show_toast=True)),
                # 注册方式下拉框放在“启动全部”前面，供用户先选择当前批次模式。
                self.register_mode_dropdown,
                # 启动全部按钮（按内容宽度显示）。
                ft.FilledButton("启动全部", icon=ft.Icons.PLAY_ARROW, on_click=lambda e: self._handle_start_all()),
                # 停止全部按钮（按内容宽度显示）。
                ft.FilledButton("停止全部", icon=ft.Icons.STOP, on_click=lambda e: self._run_action("停止全部", self.manager.stop_all)),
                # 暂停全部按钮（按内容宽度显示）。
                ft.FilledButton("暂停全部", icon=ft.Icons.PAUSE, on_click=lambda e: self._run_action("暂停全部", lambda: self.manager.send_command_all("pause"))),
                # 恢复全部按钮（按内容宽度显示）。
                ft.FilledButton("恢复全部", icon=ft.Icons.PLAY_CIRCLE_FILL, on_click=lambda e: self._run_action("恢复全部", lambda: self.manager.send_command_all("resume"))),
                # 新增“一键卸载 Facebook”按钮，作用于全部在线设备。
                ft.FilledButton(
                    "一键删除FB",
                    icon=ft.Icons.DELETE,
                    on_click=lambda e: self._run_action("一键删除FB", self.manager.uninstall_facebook_all),
                ),
                # 新增“一键安装 Facebook”按钮，使用 apks/facebook.apk 安装到全部在线设备。
                ft.FilledButton(
                    "一键安装FB",
                    icon=ft.Icons.DOWNLOAD,
                    on_click=lambda e: self._run_action("一键安装FB", self.manager.install_facebook_all),
                ),
                # 新增“一键卸载 Vinted”按钮，作用于全部在线设备。
                ft.FilledButton(
                    "一键删除VT",
                    icon=ft.Icons.DELETE,
                    on_click=lambda e: self._run_action("一键删除VT", self.manager.uninstall_vinted_all),
                ),
                # 新增“一键安装 Vinted”按钮，使用 apks/vinted.apk 安装到全部在线设备。
                ft.FilledButton(
                    "一键安装VT",
                    icon=ft.Icons.DOWNLOAD,
                    on_click=lambda e: self._run_action("一键安装VT", self.manager.install_vinted_all),
                ),
                # 新增“一键安装输入法”按钮，安装 Yosemite.apk（手动设默认）。
                ft.FilledButton(
                    "一键安装输入法",
                    icon=ft.Icons.KEYBOARD,
                    on_click=lambda e: self._run_action("一键安装输入法", self.manager.install_yosemite_all),
                ),
            ],
            # 允许按钮在宽度不足时自动换行。
            wrap=True,
            spacing=8,
            run_spacing=8,
        )

        body = ft.Column(
            controls=[
                top_actions,
                ft.Row([self.summary_text, self.last_refresh_text], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ft.Divider(height=1, color=ft.Colors.BLUE_GREY_100),
                ft.Container(
                    # 设备列表区固定较小高度，优先给日志区更多空间。
                    height=240,
                    padding=12,
                    border_radius=12,
                    border=ft.border.all(1, ft.Colors.BLUE_GREY_100),
                    bgcolor=ft.Colors.WHITE,
                    content=self.device_list_column,
                ),
                # 设备日志框容器。
                ft.Container(
                    # 日志区占据剩余全部高度，实现随窗口变化的自适应拉伸。
                    expand=True,
                    # 容器内边距。
                    padding=12,
                    # 圆角边框。
                    border_radius=12,
                    # 黑底下改深灰边框，边界更清晰。
                    border=ft.border.all(1, ft.Colors.BLUE_GREY_800),
                    # 按需求设置日志框黑色背景。
                    bgcolor=ft.Colors.BLACK,
                    # 日志区单独覆盖滚动条主题，确保黑底下清晰可见。
                    theme=ft.Theme(
                        scrollbar_theme=ft.ScrollbarTheme(
                            # 滑块常驻显示。
                            thumb_visibility=True,
                            # 轨道常驻显示。
                            track_visibility=True,
                            # 滚动条略加粗提高可见度。
                            thickness=10,
                            # 圆角滚动条样式更协调。
                            radius=8,
                            # 滑块改为亮色，黑底高对比。
                            thumb_color=ft.Colors.WHITE70,
                            # 轨道使用浅白半透明。
                            track_color=ft.Colors.with_opacity(0.18, ft.Colors.WHITE),
                            # 轨道边框进一步增强可视性。
                            track_border_color=ft.Colors.with_opacity(0.35, ft.Colors.WHITE),
                        )
                    ),
                    # 日志容器内部采用“头部工具栏 + 列表”的结构。
                    content=ft.Column(
                        controls=[
                            # 日志头部：标题、元信息、复制按钮。
                            ft.Row(
                                controls=[
                                    # 左侧标题区。
                                    ft.Row(
                                        controls=[
                                            # 标题前放终端图标增强识别。
                                            ft.Icon(ft.Icons.TERMINAL, color=ft.Colors.WHITE70, size=16),
                                            # 标题文案。
                                            ft.Text("open_settings 日志（最新 100 条）", size=13, weight=ft.FontWeight.W_600, color=ft.Colors.WHITE, expand=True),
                                        ],
                                        # 图标和标题之间留小间距。
                                        spacing=6,
                                        # 占满左侧剩余宽度。
                                        expand=True,
                                    ),
                                    # 中间显示日志条数和最近刷新时间。
                                    self.log_meta_text,
                                    # 右侧操作区：清空日志 + 复制日志。
                                    ft.Row(
                                        controls=[
                                            # 清空日志按钮。
                                            ft.OutlinedButton(
                                                "清空日志",
                                                icon=ft.Icons.DELETE_SWEEP,
                                                on_click=self._handle_clear_logs,
                                                # 按钮样式适配黑底。
                                                style=ft.ButtonStyle(
                                                    # 按钮文字改白色。
                                                    color=ft.Colors.WHITE,
                                                    # 按钮边框使用半透明白色。
                                                    side=ft.border.BorderSide(1, ft.Colors.WHITE38),
                                                ),
                                            ),
                                            # 复制日志按钮。
                                            ft.OutlinedButton(
                                                "复制日志",
                                                icon=ft.Icons.CONTENT_COPY,
                                                on_click=self._handle_copy_logs,
                                                # 按钮样式适配黑底。
                                                style=ft.ButtonStyle(
                                                    # 按钮文字改白色。
                                                    color=ft.Colors.WHITE,
                                                    # 按钮边框使用半透明白色。
                                                    side=ft.border.BorderSide(1, ft.Colors.WHITE38),
                                                ),
                                            ),
                                        ],
                                        # 两个按钮之间留出间距。
                                        spacing=8,
                                    ),
                                ],
                                # 头部三段左右分布。
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            ),
                            # 黑底下使用浅色分割线。
                            ft.Divider(height=1, color=ft.Colors.WHITE24),
                            # 日志滚动区域容器。
                            ft.Container(
                                # 拉伸占满日志面板剩余高度。
                                expand=True,
                                # 增大右侧空隙，让常驻滚动条更清晰。
                                padding=ft.padding.only(right=8),
                                # 直接挂载滚动列表，避免 SelectionArea 抢占滚轮事件。
                                content=self.log_list_view,
                            ),
                        ],
                        # 头部和内容之间保留舒适间距。
                        spacing=8,
                        # 内部列占满日志面板。
                        expand=True,
                    ),
                ),
            ],
            spacing=10,
            expand=True,
        )
        # 构建完成后先尝试回放协调器里的现有快照，避免页面创建时再单独扫盘。
        cached_snapshot = self._coordinator.get_snapshot()
        if cached_snapshot.refreshed_at > 0:
            self.apply_snapshot(snapshot=cached_snapshot, source="build", show_toast=False, update_page=False)
        # 用 expand 容器包裹根列，确保高度约束生效。
        return ft.Container(expand=True, content=body)

    def _get_selected_register_mode(self) -> str:
        """读取当前注册方式选择值，统一兼容控件值与本地缓存值。"""
        # 下拉框已创建时优先读取控件最新值。
        if self.register_mode_dropdown is not None:
            # 把当前控件值标准化为字符串，避免 None 干扰判断。
            current_value = str(self.register_mode_dropdown.value or "").strip()
            # 同步刷新缓存值，保证单设备和批量按钮读取一致。
            self.selected_register_mode = current_value
        # 返回当前缓存的注册方式值。
        return str(self.selected_register_mode or "").strip()

    def _require_register_mode(self) -> str | None:
        """启动前校验注册方式，未选择时弹提示并中断。"""
        # 读取当前用户选择的注册方式。
        register_mode = self._get_selected_register_mode()
        # 仅允许 facebook 和 vinted 两种合法值。
        if register_mode not in {"facebook", "vinted"}:
            # 界面提示用户必须先选择注册方式。
            self._show_snack("选择注册方式")
            # 记录当前非法启动尝试，便于排查操作路径。
            log.warning("启动任务前未选择合法注册方式", register_mode=register_mode)
            # 返回空值表示本次不允许继续启动。
            return None
        # 返回合法注册方式。
        return register_mode

    def _handle_start_all(self) -> None:
        """处理“启动全部”点击事件。"""
        # 先校验注册方式，再决定是否发起后台动作。
        register_mode = self._require_register_mode()
        # 未通过校验时直接中断。
        if register_mode is None:
            return
        # 把当前注册方式透传给 manager，供后续 worker 分流。
        self._run_action("启动全部", lambda: self.manager.start_all(register_mode=register_mode))

    def _handle_start_device(self, serial: str) -> None:
        """处理单设备启动动作，保持与批量启动相同的模式校验。"""
        # 先校验注册方式。
        register_mode = self._require_register_mode()
        # 未通过校验时不触发启动。
        if register_mode is None:
            return
        # 发起单设备启动动作，并把模式值一起传递。
        self._run_action(f"{serial} 启动", lambda: self.manager.start_worker(serial, register_mode=register_mode))

    def _handle_restart_device(self, serial: str) -> None:
        """处理单设备重启动作，避免重启时丢失注册方式。"""
        # 先校验注册方式。
        register_mode = self._require_register_mode()
        # 未通过校验时不触发重启。
        if register_mode is None:
            return
        # 发起单设备重启动作，并透传当前模式。
        self._run_action(f"{serial} 重启", lambda: self.manager.restart_worker(serial, register_mode=register_mode))

    def refresh(self, source: str, show_toast: bool) -> None:
        """刷新设备列表和进程状态。"""
        # 已有刷新任务在执行时直接跳过，避免并发刷新导致界面抖动。
        if self._refreshing:
            return
        # 设备列表容器未初始化时直接返回。
        if not self.device_list_column:
            return

        # 先置位刷新中标记，防止短时间重复触发 run_task。
        self._refreshing = True
        try:
            # 把刷新任务调度到异步协程，避免在按钮事件里长时间阻塞。
            self.page.run_task(self._refresh_async, source, show_toast)
        except Exception:
            # 调度失败时立即复位刷新标记，避免后续刷新被永久跳过。
            self._refreshing = False
            # 记录调度异常，便于定位 Flet 运行时问题。
            log.exception("调度设备刷新任务失败", source=source)

    async def _refresh_async(self, source: str, show_toast: bool) -> None:
        """异步刷新设备列表，数据由协调器统一提供。"""
        try:
            # 手动刷新、初始化和动作后刷新默认强制走真实数据源。
            force_refresh = source in {"manual", "init", "action", "clear_logs"}
            # 切回设备页时允许先回放最近快照，降低首帧等待时间。
            allow_cached_replay = source in {"tab_switch", "build"}
            # 从协调器请求统一快照，避免设备页自己再并发拉 adb/status/logs。
            snapshot = await self._coordinator.request_refresh(
                source=source,
                force_refresh=force_refresh,
                allow_cached_replay=allow_cached_replay,
            )
            # 把快照应用到界面。
            self.apply_snapshot(snapshot=snapshot, source=source, show_toast=show_toast)
        except Exception as exc:
            # 记录完整堆栈，便于排查刷新失败原因。
            log.exception("刷新设备列表失败", source=source)
            # 给用户一个可读错误提示。
            self._show_snack(f"刷新失败: {exc}")
        finally:
            # 无论成功失败都要复位刷新标记，避免后续无法再次刷新。
            self._refreshing = False

    def apply_snapshot(
        self,
        snapshot: DeviceRefreshSnapshot,
        source: str,
        show_toast: bool,
        update_page: bool = True,
    ) -> None:
        """把协调器快照应用到设备页。"""
        # 控件尚未初始化时直接返回，避免构建前误更新。
        if not self.device_list_column or not self.log_list_view:
            return
        # 记录 UI 应用起点，用于输出前端阶段耗时。
        apply_started_at = time.monotonic()
        # 把状态行按 serial 建索引，便于合并在线设备和离线 worker。
        status_map = {str(row["serial"]): row for row in snapshot.status_rows}
        # 合并在线设备和状态快照，保证离线但仍在跑的 worker 也可见。
        merged_serials = sorted(set(snapshot.online_serials) | set(status_map.keys()))
        # 组装渲染模型列表。
        rows: list[DeviceViewModel] = []
        for serial in merged_serials:
            row = status_map.get(serial, {})
            rows.append(
                DeviceViewModel(
                    serial=serial,
                    online=serial in snapshot.online_serials,
                    pid=int(row.get("pid", -1)),
                    alive=str(row.get("alive", "no")),
                    state=str(row.get("state", "idle")),
                    detail=str(row.get("detail", "未启动")),
                    email_account=str(row.get("email_account", "")).strip(),
                    updated_at=float(row.get("updated_at", 0.0)),
                )
            )

        # 渲染设备卡片与日志列表。
        self._render_rows(rows)
        self._render_logs_records(snapshot.log_records)
        # 更新顶部摘要和最近刷新时间。
        self._update_summary(rows=rows, online_serials=snapshot.online_serials, refreshed_at=snapshot.refreshed_at)
        # 根据来源决定是否提示设备变化或手动刷新完成。
        self._notify_changes(source=source, now_online=snapshot.online_serials, show_toast=show_toast)
        # 记录最近一次成功应用的快照。
        self._last_snapshot = snapshot
        # 需要时提交页面刷新。
        if update_page:
            self.page.update()
            # 保持“跟随最新”时，刷新后显式滚到最后一条。
            if self._logs_follow_latest:
                try:
                    self.page.run_task(self._scroll_logs_to_latest_async)
                except Exception:
                    log.debug("调度日志自动滚动任务失败", source=source)

        # 计算快照年龄，优先使用协调器已记录的值。
        snapshot_age_ms = int(snapshot.metrics.snapshot_age_ms)
        if snapshot_age_ms <= 0 and snapshot.refreshed_at > 0:
            snapshot_age_ms = int(max(0.0, time.time() - snapshot.refreshed_at) * 1000)
        # 计算 UI 应用耗时。
        ui_apply_elapsed_ms = int((time.monotonic() - apply_started_at) * 1000)
        # 刷新降级时，非自动刷新场景给用户明确反馈。
        if snapshot.error_text and source != "auto":
            self._show_snack(f"刷新降级: {snapshot.error_text}")
        # 输出统一的设备页 UI 应用日志。
        level_method = log.warning if ui_apply_elapsed_ms >= 1200 else log.debug
        level_method(
            "设备页应用快照完成",
            source=source,
            queue_wait_elapsed_ms=snapshot.metrics.queue_wait_elapsed_ms,
            adb_elapsed_ms=snapshot.metrics.adb_elapsed_ms,
            status_elapsed_ms=snapshot.metrics.status_elapsed_ms,
            log_read_elapsed_ms=snapshot.metrics.log_read_elapsed_ms,
            total_elapsed_ms=snapshot.metrics.total_elapsed_ms,
            snapshot_age_ms=snapshot_age_ms,
            cache_hit=snapshot.metrics.cache_hit,
            ui_apply_elapsed_ms=ui_apply_elapsed_ms,
            online_count=len(snapshot.online_serials),
            status_count=len(snapshot.status_rows),
            log_count=len(snapshot.log_records),
            error_text=snapshot.error_text,
        )

    # ── 内部方法 ─────────────────────────────────────────────────────────

    def _render_rows(self, rows: list[DeviceViewModel]) -> None:
        if not self.device_list_column:
            return
        if not rows:
            self.device_list_column.controls = [ft.Text("当前未检测到在线设备（adb devices 为空）。", color=ft.Colors.BLUE_GREY_700)]
            return
        self.device_list_column.controls = [self._build_card(item) for item in rows]

    def _build_card(self, item: DeviceViewModel) -> ft.Control:
        online_text = "在线" if item.online else "离线"
        online_color = ft.Colors.GREEN_700 if item.online else ft.Colors.GREY_600
        sc = state_color(item.state)
        state_label = state_text(item.state)
        updated_text = time.strftime("%H:%M:%S", time.localtime(item.updated_at)) if item.updated_at > 0 else "-"

        # 单设备操作区改为可换行 Row，按钮按内容宽度展示，避免拉伸过长。
        action_row = ft.Row(
            controls=[
                # 启动按钮（按内容宽度显示）。
                ft.OutlinedButton("启动", icon=ft.Icons.PLAY_ARROW, on_click=lambda e, s=item.serial: self._handle_start_device(s)),
                # 停止按钮（按内容宽度显示）。
                ft.OutlinedButton("停止", icon=ft.Icons.STOP, on_click=lambda e, s=item.serial: self._run_action(f"{s} 停止", lambda: self.manager.stop_worker(s))),
                # 暂停按钮（按内容宽度显示）。
                ft.OutlinedButton("暂停", icon=ft.Icons.PAUSE, on_click=lambda e, s=item.serial: self._run_action(f"{s} 暂停", lambda: self.manager.send_command(s, "pause"))),
                # 恢复按钮（按内容宽度显示）。
                ft.OutlinedButton("恢复", icon=ft.Icons.PLAY_CIRCLE_FILL, on_click=lambda e, s=item.serial: self._run_action(f"{s} 恢复", lambda: self.manager.send_command(s, "resume"))),
                # 重启按钮（按内容宽度显示）。
                ft.OutlinedButton("重启", icon=ft.Icons.RESTART_ALT, on_click=lambda e, s=item.serial: self._handle_restart_device(s)),
                # 单设备删除 Facebook 按钮。
                ft.OutlinedButton(
                    "删除FB",
                    icon=ft.Icons.DELETE,
                    on_click=lambda e, s=item.serial: self._run_action(f"{s} 删除FB", lambda: self.manager.uninstall_facebook_for_device(s)),
                ),
                # 单设备安装 Facebook 按钮。
                ft.OutlinedButton(
                    "安装FB",
                    icon=ft.Icons.DOWNLOAD,
                    on_click=lambda e, s=item.serial: self._run_action(f"{s} 安装FB", lambda: self.manager.install_facebook_for_device(s)),
                ),
                # 单设备删除 Vinted 按钮。
                ft.OutlinedButton(
                    "删除VT",
                    icon=ft.Icons.DELETE,
                    on_click=lambda e, s=item.serial: self._run_action(f"{s} 删除VT", lambda: self.manager.uninstall_vinted_for_device(s)),
                ),
                # 单设备安装 Vinted 按钮。
                ft.OutlinedButton(
                    "安装VT",
                    icon=ft.Icons.DOWNLOAD,
                    on_click=lambda e, s=item.serial: self._run_action(f"{s} 安装VT", lambda: self.manager.install_vinted_for_device(s)),
                ),
                # 单设备安装 Yosemite 输入法按钮（安装后手动设默认）。
                ft.OutlinedButton(
                    "安装输入法",
                    icon=ft.Icons.KEYBOARD,
                    on_click=lambda e, s=item.serial: self._run_action(f"{s} 安装输入法", lambda: self.manager.install_yosemite_for_device(s)),
                ),
            ],
            # 允许按钮在宽度不足时自动换行。
            wrap=True,
            spacing=6,
            run_spacing=6,
        )

        return ft.Container(
            padding=12,
            border=ft.border.all(1, ft.Colors.BLUE_GREY_100),
            border_radius=12,
            bgcolor=ft.Colors.BLUE_GREY_50,
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Text(item.serial, size=16, weight=ft.FontWeight.W_600, expand=True),
                            ft.Container(content=ft.Text(online_text, color=ft.Colors.WHITE, size=11), bgcolor=online_color, border_radius=999, padding=ft.padding.symmetric(horizontal=10, vertical=4)),
                            ft.Container(content=ft.Text(state_label, color=ft.Colors.WHITE, size=11), bgcolor=sc, border_radius=999, padding=ft.padding.symmetric(horizontal=10, vertical=4)),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    ft.Text(f"PID: {item.pid} | 存活: {item.alive} | 更新时间: {updated_text}", size=12, color=ft.Colors.BLUE_GREY_700),
                    ft.Text(f"使用邮箱: {item.email_account or '-'}", size=12, color=ft.Colors.BLUE_GREY_800),
                    ft.Text(f"详情: {item.detail}", size=12, color=ft.Colors.BLUE_GREY_800, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                    action_row,
                ],
                spacing=8,
            ),
        )

    def _update_summary(self, rows: list[DeviceViewModel], online_serials: set[str], refreshed_at: float) -> None:
        if self.summary_text:
            running_count = sum(1 for item in rows if item.alive == "yes")
            self.summary_text.value = f"在线设备: {len(online_serials)} | 运行进程: {running_count}"
        if self.last_refresh_text:
            now_text = time.strftime("%H:%M:%S", time.localtime(refreshed_at or time.time()))
            self.last_refresh_text.value = f"最近刷新: {now_text}"

    def _notify_changes(self, source: str, now_online: set[str], show_toast: bool) -> None:
        if source == "manual" and show_toast:
            self._show_snack("设备列表已刷新。")

        if source == "auto" and now_online != self._last_online_serials:
            added = sorted(now_online - self._last_online_serials)
            removed = sorted(self._last_online_serials - now_online)
            message_parts: list[str] = []
            if added:
                message_parts.append(f"新增: {', '.join(added)}")
            if removed:
                message_parts.append(f"移除: {', '.join(removed)}")
            if message_parts:
                self._show_snack(f"设备变化 -> {'；'.join(message_parts)}")

        self._last_online_serials = set(now_online)

    # ── 日志展示 ─────────────────────────────────────────────────────────

    def _render_logs_records(self, records: list[tuple[str, str]]) -> None:
        """把日志记录渲染到日志面板。"""
        # 日志容器尚未初始化时直接返回。
        if not self.log_list_view:
            return
        # 缓存可复制文本（带时间）。
        self._latest_log_messages = [f"{display_time} | {message}" for display_time, message in records]
        # 更新日志头部元信息。
        if self.log_meta_text:
            # 计算当前刷新时间。
            now_text = time.strftime("%H:%M:%S", time.localtime())
            # 写入条数与最近刷新时间。
            self.log_meta_text.value = f"{len(records)} 条 | 最近更新: {now_text}"
        # 无日志时展示占位文本。
        if not records:
            # 黑底场景使用白字提示文案，并允许选中复制。
            self.log_list_view.controls = [ft.Text("暂无 open_settings 日志。", size=12, color=ft.Colors.WHITE70, selectable=True)]
            return
        # 把每条日志渲染成“时间 + 内容”两列，提升可读性。
        self.log_list_view.controls = [
            ft.Container(
                # 每条日志增加内边距，避免文本拥挤。
                padding=ft.padding.symmetric(horizontal=8, vertical=4),
                # 行级圆角，增强层次感。
                border_radius=8,
                # 斑马纹背景提升扫描效率。
                bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.WHITE) if idx % 2 == 0 else ft.Colors.TRANSPARENT,
                content=ft.Row(
                    controls=[
                        # 左侧固定宽度时间列。
                        ft.Container(
                            # 固定时间列宽度，保持所有行对齐。
                            width=92,
                            # 时间用等宽字体和浅青色突出。
                            content=ft.Text(display_time, size=11, color=ft.Colors.CYAN_200, font_family="monospace", selectable=True),
                        ),
                        # 消息正文使用白色等宽字体并支持复制。
                        ft.Text(message, size=12, color=ft.Colors.WHITE, font_family="monospace", selectable=True, expand=True),
                    ],
                    # 时间列与消息列之间的间距。
                    spacing=8,
                    # 内容顶对齐，长文本换行时更整齐。
                    vertical_alignment=ft.CrossAxisAlignment.START,
                ),
            )
            for idx, (display_time, message) in enumerate(records)
        ]

    async def _scroll_logs_to_latest_async(self) -> None:
        """在刷新完成后显式滚到最后一条日志。"""
        # 不跟随最新或控件未初始化时直接跳过。
        if not self._logs_follow_latest or not self.log_list_view:
            return
        try:
            # 先让 Flet 完成一次布局，再执行滚动。
            await asyncio.sleep(0)
            # 显式滚到末尾，修复刷新后仍停留在旧位置的问题。
            self.log_list_view.scroll_to(offset=-1, duration=0)
            # 提交滚动指令。
            self.page.update()
        except Exception:
            # 滚动失败只记调试日志，避免影响主刷新流程。
            log.debug("设备日志滚动到最新失败")

    def _on_log_scroll(self, e: ft.OnScrollEvent) -> None:
        """根据滚动位置决定是否继续跟随最新日志。"""
        # 计算当前位置距离底部的像素。
        distance_to_bottom = max(0.0, float(e.max_scroll_extent) - float(e.pixels))
        # 离底部 24px 内视为“跟随最新”，否则视为查看历史。
        follow_latest = distance_to_bottom <= 24.0
        # 同步保存本地跟随状态。
        self._logs_follow_latest = follow_latest
        # 把跟随状态同步给协调器，便于刷新日志打点时输出上下文。
        self._coordinator.mark_log_follow_latest(follow_latest)

    def _handle_copy_logs(self, _e: ft.ControlEvent) -> None:
        """点击复制按钮时，异步把当前日志写入系统剪贴板。"""
        # 在 Flet 事件线程里调度异步复制任务。
        self.page.run_task(self._copy_logs_to_clipboard_async)

    def _handle_clear_logs(self, _e: ft.ControlEvent) -> None:
        """点击清空按钮时，清空 open_settings 日志并刷新日志框。"""
        try:
            # 已有清空任务执行中时直接提示，避免重复并发改写日志文件。
            if self._clearing_logs:
                self._show_snack("日志清空执行中，请等待当前操作完成。")
                return
            # 标记清空任务已启动，避免重复点击并发执行。
            self._clearing_logs = True
            # 在后台任务中执行日志清空，避免同步文件改写阻塞 UI。
            self.page.run_task(self._clear_logs_async)
        except Exception:
            # 调度失败时立即复位状态，避免后续按钮永久不可用。
            self._clearing_logs = False
            # 记录调度异常，便于定位 Flet 任务问题。
            log.exception("调度清空日志任务失败")
            # 给用户返回可读错误提示。
            self._show_snack("清空日志失败，请稍后重试。")

    async def _clear_logs_async(self) -> None:
        """通过协调器清空日志并回放最新快照。"""
        try:
            # 通过协调器独立串行线程清空日志，避免 DeviceTab 直接触盘。
            cleared_count = await self._coordinator.clear_logs()
            # 清空后强制请求新快照，保证面板与磁盘状态一致。
            snapshot = await self._coordinator.request_refresh(source="clear_logs", force_refresh=True)
            # 把清空后的快照回填到设备页。
            self.apply_snapshot(snapshot=snapshot, source="clear_logs", show_toast=False)
            # 反馈清空结果。
            self._show_snack(f"已清空 {cleared_count} 条日志。")
        except Exception:
            # 记录异步清空异常，便于排查文件权限或日志格式问题。
            log.exception("异步清空日志失败")
            # 给用户返回可读失败提示。
            self._show_snack("清空日志失败，请稍后重试。")
        finally:
            # 无论成功失败都复位清空标记，保证后续可再次操作。
            self._clearing_logs = False

    async def _copy_logs_to_clipboard_async(self) -> None:
        """复制当前日志列表到系统剪贴板。"""
        # 没有可复制日志时直接提示。
        if not self._latest_log_messages:
            self._show_snack("暂无可复制日志。")
            return
        # 按行拼接日志文本，便于外部粘贴查看。
        clipboard_text = "\n".join(self._latest_log_messages)
        # 尝试写入系统剪贴板。
        try:
            # 调用 Flet Clipboard 服务写入文本。
            await self.page.clipboard.set(clipboard_text)
            # 复制成功后提示条数。
            self._show_snack(f"已复制 {len(self._latest_log_messages)} 条日志。")
        # 剪贴板异常时降级提示，避免界面无反馈。
        except Exception:
            log.exception("复制日志到剪贴板失败")
            self._show_snack("复制失败，请手动拖选日志复制。")
