"""GUI 主应用协调器 — 负责页面级编排和生命周期管理。"""

from __future__ import annotations

import asyncio
import atexit
import os
import platform
import sys
from pathlib import Path
from typing import Callable

import flet as ft

from autovt.gui.account_tab import AccountTab
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

        # ── 后端服务 ──
        self.manager = DeviceProcessManager(loop_interval_sec=loop_interval_sec)
        self.user_db = UserDB()
        self.user_db.connect()

        # ── 子模块 ──
        self.login_view = LoginView(page=page, on_login_success=self._on_login_success)
        self.device_tab = DeviceTab(
            page=page, manager=self.manager,
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
        self.device_tab.refresh(source="init", show_toast=False)
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
            self.device_tab.refresh(source="tab_switch", show_toast=False)
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
        self._show_snack("正在退出并停止全部进程...")
        self._shutdown()
        self.page.run_task(self._close_window_async)

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

    def _run_action(self, action_name: str, fn: Callable[[], str | list[str]]) -> None:
        # 先记一条开始日志，便于确认按钮点击事件已触发。
        log.info("收到 GUI 动作请求", action=action_name)
        # 初始化动作结果文案，后续统一用于提示条展示。
        message_text = ""
        try:
            # 执行具体动作函数（如 start_all / stop_all / start_worker 等）。
            result = fn()
            # 列表返回值场景（批量动作）。
            if isinstance(result, list):
                # 拼接批量动作返回消息。
                message_text = f"{action_name}: {'; '.join(result)}"
            # 单条返回值场景（单设备动作）。
            else:
                # 直接构造单条动作提示文案。
                message_text = f"{action_name}: {result}"
            # 记录动作成功日志。
            log.info("GUI 动作执行完成", action=action_name, message=message_text)
        except Exception as exc:
            # 记录异常堆栈，便于定位失败原因。
            log.exception("执行动作失败", action=action_name)
            # 失败场景下也要给出可读反馈文案。
            message_text = f"{action_name} 失败: {exc}"
        # 尝试展示提示条（内部已做异常兜底）。
        self._show_snack(message_text)
        try:
            # 动作后立即刷新设备区，避免用户等待轮询才看到状态变化。
            self.device_tab.refresh(source="action", show_toast=False)
            # 提交页面更新，保证刷新结果尽快可见。
            self.page.update()
        except Exception:
            # 刷新失败不影响主流程，仅记录日志排查。
            log.exception("动作后刷新设备区失败", action=action_name)

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
            self.device_tab.refresh(source="auto", show_toast=False)

    # ═══════════════════════════════════════════════════════════════════
    # 清理
    # ═══════════════════════════════════════════════════════════════════

    def _shutdown(self) -> None:
        if not self._monitor_running:
            return
        self._monitor_running = False
        try:
            messages = self.manager.stop_all()
            log.info("GUI 退出清理完成", count=len(messages), messages=messages)
        except Exception:
            log.exception("GUI 退出清理失败（stop_all）")
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

    def _main(page: ft.Page) -> None:
        app = AutoVTGuiApp(page=page, loop_interval_sec=loop_interval_sec)
        app.start()
    ft.app(target=_main, assets_dir="assets")


def main() -> None:
    """提供 `python -m autovt.gui.app` 兼容入口。"""
    run_gui()
