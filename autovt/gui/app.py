"""GUI 主应用协调器 — 负责页面级编排和生命周期管理。"""

from __future__ import annotations

import asyncio
import atexit
import os
import platform
import signal
import sys
import threading
import time
from pathlib import Path
from typing import Callable

import flet as ft

from autovt.gui.account_tab import AccountTab
from autovt.gui.device_refresh_coordinator import DeviceRefreshCoordinator
from autovt.gui.device_tab import DeviceTab
from autovt.gui.helpers import DEVICE_MONITOR_INTERVAL_SEC
from autovt.gui.login_view import LoginView
from autovt.gui.settings_tab import SettingsTab
from autovt.logs import get_logger
from autovt.multiproc.manager import DeviceProcessManager
from autovt.settings import WORKER_LOOP_INTERVAL_SEC
from autovt.userdb import UserDB

log = get_logger("gui")


class AutoVTGuiApp:
    """AutoVT GUI 主应用，协调登录、设备、账号、设置四大模块。"""

    def __init__(self, page: ft.Page, loop_interval_sec: float) -> None:
        self.page = page
        self._logged_in = False
        self._monitor_running = True
        self._closing = False
        self._action_running = False
        self._shutdown_done = False
        self._shutdown_lock = threading.RLock()

        # ── 后端服务 ──
        self.manager = DeviceProcessManager(loop_interval_sec=loop_interval_sec)
        # GUI 连接使用短超时，避免被 worker 写锁长时间阻塞导致界面卡顿。
        self.user_db = UserDB(connect_timeout_sec=1.2, busy_timeout_ms=1200)
        self.user_db.connect()
        # 设备刷新统一交给独立协调器，避免设备页自己并发抢线程池。
        self.device_refresh_coordinator = DeviceRefreshCoordinator(manager=self.manager)

        # ── 子模块 ──
        self.login_view = LoginView(page=page, on_login_success=self._on_login_success)
        self.device_tab = DeviceTab(
            page=page, manager=self.manager, coordinator=self.device_refresh_coordinator,
            show_snack=self._show_snack, run_action=self._run_action,
        )
        self.account_tab = AccountTab(page=page, user_db=self.user_db, show_snack=self._show_snack)
        self.settings_tab = SettingsTab(page=page, user_db=self.user_db, show_snack=self._show_snack)

        # ── Tab 控件 ──
        self.tab_bar: ft.TabBar | None = None
        self.tabs_control: ft.Tabs | None = None
        self._tab_contents: list[ft.Control] = []
        self._current_tab_index = 0

        self._configure_page()
        self._register_exit_hook()

    # ═══════════════════════════════════════════════════════════════════
    # 启动
    # ═══════════════════════════════════════════════════════════════════

    def _configure_page(self) -> None:
        # 设置窗口标题，保持桌面端统一文案。
        self.page.title = "AutoVT 管理后台"
        # 设置全局主题，统一滚动条可见性与对比度。
        self.page.theme = ft.Theme(
            # 配置全局滚动条样式。
            scrollbar_theme=ft.ScrollbarTheme(
                # 滚动条滑块始终可见。
                thumb_visibility=True,
                # 滚动条轨道始终可见。
                track_visibility=True,
                # 适当加粗滚动条，提升可发现性。
                thickness=9,
                # 圆角滑块，视觉更柔和。
                radius=6,
                # 全局滑块颜色使用中性深灰。
                thumb_color=ft.Colors.BLUE_GREY_500,
                # 轨道使用浅灰半透明。
                track_color=ft.Colors.with_opacity(0.14, ft.Colors.BLUE_GREY_400),
                # 轨道边框略增强对比。
                track_border_color=ft.Colors.with_opacity(0.30, ft.Colors.BLUE_GREY_500),
            )
        )
        # 强制浅色主题，避免平台默认深色导致风格不一致。
        self.page.theme_mode = ft.ThemeMode.LIGHT
        # 页面不留默认边距，交给各子视图自行控制。
        self.page.padding = 0
        # 页面级控件间距置 0，避免出现多余空白。
        self.page.spacing = 0
        # 设置页面统一底色，登录页和主控台保持一致。
        self.page.bgcolor = ft.Colors.BLUE_GREY_50
        # 横向拉伸到满宽，避免出现“手机窄栏”观感。
        self.page.horizontal_alignment = ft.CrossAxisAlignment.STRETCH
        # 主内容从顶部开始布局，更符合后台管理台样式。
        self.page.vertical_alignment = ft.MainAxisAlignment.START
        # 彻底禁用页面级滚动，各 Tab 内部容器独立管理滚动。
        self.page.scroll = None

        # 设置默认桌面窗口宽度，提升首屏可用空间。
        self.page.window.width = 1280
        # 设置默认桌面窗口高度，避免内容区域过窄。
        self.page.window.height = 820
        # 限制最小宽度，防止缩放到“手机模式”布局。
        self.page.window.min_width = 980
        # 限制最小高度，保证顶部按钮和列表可见。
        self.page.window.min_height = 640
        # 关闭默认最大化，恢复普通窗口启动行为。
        self.page.window.maximized = False
        # 声明窗口默认对齐方式为居中，减少启动后跳位。
        self.page.window.alignment = ft.Alignment.CENTER
        # 设置运行时窗口图标（从 assets 目录加载）。
        self.page.window.icon = "icon.png"
        # 拦截系统窗口关闭事件，确保关窗时先停止全部 worker。
        self.page.window.prevent_close = True
        # 绑定窗口事件处理器，用于响应系统关闭动作。
        self.page.window.on_event = self._on_window_event

    def _register_exit_hook(self) -> None:
        atexit.register(self._shutdown)

    def start(self) -> None:
        # 先构建登录界面，保证窗口首次展示时已有完整内容。
        self.login_view.build()
        # 异步执行窗口居中并显示，避免阻塞 UI 线程。
        self.page.run_task(self._show_window_centered_async)

    async def _show_window_centered_async(self) -> None:
        # 优先走“等待就绪 -> 居中”的平滑启动路径。
        try:
            # 等待原生窗口可安全操作，减少平台时序问题。
            await self.page.window.wait_until_ready_to_show()
            # 将窗口移动到当前屏幕中心，提升首次打开体验。
            await self.page.window.center()
            # 提交窗口位置变更。
            self.page.update()
        except Exception:
            # 记录异常堆栈，便于定位某些平台的窗口 API 兼容问题。
            log.exception("窗口居中显示失败")

    # ═══════════════════════════════════════════════════════════════════
    # 登录成功回调
    # ═══════════════════════════════════════════════════════════════════

    def _on_login_success(self) -> None:
        self._logged_in = True
        self._build_dashboard_view()
        self.device_refresh_coordinator.start()
        self._request_device_refresh(source="init", show_toast=False, force_refresh=True)
        self.page.run_task(self._monitor_devices_loop)

    # ═══════════════════════════════════════════════════════════════════
    # 主控台视图
    # ═══════════════════════════════════════════════════════════════════

    def _build_dashboard_view(self) -> None:
        device_content = self.device_tab.build()
        account_content = self.account_tab.build()
        settings_content = self.settings_tab.build()

        self._tab_contents = [device_content, account_content, settings_content]

        self.tab_bar = ft.TabBar(
            tabs=[
                ft.Tab(label="设备列表", icon=ft.Icons.DEVICES),
                ft.Tab(label="账号列表", icon=ft.Icons.PEOPLE),
                ft.Tab(label="全局设置", icon=ft.Icons.SETTINGS),
            ],
            scrollable=False,
            indicator_color=ft.Colors.BLUE_700,
            label_color=ft.Colors.BLUE_700,
            unselected_label_color=ft.Colors.BLUE_GREY_600,
        )
        # 构建标签内容视图，和 TabBar 一起挂载到 Tabs 下。
        tab_view = ft.TabBarView(
            # 绑定三个 tab 的内容控件列表。
            controls=self._tab_contents,
            # 内容区域拉伸占满剩余空间。
            expand=True,
        )
        # 创建 Tabs 容器，确保 TabBar 合规使用。
        self.tabs_control = ft.Tabs(
            # 声明总标签数量。
            length=3,
            # 默认选中第一个“设备列表”。
            selected_index=0,
            # 切换标签时触发刷新逻辑。
            on_change=self._on_tab_changed,
            # Tabs 内部采用“TabBar + TabBarView”结构。
            content=ft.Column(
                controls=[
                    # 顶部标签栏控件。
                    self.tab_bar,
                    # 标签内容外层容器。
                    ft.Container(
                        # 拉伸填充剩余高度。
                        expand=True,
                        # 内容区域统一内边距。
                        padding=ft.padding.only(left=16, right=16, bottom=16),
                        # 标签对应内容视图。
                        content=tab_view,
                    ),
                ],
                # 控件间距置零，避免额外空白。
                spacing=0,
                # 整体占据可用高度。
                expand=True,
            ),
            # Tabs 自身拉伸占满父容器。
            expand=True,
        )

        header = ft.Container(
            padding=ft.padding.only(left=16, right=16, top=8),
            content=ft.Row(
                controls=[
                    ft.Text("AutoVT 管理后台", size=20, weight=ft.FontWeight.W_700, color=ft.Colors.BLUE_GREY_900, expand=True),
                    ft.OutlinedButton("退出并停止全部", icon=ft.Icons.POWER_SETTINGS_NEW, on_click=self._handle_exit),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
        )

        self.page.clean()
        self.page.add(
            ft.Column(
                controls=[header, self.tabs_control],
                expand=True,
                spacing=0,
            )
        )
        self.page.update()

    # ═══════════════════════════════════════════════════════════════════
    # Tab 切换
    # ═══════════════════════════════════════════════════════════════════

    def _on_tab_changed(self, e: ft.ControlEvent) -> None:
        try:
            new_index = int(e.data) if e.data is not None else 0
        except (ValueError, TypeError):
            new_index = 0

        self._current_tab_index = new_index

        # 切回设备列表时同步刷新设备状态。
        if new_index == 0:
            self._request_device_refresh(source="tab_switch", show_toast=False, allow_cached_replay=True)
        # 切到账号列表时刷新账号数据。
        elif new_index == 1:
            self.account_tab.refresh(source="tab_switch", show_toast=False)
        # 切到设置页时刷新配置数据。
        elif new_index == 2:
            self.settings_tab.refresh(source="tab_switch", show_toast=False)

    # ═══════════════════════════════════════════════════════════════════
    # 退出
    # ═══════════════════════════════════════════════════════════════════

    def _handle_exit(self, _e: ft.ControlEvent) -> None:
        self._request_shutdown_and_close()

    def _on_window_event(self, e: ft.WindowEvent) -> None:
        # 仅处理窗口关闭事件，其它事件直接忽略。
        if e.type != ft.WindowEventType.CLOSE:
            return
        # 记录关窗事件日志，便于排查“关窗后仍在跑”的问题。
        log.warning("收到系统窗口关闭事件，准备停止全部并退出")
        # 复用统一退出链路，避免关窗时遗漏 stop_all。
        self._request_shutdown_and_close()

    def _request_shutdown_and_close(self) -> None:
        # 已在关闭流程中时直接返回，避免重复 stop_all。
        if self._closing:
            return
        # 标记关闭流程已启动。
        self._closing = True
        # 先展示退出提示，给用户明确反馈。
        self._show_snack("正在退出并停止全部进程...")
        # 在后台任务中执行停机和关窗，避免阻塞 UI 线程。
        self.page.run_task(self._shutdown_and_close_async)

    async def _shutdown_and_close_async(self) -> None:
        # 把 stop_all/close 放到后台线程执行，避免 UI 卡死。
        await asyncio.to_thread(self._shutdown)
        # 停机完成后继续执行窗口关闭。
        await self._close_window_async()

    async def _close_window_async(self) -> None:
        await asyncio.sleep(0.5)
        try:
            await self.page.window.destroy()
        except Exception:
            try:
                await self.page.window.close()
            except Exception:
                log.exception("关闭窗口失败")

    # ═══════════════════════════════════════════════════════════════════
    # 工具方法
    # ═══════════════════════════════════════════════════════════════════

    def _request_device_refresh(
        self,
        source: str,
        show_toast: bool,
        force_refresh: bool = False,
        allow_cached_replay: bool = False,
    ) -> None:
        """调度一次设备页快照刷新。"""
        # 设备页控件尚未构建完成时直接返回，避免提前操作空引用。
        if not self.device_tab.device_list_column:
            return
        try:
            # 把刷新任务挂到 Flet 异步循环，避免按钮事件里同步阻塞。
            self.page.run_task(
                self._request_device_refresh_async,
                source,
                show_toast,
                force_refresh,
                allow_cached_replay,
            )
        except Exception:
            # 调度失败时记异常日志，方便排查生命周期时序问题。
            log.exception("调度设备刷新协调器任务失败", source=source)

    async def _request_device_refresh_async(
        self,
        source: str,
        show_toast: bool,
        force_refresh: bool = False,
        allow_cached_replay: bool = False,
    ) -> None:
        """通过协调器请求快照并回填设备页。"""
        try:
            # 从统一协调器读取设备页快照。
            snapshot = await self.device_refresh_coordinator.request_refresh(
                source=source,
                force_refresh=force_refresh,
                allow_cached_replay=allow_cached_replay,
            )
            # 把快照应用到设备页，避免 app 层重复拼装 UI 数据。
            self.device_tab.apply_snapshot(snapshot=snapshot, source=source, show_toast=show_toast)
        except Exception:
            # 刷新失败时记录完整堆栈，避免静默丢失诊断信息。
            log.exception("通过协调器刷新设备页失败", source=source)

    def _run_action(self, action_name: str, fn: Callable[[], str | list[str]]) -> None:
        # 已有后台动作执行中时直接提示，避免多个重操作并发打架。
        if self._action_running:
            # 给用户明确反馈，避免误以为当前点击无效。
            self._show_snack("已有设备动作执行中，请等待当前操作完成。")
            return
        try:
            # 标记当前已有后台动作执行中。
            self._action_running = True
            # 在后台任务中执行真正的重操作，避免阻塞 Flet 事件线程。
            self.page.run_task(self._run_action_async, action_name, fn)
        except Exception as exc:
            # 调度失败时立即复位动作标记，避免后续按钮永久不可用。
            self._action_running = False
            # 记录调度异常，便于定位 Flet 任务调度问题。
            log.exception("调度 GUI 动作任务失败", action=action_name, error=str(exc))
            # 给用户返回可读错误提示。
            self._show_snack(f"{action_name} 失败: {exc}")

    async def _run_action_async(self, action_name: str, fn: Callable[[], str | list[str]]) -> None:
        """把设备重操作放到后台线程执行，避免卡住 GUI 主线程。"""
        # 记录动作总起点时间，用于输出总耗时。
        action_started_at = time.monotonic()
        # 先记一条开始日志，便于确认按钮点击事件已触发。
        log.info("收到 GUI 动作请求", action=action_name)
        # 初始化动作结果文案，后续统一用于提示条展示。
        message_text = ""
        # 初始化动作函数执行耗时（毫秒）。
        fn_elapsed_ms = 0
        # 初始化动作后刷新耗时（毫秒）。
        refresh_elapsed_ms = 0
        try:
            # 记录动作函数执行起点。
            fn_started_at = time.monotonic()
            # 把具体动作函数放到后台线程执行，避免 UI 主线程被阻塞。
            result = await asyncio.to_thread(fn)
            # 计算动作函数执行耗时。
            fn_elapsed_ms = int((time.monotonic() - fn_started_at) * 1000)
            # 列表返回值场景（批量动作）。
            if isinstance(result, list):
                # 拼接批量动作返回消息。
                message_text = f"{action_name}: {'; '.join(result)}"
            # 单条返回值场景（单设备动作）。
            else:
                # 直接构造单条动作提示文案。
                message_text = f"{action_name}: {result}"
            # 记录动作成功日志。
            log.info("GUI 动作执行完成", action=action_name, message=message_text, fn_elapsed_ms=fn_elapsed_ms)
        except Exception as exc:
            # 记录异常堆栈，便于定位失败原因。
            log.exception("执行动作失败", action=action_name, fn_elapsed_ms=fn_elapsed_ms)
            # 失败场景下也要给出可读反馈文案。
            message_text = f"{action_name} 失败: {exc}"
        # 尝试展示提示条（内部已做异常兜底）。
        self._show_snack(message_text)
        try:
            # 记录动作后刷新设备区起点。
            refresh_started_at = time.monotonic()
            # 动作后直接驱动协调器强制刷新，避免继续使用旧 adb 缓存。
            snapshot = await self.device_refresh_coordinator.request_refresh(
                source="action",
                force_refresh=True,
            )
            # 把最新快照应用到设备页，保证用户立刻看到结果。
            self.device_tab.apply_snapshot(snapshot=snapshot, source="action", show_toast=False)
            # 计算动作后刷新耗时。
            refresh_elapsed_ms = int((time.monotonic() - refresh_started_at) * 1000)
            # 刷新耗时较长时打告警日志，便于定位卡顿。
            if refresh_elapsed_ms >= 1200:
                log.warning("动作后刷新设备区耗时较长", action=action_name, refresh_elapsed_ms=refresh_elapsed_ms)
            # 刷新耗时正常时打调试日志。
            else:
                log.debug("动作后刷新设备区完成", action=action_name, refresh_elapsed_ms=refresh_elapsed_ms)
        except Exception:
            # 刷新失败不影响主流程，仅记录日志排查。
            log.exception("动作后刷新设备区失败", action=action_name, refresh_elapsed_ms=refresh_elapsed_ms)
        finally:
            # 无论成功失败都要复位动作标记，保证后续按钮可再次使用。
            self._action_running = False
        # 计算动作总耗时（包含动作执行、提示条与刷新触发）。
        total_elapsed_ms = int((time.monotonic() - action_started_at) * 1000)
        # 总耗时超过阈值时记录告警，便于后续定位卡住点。
        if total_elapsed_ms >= 1500:
            log.warning(
                "GUI 动作总耗时较长",
                action=action_name,
                total_elapsed_ms=total_elapsed_ms,
                fn_elapsed_ms=fn_elapsed_ms,
                refresh_elapsed_ms=refresh_elapsed_ms,
            )
        # 总耗时正常时记录调试日志。
        else:
            log.debug(
                "GUI 动作总耗时完成",
                action=action_name,
                total_elapsed_ms=total_elapsed_ms,
                fn_elapsed_ms=fn_elapsed_ms,
                refresh_elapsed_ms=refresh_elapsed_ms,
            )

    def _show_snack(self, message: str) -> None:
        # 尝试展示提示条；异常时只记日志，不再把异常抛回按钮事件。
        try:
            # 构造提示条控件，统一消息展示入口。
            snack = ft.SnackBar(content=ft.Text(str(message)), duration=3000)
            # flet 0.80.5 使用 show_dialog 打开 SnackBar（Page.open 不可用）。
            self.page.show_dialog(snack)
            # 立即刷新页面，让提示条及时显示。
            self.page.update()
        except Exception:
            # 记录提示条异常，避免用户误以为“点击无响应”。
            log.exception("展示提示条失败", message=message)

    # ═══════════════════════════════════════════════════════════════════
    # 后台监控
    # ═══════════════════════════════════════════════════════════════════

    async def _monitor_devices_loop(self) -> None:
        while self._monitor_running:
            await asyncio.sleep(DEVICE_MONITOR_INTERVAL_SEC)
            if not self._logged_in:
                continue
            # 当前有后台设备动作执行时跳过自动刷新，避免和 stop/start 等重操作并发。
            if self._action_running:
                continue
            # 当前不在“设备列表”页时跳过自动刷新，避免后台日志扫描影响账号筛选流畅度。
            if self._current_tab_index != 0:
                continue
            await self._request_device_refresh_async(source="auto", show_toast=False)

    # ═══════════════════════════════════════════════════════════════════
    # 清理
    # ═══════════════════════════════════════════════════════════════════

    def _shutdown(self) -> None:
        # 使用幂等锁保护停机核心逻辑，避免窗口关闭、信号和 atexit 重复执行。
        with self._shutdown_lock:
            # 已执行过停机时直接返回，避免重复 stop_all 和重复 close。
            if self._shutdown_done:
                # 记录幂等命中日志，便于排查多入口同时关闭。
                log.debug("GUI 停机逻辑重复触发，已跳过")
                # 结束本次停机调用。
                return
            # 标记停机逻辑已经执行，后续入口不再重复收口。
            self._shutdown_done = True
        # 停掉后台监控循环，避免退出期间继续触发自动刷新。
        self._monitor_running = False
        try:
            self.device_refresh_coordinator.close()
        except Exception:
            log.exception("GUI 退出清理失败（device_refresh_coordinator.close）")
        try:
            messages = self.manager.stop_all()
            log.info("GUI 退出清理完成", count=len(messages), messages=messages)
        except Exception:
            log.exception("GUI 退出清理失败（stop_all）")
        try:
            released = self.manager.reset_all_running_accounts(reason="gui_shutdown")
            log.info("GUI 退出兜底释放运行中账号完成", released=released)
        except Exception:
            log.exception("GUI 退出清理失败（reset_all_running_accounts）")
        try:
            self.manager.close()
        except Exception:
            log.exception("GUI 退出清理失败（manager.close）")
        try:
            self.user_db.close()
        except Exception:
            log.exception("GUI 退出清理失败（user_db.close）")


# ═══════════════════════════════════════════════════════════════════════
# 入口函数
# ═══════════════════════════════════════════════════════════════════════

def run_gui(loop_interval_sec: float = WORKER_LOOP_INTERVAL_SEC) -> None:
    """GUI 启动函数，供主入口调用。"""
    # 在打包产物中补齐 FLET_PLATFORM，避免出现“宿主窗口 + 额外空白窗口”双开现象。
    # 说明：flet 通过该变量判断是否 embedded 运行；源码模式下不应强制设置。
    if not os.environ.get("FLET_PLATFORM"):
        # flet pack（PyInstaller）场景通常由 flet 内部自行处理平台模式。
        # 若这里强制覆写，可能出现“窗口空白/无法正常显示”的问题。
        if getattr(sys, "_MEIPASS", None):
            log.info("检测到 PyInstaller 打包运行，跳过 FLET_PLATFORM 强制设置")
        else:
            # 读取当前解释器/可执行文件路径，用于判断运行形态。
            exe_path = Path(sys.executable)
            # 转字符串便于做路径片段判断。
            exe_text = str(exe_path)
            # 读取当前系统名（darwin/windows/linux）。
            system_name = platform.system().lower()

            # macOS 打包 app：典型路径包含 ".app/Contents/MacOS/"。
            is_macos_bundle = system_name == "darwin" and ".app/Contents/MacOS/" in exe_text
            # Windows 打包 exe：扩展名为 .exe 且文件名不包含 python。
            is_windows_bundle = system_name.startswith("win") and exe_path.suffix.lower() == ".exe" and "python" not in exe_path.name.lower()

            if is_macos_bundle:
                # 标记为 embedded macOS 运行模式。
                os.environ["FLET_PLATFORM"] = "macos"
                log.info("检测到 macOS 打包运行，已设置 FLET_PLATFORM", value=os.environ["FLET_PLATFORM"])
            elif is_windows_bundle:
                # 标记为 embedded Windows 运行模式。
                os.environ["FLET_PLATFORM"] = "windows"
                log.info("检测到 Windows 打包运行，已设置 FLET_PLATFORM", value=os.environ["FLET_PLATFORM"])

    # 缓存当前 GUI 应用实例，供 Ctrl+C 信号处理时复用停机逻辑。
    app_holder: dict[str, AutoVTGuiApp | None] = {"app": None}
    # 记录是否已处理过退出信号，避免重复执行停机。
    exit_signal_handled = False
    # 记录本次注册过的旧信号处理器，便于退出时恢复。
    old_signal_handlers: dict[int, object] = {}

    # 定义统一退出信号处理方法。
    def _handle_exit_signal(signum: int, _frame: object | None) -> None:
        # 声明要修改外层标记变量。
        nonlocal exit_signal_handled
        # 已处理过时直接返回，防止重复 stop_all。
        if exit_signal_handled:
            return
        # 标记已处理，后续信号不再重复执行。
        exit_signal_handled = True
        # 读取当前信号名，便于日志区分 Ctrl+C 和终端结束等场景。
        signal_name = getattr(signal.Signals(signum), "name", str(signum))
        # 记录信号停机日志，便于排查源码模式终端结束链路。
        log.warning("GUI 收到退出信号，准备停止全部并退出", signal_name=signal_name, signum=signum)
        # 读取当前 GUI 应用实例。
        app = app_holder.get("app")
        # 存在应用实例时先执行优雅停机。
        if app is not None:
            # 使用异常保护停机流程，避免中断时再次抛栈。
            try:
                # 复用现有退出清理逻辑（stop_all + close）。
                app._shutdown()
            # 停机失败时记录日志，但仍继续退出进程。
            except Exception:
                # 打印完整异常栈，满足错误可追踪。
                log.exception("退出信号停机清理失败", signal_name=signal_name, signum=signum)
        # 以中断退出码强制结束进程，避免 Flet 事件循环继续阻塞。
        raise SystemExit(128 + int(signum))

    # 统一注册源码模式常见退出信号，保证 Ctrl+C、kill、终端结束都走同一停机链路。
    for current_signal in (signal.SIGINT, signal.SIGTERM, getattr(signal, "SIGHUP", None)):
        # 跳过当前平台不存在的信号常量。
        if current_signal is None:
            continue
        # 保存旧处理器，便于 finally 恢复。
        old_signal_handlers[int(current_signal)] = signal.getsignal(current_signal)
        # 把当前信号绑定到统一退出处理器。
        signal.signal(current_signal, _handle_exit_signal)

    # 定义 Flet 入口回调。
    def _main(page: ft.Page) -> None:
        try:
            # 创建 GUI 应用实例。
            app = AutoVTGuiApp(page=page, loop_interval_sec=loop_interval_sec)
            # 缓存应用实例，供 Ctrl+C 处理器停机使用。
            app_holder["app"] = app
            # 启动 GUI 页面。
            app.start()
        except Exception as exc:
            # 记录 GUI 启动阶段完整异常堆栈，避免只在 Flet 顶层看到裸异常。
            log.exception("GUI 启动失败", error=str(exc))
            try:
                # 清空页面，避免保留半初始化控件。
                page.clean()
                # 展示可读的启动失败提示，避免用户看到空白页。
                page.add(
                    ft.Container(
                        expand=True,
                        alignment=ft.Alignment.CENTER,
                        content=ft.Text(f"GUI 启动失败: {exc}", color=ft.Colors.RED_700, size=16),
                    )
                )
                # 提交页面更新，确保错误信息立即可见。
                page.update()
            except Exception:
                # 连错误页都展示失败时，只记录日志避免再次抛栈。
                log.exception("展示 GUI 启动失败页面失败", error=str(exc))

    # 执行 Flet 事件循环。
    try:
        # 启动 Flet 应用主循环。
        ft.app(target=_main, assets_dir="assets")
    # 捕获 Ctrl+C 触发的 SystemExit，避免额外 traceback。
    except SystemExit as exc:
        # 仅在中断退出码场景吞掉异常，其它退出码继续抛出。
        if int(getattr(exc, "code", 0) or 0) != 130:
            raise
    # 捕获 GUI 主循环异常，统一记录错误日志，避免启动失败时静默退出。
    except Exception as exc:
        # 记录 GUI 主循环异常堆栈，便于排查 Flet 运行时问题。
        log.exception("GUI 主循环异常退出", error=str(exc))
        # 继续向上抛出异常，保持调用方可感知失败。
        raise
    # 退出时恢复原始 SIGINT 处理器。
    finally:
        # 逐个恢复调用 run_gui 前的原始信号处理器。
        for signum, old_handler in old_signal_handlers.items():
            # 尝试恢复当前信号的旧处理器。
            signal.signal(signum, old_handler)


def main() -> None:
    """提供 `python -m autovt.gui.app` 兼容入口。"""
    run_gui()
