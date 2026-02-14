"""设备列表 Tab 模块。"""

from __future__ import annotations

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
DEVICE_LOG_MAX_LINES = 100  # 设备页日志框最多展示 100 条消息文本。
DEVICE_LOG_TAIL_PER_FILE = 200  # 每个日志文件最多回读 200 行，兼顾性能和“最新”准确度。
OPEN_SETTINGS_COMPONENT_TOKENS = (  # 仅展示 task.open_settings 组件日志（按 component 字段过滤）。
    "component=task.open_settings",  # 当前 compact 文本中的常规输出格式。
    'component="task.open_settings"',  # 兼容历史日志里带引号的输出格式。
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
        self._latest_log_messages: list[str] = []  # 缓存当前日志框的最新消息列表，供“一键复制”直接使用。
        self._logs_follow_latest = True  # 是否跟随最新日志到底部；用户手动上滑后会临时关闭。

        self.summary_text: ft.Text | None = None
        self.last_refresh_text: ft.Text | None = None
        self.device_list_column: ft.Column | None = None
        self.log_list_column: ft.Column | None = None
        self.log_meta_text: ft.Text | None = None  # 日志区元信息文本（条数 + 最近刷新时间）。

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
            scroll=ft.ScrollMode.ALWAYS,  # 设备列表滚动条常驻，避免误以为不可滚动。
            expand=True,
        )
        self.log_list_column = ft.Column(  # 创建设备日志列表容器（仅展示消息文本）。
            controls=[ft.Text("日志待加载...", color=ft.Colors.WHITE70)],  # 初始占位文本改成白字，匹配黑底日志框。
            spacing=4,  # 日志行间距设置为 4，提升可读性。
            scroll=ft.ScrollMode.ALWAYS,  # 日志列表滚动条常驻显示，避免“看不清是否可滚动”。
            auto_scroll=False,  # 关闭强制自动滚动，改为“默认跟随最新 + 用户上滑可查看历史”。
            on_scroll=self._on_log_scroll,  # 监听日志滚动位置，判断是否继续跟随最新。
            expand=True,  # 日志容器拉伸占满日志区域高度。
        )
        self.log_meta_text = ft.Text(  # 初始化日志区的右上角元信息文案。
            "0 条 | 最近更新: -",  # 默认显示 0 条和空更新时间。
            size=11,  # 使用较小字号，避免与标题抢视觉层级。
            color=ft.Colors.WHITE70,  # 黑底场景下使用半透明白字。
        )
        self._refresh_logs_view()  # 构建设备页时先加载一次日志，避免初次进入为空白。

        top_actions = ft.ResponsiveRow(
            controls=[
                ft.FilledButton("刷新设备", icon=ft.Icons.REFRESH, on_click=lambda e: self.refresh(source="manual", show_toast=True), col={"xs": 12, "sm": 6, "md": 2}),
                ft.FilledButton("启动全部", icon=ft.Icons.PLAY_ARROW, on_click=lambda e: self._run_action("启动全部", self.manager.start_all), col={"xs": 12, "sm": 6, "md": 2}),
                ft.FilledButton("停止全部", icon=ft.Icons.STOP, on_click=lambda e: self._run_action("停止全部", self.manager.stop_all), col={"xs": 12, "sm": 6, "md": 2}),
                ft.FilledButton("暂停全部", icon=ft.Icons.PAUSE, on_click=lambda e: self._run_action("暂停全部", lambda: self.manager.send_command_all("pause")), col={"xs": 12, "sm": 6, "md": 3}),
                ft.FilledButton("恢复全部", icon=ft.Icons.PLAY_CIRCLE_FILL, on_click=lambda e: self._run_action("恢复全部", lambda: self.manager.send_command_all("resume")), col={"xs": 12, "sm": 6, "md": 3}),
            ],
            spacing=8,
            run_spacing=8,
        )

        body = ft.Column(
            controls=[
                top_actions,
                ft.Row([self.summary_text, self.last_refresh_text], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ft.Divider(height=1, color=ft.Colors.BLUE_GREY_100),
                ft.Container(
                    height=240,  # 设备列表区固定较小高度，优先给日志区更多空间。
                    padding=12,
                    border_radius=12,
                    border=ft.border.all(1, ft.Colors.BLUE_GREY_100),
                    bgcolor=ft.Colors.WHITE,
                    content=self.device_list_column,
                ),
                ft.Container(  # 设备日志框容器。
                    expand=True,  # 日志区占据剩余全部高度，实现随窗口变化的自适应拉伸。
                    padding=12,  # 容器内边距。
                    border_radius=12,  # 圆角边框。
                    border=ft.border.all(1, ft.Colors.BLUE_GREY_800),  # 黑底下改深灰边框，边界更清晰。
                    bgcolor=ft.Colors.BLACK,  # 按需求设置日志框黑色背景。
                    theme=ft.Theme(  # 日志区单独覆盖滚动条主题，确保黑底下清晰可见。
                        scrollbar_theme=ft.ScrollbarTheme(
                            thumb_visibility=True,  # 滑块常驻显示。
                            track_visibility=True,  # 轨道常驻显示。
                            thickness=10,  # 滚动条略加粗提高可见度。
                            radius=8,  # 圆角滚动条样式更协调。
                            thumb_color=ft.Colors.WHITE70,  # 滑块改为亮色，黑底高对比。
                            track_color=ft.Colors.with_opacity(0.18, ft.Colors.WHITE),  # 轨道使用浅白半透明。
                            track_border_color=ft.Colors.with_opacity(0.35, ft.Colors.WHITE),  # 轨道边框进一步增强可视性。
                        )
                    ),
                    content=ft.Column(  # 日志容器内部采用“头部工具栏 + 列表”的结构。
                        controls=[
                            ft.Row(  # 日志头部：标题、元信息、复制按钮。
                                controls=[
                                    ft.Row(  # 左侧标题区。
                                        controls=[
                                            ft.Icon(ft.Icons.TERMINAL, color=ft.Colors.WHITE70, size=16),  # 标题前放终端图标增强识别。
                                            ft.Text("open_settings 日志（最新 100 条）", size=13, weight=ft.FontWeight.W_600, color=ft.Colors.WHITE, expand=True),  # 标题文案。
                                        ],
                                        spacing=6,  # 图标和标题之间留小间距。
                                        expand=True,  # 占满左侧剩余宽度。
                                    ),
                                    self.log_meta_text,  # 中间显示日志条数和最近刷新时间。
                                    ft.Row(  # 右侧操作区：清空日志 + 复制日志。
                                        controls=[
                                            ft.OutlinedButton(  # 清空日志按钮。
                                                "清空日志",
                                                icon=ft.Icons.DELETE_SWEEP,
                                                on_click=self._handle_clear_logs,
                                                style=ft.ButtonStyle(  # 按钮样式适配黑底。
                                                    color=ft.Colors.WHITE,  # 按钮文字改白色。
                                                    side=ft.border.BorderSide(1, ft.Colors.WHITE38),  # 按钮边框使用半透明白色。
                                                ),
                                            ),
                                            ft.OutlinedButton(  # 复制日志按钮。
                                                "复制日志",
                                                icon=ft.Icons.CONTENT_COPY,
                                                on_click=self._handle_copy_logs,
                                                style=ft.ButtonStyle(  # 按钮样式适配黑底。
                                                    color=ft.Colors.WHITE,  # 按钮文字改白色。
                                                    side=ft.border.BorderSide(1, ft.Colors.WHITE38),  # 按钮边框使用半透明白色。
                                                ),
                                            ),
                                        ],
                                        spacing=8,  # 两个按钮之间留出间距。
                                    ),
                                ],
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,  # 头部三段左右分布。
                            ),
                            ft.Divider(height=1, color=ft.Colors.WHITE24),  # 黑底下使用浅色分割线。
                            ft.Container(  # 日志滚动区域容器。
                                expand=True,  # 拉伸占满日志面板剩余高度。
                                padding=ft.padding.only(right=8),  # 增大右侧空隙，让常驻滚动条更清晰。
                                content=self.log_list_column,  # 直接挂载滚动列表，避免 SelectionArea 抢占滚轮事件。
                            ),
                        ],
                        spacing=8,  # 头部和内容之间保留舒适间距。
                        expand=True,  # 内部列占满日志面板。
                    ),
                ),
            ],
            spacing=10,
            expand=True,
        )
        return ft.Container(expand=True, content=body)  # 用 expand 容器包裹根列，确保高度约束生效。

    def refresh(self, source: str, show_toast: bool) -> None:
        """刷新设备列表和进程状态。"""
        if self._refreshing:
            return
        if not self.device_list_column:
            return

        self._refreshing = True
        try:
            online_serials = set(self.manager.list_online_devices())
            status_rows = self.manager.status()
            status_map = {str(row["serial"]): row for row in status_rows}
            merged_serials = sorted(online_serials | set(status_map.keys()))
            rows: list[DeviceViewModel] = []

            for serial in merged_serials:
                row = status_map.get(serial, {})
                rows.append(
                    DeviceViewModel(
                        serial=serial,
                        online=serial in online_serials,
                        pid=int(row.get("pid", -1)),
                        alive=str(row.get("alive", "no")),
                        state=str(row.get("state", "idle")),
                        detail=str(row.get("detail", "未启动")),
                        email_account=str(row.get("email_account", "")).strip(),
                        updated_at=float(row.get("updated_at", 0.0)),
                    )
                )

            self._render_rows(rows)
            self._refresh_logs_view()
            self._update_summary(rows, online_serials)
            self._notify_changes(source=source, now_online=online_serials, show_toast=show_toast)
            self.page.update()
        except Exception as exc:
            log.exception("刷新设备列表失败", source=source)
            self._show_snack(f"刷新失败: {exc}")
        finally:
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

        action_row = ft.ResponsiveRow(
            controls=[
                ft.OutlinedButton("启动", icon=ft.Icons.PLAY_ARROW, on_click=lambda e, s=item.serial: self._run_action(f"{s} 启动", lambda: self.manager.start_worker(s)), col={"xs": 6, "sm": 3, "md": 2}),
                ft.OutlinedButton("停止", icon=ft.Icons.STOP, on_click=lambda e, s=item.serial: self._run_action(f"{s} 停止", lambda: self.manager.stop_worker(s)), col={"xs": 6, "sm": 3, "md": 2}),
                ft.OutlinedButton("暂停", icon=ft.Icons.PAUSE, on_click=lambda e, s=item.serial: self._run_action(f"{s} 暂停", lambda: self.manager.send_command(s, "pause")), col={"xs": 6, "sm": 3, "md": 2}),
                ft.OutlinedButton("恢复", icon=ft.Icons.PLAY_CIRCLE_FILL, on_click=lambda e, s=item.serial: self._run_action(f"{s} 恢复", lambda: self.manager.send_command(s, "resume")), col={"xs": 6, "sm": 3, "md": 2}),
                ft.OutlinedButton("重启", icon=ft.Icons.RESTART_ALT, on_click=lambda e, s=item.serial: self._run_action(f"{s} 重启", lambda: self.manager.restart_worker(s)), col={"xs": 12, "sm": 6, "md": 2}),
            ],
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
        line_buf: deque[str] = deque(maxlen=max(1, int(max_lines)))  # 使用 deque 固定容量缓存文件尾部行。
        with path.open("r", encoding="utf-8", errors="ignore") as f:  # 以 utf-8 打开文件，忽略异常字符避免解析中断。
            for line in f:  # 顺序读取文件所有行。
                line_buf.append(line.rstrip("\n"))  # 保留尾部最近 max_lines 行并去掉换行符。
        return list(line_buf)  # 返回尾部行列表。

    @staticmethod
    def _parse_text_payload(raw_line: str) -> str | None:
        """从日志原始行提取 text 字段（仅接受结构化 JSON 行）。"""
        raw = str(raw_line or "").strip()  # 先标准化原始日志行文本。
        if raw == "":  # 空行直接返回空值。
            return None
        try:  # 尝试把日志行解析为 JSON 对象。
            obj = json.loads(raw)  # 解析 JSON 日志行。
        except Exception:
            return None  # 非 JSON 行（如 traceback 纯文本）直接丢弃。
        if not isinstance(obj, dict):  # 仅接受对象结构。
            return None
        if "text" not in obj:  # 仅接受 log 包统一输出的 text 字段。
            return None
        return str(obj.get("text", "")).strip()  # 返回 text 文本（可能为空，后续再过滤）。

    @staticmethod
    def _extract_message_text(text_payload: str) -> str:
        """从紧凑日志文本中抽取“消息正文”，去掉前缀并保留业务参数。"""
        payload = str(text_payload or "").strip()  # 先标准化输入文本。
        if payload == "":  # 空文本直接返回空字符串。
            return ""

        if " - " in payload:  # 命中标准格式“... - 消息 | extra”时抽取消息段。
            payload = payload.split(" - ", 1)[1].strip()  # 截取 “-” 后面的消息部分。
        payload = " ".join(payload.splitlines()).strip()  # 把潜在多行文本压成单行，避免日志框换行抖动。
        return payload  # 返回最终可展示的消息正文。

    @staticmethod
    def _extract_sort_key(text_payload: str, fallback_index: int) -> str:
        """提取日志排序键（优先时间前缀，失败时回退顺序索引）。"""
        raw = str(text_payload or "")  # 读取日志文本。
        if len(raw) >= 23 and raw[4:5] == "-" and raw[7:8] == "-" and raw[10:11] == " ":  # 粗判是否为时间前缀格式。
            return raw[:23]  # 返回毫秒级时间前缀（字符串可直接比较大小）。
        return f"zzzz-{int(fallback_index):09d}"  # 非标准行回退到输入顺序，保证排序稳定。

    @staticmethod
    def _extract_display_time(text_payload: str) -> str:
        """从日志文本中提取展示时间（默认 HH:MM:SS.mmm）。"""
        raw = str(text_payload or "").strip()  # 读取并标准化日志文本。
        if len(raw) >= 23 and raw[4:5] == "-" and raw[7:8] == "-" and raw[10:11] == " ":  # 粗判是否包含时间前缀。
            return raw[11:23]  # 返回时间片段 HH:MM:SS.mmm。
        return "--:--:--.---"  # 非标准格式返回占位时间。

    @staticmethod
    def _is_task_open_settings_log(text_payload: str) -> bool:
        """判断是否为 get_logger('task.open_settings') 产出的日志行。"""
        payload = str(text_payload or "")  # 读取原始 text 日志字符串。
        return any(token in payload for token in OPEN_SETTINGS_COMPONENT_TOKENS)  # 只认 component=task.open_settings。

    def _load_latest_log_messages(self, limit: int = DEVICE_LOG_MAX_LINES) -> list[tuple[str, str]]:
        """读取 log/json 下多文件日志并返回最新 N 条 (时间, 消息正文)。"""
        log_dir = Path(JSON_LOG_DIR)  # 日志目录路径对象。
        if not log_dir.exists():  # 日志目录不存在时返回空列表。
            return []

        entries: list[tuple[str, str, str]] = []  # 收集 (排序键, 时间文本, 消息正文) 元组列表。
        fallback_index = 0  # 非标准行排序回退计数器。
        for path in sorted(log_dir.glob("*.jsonl")):  # 遍历日志目录内所有 jsonl 文件。
            if not path.is_file():  # 只处理普通文件，跳过目录或软链接异常项。
                continue
            try:  # 逐文件读取尾部日志行，单文件失败不影响整体展示。
                for line in self._tail_lines(path, DEVICE_LOG_TAIL_PER_FILE):  # 读取当前文件末尾若干行。
                    payload = self._parse_text_payload(line)  # 解析为 text 日志字符串。
                    if payload is None:  # 非结构化 JSON 日志行直接跳过（例如 traceback 原文）。
                        continue
                    if not self._is_task_open_settings_log(payload):  # 仅保留 get_logger('task.open_settings') 输出日志。
                        continue
                    message = self._extract_message_text(payload)  # 提取消息正文。
                    if message == "":  # 空正文跳过，避免日志框出现空行。
                        continue
                    sort_key = self._extract_sort_key(payload, fallback_index)  # 计算排序键。
                    display_time = self._extract_display_time(payload)  # 提取日志展示时间文本。
                    entries.append((sort_key, display_time, message))  # 追加一条可展示日志记录。
                    fallback_index += 1  # 增加回退计数器，保证排序键唯一性。
            except Exception:  # 单文件读取失败时记录警告并继续其它文件。
                log.warning("读取日志文件失败", path=str(path))

        entries.sort(key=lambda item: item[0])  # 按时间（或回退序）升序排序。
        return [(display_time, message) for _, display_time, message in entries[-max(1, int(limit)) :]]  # 返回最后 N 条时间+消息。

    def _refresh_logs_view(self) -> None:
        """刷新设备页日志框显示内容。"""
        if not self.log_list_column:  # 日志容器尚未初始化时直接返回。
            return
        records = self._load_latest_log_messages(limit=DEVICE_LOG_MAX_LINES)  # 读取最新日志时间+消息列表。
        self._latest_log_messages = [f"{display_time} | {message}" for display_time, message in records]  # 缓存可复制文本（带时间）。
        if self.log_meta_text:  # 更新日志头部元信息。
            now_text = time.strftime("%H:%M:%S", time.localtime())  # 计算当前刷新时间。
            self.log_meta_text.value = f"{len(records)} 条 | 最近更新: {now_text}"  # 写入条数与最近刷新时间。
        if not records:  # 无日志时展示占位文本。
            self.log_list_column.controls = [ft.Text("暂无 open_settings 日志。", size=12, color=ft.Colors.WHITE70, selectable=True)]  # 黑底场景使用白字提示文案，并允许选中复制。
            return
        self.log_list_column.controls = [  # 把每条日志渲染成“时间 + 内容”两列，提升可读性。
            ft.Container(
                padding=ft.padding.symmetric(horizontal=8, vertical=4),  # 每条日志增加内边距，避免文本拥挤。
                border_radius=8,  # 行级圆角，增强层次感。
                bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.WHITE) if idx % 2 == 0 else ft.Colors.TRANSPARENT,  # 斑马纹背景提升扫描效率。
                content=ft.Row(
                    controls=[
                        ft.Container(  # 左侧固定宽度时间列。
                            width=92,  # 固定时间列宽度，保持所有行对齐。
                            content=ft.Text(display_time, size=11, color=ft.Colors.CYAN_200, font_family="monospace", selectable=True),  # 时间用等宽字体和浅青色突出。
                        ),
                        ft.Text(message, size=12, color=ft.Colors.WHITE, font_family="monospace", selectable=True, expand=True),  # 消息正文使用白色等宽字体并支持复制。
                    ],
                    spacing=8,  # 时间列与消息列之间的间距。
                    vertical_alignment=ft.CrossAxisAlignment.START,  # 内容顶对齐，长文本换行时更整齐。
                ),
            )
            for idx, (display_time, message) in enumerate(records)
        ]
        if self._logs_follow_latest:  # 仅在“跟随最新”状态时自动滚到底部。
            try:
                self.log_list_column.scroll_to(offset=-1, duration=0)  # 直接定位到最底部，默认展示最新日志。
            except Exception:
                pass  # 某些平台初次布局前滚动可能失败，这里静默忽略即可。

    def _on_log_scroll(self, e: ft.OnScrollEvent) -> None:
        """根据滚动位置决定是否继续跟随最新日志。"""
        distance_to_bottom = max(0.0, float(e.max_scroll_extent) - float(e.pixels))  # 计算当前位置距离底部的像素。
        self._logs_follow_latest = distance_to_bottom <= 24.0  # 离底部 24px 内视为“跟随最新”，否则视为查看历史。

    def _handle_copy_logs(self, _e: ft.ControlEvent) -> None:
        """点击复制按钮时，异步把当前日志写入系统剪贴板。"""
        self.page.run_task(self._copy_logs_to_clipboard_async)  # 在 Flet 事件线程里调度异步复制任务。

    def _handle_clear_logs(self, _e: ft.ControlEvent) -> None:
        """点击清空按钮时，清空 open_settings 日志并刷新日志框。"""
        cleared_count = self._clear_open_settings_logs()  # 执行清空逻辑并返回清理条数。
        self._refresh_logs_view()  # 清空后立即刷新日志面板。
        try:
            self.page.update()  # 提交界面刷新，确保日志列表立即变化。
        except Exception:
            log.exception("清空日志后刷新页面失败")
        self._show_snack(f"已清空 {cleared_count} 条日志。")  # 反馈清空结果。

    def _clear_open_settings_logs(self) -> int:
        """清空 log/json 目录下 component=task.open_settings 对应日志行。"""
        log_dir = Path(JSON_LOG_DIR)  # 日志目录路径对象。
        if not log_dir.exists():  # 目录不存在时直接返回 0。
            return 0

        cleared_count = 0  # 统计被清理的日志条数。
        for path in sorted(log_dir.glob("*.jsonl")):  # 遍历所有 jsonl 日志文件。
            if not path.is_file():  # 跳过非普通文件。
                continue
            try:
                kept_lines: list[str] = []  # 保存保留行（非 open_settings 日志）。
                with path.open("r", encoding="utf-8", errors="ignore") as f:  # 读取原文件全部行。
                    for raw_line in f:  # 按行处理日志内容。
                        line = raw_line.rstrip("\n")  # 去掉换行，便于统一处理。
                        payload = self._parse_text_payload(line)  # 尝试解析结构化日志 text。
                        if payload is not None and self._is_task_open_settings_log(payload):  # 命中 open_settings 日志则清理。
                            cleared_count += 1  # 增加清理计数。
                            continue  # 不写回该行，实现清空。
                        kept_lines.append(line)  # 非目标日志原样保留。
                with path.open("w", encoding="utf-8") as f:  # 回写保留行到原文件。
                    for line in kept_lines:  # 逐行写回，保持 JSONL 结构。
                        f.write(f"{line}\n")  # 每行补回换行符。
            except Exception:
                log.exception("清空日志文件失败", path=str(path))
        self._latest_log_messages = []  # 清空缓存，避免复制按钮复制旧数据。
        return cleared_count  # 返回总清空条数给 UI 展示。

    async def _copy_logs_to_clipboard_async(self) -> None:
        """复制当前日志列表到系统剪贴板。"""
        if not self._latest_log_messages:  # 没有可复制日志时直接提示。
            self._show_snack("暂无可复制日志。")
            return
        clipboard_text = "\n".join(self._latest_log_messages)  # 按行拼接日志文本，便于外部粘贴查看。
        try:  # 尝试写入系统剪贴板。
            await self.page.clipboard.set(clipboard_text)  # 调用 Flet Clipboard 服务写入文本。
            self._show_snack(f"已复制 {len(self._latest_log_messages)} 条日志。")  # 复制成功后提示条数。
        except Exception:  # 剪贴板异常时降级提示，避免界面无反馈。
            log.exception("复制日志到剪贴板失败")
            self._show_snack("复制失败，请手动拖选日志复制。")
