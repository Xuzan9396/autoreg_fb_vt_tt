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
        self.mojiwang_desc_text: ft.Text | None = None
        self.status_23_retry_desc_text: ft.Text | None = None
        self.vt_pwd_desc_text: ft.Text | None = None
        self.fb_delete_num_desc_text: ft.Text | None = None
        self.setting_fb_del_num_desc_text: ft.Text | None = None
        self.config_last_refresh_text: ft.Text | None = None
        # 标记“刷新任务是否进行中”，避免重复触发导致并发读库。
        self._refreshing = False

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
            # 限制最多输入 1 位数字，避免输入多位值。
            max_length=1,
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
            width=320,
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
            width=320,
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
            width=320,
            # 使用数字键盘输入。
            keyboard_type=ft.KeyboardType.NUMBER,
            # 输入变化时做软校验。
            on_change=self._sanitize_setting_fb_del_num_input,
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
                            self.vt_pwd_desc_text,
                            self.vt_pwd_value_input,
                            self.fb_delete_num_desc_text,
                            self.fb_delete_num_value_input,
                            self.setting_fb_del_num_desc_text,
                            self.setting_fb_del_num_value_input,
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

    def refresh(self, source: str, show_toast: bool) -> None:
        """刷新设置 Tab 数据。"""
        if (
            not self.mojiwang_value_input
            or not self.status_23_retry_value_input
            or not self.vt_pwd_value_input
            or not self.fb_delete_num_value_input
            or not self.setting_fb_del_num_value_input
            or not self.mojiwang_desc_text
            or not self.status_23_retry_desc_text
            or not self.vt_pwd_desc_text
            or not self.fb_delete_num_desc_text
            or not self.setting_fb_del_num_desc_text
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

            # 计算五个配置中较新的更新时间。
            latest_update_at = max(
                int(mojiwang_row.get("update_at", 0)),
                int(retry_row.get("update_at", 0)),
                int(vt_pwd_row.get("update_at", 0)),
                int(fb_delete_num_row.get("update_at", 0)),
                int(setting_fb_del_num_row.get("update_at", 0)),
            )
            # 组装配置快照并返回给主线程渲染。
            return {
                "mojiwang_val": str(mojiwang_row.get("val", "3")),
                "retry_val": str(retry_row.get("val", "0")),
                "vt_pwd_val": str(vt_pwd_row.get("val", "")),
                "fb_delete_num_val": str(fb_delete_num_row.get("val", "0")),
                "setting_fb_del_num_val": str(setting_fb_del_num_row.get("val", "0")),
                "mojiwang_desc": str(mojiwang_row.get("desc", MOJIWANG_RUN_NUM_DESC)),
                "retry_desc": str(retry_row.get("desc", STATUS_23_RETRY_MAX_DESC)),
                "vt_pwd_desc": str(vt_pwd_row.get("desc", VT_PWD_DESC)),
                "fb_delete_num_desc": FB_DELETE_NUM_DESC,
                "setting_fb_del_num_desc": SETTING_FB_DEL_NUM_DESC,
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
        """保存 mojiwang_run_num、status_23_retry_max_num、vt_pwd、fb_delete_num 与 setting_fb_del_num 配置值。"""
        if (
            not self.mojiwang_value_input
            or not self.status_23_retry_value_input
            or not self.vt_pwd_value_input
            or not self.fb_delete_num_value_input
            or not self.setting_fb_del_num_value_input
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
