"""设备列表 Tab 模块。"""

from __future__ import annotations

import asyncio
import json
import time
from collections import deque
from pathlib import Path
from typing import Any, Callable

import flet as ft

from autovt.gui.helpers import DeviceViewModel, state_color, state_text
from autovt.logs import get_logger
from autovt.multiproc.manager import DeviceProcessManager
from autovt.settings import JSON_LOG_DIR

log = get_logger("gui.device")
# 设备页日志框最多展示 100 条消息文本。
DEVICE_LOG_MAX_LINES = 100
# 每个日志文件最多回读 200 行，兼顾性能和“最新”准确度。
DEVICE_LOG_TAIL_PER_FILE = 200
# 自动刷新时日志读取最小间隔（秒），避免每轮都扫磁盘导致卡顿。
DEVICE_LOG_AUTO_REFRESH_MIN_INTERVAL_SEC = 12.0
# 每轮最多扫描最近 N 个日志文件，避免历史文件过多时读取过慢。
DEVICE_LOG_SCAN_MAX_FILES = 6
# 仅展示 task.open_settings 组件日志（按 component 字段过滤）。
OPEN_SETTINGS_COMPONENT_TOKENS = (
    # 当前 compact 文本中的常规输出格式。
    "component=task.open_settings",
    # 兼容历史日志里带引号的输出格式。
    'component="task.open_settings"',
)


class DeviceTab:
    """封装设备列表 Tab 的构建、刷新和渲染逻辑。"""

    def __init__(
        self,
        page: ft.Page,
        manager: DeviceProcessManager,
        show_snack: Callable[[str], None],
        run_action: Callable[[str, Callable[[], str | list[str]]], None],
    ) -> None:
        self.page = page
        self.manager = manager
        self._show_snack = show_snack
        self._run_action = run_action

        self._refreshing = False
        self._last_online_serials: set[str] = set()
        # 缓存当前日志框的最新消息列表，供“一键复制”直接使用。
        self._latest_log_messages: list[str] = []
        # 缓存最近一次“解析后日志记录”（时间, 消息），用于自动刷新节流复用。
        self._cached_log_records: list[tuple[str, str]] = []
        # 记录最近一次日志读取时间（monotonic 秒）。
        self._last_log_load_mono_ts: float = 0.0
        # 是否跟随最新日志到底部；用户手动上滑后会临时关闭。
        self._logs_follow_latest = True
        # 是否正在执行日志清空任务，避免重复并发改写日志文件。
        self._clearing_logs = False

        self.summary_text: ft.Text | None = None
        self.last_refresh_text: ft.Text | None = None
        self.device_list_column: ft.Column | None = None
        self.log_list_column: ft.Column | None = None
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
        # 创建设备日志列表容器（仅展示消息文本）。
        self.log_list_column = ft.Column(
            # 初始占位文本改成白字，匹配黑底日志框。
            controls=[ft.Text("日志待加载...", color=ft.Colors.WHITE70)],
            # 日志行间距设置为 4，提升可读性。
            spacing=4,
            # 日志列表滚动条常驻显示，避免“看不清是否可滚动”。
            scroll=ft.ScrollMode.ALWAYS,
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
        try:
            # 构建设备页时异步加载一次日志，避免首次进入同步扫盘卡住界面。
            self.page.run_task(self._refresh_logs_view_async, True)
        except Exception:
            # 调度失败时记录日志，避免初次进入因日志任务异常而无反馈。
            log.exception("调度设备页初始日志加载任务失败")

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
                                content=self.log_list_column,
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
        """异步刷新设备列表，耗时 IO 放到后台线程执行。"""
        # 记录刷新开始时间，用于输出耗时诊断日志。
        started_at = time.monotonic()
        # 初始化各阶段耗时，默认值为 0（毫秒）。
        adb_elapsed_ms = 0
        # 初始化日志读取阶段耗时（毫秒）。
        log_read_elapsed_ms = 0
        # 初始化状态查询阶段耗时（毫秒）。
        status_elapsed_ms = 0
        # 初始化模型组装阶段耗时（毫秒）。
        model_build_elapsed_ms = 0
        # 初始化渲染提交阶段耗时（毫秒）。
        render_elapsed_ms = 0
        try:
            # 定义“后台读取在线设备 + 统计耗时”的小方法。
            async def _load_online_with_timing() -> tuple[set[str], int]:
                # 记录读取在线设备起点。
                online_started_at = time.monotonic()
                # 在线程池读取在线设备，避免阻塞 UI 事件循环。
                online_values = set(await asyncio.to_thread(self.manager.list_online_devices))
                # 返回结果和耗时毫秒。
                return online_values, int((time.monotonic() - online_started_at) * 1000)

            # 定义“后台读取日志 + 统计耗时”的小方法。
            async def _load_logs_with_timing() -> tuple[list[tuple[str, str]], int]:
                # 记录日志读取起点。
                logs_started_at = time.monotonic()
                # 在线程池读取日志，避免阻塞 UI 事件循环。
                records = await asyncio.to_thread(self._load_latest_log_messages, DEVICE_LOG_MAX_LINES)
                # 返回日志记录和耗时毫秒。
                return records, int((time.monotonic() - logs_started_at) * 1000)

            # 默认标记“本轮需要重新读取日志”。
            need_reload_logs = True
            # 仅自动刷新场景做日志读取节流，减少磁盘扫描压力。
            if source == "auto":
                # 读取当前单调时钟秒数。
                now_mono = time.monotonic()
                # 距离上次日志读取未超过阈值时，复用缓存日志。
                if now_mono - self._last_log_load_mono_ts < DEVICE_LOG_AUTO_REFRESH_MIN_INTERVAL_SEC:
                    # 标记本轮跳过日志重读。
                    need_reload_logs = False

            # 需要重读日志时并行执行“adb 在线设备读取”和“日志读取”。
            if need_reload_logs:
                # 并行启动两个后台任务，降低总等待时间。
                online_task = _load_online_with_timing()
                # 并行启动日志读取任务。
                logs_task = _load_logs_with_timing()
                # 等待两项任务同时完成。
                (online_serials, adb_elapsed_ms), (log_records, log_read_elapsed_ms) = await asyncio.gather(online_task, logs_task)
                # 更新日志缓存，供后续自动刷新复用。
                self._cached_log_records = list(log_records)
                # 记录本次日志读取时间。
                self._last_log_load_mono_ts = time.monotonic()
            # 不需要重读日志时，只读取在线设备，日志直接走缓存。
            else:
                # 仅执行在线设备读取，减少自动刷新耗时。
                online_serials, adb_elapsed_ms = await _load_online_with_timing()
                # 复用缓存日志记录，避免重复扫盘。
                log_records = list(self._cached_log_records)
                # 复用缓存场景记 0ms，表示未实际读取磁盘。
                log_read_elapsed_ms = 0

            # 记录状态查询阶段起点。
            step_started_at = time.monotonic()
            # 在线程池中读取状态快照，避免事件循环线程被设备状态查询阻塞。
            status_rows = await asyncio.to_thread(self.manager.status)
            # 计算状态查询阶段耗时。
            status_elapsed_ms = int((time.monotonic() - step_started_at) * 1000)

            # 记录模型组装阶段起点。
            step_started_at = time.monotonic()
            # 把状态行按 serial 建成索引表，便于后续快速合并。
            status_map = {str(row["serial"]): row for row in status_rows}
            # 合并在线设备与已有 worker 状态，保证离线但仍在跑的进程可见。
            merged_serials = sorted(online_serials | set(status_map.keys()))
            # 准备最终渲染给 UI 的设备模型列表。
            rows: list[DeviceViewModel] = []

            # 遍历合并后的 serial，组装展示模型。
            for serial in merged_serials:
                # 读取当前设备对应的状态行（可能为空）。
                row = status_map.get(serial, {})
                # 追加一条设备展示模型。
                rows.append(
                    DeviceViewModel(
                        # 设备序列号。
                        serial=serial,
                        # 是否在线（来自 adb devices）。
                        online=serial in online_serials,
                        # worker 进程 pid。
                        pid=int(row.get("pid", -1)),
                        # worker 存活标记。
                        alive=str(row.get("alive", "no")),
                        # worker 状态（running/paused/waiting...）。
                        state=str(row.get("state", "idle")),
                        # worker 详情文案。
                        detail=str(row.get("detail", "未启动")),
                        # 当前设备占用邮箱。
                        email_account=str(row.get("email_account", "")).strip(),
                        # 最近状态更新时间戳。
                        updated_at=float(row.get("updated_at", 0.0)),
                    )
                )
            # 计算模型组装阶段耗时。
            model_build_elapsed_ms = int((time.monotonic() - step_started_at) * 1000)

            # 记录渲染提交阶段起点。
            step_started_at = time.monotonic()
            # 渲染设备卡片列表。
            self._render_rows(rows)
            # 渲染日志列表（使用后台线程已读取好的数据）。
            self._render_logs_records(log_records)
            # 更新顶部统计摘要。
            self._update_summary(rows, online_serials)
            # 根据刷新来源决定是否提示设备变化。
            self._notify_changes(source=source, now_online=online_serials, show_toast=show_toast)
            # 提交页面更新，确保控件变化立刻生效。
            self.page.update()
            # 计算渲染提交阶段耗时。
            render_elapsed_ms = int((time.monotonic() - step_started_at) * 1000)
            # 计算本次刷新总耗时（毫秒）。
            elapsed_ms = int((time.monotonic() - started_at) * 1000)
            # 耗时超过阈值时打告警日志，便于定位卡顿源头。
            if elapsed_ms >= 1500:
                log.warning(
                    "设备页刷新耗时较长",
                    source=source,
                    elapsed_ms=elapsed_ms,
                    adb_elapsed_ms=adb_elapsed_ms,
                    log_read_elapsed_ms=log_read_elapsed_ms,
                    status_elapsed_ms=status_elapsed_ms,
                    model_build_elapsed_ms=model_build_elapsed_ms,
                    render_elapsed_ms=render_elapsed_ms,
                    online_count=len(online_serials),
                    status_count=len(status_rows),
                    log_count=len(log_records),
                )
            # 正常耗时记录调试日志，便于后续对比。
            else:
                log.debug(
                    "设备页刷新完成",
                    source=source,
                    elapsed_ms=elapsed_ms,
                    adb_elapsed_ms=adb_elapsed_ms,
                    log_read_elapsed_ms=log_read_elapsed_ms,
                    status_elapsed_ms=status_elapsed_ms,
                    model_build_elapsed_ms=model_build_elapsed_ms,
                    render_elapsed_ms=render_elapsed_ms,
                    online_count=len(online_serials),
                    status_count=len(status_rows),
                    log_count=len(log_records),
                )
        except Exception as exc:
            # 记录完整堆栈，便于排查刷新失败原因。
            log.exception(
                "刷新设备列表失败",
                source=source,
                adb_elapsed_ms=adb_elapsed_ms,
                log_read_elapsed_ms=log_read_elapsed_ms,
                status_elapsed_ms=status_elapsed_ms,
                model_build_elapsed_ms=model_build_elapsed_ms,
                render_elapsed_ms=render_elapsed_ms,
            )
            # 给用户一个可读错误提示。
            self._show_snack(f"刷新失败: {exc}")
        finally:
            # 无论成功失败都要复位刷新标记，避免后续无法再次刷新。
            self._refreshing = False

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

    def _update_summary(self, rows: list[DeviceViewModel], online_serials: set[str]) -> None:
        if self.summary_text:
            running_count = sum(1 for item in rows if item.alive == "yes")
            self.summary_text.value = f"在线设备: {len(online_serials)} | 运行进程: {running_count}"
        if self.last_refresh_text:
            now_text = time.strftime("%H:%M:%S", time.localtime())
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

    @staticmethod
    def _tail_lines(path: Path, max_lines: int) -> list[str]:
        """读取文件尾部最多 max_lines 行。"""
        # 使用 deque 固定容量缓存文件尾部行。
        line_buf: deque[str] = deque(maxlen=max(1, int(max_lines)))
        # 以 utf-8 打开文件，忽略异常字符避免解析中断。
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            # 顺序读取文件所有行。
            for line in f:
                # 保留尾部最近 max_lines 行并去掉换行符。
                line_buf.append(line.rstrip("\n"))
        # 返回尾部行列表。
        return list(line_buf)

    @staticmethod
    def _parse_text_payload(raw_line: str) -> str | None:
        """从日志原始行提取 text 字段（仅接受结构化 JSON 行）。"""
        # 先标准化原始日志行文本。
        raw = str(raw_line or "").strip()
        # 空行直接返回空值。
        if raw == "":
            return None
        # 尝试把日志行解析为 JSON 对象。
        try:
            # 解析 JSON 日志行。
            obj = json.loads(raw)
        except Exception:
            # 非 JSON 行（如 traceback 纯文本）直接丢弃。
            return None
        # 仅接受对象结构。
        if not isinstance(obj, dict):
            return None
        # 仅接受 log 包统一输出的 text 字段。
        if "text" not in obj:
            return None
        # 返回 text 文本（可能为空，后续再过滤）。
        return str(obj.get("text", "")).strip()

    @staticmethod
    def _extract_message_text(text_payload: str) -> str:
        """从紧凑日志文本中抽取“消息正文”，去掉前缀并保留业务参数。"""
        # 先标准化输入文本。
        payload = str(text_payload or "").strip()
        # 空文本直接返回空字符串。
        if payload == "":
            return ""

        # 命中标准格式“... - 消息 | extra”时抽取消息段。
        if " - " in payload:
            # 截取 “-” 后面的消息部分。
            payload = payload.split(" - ", 1)[1].strip()
        # 把潜在多行文本压成单行，避免日志框换行抖动。
        payload = " ".join(payload.splitlines()).strip()
        # 返回最终可展示的消息正文。
        return payload

    @staticmethod
    def _extract_sort_key(text_payload: str, fallback_index: int) -> str:
        """提取日志排序键（优先时间前缀，失败时回退顺序索引）。"""
        # 读取日志文本。
        raw = str(text_payload or "")
        # 粗判是否为时间前缀格式。
        if len(raw) >= 23 and raw[4:5] == "-" and raw[7:8] == "-" and raw[10:11] == " ":
            # 返回毫秒级时间前缀（字符串可直接比较大小）。
            return raw[:23]
        # 非标准行回退到输入顺序，保证排序稳定。
        return f"zzzz-{int(fallback_index):09d}"

    @staticmethod
    def _extract_display_time(text_payload: str) -> str:
        """从日志文本中提取展示时间（默认 HH:MM:SS.mmm）。"""
        # 读取并标准化日志文本。
        raw = str(text_payload or "").strip()
        # 粗判是否包含时间前缀。
        if len(raw) >= 23 and raw[4:5] == "-" and raw[7:8] == "-" and raw[10:11] == " ":
            # 返回时间片段 HH:MM:SS.mmm。
            return raw[11:23]
        # 非标准格式返回占位时间。
        return "--:--:--.---"

    @staticmethod
    def _is_task_open_settings_log(text_payload: str) -> bool:
        """判断是否为 get_logger('task.open_settings') 产出的日志行。"""
        # 读取原始 text 日志字符串。
        payload = str(text_payload or "")
        # 只认 component=task.open_settings。
        return any(token in payload for token in OPEN_SETTINGS_COMPONENT_TOKENS)

    def _load_latest_log_messages(self, limit: int = DEVICE_LOG_MAX_LINES) -> list[tuple[str, str]]:
        """读取 log/json 下多文件日志并返回最新 N 条 (时间, 消息正文)。"""
        # 日志目录路径对象。
        log_dir = Path(JSON_LOG_DIR)
        # 日志目录不存在时返回空列表。
        if not log_dir.exists():
            return []

        # 收集 (排序键, 时间文本, 消息正文) 元组列表。
        entries: list[tuple[str, str, str]] = []
        # 非标准行排序回退计数器。
        fallback_index = 0
        # 收集日志目录内所有 jsonl 文件并按“最近修改时间倒序”排序。
        all_paths: list[Path] = []
        # 定义“安全读取文件修改时间”方法，避免日志轮转删除时抛异常。
        def _safe_mtime(path: Path) -> float:
            # 使用异常保护 stat 调用。
            try:
                # 返回文件最近修改时间戳。
                return float(path.stat().st_mtime)
            # 读取失败时回退 0，保证排序稳定。
            except Exception:
                return 0.0
        # 遍历日志目录内的 jsonl 文件。
        for path in log_dir.glob("*.jsonl"):
            # 仅保留普通文件。
            if path.is_file():
                # 追加到候选列表。
                all_paths.append(path)
        # 按文件最近修改时间倒序排序，优先读取最新文件。
        all_paths.sort(key=_safe_mtime, reverse=True)
        # 仅取最近 N 个文件，避免历史日志过多导致每轮扫描过慢。
        selected_paths = all_paths[:DEVICE_LOG_SCAN_MAX_FILES]

        # 遍历选中的日志文件列表。
        for path in selected_paths:
            # 只处理普通文件，跳过目录或软链接异常项。
            if not path.is_file():
                continue
            # 逐文件读取尾部日志行，单文件失败不影响整体展示。
            try:
                # 读取当前文件末尾若干行。
                for line in self._tail_lines(path, DEVICE_LOG_TAIL_PER_FILE):
                    # 解析为 text 日志字符串。
                    payload = self._parse_text_payload(line)
                    # 非结构化 JSON 日志行直接跳过（例如 traceback 原文）。
                    if payload is None:
                        continue
                    # 仅保留 get_logger('task.open_settings') 输出日志。
                    if not self._is_task_open_settings_log(payload):
                        continue
                    # 提取消息正文。
                    message = self._extract_message_text(payload)
                    # 空正文跳过，避免日志框出现空行。
                    if message == "":
                        continue
                    # 计算排序键。
                    sort_key = self._extract_sort_key(payload, fallback_index)
                    # 提取日志展示时间文本。
                    display_time = self._extract_display_time(payload)
                    # 追加一条可展示日志记录。
                    entries.append((sort_key, display_time, message))
                    # 增加回退计数器，保证排序键唯一性。
                    fallback_index += 1
            # 单文件读取失败时记录警告并继续其它文件。
            except Exception:
                log.warning("读取日志文件失败", path=str(path))

        # 按时间（或回退序）升序排序。
        entries.sort(key=lambda item: item[0])
        # 返回最后 N 条时间+消息。
        return [(display_time, message) for _, display_time, message in entries[-max(1, int(limit)) :]]

    def _refresh_logs_view(self) -> None:
        """刷新设备页日志框显示内容。"""
        # 日志容器尚未初始化时直接返回。
        if not self.log_list_column:
            return
        # 读取最新日志时间+消息列表。
        records = self._load_latest_log_messages(limit=DEVICE_LOG_MAX_LINES)
        # 渲染日志记录到日志面板。
        self._render_logs_records(records)

    async def _refresh_logs_view_async(self, update_page: bool = False) -> None:
        """在线程池中读取日志列表，避免同步扫盘阻塞 GUI。"""
        # 日志容器尚未初始化时直接返回。
        if not self.log_list_column:
            return
        try:
            # 在线程池中读取最新日志记录，避免主线程直接扫描日志文件。
            records = await asyncio.to_thread(self._load_latest_log_messages, DEVICE_LOG_MAX_LINES)
            # 回填日志缓存，便于自动刷新节流直接复用。
            self._cached_log_records = list(records)
            # 更新最近一次日志读取时间，避免后续自动刷新马上再次扫盘。
            self._last_log_load_mono_ts = time.monotonic()
            # 把日志记录渲染到界面。
            self._render_logs_records(records)
            # 需要时提交一次页面刷新，确保初始日志尽快可见。
            if update_page:
                self.page.update()
        except Exception:
            # 记录异步日志加载异常，避免用户误以为日志面板空白就是没有日志。
            log.exception("异步刷新设备日志视图失败")

    def _render_logs_records(self, records: list[tuple[str, str]]) -> None:
        """把日志记录渲染到日志面板。"""
        # 日志容器尚未初始化时直接返回。
        if not self.log_list_column:
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
            self.log_list_column.controls = [ft.Text("暂无 open_settings 日志。", size=12, color=ft.Colors.WHITE70, selectable=True)]
            return
        # 把每条日志渲染成“时间 + 内容”两列，提升可读性。
        self.log_list_column.controls = [
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
        # 仅在“跟随最新”状态时自动滚到底部。
        if self._logs_follow_latest:
            try:
                # 直接定位到最底部，默认展示最新日志。
                self.log_list_column.scroll_to(offset=-1, duration=0)
            except Exception:
                # 某些平台初次布局前滚动可能失败，这里静默忽略即可。
                pass

    def _on_log_scroll(self, e: ft.OnScrollEvent) -> None:
        """根据滚动位置决定是否继续跟随最新日志。"""
        # 计算当前位置距离底部的像素。
        distance_to_bottom = max(0.0, float(e.max_scroll_extent) - float(e.pixels))
        # 离底部 24px 内视为“跟随最新”，否则视为查看历史。
        self._logs_follow_latest = distance_to_bottom <= 24.0

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

    def _clear_open_settings_logs(self) -> int:
        """清空 log/json 目录下 component=task.open_settings 对应日志行。"""
        # 日志目录路径对象。
        log_dir = Path(JSON_LOG_DIR)
        # 目录不存在时直接返回 0。
        if not log_dir.exists():
            return 0

        # 统计被清理的日志条数。
        cleared_count = 0
        # 遍历所有 jsonl 日志文件。
        for path in sorted(log_dir.glob("*.jsonl")):
            # 跳过非普通文件。
            if not path.is_file():
                continue
            try:
                # 保存保留行（非 open_settings 日志）。
                kept_lines: list[str] = []
                # 读取原文件全部行。
                with path.open("r", encoding="utf-8", errors="ignore") as f:
                    # 按行处理日志内容。
                    for raw_line in f:
                        # 去掉换行，便于统一处理。
                        line = raw_line.rstrip("\n")
                        # 尝试解析结构化日志 text。
                        payload = self._parse_text_payload(line)
                        # 命中 open_settings 日志则清理。
                        if payload is not None and self._is_task_open_settings_log(payload):
                            # 增加清理计数。
                            cleared_count += 1
                            # 不写回该行，实现清空。
                            continue
                        # 非目标日志原样保留。
                        kept_lines.append(line)
                # 回写保留行到原文件。
                with path.open("w", encoding="utf-8") as f:
                    # 逐行写回，保持 JSONL 结构。
                    for line in kept_lines:
                        # 每行补回换行符。
                        f.write(f"{line}\n")
            except Exception:
                log.exception("清空日志文件失败", path=str(path))
        # 清空缓存，避免复制按钮复制旧数据。
        self._latest_log_messages = []
        # 清空日志缓存记录，避免自动刷新继续展示旧数据。
        self._cached_log_records = []
        # 重置最近一次日志读取时间，确保下次刷新会重新扫盘。
        self._last_log_load_mono_ts = 0.0
        # 返回总清空条数给 UI 展示。
        return cleared_count

    async def _clear_logs_async(self) -> None:
        """在线程池中清空日志并回填最新视图，避免同步文件改写阻塞 GUI。"""
        try:
            # 在线程池中执行日志清空动作，避免阻塞 Flet 事件线程。
            cleared_count = await asyncio.to_thread(self._clear_open_settings_logs)
            # 清空后在线程池中重新读取最新日志，保持面板状态一致。
            records = await asyncio.to_thread(self._load_latest_log_messages, DEVICE_LOG_MAX_LINES)
            # 把清空后的记录渲染到日志面板。
            self._render_logs_records(records)
            # 提交界面刷新，确保日志列表立即变化。
            self.page.update()
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
