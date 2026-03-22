# 导入 Any 类型，方便给 Poco 节点做类型标注。
from typing import Any
# 导入 Path，便于解析外置 apk 路径。
from pathlib import Path
# 导入 sys，便于读取打包后可执行文件路径。
import sys
# 导入随机模块，用于头像相册随机选图。
import random
# 导入时间模块，用于精确统计轮询超时。
import time

# 导入清理应用数据方法。
from airtest.core.api import clear_app
# 导入回到桌面方法。
from airtest.core.api import home
# 导入按键事件方法，用于切换输入焦点。
from airtest.core.api import keyevent
# 导入安装应用方法，用于 fb_delete_num 命中时重装 Facebook。
from airtest.core.api import install
# 导入粘贴事件方法，用于向当前焦点粘贴文本。
from airtest.core.api import paste
# 导入设置剪贴板方法，配合 paste 做输入兜底。
from airtest.core.api import set_clipboard
# 导入休眠方法，避免轮询过快。
from airtest.core.api import sleep
# 导入启动应用方法。
from airtest.core.api import start_app
# 导入停止应用方法。
from airtest.core.api import stop_app
# 导入滑动方法，用于设置页下拉查找目标入口。
from airtest.core.api import swipe
# 导入输入事件方法，用于给当前焦点输入文本。
from airtest.core.api import text
# 导入卸载应用方法，用于 fb_delete_num 命中时卸载 Facebook。
from airtest.core.api import uninstall
# 导入唤醒屏幕方法。
from airtest.core.api import wake
from airtest.core.api import exists
from airtest.core.api import wait
from airtest.core.api import touch
from airtest.core.cv import Template

# 导入路径安全化方法，便于复用 worker 的日志目录规则。
from autovt.adb import safe_path_part
# 导入项目日志工厂。
from autovt.logs import get_logger
# 导入 Poco 节点代理类型，用于连接重建后按 query 重新绑定节点。
from poco.proxy import UIObjectProxy
# 导入运行时重建相关方法。
from autovt.runtime import create_poco
from autovt.runtime import get_poco
from autovt.runtime import setup_device
# 导入任务上下文对象，统一承载设备信息。
from autovt.tasks.task_context import TaskContext
# 导入用户数据库封装，供任务结束后回写账号状态。
from autovt.userdb.user_db import FB_DELETE_NUM_MAX
from autovt.userdb.user_db import FB_DELETE_NUM_MIN
from autovt.userdb.user_db import PROXYIP_END_NUM_DEFAULT
from autovt.userdb.user_db import PROXYIP_END_NUM_KEY
from autovt.userdb.user_db import PROXYIP_NUM_MAX
from autovt.userdb.user_db import PROXYIP_NUM_MIN
from autovt.userdb.user_db import PROXYIP_START_NUM_DEFAULT
from autovt.userdb.user_db import PROXYIP_START_NUM_KEY
from autovt.userdb.user_db import SETTING_FB_DEL_NUM_DEFAULT
from autovt.userdb.user_db import SETTING_FB_DEL_NUM_KEY
from autovt.userdb.user_db import VT_DELETE_NUM_DEFAULT
from autovt.userdb.user_db import VT_DELETE_NUM_KEY
from autovt.userdb.user_db import UserDB
from autovt.desc import  *
import json
from datetime import datetime

from autovt.emails import getfackbook_code

# 定义“打开设置并执行清理流程”的任务类。
class OpenSettingsTask:
    # 定义任务类的初始化方法，强制要求传入完整上下文。
    def __init__(self, task_context: TaskContext) -> None:
        # 创建当前任务专用日志对象。
        self.log = get_logger("task.open_settings")
        # 保存当前任务实例使用的 Poco 对象（先置空，后续再获取）。
        self.poco: Any | None = None
        # 保存任务上下文对象，后续字段统一从这里取值。
        self.task_context = task_context
        # 强制校验 serial/locale/lang 必填字段，缺失则立即抛错阻断执行。
        self.task_context.ensure_required()
        # 保存设备 serial，便于日志和分支判断使用。
        self.device_serial = self.task_context.serial
        # 保存设备语言区域码（例如 en-US / zh-CN）。
        self.device_locale = self.task_context.device_locale
        # 保存设备语言主码（例如 en / zh）。
        self.device_lang = self.task_context.device_lang
        # 读取当前设备绑定的一条 t_user 数据（完整账号信息)
        self.user_info = dict(self.task_context.user_info or {})

        print(f"DEBUG DATA: {json.dumps(self.user_info, indent=4, ensure_ascii=False)}")

        # 读取 t_config 全量 key->val 映射。
        self.config_map = {str(k): str(v) for k, v in dict(self.task_context.config_map or {}).items()}
        # 读取当前 worker 子进程任务轮次（由 worker 在每次 run_once 前注入）。
        self.worker_loop_seq = self._read_worker_loop_seq()
        # 读取当前 worker 透传下来的注册方式，默认回退为 facebook。
        self.register_mode = self._read_register_mode()
        # 缓存当前账号邮箱，便于日志追踪。
        self.user_email = str(self.user_info.get("email_account", "")).strip()
        # 缓存 first_name，供 Facebook 表单输入。
        self.user_first_name = str(self.user_info.get("first_name", "")).strip()
        # 缓存 last_name，供 Facebook 表单输入。
        self.user_last_name = str(self.user_info.get("last_name", "")).strip()
        # 缓存密码，供 Facebook 表单输入。
        self.pwd = str(self.user_info.get("pwd", "")).strip()
        # 缓存全局 vt_pwd，供账号密码缺失时兜底使用。
        self.vt_pwd = str(self.config_map.get("vt_pwd", "")).strip()
        # 当账号 pwd 为空且配置了全局 vt_pwd 时，自动使用全局密码兜底。
        if self.pwd == "" and self.vt_pwd != "":
            # 使用全局 vt_pwd 作为当前任务密码。
            self.pwd = self.vt_pwd
            # 记录兜底日志，便于排查密码来源。
            self.log.warning("账号 pwd 为空，已使用全局 vt_pwd 兜底", user_email=self.user_email)
        # 保存需要先清理数据的业务应用包名。
        self.vinted_package = "fr.vinted"
        # 保存插件应用包名。
        self.mojiwang_packge = "com.yztc.studio.plugin"
        # Facebook 应用包名
        self.facebook_package = "com.facebook.katana"
        # 系统设置应用包名。
        self.settings_package = "com.android.settings"
        # 代理
        self.nekobox_package = "moe.nb4a"
        # vinted
        # 保存“清理按钮”资源 ID。
        self.mojiwang_wipe_button_id = "com.yztc.studio.plugin:id/wipedev_btn_wipe"
        # 保存“任务结束提示”资源 ID。
        self.mojiwang_done_msg_id = "com.yztc.studio.plugin:id/wipe_task_tv_msg"
        # 保存“任务结束提示”文本内容。
        self.mojiwang_done_msg_text = "任务结束-点击返回"
        # 从 t_config 读取抹机王轮次，默认值回退到 3。
        self.mojiwang_loop_count = self._read_mojiwang_loop_count()
        # 从 t_config 读取 Facebook 删除控制（0=不删除，1=第2轮删除一次）。
        self.fb_delete_num = self._read_fb_delete_num()
        # 从 t_config 读取 Vinted 删除控制（0=不删除，>0=按周期重装）。
        self.vt_delete_num = self._read_vt_delete_num()
        # 从 t_config 读取设置页 Facebook 账号清理控制（0=不清理，>0=按周期清理）。
        self.setting_fb_del_num = self._read_setting_fb_del_num()
        # 从 t_config 读取代理开始位置配置（1~5）。
        self.proxyip_start_num = self._read_proxyip_start_num()
        # self.proxyip_start_num = 1
        # 从 t_config 读取代理结束位置配置（1~5）。
        self.proxyip_end_num = self._read_proxyip_end_num()
        # self.proxyip_end_num = 5
        # 保存每次等待控件出现的最大秒数。
        self.mojiwang_wait_timeout_sec = 5.0
        # 创建用户数据库对象，供注册成功/失败后统一更新状态。
        self.user_db = UserDB()
        # 初始化通用失败原因缓存，供不同注册任务复用。
        self.task_result_reason = ""
        # 初始化通用失败状态码，默认普通失败写入 status=3。
        self.task_result_status = 3
        # 初始化 Facebook 失败原因缓存，失败时会写入 t_user.msg。
        self.facebook_error_reason = ""
        # 初始化 Facebook 失败状态码，默认普通失败写入 status=3。
        self.facebook_error_status = 3
        # 初始化“本轮是否检测到设备连接异常”标记，默认未检测到。
        self._runtime_disconnect_detected = False

    # 定义“读取抹机王轮次配置”的方法。
    def _read_mojiwang_loop_count(self) -> int:
        # 从配置映射读取 mojiwang_run_num，缺失时回退 3。
        raw_value = str(self.config_map.get("mojiwang_run_num", "3")).strip()
        # 尝试把配置值解析为整数。
        try:
            # 转成整数做边界校验。
            parsed_value = int(raw_value)
        # 非法值（非整数）时回退默认值。
        except Exception:
            # 返回默认轮次 3。
            return 3
        # 小于最小值时回退默认值。
        if parsed_value < 1:
            # 返回默认轮次 3。
            return 3
        # 大于最大值时截断到 100，避免异常大值拖慢流程。
        if parsed_value > 100:
            # 返回上限值 100。
            return 100
        # 返回合法轮次配置值。
        return parsed_value

    # 定义“读取 worker 轮次”的方法。
    def _read_worker_loop_seq(self) -> int:
        # 从 task_context.extras 读取 worker 注入的轮次值。
        raw_value = (self.task_context.extras or {}).get("worker_loop_seq", 0)
        # 尝试把轮次值解析成整数。
        try:
            # 转成整数后统一做边界保护。
            parsed_value = int(raw_value)
        # 非法值时回退到 0。
        except Exception:
            # 返回默认值 0。
            return 0
        # 小于 0 时回退到 0。
        if parsed_value < 0:
            # 返回最小值 0。
            return 0
        # 返回合法轮次。
        return parsed_value

    # 定义“读取注册方式”的方法。
    def _read_register_mode(self) -> str:
        # 从 task_context.extras 读取 worker 透传的注册方式。
        raw_value = str((self.task_context.extras or {}).get("register_mode", "facebook")).strip().lower()
        # 非法值时回退到 facebook，避免旧调用链直接报错。
        if raw_value not in {"facebook", "vinted"}:
            # 记录告警日志，便于排查启动链路是否正确传值。
            self.log.warning("注册方式缺失或非法，已回退为 facebook", register_mode=raw_value)
            # 返回默认注册方式。
            return "facebook"
        # 返回合法注册方式。
        return raw_value

    # 定义“读取 Facebook 重装周期配置”的方法。
    def _read_fb_delete_num(self) -> int:
        # 从配置映射读取 fb_delete_num，缺失时回退 0。
        raw_value = str(self.config_map.get("fb_delete_num", "0")).strip()
        # 尝试解析整数。
        try:
            # 转成整数后统一做边界保护。
            parsed_value = int(raw_value)
        # 非法值时回退默认值 0。
        except Exception:
            # 返回默认值 0。
            return 0
        # 小于最小值时回退到最小值。
        if parsed_value < FB_DELETE_NUM_MIN:
            # 返回最小值。
            return FB_DELETE_NUM_MIN
        # 大于最大值时截断到最大值。
        if parsed_value > FB_DELETE_NUM_MAX:
            # 返回最大值。
            return FB_DELETE_NUM_MAX
        # 返回合法配置值。
        return parsed_value

    # 定义“读取 Vinted 重装周期配置”的方法。
    def _read_vt_delete_num(self) -> int:
        # 从配置映射读取 vt_delete_num，缺失时回退默认值 0。
        raw_value = str(self.config_map.get(VT_DELETE_NUM_KEY, VT_DELETE_NUM_DEFAULT)).strip()
        # 尝试解析整数。
        try:
            # 转成整数后统一做边界保护。
            parsed_value = int(raw_value)
        # 非法值时回退默认值 0。
        except Exception:
            # 返回默认值 0。
            return int(VT_DELETE_NUM_DEFAULT)
        # 小于最小值时回退到最小值。
        if parsed_value < FB_DELETE_NUM_MIN:
            # 返回最小值。
            return FB_DELETE_NUM_MIN
        # 大于最大值时截断到最大值。
        if parsed_value > FB_DELETE_NUM_MAX:
            # 返回最大值。
            return FB_DELETE_NUM_MAX
        # 返回合法配置值。
        return parsed_value

    # 定义“读取设置页 Facebook 账号清理周期配置”的方法。
    def _read_setting_fb_del_num(self) -> int:
        # 从配置映射读取 setting_fb_del_num，缺失时回退 0。
        raw_value = str(self.config_map.get(SETTING_FB_DEL_NUM_KEY, SETTING_FB_DEL_NUM_DEFAULT)).strip()
        # 尝试解析整数。
        try:
            # 转成整数后统一做边界保护。
            parsed_value = int(raw_value)
        # 非法值时回退默认值 0。
        except Exception:
            # 返回默认值 0。
            return int(SETTING_FB_DEL_NUM_DEFAULT)
        # 小于最小值时回退到最小值。
        if parsed_value < FB_DELETE_NUM_MIN:
            # 返回最小值。
            return FB_DELETE_NUM_MIN
        # 大于最大值时截断到最大值。
        if parsed_value > FB_DELETE_NUM_MAX:
            # 返回最大值。
            return FB_DELETE_NUM_MAX
        # 返回合法配置值。
        return parsed_value

    # 定义“读取代理开始位置配置”的方法。
    def _read_proxyip_start_num(self) -> int:
        # 从配置映射读取 proxyip_start_num，缺失时回退默认值 1。
        raw_value = str(self.config_map.get(PROXYIP_START_NUM_KEY, PROXYIP_START_NUM_DEFAULT)).strip()
        # 尝试解析整数。
        try:
            # 转成整数后统一做边界保护。
            parsed_value = int(raw_value)
        # 非法值时回退默认值 1。
        except Exception:
            # 返回默认值 1。
            return int(PROXYIP_START_NUM_DEFAULT)
        # 小于最小值时回退到最小值。
        if parsed_value < PROXYIP_NUM_MIN:
            # 返回最小值。
            return PROXYIP_NUM_MIN
        # 大于最大值时截断到最大值。
        if parsed_value > PROXYIP_NUM_MAX:
            # 返回最大值。
            return PROXYIP_NUM_MAX
        # 返回合法配置值。
        return parsed_value

    # 定义“读取代理结束位置配置”的方法。
    def _read_proxyip_end_num(self) -> int:
        # 从配置映射读取 proxyip_end_num，缺失时回退默认值 1。
        raw_value = str(self.config_map.get(PROXYIP_END_NUM_KEY, PROXYIP_END_NUM_DEFAULT)).strip()
        # 尝试解析整数。
        try:
            # 转成整数后统一做边界保护。
            parsed_value = int(raw_value)
        # 非法值时回退默认值 1。
        except Exception:
            # 返回默认值 1。
            return int(PROXYIP_END_NUM_DEFAULT)
        # 小于最小值时回退到最小值。
        if parsed_value < PROXYIP_NUM_MIN:
            # 返回最小值。
            return PROXYIP_NUM_MIN
        # 大于最大值时截断到最大值。
        if parsed_value > PROXYIP_NUM_MAX:
            # 返回最大值。
            return PROXYIP_NUM_MAX
        # 返回合法配置值。
        return parsed_value

    # 定义“为 Nekobox 模式节点计算安全随机索引”的方法。
    def _resolve_safe_proxy_mode_index(self, total_modes: int) -> int | None:
        # 没有任何模式节点时直接返回空，交给调用方按失败处理。
        if total_modes <= 0:
            # 记录错误日志。
            self.log.error("Nekobox 配置列表为空，无法选择代理模式", package=self.nekobox_package, total_modes=total_modes)
            # 返回 None 表示无法得到可用索引。
            return None
        # 读取配置中的开始位置。
        start_num = int(self.proxyip_start_num)
        # 读取配置中的结束位置。
        end_num = int(self.proxyip_end_num)
        # 反向区间时自动交换，避免异常配置导致全流程失败。
        if start_num > end_num:
            # 记录告警日志。
            self.log.warning(
                "代理点击范围配置反向，已自动交换开始和结束位置",
                package=self.nekobox_package,
                proxyip_start_num=start_num,
                proxyip_end_num=end_num,
            )
            # 交换开始和结束位置。
            start_num, end_num = end_num, start_num
        # 转成 0-based 起始索引。
        configured_start_index = max(0, start_num - 1)
        # 转成 0-based 结束索引。
        configured_end_index = max(0, end_num - 1)
        # 计算当前模式节点可用的最大索引。
        max_available_index = total_modes - 1
        # 把起始索引压到可用范围内。
        safe_start_index = min(configured_start_index, max_available_index)
        # 把结束索引压到可用范围内。
        safe_end_index = min(configured_end_index, max_available_index)
        # 压缩后若起始索引仍大于结束索引，则回退到结束索引。
        if safe_start_index > safe_end_index:
            # 把起始索引对齐到结束索引，保证 random 范围合法。
            safe_start_index = safe_end_index
        # 在最终安全范围内随机一个模式索引。
        selected_mode_index = random.randint(safe_start_index, safe_end_index)
        # 记录本轮实际使用的模式索引，便于排查越界和范围收缩。
        self.log.info(
            "已解析 Nekobox 代理点击索引",
            package=self.nekobox_package,
            proxyip_start_num=start_num,
            proxyip_end_num=end_num,
            total_modes=total_modes,
            safe_start_index=safe_start_index,
            safe_end_index=safe_end_index,
            selected_mode_index=selected_mode_index,
        )
        # 返回安全随机后的 0-based 索引。
        return selected_mode_index

    # 定义“判断本轮是否需要执行 Facebook 重装”的方法。
    def _should_delete_fb_this_loop(self) -> bool:
        # 配置为 0 时不执行重装。
        if self.fb_delete_num <= 0:
            # 返回 False 表示不重装。
            return False
        # 当前轮次无效时不执行重装。
        if self.worker_loop_seq <= 0:
            # 返回 False 表示不重装。
            return False
        # 达到配置指定轮次后，每轮都执行重装。
        return self.worker_loop_seq >= self.fb_delete_num

    # 定义“判断本轮是否需要执行 Vinted 重装”的方法。
    def _should_delete_vt_this_loop(self) -> bool:
        # 配置为 0 时不执行重装。
        if self.vt_delete_num <= 0:
            # 返回 False 表示不重装。
            return False
        # 当前轮次无效时不执行重装。
        if self.worker_loop_seq <= 0:
            # 返回 False 表示不重装。
            return False
        # 达到配置指定轮次后，每轮都执行重装。
        return self.worker_loop_seq >= self.vt_delete_num

    # 定义“判断本轮是否需要执行设置页 Facebook 账号清理”的方法。
    def _should_delete_setting_fb_this_loop(self) -> bool:
        # 配置为 0 时不执行设置页清理。
        if self.setting_fb_del_num <= 0:
            # 返回 False 表示不清理。
            return False
        # 当前轮次无效时不执行设置页清理。
        if self.worker_loop_seq <= 0:
            # 返回 False 表示不清理。
            return False
        # 只有“循环次数 % setting_fb_del_num == 0”时才执行设置页清理。
        return (self.worker_loop_seq % self.setting_fb_del_num) == 0

    # 定义“解析 Facebook 安装包路径”的方法。
    def _resolve_facebook_apk_path(self) -> Path:
        # 保存候选路径列表，按优先级依次尝试。
        candidates: list[Path] = []
        # 读取当前可执行文件所在目录（源码运行/打包运行都可用）。
        exe_dir = Path(sys.executable).resolve().parent
        # 候选 1：可执行文件同级目录下的 apks/facebook.apk。
        candidates.append(exe_dir / "apks" / "facebook.apk")
        # 候选 2：可执行文件上一级目录下的 apks/facebook.apk。
        candidates.append(exe_dir.parent / "apks" / "facebook.apk")
        # 候选 3：macOS .app 场景下，app 包外层目录同级 apks/facebook.apk。
        try:
            # 尝试追加 .app 外层候选路径。
            candidates.append(exe_dir.parents[2] / "apks" / "facebook.apk")
        # 非 .app 目录结构时忽略该候选。
        except Exception:
            # 不中断流程，继续尝试其他候选路径。
            pass
        # 候选 4：当前工作目录下的 apks/facebook.apk。
        candidates.append(Path.cwd() / "apks" / "facebook.apk")
        # 候选 5：源码项目根目录下的 apks/facebook.apk。
        candidates.append(Path(__file__).resolve().parents[2] / "apks" / "facebook.apk")
        # 逐个候选检查文件是否存在。
        for candidate in candidates:
            # 命中存在且是文件时直接返回。
            if candidate.exists() and candidate.is_file():
                return candidate
        # 全部候选都不存在时抛出明确错误，便于排查。
        raise FileNotFoundError(
            "未找到 facebook.apk（期望外置在可执行文件同级 apks 目录），候选路径："
            + " / ".join(str(path) for path in candidates)
        )

    # 定义“解析 Vinted 安装包路径”的方法。
    def _resolve_vinted_apk_path(self) -> Path:
        # 保存候选路径列表，按优先级依次尝试。
        candidates: list[Path] = []
        # 读取当前可执行文件所在目录（源码运行/打包运行都可用）。
        exe_dir = Path(sys.executable).resolve().parent
        # 候选 1：可执行文件同级目录下的 apks/vinted.apk。
        candidates.append(exe_dir / "apks" / "vinted.apk")
        # 候选 2：可执行文件上一级目录下的 apks/vinted.apk。
        candidates.append(exe_dir.parent / "apks" / "vinted.apk")
        # 候选 3：macOS .app 场景下，app 包外层目录同级 apks/vinted.apk。
        try:
            # 尝试追加 .app 外层候选路径。
            candidates.append(exe_dir.parents[2] / "apks" / "vinted.apk")
        # 非 .app 目录结构时忽略该候选。
        except Exception:
            # 不中断流程，继续尝试其他候选路径。
            pass
        # 候选 4：当前工作目录下的 apks/vinted.apk。
        candidates.append(Path.cwd() / "apks" / "vinted.apk")
        # 候选 5：源码项目根目录下的 apks/vinted.apk。
        candidates.append(Path(__file__).resolve().parents[2] / "apks" / "vinted.apk")
        # 逐个候选检查文件是否存在。
        for candidate in candidates:
            # 命中存在且是文件时直接返回。
            if candidate.exists() and candidate.is_file():
                return candidate
        # 全部候选都不存在时抛出明确错误，便于排查。
        raise FileNotFoundError(
            "未找到 vinted.apk（期望外置在可执行文件同级 apks 目录），候选路径："
            + " / ".join(str(path) for path in candidates)
        )

    # 定义“解析图片资源路径”的方法，兼容源码运行和打包运行。
    def _resolve_image_asset_path(self, *relative_parts: str) -> Path:
        # 把相对路径片段拼成统一相对路径对象。
        relative_path = Path(*relative_parts)
        # 保存候选路径列表，按优先级依次尝试。
        candidates: list[Path] = []
        # 读取当前可执行文件所在目录（源码运行/打包运行都可用）。
        exe_dir = Path(sys.executable).resolve().parent
        # 优先尝试 PyInstaller/Flet 打包后的解包目录，确保优先使用软件内资源。
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            # 追加打包运行时的解包目录候选。
            candidates.append(Path(str(meipass)) / relative_path)
        # 候选 1：可执行文件同级目录下的资源路径。
        candidates.append(exe_dir / relative_path)
        # 候选 2：可执行文件上一级目录下的资源路径。
        candidates.append(exe_dir.parent / relative_path)
        # 候选 3：macOS .app 场景下，app 包外层目录同级资源路径。
        try:
            # 尝试追加 .app 外层候选路径。
            candidates.append(exe_dir.parents[2] / relative_path)
        # 非 .app 目录结构时忽略该候选。
        except Exception:
            # 不中断流程，继续尝试其他候选路径。
            pass
        # 候选 4：源码项目根目录下的资源路径。
        candidates.append(Path(__file__).resolve().parents[2] / relative_path)
        # 候选 5：当前工作目录下的资源路径（仅作为源码调试兜底）。
        candidates.append(Path.cwd() / relative_path)
        # 逐个候选检查文件是否存在。
        for candidate in candidates:
            # 命中存在且是文件时直接返回。
            if candidate.exists() and candidate.is_file():
                return candidate
        # 全部候选都不存在时抛出明确错误，便于排查。
        raise FileNotFoundError(
            "未找到图片资源，候选路径："
            + " / ".join(str(path) for path in candidates)
        )

    # 定义“安全等待并点击图片模板”的方法，避免图片未出现时直接抛异常中断主流程。
    def _safe_wait_touch_template(
        self,
        template: Template,
        desc: str,
        timeout_sec: float = 20.0,
        interval_sec: float = 3.0,
        optional: bool = True,
    ) -> bool:
        # 尝试执行“等待图片出现并点击”的动作。
        try:
            # 先等待模板出现，降低直接 exists 的偶发抖动。
            wait(template, timeout=timeout_sec, interval=interval_sec)
            # 图片存在时执行点击。
            if exists(template):
                # 点击模板对应位置。
                touch(template)
                # 记录图片点击成功日志。
                self.log.info("图片模板点击成功", target=desc, timeout_sec=timeout_sec, interval_sec=interval_sec)
                # 返回 True 表示点击成功。
                return True
            # 等待后仍未命中时记录日志。
            self.log.warning("图片模板等待结束但未命中", target=desc, timeout_sec=timeout_sec, interval_sec=interval_sec)
            # 返回 False 表示未命中。
            return False
        # 捕获图片等待/点击异常。
        except Exception as exc:
            # 连接类异常仍走统一恢复链路，避免把运行时断开误判成普通未命中。
            if self._is_poco_disconnect_error(exc):
                # 统一记录异常并尝试恢复连接。
                recovered = self._handle_safe_action_exception("template_wait_touch", desc, exc)
                # 恢复失败时直接交给 worker 做整套运行时重建。
                self._raise_if_disconnect_unrecovered("template_wait_touch", desc, exc, recovered)
                # 当前图片步骤不在任务层继续重试，按失败返回给调用方。
                return False
            # 可选图片未命中时仅记日志，不中断主流程。
            if optional:
                # 记录可选图片未命中的日志。
                self.log.info("可选图片模板未命中，按跳过处理", target=desc, error=str(exc))
                # 返回 False 表示未命中。
                return False
            # 必选图片失败时记录异常日志。
            self.log.exception("图片模板处理失败", target=desc, error=str(exc))
            # 返回 False 表示处理失败。
            return False

    # 定义“根据图片资源路径构建 Template 对象”的方法。
    def _build_asset_template(
        self,
        *relative_parts: str,
        threshold: float | None = None,
        target_pos: int = 5,
        record_pos: tuple[float, float] | None = None,
        resolution: tuple[int, int] = (),
        rgb: bool = False,
    ) -> Template:
        # 解析图片资源绝对路径，兼容源码运行和打包运行。
        image_path = self._resolve_image_asset_path(*relative_parts)
        # 使用源码签名中的原始参数直接构建 Template。
        return Template(
            str(image_path),
            threshold=threshold,
            target_pos=target_pos,
            record_pos=record_pos,
            resolution=resolution,
            rgb=rgb,
        )

    # 定义“安全找图并点击”的统一方法，返回 True/False。
    def _safe_click_image_template(
        self,
        desc: str,
        *relative_parts: str,
        timeout_sec: float = 20.0,
        interval_sec: float = 3.0,
        optional: bool = True,
        threshold: float | None = None,
        target_pos: int = 5,
        record_pos: tuple[float, float] | None = None,
        resolution: tuple[int, int] = (),
        rgb: bool = False,
    ) -> bool:
        # 使用异常保护整个“解析路径 + 构建模板 + 点击”流程。
        try:
            # 构建当前图片资源对应的 Template 对象。
            template = self._build_asset_template(
                *relative_parts,
                threshold=threshold,
                target_pos=target_pos,
                record_pos=record_pos,
                resolution=resolution,
                rgb=rgb,
            )
            # 调用已有安全模板点击方法执行真正的等待和点击。
            return self._safe_wait_touch_template(
                template=template,
                desc=desc,
                timeout_sec=timeout_sec,
                interval_sec=interval_sec,
                optional=optional,
            )
        # 模板构建或路径解析失败时记录日志并返回 False。
        except Exception as exc:
            # 记录统一图片点击失败日志。
            self.log.exception("图片资源点击失败", target=desc, error=str(exc))
            # 返回 False 表示当前图片点击失败。
            return False

    # 定义“安全卸载应用”的方法。
    def _safe_uninstall_app(self, package: str) -> bool:
        # 包名为空时直接按失败处理。
        if str(package or "").strip() == "":
            # 记录错误日志。
            self.log.error("卸载应用失败：包名为空")
            # 返回 False 表示失败。
            return False
        # 先判断包是否已安装，未安装时直接跳过卸载。
        installed = self._is_package_installed(package)
        # 明确未安装时按成功处理，避免无意义卸载动作。
        if installed is False:
            # 记录跳过日志。
            self.log.info("应用未安装，跳过卸载", package=package)
            # 返回 True 表示本步骤已安全完成。
            return True
        # 尝试执行卸载动作。
        try:
            clear_app(package)
            sleep(1)
            # 调用 Airtest 卸载接口。
            uninstall(package)
            # 记录卸载成功日志。
            self.log.info("已卸载应用", package=package)
            # 返回 True 表示卸载成功。
            return True
        # 捕获卸载异常并做安全处理。
        except Exception as exc:
            # 连接异常继续抛出，让 worker 触发重建运行时。
            if self._is_poco_disconnect_error(exc):
                # 标记当前轮检测到连接异常。
                self._runtime_disconnect_detected = True
                # 记录连接异常日志。
                self.log.warning("卸载应用遇到连接异常，准备抛出触发重建", package=package, error=str(exc))
                # 抛出异常给上层处理。
                raise
            # 提取异常详情文本做关键字匹配。
            detail = str(exc).strip().lower()
            # 命中未安装关键字时按成功处理。
            if "unknown package" in detail or "not installed" in detail or "not found" in detail:
                # 记录未安装日志。
                self.log.info("卸载应用时判定未安装，按成功处理", package=package, error=str(exc))
                # 返回 True 表示可接受结果。
                return True
            # 其他异常记录告警并返回失败，但不抛出防止流程崩溃。
            self.log.warning("卸载应用失败，按可恢复异常继续", package=package, error=str(exc))
            # 返回 False 表示卸载失败。
            return False

    # 定义“安全安装 Facebook”的方法。
    def _safe_install_facebook_apk(self) -> bool:
        # 先解析 facebook.apk 外置路径。
        try:
            # 获取安装包绝对路径。
            apk_path = self._resolve_facebook_apk_path()
        # 路径解析失败时记录错误并返回失败。
        except Exception as exc:
            # 记录找包失败日志。
            self.log.error("安装 Facebook 失败：未找到安装包", error=str(exc))
            # 返回 False 表示安装失败。
            return False
        # 尝试执行安装动作。
        try:
            # 使用 -r 覆盖安装，-d 允许降级安装。
            install(str(apk_path), install_options=["-r", "-d"])
            # 记录安装成功日志。
            self.log.info("已安装 Facebook 应用", package=self.facebook_package, apk_path=str(apk_path))
        # 捕获安装异常并做安全处理。
        except Exception as exc:
            # 连接异常继续抛出，让 worker 触发重建运行时。
            if self._is_poco_disconnect_error(exc):
                # 标记当前轮检测到连接异常。
                self._runtime_disconnect_detected = True
                # 记录连接异常日志。
                self.log.warning("安装 Facebook 遇到连接异常，准备抛出触发重建", error=str(exc), apk_path=str(apk_path))
                # 抛出异常给上层处理。
                raise
            # 非连接异常记录告警并返回失败。
            self.log.warning("安装 Facebook 失败，按可恢复异常继续", error=str(exc), apk_path=str(apk_path))
            # 返回 False 表示安装失败。
            return False
        # 安装完成后再次校验是否真的已安装。
        installed = self._is_package_installed(self.facebook_package)
        # 明确未安装时按失败处理并记录日志。
        if installed is False:
            # 记录安装后校验失败日志。
            self.log.error("安装 Facebook 后校验失败：包不存在", package=self.facebook_package, apk_path=str(apk_path))
            # 返回 False 表示安装失败。
            return False
        # 返回 True 表示安装成功或状态未知但已执行安装命令。
        return True

    # 定义“安全安装 Vinted”的方法。
    def _safe_install_vinted_apk(self) -> bool:
        # 先解析 vinted.apk 外置路径。
        try:
            # 获取安装包绝对路径。
            apk_path = self._resolve_vinted_apk_path()
        # 路径解析失败时记录错误并返回失败。
        except Exception as exc:
            # 记录找包失败日志。
            self.log.error("安装 Vinted 失败：未找到安装包", error=str(exc))
            # 返回 False 表示安装失败。
            return False
        # 尝试执行安装动作。
        try:
            # 使用 -r 覆盖安装，-d 允许降级安装。
            install(str(apk_path), install_options=["-r", "-d"])
            # 记录安装成功日志。
            self.log.info("已安装 Vinted 应用", package=self.vinted_package, apk_path=str(apk_path))
        # 捕获安装异常并做安全处理。
        except Exception as exc:
            # 连接异常继续抛出，让 worker 触发重建运行时。
            if self._is_poco_disconnect_error(exc):
                # 标记当前轮检测到连接异常。
                self._runtime_disconnect_detected = True
                # 记录连接异常日志。
                self.log.warning("安装 Vinted 遇到连接异常，准备抛出触发重建", error=str(exc), apk_path=str(apk_path))
                # 抛出异常给上层处理。
                raise
            # 非连接异常记录告警并返回失败。
            self.log.warning("安装 Vinted 失败，按可恢复异常继续", error=str(exc), apk_path=str(apk_path))
            # 返回 False 表示安装失败。
            return False
        # 安装完成后再次校验是否真的已安装。
        installed = self._is_package_installed(self.vinted_package)
        # 明确未安装时按失败处理并记录日志。
        if installed is False:
            # 记录安装后校验失败日志。
            self.log.error("安装 Vinted 后校验失败：包不存在", package=self.vinted_package, apk_path=str(apk_path))
            # 返回 False 表示安装失败。
            return False
        # 返回 True 表示安装成功或状态未知但已执行安装命令。
        return True

    # 定义“获取并校验 Poco 实例”的方法。
    def _require_poco(self) -> Any:
        # 如果当前实例已经保存了 Poco，就直接复用。
        if self.poco is not None:
            # 返回已缓存的 Poco 对象。
            return self.poco
        # 开始尝试从运行时获取 Poco。
        try:
            # 从 runtime 获取当前进程中的 Poco 实例。
            self.poco = get_poco()
        # 如果获取过程中抛异常，先记录日志。
        except Exception as exc:
            # 打印异常日志，方便排查。
            self.log.exception("获取 Poco 实例失败", error=str(exc))
            # 尝试自动重建 Poco 连接，尽量避免流程直接崩溃。
            if self._try_recover_poco("require_poco"):
                # 重建成功后返回当前可用 Poco。
                return self.poco
            # 抛出更明确的业务异常。
            raise RuntimeError("Poco 实例不存在或未初始化，请先检查 worker 初始化日志") from exc
        # 双保险：即便没抛异常，也要防止拿到空对象。
        if self.poco is None:
            # 打印错误日志。
            self.log.error("获取 Poco 实例失败", reason="实例为空")
            # 主动抛错阻断后续流程。
            raise RuntimeError("Poco 实例为空，请先执行 create_poco()")
        # 记录成功拿到 Poco 的日志。
        self.log.info("已获取 Poco 实例", poco_type=type(self.poco).__name__)
        # 返回可用的 Poco 对象。
        return self.poco

    # 定义“判断是否为 Poco/ADB 连接异常”的方法。
    def _is_poco_disconnect_error(self, exc: Exception) -> bool:
        # 把异常转成小写字符串，便于统一关键字匹配。
        detail = str(exc).lower()
        # 空异常文本时直接判定为非连接异常。
        if not detail:
            # 返回 False 表示不是连接异常。
            return False
        # 定义连接中断相关关键字集合。
        keywords = (
            "transportdisconnected",
            "connection refused",
            "max retries exceeded",
            "failed to establish a new connection",
            "broken pipe",
            "connection aborted",
            "remote end closed connection",
            "device not found",
            "adb: device",
            "adberror",
            "adbshellerror",
            "pocoservice",
            "127.0.0.1",
        )
        # 只要命中任意关键字就判定为连接异常。
        return any(keyword in detail for keyword in keywords)

    # 定义“构建任务级运行时日志目录”的方法。
    def _build_runtime_log_subdir(self) -> str:
        # 使用与 worker 初始化一致的目录规则，避免运行时重建日志落到错误目录。
        return f"workers/{safe_path_part(self.device_serial)}"

    # 定义“把连接异常抛给 worker 做整套运行时重建”的方法。
    def _raise_runtime_disconnect_to_worker(self, action: str, desc: str, exc: Exception) -> None:
        # 标准化动作名，避免异常文案为空不利于排查。
        safe_action = str(action or "").strip() or "unknown_action"
        # 标准化目标描述，避免异常文案为空不利于排查。
        safe_desc = str(desc or "").strip() or "unknown_target"
        # 标记当前轮存在运行时连接异常。
        self._runtime_disconnect_detected = True
        # 记录升级抛出的错误日志，便于确认是“任务层放弃继续执行”而不是普通失败。
        self.log.error(
            "连接异常未恢复，终止当前任务并交给 worker 重建运行时",
            action=safe_action,
            target=safe_desc,
            error=str(exc),
        )
        # 抛出可被 worker 识别的可重试连接异常。
        raise ConnectionResetError(
            f"TransportDisconnected: {safe_action}:{safe_desc} 连接恢复失败，请求 worker 重建运行时"
        ) from exc

    # 定义“首轮恢复失败时按需抛给 worker”的方法。
    def _raise_if_disconnect_unrecovered(self, action: str, desc: str, exc: Exception, recovered: bool) -> None:
        # 已恢复成功时无需抛给 worker。
        if bool(recovered):
            return
        # 非连接类异常不升级，保持原有业务失败语义。
        if not self._is_poco_disconnect_error(exc):
            return
        # 连接异常且恢复失败时，立即交给 worker 做整套重建。
        self._raise_runtime_disconnect_to_worker(action, desc, exc)

    # 定义“尝试重建 Poco 连接”的方法。
    def _try_recover_poco(self, reason: str) -> bool:
        # 使用异常保护重建流程，避免二次异常导致崩溃。
        try:
            # 先清空当前缓存 Poco，避免复用失效对象。
            self.poco = None
            # 先重建 Airtest 当前设备，确保触控/截图/adb 通道一起恢复。
            setup_device(
                serial=self.device_serial,
                script_file=__file__,
                log_subdir=self._build_runtime_log_subdir(),
            )
            # 再重新创建当前进程的 Poco 实例。
            create_poco()
            # 重新读取并缓存新 Poco 对象。
            self.poco = get_poco()
            # 记录重建成功日志。
            self.log.warning("Poco 连接已重建", reason=reason, poco_type=type(self.poco).__name__)
            # 返回 True 表示重建成功。
            return True
        # 捕获重建中的全部异常并记录日志。
        except Exception as exc:
            # 记录重建失败详情，便于排查设备连接问题。
            self.log.exception("Poco 连接重建失败", reason=reason, error=str(exc))
            # 返回 False 表示重建失败。
            return False

    # 定义“统一处理安全动作异常”的方法。
    def _handle_safe_action_exception(self, action: str, desc: str, exc: Exception) -> bool:
        # 先记录原始异常堆栈，便于定位真实报错点。
        self.log.exception("动作执行异常，按失败处理", action=action, target=desc, error=str(exc))
        # 如果识别到 Poco/ADB 连接异常，则尝试自动重建连接。
        if self._is_poco_disconnect_error(exc):
            # 标记本轮检测到设备连接异常，供 run_once 收尾阶段跳过 status=3 回写。
            self._runtime_disconnect_detected = True
            # 记录连接异常告警日志。
            self.log.warning("检测到 Poco/ADB 连接异常，尝试重建连接", action=action, target=desc)
            # 执行重建，不论成功失败都不再抛异常。
            recovered = self._try_recover_poco(reason=f"{action}:{desc}")
            # 返回重建结果，供调用方决定是否重试当前步骤。
            return bool(recovered)
        # 非连接异常返回 False，表示不执行重试。
        return False

    # 定义“在 Poco 重建后按原 query 重新绑定节点”的方法。
    def _rebind_poco_node(self, node: Any) -> Any:
        # 不是 Poco 节点代理类型时，直接返回原对象给调用方兜底处理。
        if not isinstance(node, UIObjectProxy):
            # 返回原对象，兼容非 Poco 节点场景。
            return node
        # 没有 query 属性时无法重建，直接返回原对象。
        if not hasattr(node, "query"):
            # 返回原对象，避免重建过程再抛异常。
            return node
        # 尝试基于当前最新 Poco 重新创建节点代理。
        try:
            # 读取当前已重建后的 Poco 实例。
            current_poco = self._require_poco()
            # 创建一个绑定到新 Poco 的空节点代理。
            rebound_node = UIObjectProxy(current_poco)
            # 把原节点 query 复制到新节点上，保持定位链路一致。
            rebound_node.query = node.query
            # 尽量复制焦点偏移配置，保证点击位置一致。
            rebound_node._focus = getattr(node, "_focus", None)
            # 返回已重绑的新节点。
            return rebound_node
        # 重建失败时记录日志并回退原对象。
        except Exception as exc:
            # 记录节点重绑失败日志，便于后续排查 query 兼容性问题。
            self.log.warning("Poco 节点重绑失败，回退原节点对象", error=str(exc), node_type=type(node).__name__)
            # 返回原对象，让调用方继续按失败分支处理。
            return node

    # 定义“安全获取序列指定索引值”的方法，避免元组越界。
    def _safe_get_sequence_item(self, sequence: Any, index: int, default: str = "") -> str:
        # 入参索引非法时直接回退默认值。
        if int(index) < 0:
            # 返回默认值，避免负索引带来歧义。
            return str(default or "")
        # 当序列对象为空时直接返回默认值。
        if sequence is None:
            # 返回默认值表示未取到内容。
            return str(default or "")
        # 尝试按索引读取值。
        try:
            # 当前索引越界时直接返回默认值。
            if len(sequence) <= int(index):
                return str(default or "")
            # 读取指定索引的原始值。
            raw_value = sequence[int(index)]
        # 读取失败时统一回退默认值。
        except Exception:
            # 返回默认值表示安全兜底。
            return str(default or "")
        # 当前值为空时回退默认值。
        if raw_value is None:
            return str(default or "")
        # 返回标准化后的字符串值。
        return str(raw_value).strip()

    # 定义“读取当前顶层 Activity 信息”的方法。
    def _get_top_activity_info(self) -> tuple[str, str, str]:
        # 延迟导入 device，避免模块导入阶段强绑定 Airtest 运行时。
        try:
            # 导入 Airtest 当前设备对象获取方法。
            from airtest.core.api import device
        # 导入失败时记录日志并返回空结果。
        except Exception as exc:
            # 记录导入失败日志。
            self.log.warning("读取顶层 Activity 失败：导入 device 失败", error=str(exc))
            # 返回空元组内容表示未知。
            return "", "", ""
        # 尝试读取顶层 Activity 信息。
        try:
            # 获取当前 Airtest 绑定的设备对象。
            current_device = device()
            # 调用 Airtest 设备方法读取顶层 Activity 信息。
            top_activity = current_device.get_top_activity()
            # 安全提取包名，避免返回值越界。
            package_name = self._safe_get_sequence_item(top_activity, 0, "")
            # 安全提取 Activity 名称，避免返回值越界。
            activity_name = self._safe_get_sequence_item(top_activity, 1, "")
            # 安全提取 pid，避免返回值越界。
            pid_value = self._safe_get_sequence_item(top_activity, 2, "")
            # 返回顶层 Activity 三元组。
            return package_name, activity_name, pid_value
        # 读取过程中的异常统一做安全处理。
        except Exception as exc:
            # 连接异常继续抛出，让上层恢复链路接管。
            if self._is_poco_disconnect_error(exc):
                # 标记当前轮检测到连接异常。
                self._runtime_disconnect_detected = True
                # 记录连接异常日志。
                self.log.warning("读取顶层 Activity 遇到连接异常，准备抛出触发重建", error=str(exc))
                # 继续抛给上层处理。
                raise
            # 非连接异常记录日志并返回空结果。
            self.log.warning("读取顶层 Activity 失败，返回未知结果", error=str(exc))
            # 返回空元组内容表示未知。
            return "", "", ""

    # 定义“读取当前前台包名”的方法。
    def _get_foreground_package(self) -> str:
        # 从顶层 Activity 信息中取出包名。
        package_name, _, _ = self._get_top_activity_info()
        # 返回当前前台包名。
        return str(package_name or "").strip()

    # 定义“判断当前前台包名是否符合预期”的方法。
    def _is_expected_package_foreground(self, expected_package: str, desc: str) -> bool:
        # 标准化期望包名，避免空白字符干扰判断。
        safe_expected_package = str(expected_package or "").strip()
        # 期望包名为空时按通过处理。
        if safe_expected_package == "":
            return True
        # 读取当前前台包名。
        current_package = str(self._get_foreground_package() or "").strip()
        # 未读取到当前前台包名时按通过处理，避免误伤主流程。
        if current_package == "":
            return True
        # 当前前台包名命中预期时返回 True。
        if current_package == safe_expected_package:
            return True
        # 当前前台包名不符时记录错误日志，供后续真正启用判断时复用。
        self.log.error(
            "当前前台包名与预期不一致",
            target=desc,
            expected_package=safe_expected_package,
            current_package=current_package,
        )
        # 返回 False 表示当前前台包名不符合预期。
        return False

    # 定义“判断 clear_app 错误是否可忽略”的方法。
    def _is_ignorable_clear_error(self, exc: Exception) -> bool:
        # 把异常详情转小写，便于统一匹配。
        detail = str(exc).strip().lower()
        # 空详情按不可忽略处理，避免误吞未知错误。
        if detail == "":
            # 返回 False 表示不忽略。
            return False
        # 定义 clear_app 常见可忽略错误关键字。
        ignorable_keywords = (
            "unknown package",
            "not installed",
            "package not found",
            "name not found",
            "stderr[b'failed",
            "stderr[b\"failed",
            "securityexception",
            "security exception",
            "permission denial",
        )
        # 命中关键字时按可忽略处理。
        return any(keyword in detail for keyword in ignorable_keywords)

    # 定义“判断包是否已安装”的方法。
    def _is_package_installed(self, package: str) -> bool | None:
        # 把包名标准化，避免空值导致命令异常。
        safe_package = str(package or "").strip()
        # 包名为空时无法查询，直接返回 False。
        if safe_package == "":
            # 记录无效入参日志，便于排查调用方问题。
            self.log.warning("查询包安装状态失败：包名为空")
            # 返回 False 表示未安装。
            return False
        # 延迟导入 device，避免模块导入阶段强绑定 Airtest 运行时。
        try:
            # 导入 Airtest 当前设备对象获取方法。
            from airtest.core.api import device
        # 导入失败时返回 None，后续交给 clear_app 兜底分支处理。
        except Exception as exc:
            # 记录导入失败日志。
            self.log.warning("查询包安装状态失败：导入 device 失败", package=safe_package, error=str(exc))
            # 返回 None 表示状态未知。
            return None
        # 查询包安装状态。
        try:
            # 获取当前 Airtest 绑定设备。
            current_device = device()
            # 读取设备 adb 客户端。
            adb_client = current_device.adb
            # 执行 pm path 查询命令。
            output = str(adb_client.shell(["pm", "path", safe_package])).strip()
            # 统一转小写，便于关键字匹配。
            output_lower = output.lower()
            # 命中 package: 前缀表示包已安装。
            if "package:" in output_lower:
                # 记录查询命中日志。
                self.log.info("包安装状态查询命中：已安装", package=safe_package, output=output)
                # 返回 True 表示已安装。
                return True
            # 命中未安装关键字时返回 False。
            if "unknown package" in output_lower or "not found" in output_lower or "not installed" in output_lower:
                # 记录未安装日志。
                self.log.info("包安装状态查询命中：未安装", package=safe_package, output=output)
                # 返回 False 表示未安装。
                return False
            # 返回为空时按未安装处理，避免无意义 clear_app。
            if output_lower == "":
                # 记录空输出日志。
                self.log.info("包安装状态查询为空输出，按未安装处理", package=safe_package)
                # 返回 False 表示未安装。
                return False
            # 其他输出按未知处理，留给 clear_app 再做一次兜底。
            self.log.warning("包安装状态查询返回未知结果，后续继续尝试清理", package=safe_package, output=output)
            # 返回 None 表示状态未知。
            return None
        # 捕获查询异常并做容错。
        except Exception as exc:
            # 连接异常需要继续抛出，触发 worker 重建运行时。
            if self._is_poco_disconnect_error(exc):
                # 标记本轮检测到连接异常，供收尾逻辑使用。
                self._runtime_disconnect_detected = True
                # 记录连接异常日志。
                self.log.warning("查询包安装状态遇到连接异常，准备抛出触发重建", package=safe_package, error=str(exc))
                # 继续抛给上层处理。
                raise
            # 提取异常详情文本做关键字匹配。
            detail = str(exc).strip().lower()
            # 命中未安装关键字时按未安装处理。
            if "unknown package" in detail or "not found" in detail or "not installed" in detail:
                # 记录异常态未安装日志。
                self.log.info("包安装状态查询异常但判定未安装，跳过清理", package=safe_package, error=str(exc))
                # 返回 False 表示未安装。
                return False
            # 未知异常返回 None，由 clear_app 分支再兜底。
            self.log.warning("查询包安装状态失败，后续继续尝试清理", package=safe_package, error=str(exc))
            # 返回 None 表示状态未知。
            return None

    # 定义“安全停止应用”的方法。
    def _safe_stop_app(self, package: str) -> bool:
        # 尝试停止应用，异常时按类型决定是否继续。
        try:
            # 执行停止应用动作。
            stop_app(package)
            # 记录停止成功日志。
            self.log.info("已停止应用", package=package)
            # 返回 True 表示停止成功。
            return True
        # 捕获停止过程中的全部异常。
        except Exception as exc:
            # 连接异常要继续抛出，让 worker 重建运行时。
            if self._is_poco_disconnect_error(exc):
                # 标记当前轮检测到连接异常，供 run_once 跳过 status=3 回写。
                self._runtime_disconnect_detected = True
                # 记录连接异常日志。
                self.log.warning("停止应用遇到连接异常，准备抛出触发重建", package=package, error=str(exc))
                # 继续抛给上层处理。
                raise
            # 非连接异常只记录告警并继续，避免预清理阶段中断整轮任务。
            self.log.warning("停止应用失败，按可恢复异常继续", package=package, error=str(exc))
            # 返回 False 表示停止失败但已忽略。
            return False

    # 定义“安全清理应用数据”的方法。
    def _safe_clear_app(self, package: str) -> bool:
        # 先查询包安装状态，避免包不存在时直接 clear 触发 Failed。
        installed = self._is_package_installed(package)
        # 明确未安装时直接跳过清理。
        if installed is False:
            # 记录跳过日志，避免误判清理失败。
            self.log.info("应用未安装，跳过清理数据", package=package)
            # 返回 True 表示本步骤已安全完成。
            return True
        # 尝试清理应用数据，异常时按类型决定是否继续。
        try:
            # 执行清理动作。
            clear_app(package)
            # 记录清理成功日志。
            self.log.info("已清理应用数据", package=package)
            # 返回 True 表示清理成功。
            return True
        # 捕获清理过程中的全部异常。
        except Exception as exc:
            # 连接异常要继续抛出，让 worker 重建运行时。
            if self._is_poco_disconnect_error(exc):
                # 标记当前轮检测到连接异常，供 run_once 跳过 status=3 回写。
                self._runtime_disconnect_detected = True
                # 记录连接异常日志。
                self.log.warning("清理应用数据遇到连接异常，准备抛出触发重建", package=package, error=str(exc))
                # 继续抛给上层处理。
                raise
            # clear_app 常见失败按可忽略处理，避免误判账号失败。
            if self._is_ignorable_clear_error(exc):
                # 记录可忽略失败日志。
                self.log.warning("清理应用数据失败，按可忽略异常继续", package=package, error=str(exc))
                # 返回 False 表示清理失败但已忽略。
                return False
            # 其他异常也仅记录告警并继续，避免预清理步骤阻断主流程。
            self.log.warning("清理应用数据失败，按可恢复异常继续", package=package, error=str(exc))
            # 返回 False 表示清理失败但已忽略。
            return False

    # 定义“通过系统设置清理 Facebook 账号”的方法。
    def setting_clean_fb(self) -> bool:
        # 从当前任务实例中拿到可用的 Poco 对象。
        poco = self._require_poco()
        # 收集“密码和账户”入口的多语言文案。
        password_and_accounts_texts = self._collect_locale_values(SETTING_PASSWORDS_AND_ACCOUNTS)
        # 收集 Facebook 账号项的多语言文案。
        facebook_account_texts = self._collect_locale_values(SETTING_FACEBOOK_ACCOUNT)
        # 收集顶部返回按钮的多语言文案。
        navigate_up_texts = self._collect_locale_values(SETTING_NAVIGATE_UP)
        # 预构建返回按钮候选节点（同时兼容 desc 与 name 形式）。
        navigate_up_nodes: list[Any] = []
        # 遍历多语言返回按钮文案并构建候选节点。
        for navigate_up_text in navigate_up_texts:
            # 追加按 desc 定位的候选节点。
            navigate_up_nodes.append(poco(desc=navigate_up_text))
            # 追加按 name 定位的候选节点，兼容不同 Poco 层级实现。
            navigate_up_nodes.append(poco(navigate_up_text))

        # 记录本次设置页清理开始日志。
        self.log.info(
            "开始执行设置页 Facebook 账号清理",
            setting_fb_del_num=self.setting_fb_del_num,
            worker_loop_seq=self.worker_loop_seq,
        )
        # 启动系统设置应用。
        start_app(self.settings_package)
        # 给设置页一点加载时间。
        sleep(1.5)
        try:
            # 先滚动并点击“密码和账户”入口。
            if not self._scroll_and_click_setting_entry(
                poco=poco,
                texts=password_and_accounts_texts,
                desc="设置页-密码和账户入口",
                max_swipes=7,
            ):
                # 记录失败日志并返回 False。
                self.log.error("设置页清理 Facebook 账号失败：未找到密码和账户入口")
                return False
            # 给账户页一点时间完成渲染。
            sleep(1.0)
            # 初始化删除计数，便于日志追踪。
            deleted_count = 0
            # 最多循环 20 次，避免异常场景死循环。
            for round_index in range(20):
                # 预构建 Facebook 账号候选节点列表。
                facebook_nodes = [poco(text=text_value) for text_value in facebook_account_texts]
                # 当前轮没有任何可用候选时直接结束，避免构造空选择器。
                if not facebook_nodes:
                    # 记录配置缺失日志。
                    self.log.error("设置页清理 Facebook 账号失败：Facebook 文案候选为空", device_lang=self.device_lang)
                    return False
                # 当前轮查找不到 Facebook 账号时，说明已经删完。
                if not self._try_click_first_existing_node(
                    nodes=facebook_nodes,
                    desc=f"设置页-Facebook 账号入口-第{round_index + 1}轮",
                    sleep_interval=0.8,
                ):
                    # 记录清理完成日志。
                    self.log.info("设置页 Facebook 账号清理完成", deleted_count=deleted_count)
                    # 返回 True 表示流程成功结束。
                    return True
                # 给详情页一点加载时间。
                sleep(1.0)
                # 点击顶部返回按钮，进入可删除账号的页面。
                if not self._try_click_first_existing_node(
                    nodes=navigate_up_nodes,
                    desc=f"设置页-Facebook 账号返回按钮-第{round_index + 1}轮",
                    sleep_interval=0.8,
                ):
                    # 记录失败日志并返回 False。
                    self.log.error("设置页清理 Facebook 账号失败：未找到返回按钮", round_no=round_index + 1)
                    return False
                # 给页面一点时间刷新删除按钮区域。
                sleep(1.0)
                # 点击设置页删除按钮。
                if not self._safe_wait_click(
                    poco("com.android.settings:id/button"),
                    2.0,
                    f"设置页-Facebook 删除按钮-第{round_index + 1}轮",
                    sleep_interval=1.0,
                ):
                    # 记录失败日志并返回 False。
                    self.log.error("设置页清理 Facebook 账号失败：未找到删除按钮", round_no=round_index + 1)
                    return False
                # 点击系统确认删除按钮。
                if not self._safe_wait_click(
                    poco("android:id/button1"),
                    2.0,
                    f"设置页-Facebook 确认删除按钮-第{round_index + 1}轮",
                    sleep_interval=1.0,
                ):
                    # 记录失败日志并返回 False。
                    self.log.error("设置页清理 Facebook 账号失败：未找到确认删除按钮", round_no=round_index + 1)
                    return False
                # 删除计数加一，记录本轮删除成功。
                deleted_count += 1
                # 给系统删除账号一点时间完成状态回收。
                sleep(1.2)
            # 超过安全轮次上限仍未结束时记录告警。
            self.log.warning("设置页 Facebook 账号清理达到安全轮次上限", deleted_count=deleted_count)
            # 返回 True，避免因重复账号过多导致整轮任务失败。
            return True
        # 无论成功失败都尝试关闭设置应用，避免影响后续流程。
        finally:
            # 安全停止系统设置应用。
            self._safe_stop_app(self.settings_package)

    def _run_vinted_cleanup_flow(self) -> None:
        # 执行 Vinted 独立应用清理，保证只处理 Vinted 包数据。
        # 停止业务应用，确保可执行清理数据。
        self._safe_stop_app(self.vinted_package)
        sleep(0.5)
        # 清理业务应用数据，确保环境干净。
        self._safe_clear_app(self.vinted_package)
        # 命中“达到 vt_delete_num 指定轮次后每轮重装”条件时再执行重装。
        if self._should_delete_vt_this_loop():
            # 记录命中删除条件日志。
            self.log.info(
                "命中 Vinted 重装条件，执行 uninstall + install",
                vt_delete_num=self.vt_delete_num,
                worker_loop_seq=self.worker_loop_seq,
            )
            # 再卸载 Vinted 应用（未安装时会自动跳过）。
            uninstall_ok = self._safe_uninstall_app(self.vinted_package)
            # 卸载后重新安装 Vinted。
            install_ok = self._safe_install_vinted_apk()
            # 重装失败时记录错误日志，方便排查后续流程失败原因。
            if not install_ok:
                self.log.error(
                    "Vinted 删除后重装失败，后续流程可能受影响",
                    vt_delete_num=self.vt_delete_num,
                    worker_loop_seq=self.worker_loop_seq,
                    uninstall_ok=uninstall_ok,
                )
                # 主动抛出可读错误，让 run_once 按失败回写并中断本轮后续流程。
                raise RuntimeError("Vinted 删除后重装失败，请检查 apks/vinted.apk 或设备安装权限")
        # 未命中重装条件时，保留本轮仅清理流程。
        else:
            # 记录跳过重装日志，便于核对配置是否生效。
            self.log.info(
                "未命中 Vinted 重装条件，本轮仅清理不重装",
                vt_delete_num=self.vt_delete_num,
                worker_loop_seq=self.worker_loop_seq,
            )
        # 记录 Vinted 清理完成，便于核对当前任务只处理本包。
        self.log.info("Vinted 应用清理完成", register_mode=self.register_mode, user_email=self.user_email, package=self.vinted_package)

    # 定义“执行 Facebook 专属清理流程”的方法。
    def _run_facebook_cleanup_flow(self) -> None:
        # 先停止 Facebook 应用，避免脏状态残留。
        self._safe_stop_app(self.facebook_package)
        sleep(0.5)
        # 每轮都先清理 Facebook 数据。
        self._safe_clear_app(self.facebook_package)
        # 命中“达到 fb_delete_num 指定轮次后每轮重装”条件时再执行重装。
        if self._should_delete_fb_this_loop():
            # 记录命中删除条件日志。
            self.log.info(
                "命中 Facebook 重装条件，执行 uninstall + install",
                fb_delete_num=self.fb_delete_num,
                worker_loop_seq=self.worker_loop_seq,
            )
            # 再卸载 Facebook 应用（未安装时会自动跳过）。
            uninstall_ok = self._safe_uninstall_app(self.facebook_package)
            # 卸载后重新安装 Facebook。
            install_ok = self._safe_install_facebook_apk()
            # 重装失败时记录错误日志，方便排查后续流程失败原因。
            if not install_ok:
                self.log.error(
                    "Facebook 删除后重装失败，后续流程可能受影响",
                    fb_delete_num=self.fb_delete_num,
                    worker_loop_seq=self.worker_loop_seq,
                    uninstall_ok=uninstall_ok,
                )
                # 主动抛出可读错误，让 run_once 按失败回写并中断本轮后续流程。
                raise RuntimeError("Facebook 删除后重装失败，请检查 apks/facebook.apk 或设备安装权限")

        # 未命中重装条件时，保留本轮仅清理流程。
        else:
            # 记录跳过重装日志，便于核对配置是否生效。
            self.log.info(
                "未命中 Facebook 重装条件，本轮仅清理不重装",
                fb_delete_num=self.fb_delete_num,
                worker_loop_seq=self.worker_loop_seq,
            )

        # 命中设置页清理条件时再执行系统设置里的 Facebook 账号清理。
        if self._should_delete_setting_fb_this_loop():
            # 记录命中设置页清理条件日志。
            self.log.info(
                "命中设置页 Facebook 账号清理条件，执行 setting_clean_fb",
                setting_fb_del_num=self.setting_fb_del_num,
                worker_loop_seq=self.worker_loop_seq,
            )
            # 执行设置页 Facebook 账号清理。
            setting_clean_ok = self.setting_clean_fb()
            # 设置页清理失败时仅记录告警，不中断后续主流程。
            if not setting_clean_ok:
                self.log.warning(
                    "设置页 Facebook 账号清理未完成，继续后续流程",
                    setting_fb_del_num=self.setting_fb_del_num,
                    worker_loop_seq=self.worker_loop_seq,
                )
        # 未命中设置页清理条件时记录跳过日志。
        else:
            # 记录跳过设置页清理日志，便于核对配置是否生效。
            self.log.info(
                "未命中设置页 Facebook 账号清理条件，本轮跳过设置页清理",
                setting_fb_del_num=self.setting_fb_del_num,
                worker_loop_seq=self.worker_loop_seq,
            )

    # 定义“执行共享设备准备流程”的方法。
    def _run_shared_device_prepare_flow(self) -> None:
        # 先停止抹机王应用，避免脏状态残留影响新一轮流程。
        self._safe_stop_app(self.mojiwang_packge)
        # 执行抹机王完整循环动作。
        self.mojiwang_run_all()
        # 执行代理流程（根据配置范围安全随机选择代理模式）。
        self.nekobox_run_all()

    # 定义“等待节点可点击并点击”的通用方法。
    def _wait_and_click_node(self, node: Any, desc: str) -> bool:
        # 尝试执行“等待 + 点击”动作。
        try:
            # 使用你原来的 wait 逻辑：先等待，再判断是否存在。
            if node.wait(self.mojiwang_wait_timeout_sec).exists():
                # 节点在超时前出现后直接点击。
                node.click()
                # 记录点击成功日志，方便排查。
                self.log.info("点击成功", target=desc)
                # 返回 True 表示本次点击已经成功完成。
                return True
            # 超时后记录警告日志。
            self.log.error("等待超时，未点击", target=desc, timeout_sec=self.mojiwang_wait_timeout_sec)
            # 返回 False 表示本次没有点到目标控件。
            return False
        # 捕获异常并按失败处理，保证流程不会崩溃。
        except Exception as exc:
            # 统一记录异常并尝试恢复连接。
            recovered = self._handle_safe_action_exception("wait_and_click", desc, exc)
            # 仅在连接重建成功时，对当前失败步骤再重试一次。
            if recovered:
                # 连接恢复后先按原 query 重绑节点，避免继续复用旧代理。
                rebound_node = self._rebind_poco_node(node)
                # 记录重试日志，便于排查“重建后是否恢复”。
                self.log.warning("连接重建后重试步骤", action="wait_and_click", target=desc)
                try:
                    # 重建后再次等待并判断节点是否存在。
                    if rebound_node.wait(self.mojiwang_wait_timeout_sec).exists():
                        # 重建后节点出现则点击。
                        rebound_node.click()
                        # 记录重试点击成功日志。
                        self.log.info("连接重建后点击成功", target=desc)
                        # 返回 True 表示重试成功。
                        return True
                    # 重建后仍未命中时记录错误日志。
                    self.log.error("连接重建后等待超时，未点击", target=desc, timeout_sec=self.mojiwang_wait_timeout_sec)
                    # 返回 False 表示重试失败。
                    return False
                # 捕获重试中的二次异常并继续兜底。
                except Exception as retry_exc:
                    # 记录二次异常并尝试再次恢复（不再重复重试步骤）。
                    self._handle_safe_action_exception("wait_and_click_retry", desc, retry_exc)
                    # 第二次仍是连接异常时，不再继续本轮任务，直接交给 worker 重建运行时。
                    if self._is_poco_disconnect_error(retry_exc):
                        self._raise_runtime_disconnect_to_worker("wait_and_click_retry", desc, retry_exc)
                    # 返回 False 表示重试失败。
                    return False
            # 首轮恢复失败且属于连接异常时，直接交给 worker 做整套重建。
            self._raise_if_disconnect_unrecovered("wait_and_click", desc, exc, recovered)
            # 返回 False 表示本次动作失败。
            return False

    # 定义“安全等待并判断存在”的方法，避免 UI 查询异常直接中断流程。
    def _safe_wait_exists(self, node: Any, wait_seconds: float, desc: str) -> bool:
        # 尝试执行等待和存在判断。
        try:
            # 成功时返回布尔值，统一给调用方使用。
            bools =  bool(node.wait(wait_seconds).exists())
            if not bools:
                self.log.error("查找失败", target=desc, wait_seconds=wait_seconds)

            return bools
        # 任意异常都在这里兜底，避免流程直接崩溃。
        except Exception as exc:
            # 统一记录异常并尝试恢复连接。
            recovered = self._handle_safe_action_exception("wait_exists", desc, exc)
            # 仅在连接重建成功时，对当前查找步骤再重试一次。
            if recovered:
                # 连接恢复后先按原 query 重绑节点，避免继续复用旧代理。
                rebound_node = self._rebind_poco_node(node)
                # 记录重试日志，便于后续定位。
                self.log.warning("连接重建后重试步骤", action="wait_exists", target=desc, wait_seconds=wait_seconds)
                try:
                    # 重建后再次执行等待并判断存在。
                    bools = bool(rebound_node.wait(wait_seconds).exists())
                    # 重试仍未命中时记录错误日志。
                    if not bools:
                        self.log.error("连接重建后查找失败", target=desc, wait_seconds=wait_seconds)
                    # 返回重试结果。
                    return bools
                # 捕获重试中的二次异常并继续兜底。
                except Exception as retry_exc:
                    # 记录二次异常并尝试恢复（不再重复重试步骤）。
                    self._handle_safe_action_exception("wait_exists_retry", desc, retry_exc)
                    # 第二次仍是连接异常时，直接终止当前任务并让 worker 重建运行时。
                    if self._is_poco_disconnect_error(retry_exc):
                        self._raise_runtime_disconnect_to_worker("wait_exists_retry", desc, retry_exc)
                    # 返回 False 表示重试失败。
                    return False
            # 首轮恢复失败且属于连接异常时，直接交给 worker 做整套重建。
            self._raise_if_disconnect_unrecovered("wait_exists", desc, exc, recovered)
            # 发生异常时按不存在处理，让主流程安全退出。
            return False

    # 定义“安全点击”的方法，避免点击异常中断流程。
    def _safe_click(self, node: Any, desc: str, sleep_interval: float | None = None) -> bool:
        # 尝试执行点击动作。
        try:
            # 仅使用关键字参数传递 sleep_interval，避免参数歧义。
            node.click(sleep_interval=sleep_interval)
            # 记录点击成功日志。
            self.log.info("点击成功", target=desc, sleep_interval=sleep_interval)
            # 返回 True 表示点击成功。
            return True
        # 任意点击异常都在这里兜底。
        except Exception as exc:
            # 统一记录异常并尝试恢复连接。
            recovered = self._handle_safe_action_exception("click", desc, exc)
            # 仅在连接重建成功时，对当前点击步骤再重试一次。
            if recovered:
                # 连接恢复后先按原 query 重绑节点，避免继续复用旧代理。
                rebound_node = self._rebind_poco_node(node)
                # 记录重试日志，便于后续排查。
                self.log.warning("连接重建后重试步骤", action="click", target=desc)
                try:
                    # 重建后再次执行点击动作。
                    rebound_node.click(sleep_interval=sleep_interval)
                    # 记录重试点击成功日志。
                    self.log.info("连接重建后点击成功", target=desc, sleep_interval=sleep_interval)
                    # 返回 True 表示重试成功。
                    return True
                # 捕获重试中的二次异常并继续兜底。
                except Exception as retry_exc:
                    # 记录二次异常并尝试恢复（不再重复重试步骤）。
                    self._handle_safe_action_exception("click_retry", desc, retry_exc)
                    # 第二次仍是连接异常时，直接终止当前任务并让 worker 重建运行时。
                    if self._is_poco_disconnect_error(retry_exc):
                        self._raise_runtime_disconnect_to_worker("click_retry", desc, retry_exc)
                    # 返回 False 表示重试失败。
                    return False
            # 首轮恢复失败且属于连接异常时，直接交给 worker 做整套重建。
            self._raise_if_disconnect_unrecovered("click", desc, exc, recovered)
            # 返回 False 表示点击失败。
            return False
    def _safe_wait_click(self, node: Any, wait_seconds: float, desc: str,sleep_interval: float | None = None ) -> bool:
        ok = self._safe_wait_exists(node,wait_seconds,desc)
        if not ok:
            return False

        return self._safe_click(node,desc,sleep_interval=sleep_interval)

    # 定义“安全滑动”的方法，避免滑动异常中断流程。
    def _safe_swipe(
        self,
        v1: tuple[float, float] | tuple[int, int],
        v2: tuple[float, float] | tuple[int, int] | None = None,
        vector: tuple[float, float] | tuple[int, int] | None = None,
        desc: str = "",
        **kwargs: Any,
    ) -> bool:
        # 尝试执行滑动动作。
        try:
            # 调用 Airtest 滑动接口执行手势。
            swipe(v1, v2=v2, vector=vector, **kwargs)
            # 记录滑动成功日志。
            self.log.info("滑动成功", target=desc, v1=v1, v2=v2, vector=vector, kwargs=kwargs)
            # 返回 True 表示滑动成功。
            return True
        # 任意滑动异常都在这里兜底。
        except Exception as exc:
            # 统一记录异常并尝试恢复连接。
            recovered = self._handle_safe_action_exception("swipe", desc, exc)
            # 仅在连接重建成功时，对当前滑动步骤再重试一次。
            if recovered:
                # 记录重试日志，便于后续排查。
                self.log.warning("连接重建后重试步骤", action="swipe", target=desc)
                try:
                    # 重建后再次执行滑动动作。
                    swipe(v1, v2=v2, vector=vector, **kwargs)
                    # 记录重试滑动成功日志。
                    self.log.info("连接重建后滑动成功", target=desc, v1=v1, v2=v2, vector=vector, kwargs=kwargs)
                    # 返回 True 表示重试成功。
                    return True
                # 捕获重试中的二次异常并继续兜底。
                except Exception as retry_exc:
                    # 记录二次异常并尝试恢复（不再重复重试步骤）。
                    self._handle_safe_action_exception("swipe_retry", desc, retry_exc)
                    # 第二次仍是连接异常时，直接终止当前任务并让 worker 重建运行时。
                    if self._is_poco_disconnect_error(retry_exc):
                        self._raise_runtime_disconnect_to_worker("swipe_retry", desc, retry_exc)
                    # 返回 False 表示重试失败。
                    return False
            # 首轮恢复失败且属于连接异常时，直接交给 worker 做整套重建。
            self._raise_if_disconnect_unrecovered("swipe", desc, exc, recovered)
            # 返回 False 表示滑动失败。
            return False

    # 定义“收集当前语言优先的多语言文案列表”的方法。
    def _collect_locale_values(self, value_map: dict[str, str]) -> list[str]:
        # 初始化结果列表，保持当前语言优先。
        values: list[str] = []
        # 优先读取当前设备语言对应文案。
        current_value = str(value_map.get(self.device_lang, "")).strip()
        # 当前语言文案非空时优先加入结果。
        if current_value != "":
            values.append(current_value)
        # 继续补充其他语言的非空文案，兼容识别偏差场景。
        for raw_value in value_map.values():
            # 标准化当前遍历到的文案。
            normalized_value = str(raw_value or "").strip()
            # 空文案或重复文案都直接跳过，避免构造空选择器。
            if normalized_value == "" or normalized_value in values:
                continue
            # 把未重复的非空文案加入候选列表。
            values.append(normalized_value)
        # 返回去重后的候选文案列表。
        return values

    # 定义“滚动查找并点击设置项”的方法。
    def _scroll_and_click_setting_entry(self, poco: Any, texts: list[str], desc: str, max_swipes: int = 6) -> bool:
        # 文案候选为空时直接返回失败，避免构造无意义选择器。
        if not texts:
            # 记录缺少文案日志，便于排查 desc.py 配置问题。
            self.log.error("滚动查找设置项失败：文案候选为空", target=desc, device_lang=self.device_lang)
            # 返回 False 表示失败。
            return False
        # 预构建文本节点，避免循环中重复创建对象。
        candidate_nodes = [poco(text=text_value) for text_value in texts]
        # 按“查找一次 + 上滑一次”的节奏循环。
        for swipe_index in range(max(0, max_swipes) + 1):
            # 当前轮先尝试点击目标设置项。
            if self._try_click_first_existing_node(
                nodes=candidate_nodes,
                desc=f"{desc}-第{swipe_index + 1}轮查找",
                sleep_interval=0.8,
            ):
                # 点击成功后直接返回 True。
                return True
            # 最后一轮查找结束后不再继续滑动。
            if swipe_index >= max(0, max_swipes):
                break
            # 执行一次“向下浏览列表”的上滑手势。
            if not self._safe_swipe(
                (0.5, 0.78),
                vector=(0.0, -0.58),
                desc=f"{desc}-第{swipe_index + 1}轮上滑",
                duration=0.35,
                steps=12,
            ):
                # 滑动失败时提前结束，避免空转。
                return False
            # 给界面一点时间完成滚动和重绘。
            sleep(0.8)
        # 所有轮次都未命中时记录失败日志。
        self.log.error("滚动查找设置项失败：未找到目标入口", target=desc, max_swipes=max_swipes, texts=texts)
        # 返回 False 表示未找到目标入口。
        return False

    # 定义“静默探测并点击首个可见候选节点”的方法。
    def _try_click_first_existing_node(self, nodes: list[Any], desc: str, sleep_interval: float = 0.8) -> bool:
        # 未传候选节点时直接返回失败。
        if not nodes:
            # 返回 False 表示未命中。
            return False
        # 逐个探测候选节点是否存在。
        for node_index, node in enumerate(nodes):
            # 使用异常保护 exists 查询，避免静默探测把流程打断。
            try:
                # 当前候选节点存在时尝试点击。
                if bool(node.exists()):
                    # 点击成功时直接返回结果。
                    return self._safe_click(node, f"{desc}-候选{node_index}", sleep_interval=sleep_interval)
            # 捕获查询异常并按失败处理。
            except Exception as exc:
                # 统一记录异常并尝试恢复连接。
                recovered = self._handle_safe_action_exception("try_click_existing_node", f"{desc}-候选{node_index}", exc)
                # 当前候选恢复失败且属于连接异常时，直接终止本轮任务。
                self._raise_if_disconnect_unrecovered("try_click_existing_node", f"{desc}-候选{node_index}", exc, recovered)
        # 所有候选都未命中时返回 False。
        return False

    # 定义“在短超时内探测并点击弹框节点”的方法。
    def _safe_probe_and_click_popup(
        self,
        node: Any,
        desc: str,
        timeout_sec: float = 1.2,
        poll_interval_sec: float = 0.2,
    ) -> bool:
        # 记录本次探测开始时间。
        started_at = time.monotonic()
        # 在超时窗口内循环探测节点是否出现。
        while time.monotonic() - started_at <= max(0.0, timeout_sec):
            # 使用异常保护 exists 查询，避免弹框探测导致主流程崩溃。
            try:
                # 当前节点存在时尝试点击并返回结果。
                if bool(node.exists()):
                    # 点击成功时返回 True。
                    if self._safe_click(node, desc, sleep_interval=0.8):
                        return True
            # 捕获查询异常并按失败处理。
            except Exception as exc:
                # 统一记录异常并尝试恢复连接。
                recovered = self._handle_safe_action_exception("probe_popup_exists", desc, exc)
                # 当前弹框探测恢复失败且属于连接异常时，直接终止本轮任务。
                self._raise_if_disconnect_unrecovered("probe_popup_exists", desc, exc, recovered)
                # 当前节点探测异常时按未点击处理。
                return False
            # 两次探测之间短暂休眠，避免空转过快。
            sleep(max(0.0, poll_interval_sec))
        # 超时未命中时返回 False。
        return False

    # 定义“处理 Facebook 干扰弹框”的方法。
    def  _handle_facebook_blocking_popups(self, poco: Any) -> bool:
        # 标记是否至少点击过一个干扰弹框。
        clicked_any_popup = False
        # 组合常见系统权限弹框候选节点（跨 ROM 兼容）。
        popup_candidates: list[tuple[Any, str]] = [
            # Android 12+ 常见权限允许按钮。
            (poco("com.android.permissioncontroller:id/permission_allow_button"), "Facebook-干扰弹框-系统权限允许按钮"),
            # 通用系统确认按钮（很多弹框共用 android:id/button1）。
            (poco("android:id/button1"), "Facebook-干扰弹框-系统确认按钮"),
            # 旧版 packageinstaller 权限允许按钮。
            (poco("com.android.packageinstaller:id/permission_allow_button"), "Facebook-干扰弹框-旧版权限允许按钮"),
            (poco(text=FACEBOOK_REFRESH_FONT_BUTTON[self.device_lang]),"刷新按钮也查找v333"),
            (poco(text=FACEBOOK_POPUP_IGNORE_BUTTON[self.device_lang]),"刷新按钮也查找v333"),

        ]
        # 连续扫描多轮，兼容“一个弹框点完又弹下一个”的场景。
        for round_index in range(5):
            # 标记当前轮是否有命中弹框。
            clicked_in_round = False
            # 逐个尝试点击候选弹框。
            for node, desc in popup_candidates:
                # 在短超时内探测并点击当前候选弹框。
                if self._safe_probe_and_click_popup(node=node, desc=f"{desc}-第{round_index + 1}轮", timeout_sec=1.0):
                    # 标记本轮命中。
                    clicked_in_round = True
                    # 标记总流程命中。
                    clicked_any_popup = True
            # 本轮未命中时提前结束扫描。
            if not clicked_in_round:
                break
            # 本轮命中后稍等，让下一层弹框有机会渲染出来。
            sleep(0.4)
        # 命中过弹框时记录恢复日志。
        if clicked_any_popup:
            # 记录恢复动作，便于回溯“为什么会走重试”。
            self.log.info("已处理 Facebook 干扰弹框，准备继续流程")
        # 返回是否处理过干扰弹框。
        return clicked_any_popup

    # 定义“步骤失败后处理弹框并重试一次”的通用方法。
    def _facebook_retry_step_after_popup(
        self,
        poco: Any,
        step_desc: str,
        fail_reason: str,
        retry_action: Any,
    ) -> bool:
        # 记录步骤失败，准备尝试弹框恢复。
        self.log.warning("Facebook 步骤失败，准备处理弹框后重试", step=step_desc, reason=fail_reason)
        # 先尝试处理干扰弹框。
        handled_popup = self._handle_facebook_blocking_popups(poco)
        # 未发现干扰弹框时直接按原失败原因返回。
        if not handled_popup:
            # 返回失败并记录原失败原因。
            return self._facebook_fail(fail_reason)
        # 执行当前步骤的一次重试。
        try:
            # 重试成功时直接返回 True。
            if bool(retry_action()):
                # 记录步骤重试成功日志。
                self.log.info("Facebook 步骤重试成功", step=step_desc)
                return True
        # 捕获重试异常并统一处理，不抛出到外层。
        except Exception as exc:
            # 记录异常并尝试恢复连接。
            recovered = self._handle_safe_action_exception("facebook_step_retry", step_desc, exc)
            # Facebook 步骤重试阶段若连接恢复失败，立即交给 worker 做整套运行时重建。
            self._raise_if_disconnect_unrecovered("facebook_step_retry", step_desc, exc, recovered)
        # 重试后仍失败时按原失败原因返回。
        return self._facebook_fail(fail_reason)

    # 定义“安全动作失败时按步骤重试并统一返回”的方法。

    def _facebook_action_or_fail(
        # 当前逻辑是：
        #
        # 1. 先执行原步骤一次（第一次尝试） 位置：open_settings.py:420
        # 2. 第一次失败后进入重试分支 _facebook_retry_step_after_popup(...) 位置：open_settings.py:430
        # 3. 在重试分支里，先处理弹框 _handle_facebook_blocking_popups(...) 位置：open_settings.py:393
        # 4. 只有处理到弹框后，才重试失败步骤 retry_action() 位置：open_settings.py:399

        self,
        poco: Any,
        step_desc: str,
        fail_reason: str,
        action: Any,
    ) -> bool:
        # 先尝试执行当前步骤动作。
        try:
            # 动作成功时直接返回 True。
            if bool(action()):
                return True
        # 动作异常时统一记录，不让流程崩溃。
        except Exception as exc:
            # 记录异常并尝试恢复连接。
            recovered = self._handle_safe_action_exception("facebook_step_action", step_desc, exc)
            # Facebook 步骤首次执行若连接恢复失败，立即交给 worker 做整套运行时重建。
            self._raise_if_disconnect_unrecovered("facebook_step_action", step_desc, exc, recovered)
        # 首次动作失败时，尝试处理弹框并仅重试当前步骤一次。
        return self._facebook_retry_step_after_popup(
            poco=poco,
            step_desc=step_desc,
            fail_reason=fail_reason,
            retry_action=action,
        )

    # 定义“安全点击 Facebook 深层 next 节点”的方法。
    def _safe_click_facebook_next_v2_deep(self, poco: Any) -> bool:
        # 使用异常保护构建深层节点，避免索引越界导致流程崩溃。
        try:
            # 根据固定层级链路定位 next 按钮节点。
            deep_next_node = (
                # 从页面 content 根节点开始向下查找。
                poco("android:id/content")
                # 进入 Facebook 页面第一层容器。
                .child("com.facebook.katana:id/(name removed)")
                # 进入 Facebook 页面第二层容器。
                .child("com.facebook.katana:id/(name removed)")
                # 进入第一层 FrameLayout。
                .child("android.widget.FrameLayout")
                # 进入第二层 FrameLayout。
                .child("android.widget.FrameLayout")
                # 选择第三层 FrameLayout 的索引 1。
                .child("android.widget.FrameLayout")[1]
                # 继续选择下一层 FrameLayout 的索引 1。
                .child("android.widget.FrameLayout")[1]
                # 逐层进入 ViewGroup 容器。
                .child("android.view.ViewGroup")
                # 逐层进入 ViewGroup 容器。
                .child("android.view.ViewGroup")
                # 逐层进入 ViewGroup 容器。
                .child("android.view.ViewGroup")
                # 逐层进入 ViewGroup 容器。
                .child("android.view.ViewGroup")
                # 在当前层级向下查找 RecyclerView。
                .offspring("androidx.recyclerview.widget.RecyclerView")[0]
                # 进入 RecyclerView 的第 2 个子节点。
                .child("android.view.ViewGroup")[1]
                # 继续进入下一层 ViewGroup。
                .child("android.view.ViewGroup")
                # 继续进入下一层 ViewGroup。
                .child("android.view.ViewGroup")
                # 进入最终目标 ViewGroup 的第 1 个子节点。
                .child("android.view.ViewGroup")[0]
            )
        # 捕获深层节点构建异常并按失败处理。
        except Exception as exc:
            # 统一记录异常并尝试恢复连接。
            recovered = self._handle_safe_action_exception("build_facebook_next_v2_deep", "next输入点v2-深层路径", exc)
            # 深层节点构建若连接恢复失败，立即交给 worker 做整套运行时重建。
            self._raise_if_disconnect_unrecovered("build_facebook_next_v2_deep", "next输入点v2-深层路径", exc, recovered)
            # 返回 False 表示本次定位失败。
            return False
        # 等待深层 next 节点出现。
        if not self._safe_wait_exists(deep_next_node, 2, "next输入点v2-深层路径"):
            # 返回 False 表示节点不存在。
            return False
        # 点击深层 next 节点并返回点击结果。
        if  self._safe_click(deep_next_node, "next输入点v2-深层路径点击", sleep_interval=2):
            return self._safe_click(poco(text=FACEBOOK_FIRST_LAST_NAME_NEXT[self.device_lang]), "重命名名称了", sleep_interval=1)
        return False

    # 定义“安全输入事件”的方法，避免使用 set_text 造成不可编辑异常。
    def _safe_input_by_event(self, node: Any, value: str, desc: str) -> bool:
        # 先点击目标节点尝试聚焦输入框。
        if not self._safe_click(node, f"{desc}-聚焦", sleep_interval=0.3):
            # 如果直接点击失败，再尝试点击父节点作为兜底。
            try:
                # 获取当前节点父节点，某些页面点击父容器才会聚焦输入框。
                parent = node.parent()
            # 父节点获取失败时直接返回失败。
            except Exception:
                # 标记父节点不可用。
                parent = None
            # 如果没有可用父节点。
            if parent is None:
                # 记录无法聚焦原因。
                self.log.info("输入框节点不可点击，无法触发输入事件", target=desc, value=value)
                # 返回 False 表示无法继续输入。
                return False
            # 尝试点击父节点聚焦输入框。
            if not self._safe_click(parent, f"{desc}-父节点聚焦", sleep_interval=0.3):
                # 记录兜底失败原因。
                self.log.info("输入框及父节点都不可点击，无法触发输入事件", target=desc, value=value)
                # 返回 False 表示输入失败。
                return False
        # 节点聚焦后执行输入事件。
        try:
            # 使用 Airtest 输入事件把文本打到当前焦点输入框。
            text(value, enter=False)
            # 记录输入事件成功日志。
            self.log.info("输入事件成功", target=desc, value=value)
            # 返回 True 表示输入成功。
            return True
        # 输入事件异常时兜底，不中断流程。
        except Exception as exc:
            # 如果识别到连接异常，走统一恢复逻辑并直接返回失败。
            if self._is_poco_disconnect_error(exc):
                # 统一记录异常并尝试恢复连接。
                self._handle_safe_action_exception("input_event", desc, exc)
                # 输入场景未做节点级重试，直接交给 worker 重建整套运行时。
                self._raise_runtime_disconnect_to_worker("input_event", desc, exc)
            # 记录 text 输入失败原因，并进入 adb shell 输入兜底。
            self.log.error("输入事件失败，尝试 adb shell 输入", target=desc, value=value, error=str(exc))
            # 尝试使用 adb shell 对当前焦点输入文本。
            if self._safe_input_by_adb_shell(value=value, desc=desc, enter=False):
                # adb 输入成功则返回 True。
                return True
            # adb 兜底也失败时返回 False。
            return False

    # 定义“把文本转换为 adb input text 安全参数”的方法。
    def _build_adb_input_text_arg(self, value: str) -> str:
        # 先把入参标准化为字符串，避免 None 引发异常。
        raw_value = str(value or "")
        # 准备字符片段列表，后续逐字符拼接安全文本。
        pieces: list[str] = []
        # 逐个字符进行转换。
        for char in raw_value:
            # 空格转换为 %s，兼容 adb input text 语法。
            if char == " ":
                pieces.append("%s")
                continue
            # 常见 shell 特殊字符前补反斜杠，避免命令被解释。
            if char in {'\\', '"', "'", "&", "|", "<", ">", ";", "(", ")", "$", "`", "!", "*", "?", "[", "]", "{", "}", "#"}:
                pieces.append(f"\\{char}")
                continue
            # 普通字符按原样保留。
            pieces.append(char)
        # 返回转换后的安全参数字符串。
        return "".join(pieces)

    # 定义“使用 adb shell input text 输入当前焦点文本”的方法。
    def _safe_input_by_adb_shell(self, value: str, desc: str, enter: bool = False) -> bool:
        # 标准化输入文本，避免 None 透传到 adb。
        safe_value = str(value or "")
        # 空值输入没有业务意义，直接返回失败。
        if safe_value == "":
            # 记录空值失败原因，便于调用方定位。
            self.log.error("ADB Shell 输入失败：值为空", target=desc)
            # 返回 False 表示输入失败。
            return False
        # 把输入值转换成 adb input text 可接受格式。
        adb_text_arg = self._build_adb_input_text_arg(safe_value)
        # 转换后为空时直接返回失败。
        if adb_text_arg == "":
            # 记录转换失败日志。
            self.log.error("ADB Shell 输入失败：参数为空", target=desc, value=safe_value)
            # 返回 False 表示输入失败。
            return False
        # 延迟导入 device，避免主流程初始化阶段提前绑定 airtest。
        try:
            # 导入当前设备对象获取方法。
            from airtest.core.api import device
        # 导入失败时记录日志并返回失败。
        except Exception as exc:
            # 记录导入异常。
            self.log.error("ADB Shell 输入失败：导入 device 失败", target=desc, value=safe_value, error=str(exc))
            # 返回 False，避免异常扩散。
            return False
        # 尝试执行 adb shell 输入命令。
        try:
            # 获取当前 Airtest 绑定的设备对象。
            current_device = device()
            # 读取当前设备的 adb 客户端。
            adb_client = current_device.adb
            # 使用 adb input text 向当前焦点输入文本。
            adb_client.shell(["input", "text", adb_text_arg])
            # 当调用方要求回车时，补发 ENTER 键。
            if enter:
                # KEYCODE_ENTER 对应值是 66。
                adb_client.shell(["input", "keyevent", "66"])
            # 记录 adb 输入成功日志。
            self.log.info("焦点输入成功", target=desc, value=safe_value, mode="adb_input_text")
            # 返回 True 表示输入成功。
            return True
        # adb 输入异常时统一兜底。
        except Exception as exc:
            # 连接类异常走统一恢复流程。
            if self._is_poco_disconnect_error(exc):
                # 统一记录并尝试恢复连接。
                self._handle_safe_action_exception("focus_adb_input", desc, exc)
                # adb 输入场景未做焦点重试，直接交给 worker 重建整套运行时。
                self._raise_runtime_disconnect_to_worker("focus_adb_input", desc, exc)
            # 记录 adb 输入失败原因。
            self.log.error("ADB Shell 输入失败，按跳过处理", target=desc, value=safe_value, error=str(exc))
            # 返回 False 表示输入失败。
            return False

    # 定义“对当前焦点输入文本”的方法，不依赖节点定位。
    def _safe_input_on_focused(self, value: str, desc: str,enter: bool = False) -> bool:
        # 先尝试直接发送输入事件。
        try:
            # 把文本输入到当前已聚焦的输入框。
            text(value, enter=enter)
            # 记录 text 方式输入成功。
            self.log.info("焦点输入成功", target=desc, value=value, mode="text")
            # 返回 True 表示输入成功。
            return True
        # text 失败后进入粘贴兜底流程。
        except Exception as exc:
            # 如果识别到连接异常，走统一恢复逻辑并直接返回失败。
            if self._is_poco_disconnect_error(exc):
                # 统一记录异常并尝试恢复连接。
                self._handle_safe_action_exception("focus_text_input", desc, exc)
                # text 输入场景未做焦点重试，直接交给 worker 重建整套运行时。
                self._raise_runtime_disconnect_to_worker("focus_text_input", desc, exc)
            # 记录 text 失败原因，并进入 adb shell 输入兜底。
            self.log.error("text 输入失败，尝试 adb shell 输入", target=desc, value=value, error=str(exc))
        # 先尝试 adb shell 输入作为第一层兜底。
        if self._safe_input_by_adb_shell(value=value, desc=desc, enter=enter):
            # adb 输入成功时直接返回。
            return True
        # adb 失败后再尝试剪贴板粘贴。
        self.log.warning("adb shell 输入失败，尝试剪贴板粘贴", target=desc, value=value)
        # 尝试剪贴板粘贴作为兜底方案。
        try:
            # 先把要输入的值写入系统剪贴板。
            set_clipboard(value)
            # 向当前焦点执行粘贴动作。
            paste()
            # 记录 paste 方式输入成功。
            self.log.info("焦点粘贴成功", target=desc, value=value, mode="paste")
            # 返回 True 表示输入成功。
            return True
        # 粘贴也失败则返回失败，不抛异常。
        except Exception as exc:
            # 如果识别到连接异常，走统一恢复逻辑并返回失败。
            if self._is_poco_disconnect_error(exc):
                # 统一记录异常并尝试恢复连接。
                self._handle_safe_action_exception("focus_paste_input", desc, exc)
                # 粘贴输入场景未做焦点重试，直接交给 worker 重建整套运行时。
                self._raise_runtime_disconnect_to_worker("focus_paste_input", desc, exc)
            # 记录最终失败原因。
            self.log.error("焦点输入失败，已跳过", target=desc, value=value, error=str(exc))
            # 返回 False 表示输入失败。
            return False

    # 定义“安全按键事件”方法，用于焦点切换。
    def _safe_keyevent(self, key: str, desc: str) -> bool:
        # 尝试发送按键事件。
        try:
            # 发送指定按键（例如 KEYCODE_TAB）。
            keyevent(key)
            # 记录按键成功日志。
            self.log.info("按键事件成功", target=desc, key=key)
            # 返回 True 表示按键发送成功。
            return True
        # 按键异常时兜底，不中断主流程。
        except Exception as exc:
            # 如果识别到连接异常，走统一恢复逻辑并返回失败。
            if self._is_poco_disconnect_error(exc):
                # 统一记录异常并尝试恢复连接。
                self._handle_safe_action_exception("keyevent", desc, exc)
                # 按键事件未做本地重试，直接交给 worker 重建整套运行时。
                self._raise_runtime_disconnect_to_worker("keyevent", desc, exc)
            # 记录按键失败原因。
            self.log.error("按键事件失败，按跳过处理", target=desc, key=key, error=str(exc))
            # 返回 False 表示按键失败。
            return False

    # 定义“清空通用任务结果缓存”的方法。
    def _reset_task_result_state(self) -> None:
        # 把通用失败原因重置为空字符串，避免串到下一轮任务。
        self.task_result_reason = ""
        # 把通用失败状态码重置为普通失败状态，避免串到下一轮任务。
        self.task_result_status = 3
        # 同步重置 Facebook 失败原因缓存，保持旧逻辑兼容。
        self.facebook_error_reason = ""
        # 同步重置 Facebook 失败状态码，保持旧逻辑兼容。
        self.facebook_error_status = 3

    # 定义“清空 Facebook 失败原因缓存”的方法。
    def _reset_facebook_error_reason(self) -> None:
        # 复用通用任务结果重置逻辑，保持字段状态一致。
        self._reset_task_result_state()

    # 定义“记录通用任务失败原因”的方法。
    def _set_task_result_failure(self, reason: str, target_status: int = 3) -> None:
        # 标准化失败原因字符串，避免空值落库不可读。
        safe_reason = str(reason or "").strip()
        # 当调用方传空原因时，回退统一文案。
        if safe_reason == "":
            # 使用兜底错误文案。
            safe_reason = "任务执行失败：未知原因"
        # 保存通用失败原因，供子类和收尾逻辑复用。
        self.task_result_reason = safe_reason
        # 保存通用失败状态码，供收尾阶段统一回写。
        self.task_result_status = int(target_status)
        # 同步写回 Facebook 兼容字段，避免旧逻辑丢值。
        self.facebook_error_reason = safe_reason
        # 同步写回 Facebook 兼容状态码。
        self.facebook_error_status = int(target_status)

    # 定义“记录 Facebook 失败原因并返回 False”的方法。
    def _facebook_fail(self, reason: str, target_status: int = 3) -> bool:
        # 先保存通用失败结果，供基类和子类共用。
        self._set_task_result_failure(reason=reason or "Facebook 注册失败：未知原因", target_status=target_status)
        # 记录错误日志，确保失败链路可追踪。
        self.log.error(
            "Facebook 注册流程失败",
            reason=self.facebook_error_reason,
            target_status=self.facebook_error_status,
            user_email=self.user_email,
        )
        # 返回 False，便于调用方直接 `return self._facebook_fail(...)`。
        return False

    # 定义“格式化异常文本”的方法，供 msg 字段落库复用。
    def _build_failure_msg(self, exc: Exception, prefix: str = "") -> str:
        # 提取异常类型名，提升可读性。
        exc_type = type(exc).__name__
        # 提取异常明细文本。
        exc_detail = str(exc).strip()
        # 当异常文本为空时回退为类型名。
        if exc_detail == "":
            # 用类型名作为兜底详情。
            exc_detail = exc_type
        # 组装“前缀 + 类型 + 详情”格式文本。
        base_message = f"{prefix} | {exc_type}: {exc_detail}" if prefix else f"{exc_type}: {exc_detail}"
        # 控制 msg 长度，避免异常文本过长影响列表查看。
        return base_message[:300]

    # 定义“通用回写任务结果到 t_user”的方法。
    def _update_result_to_db(
        self,
        *,
        success: bool,
        reason: str = "",
        status_field: str,
        success_status_value: int = 1,
        failure_status_value: int = 0,
        increment_fb_fail_num: bool = False,
        increment_vt_fail_num: bool = False,
        log_label: str = "任务",
    ) -> None:
        # 邮箱为空时无法按账号更新，直接记录错误并返回。
        if self.user_email == "":
            # 记录无法更新的根因。
            self.log.error("更新 t_user 失败：email_account 为空", success=success, log_label=log_label)
            # 直接返回，避免无意义 SQL。
            return
        # 成功时账号状态写 2（已完成），失败时使用流程内记录的失败状态码。
        target_status = 2 if success else int(self.task_result_status)
        # 根据调用方传入的状态字段值构造目标注册状态。
        target_register_status = int(success_status_value if success else failure_status_value)
        # 失败且调用方要求时才累加 Facebook 失败次数。
        should_increment_fb_fail_num = bool((not success) and increment_fb_fail_num)
        # 失败且调用方要求时才累加 Vinted 失败次数。
        should_increment_vt_fail_num = bool((not success) and increment_vt_fail_num)
        # 成功时清空 msg，失败时写入具体错误原因。
        target_msg = "" if success else str(reason or f"{log_label}失败：未知原因").strip()
        # 控制 msg 长度，避免写入过长异常字符串。
        target_msg = target_msg[:300]
        # 初始化动态更新参数字典。
        update_kwargs: dict[str, Any] = {}
        # Facebook 路径写入 fb_status 字段。
        if status_field == "fb_status":
            # 写入 Facebook 注册状态。
            update_kwargs["fb_status"] = target_register_status
        # Vinted 路径写入 vinted_status 字段。
        elif status_field == "vinted_status":
            # 写入 Vinted 注册状态。
            update_kwargs["vinted_status"] = target_register_status
        # 未知字段直接记录错误并返回，避免误更新。
        else:
            # 记录非法字段错误。
            self.log.error("回写任务结果失败：状态字段非法", status_field=status_field, log_label=log_label)
            # 直接返回，避免执行错误 SQL。
            return
        # 使用异常保护数据库更新，确保任务流程不崩溃。
        try:
            # 执行按邮箱更新状态（status/注册状态/msg）。
            affected_rows = self.user_db.update_status(
                # 目标邮箱账号。
                email_account=self.user_email,
                # 目标账号状态。
                status=target_status,
                # 目标备注信息。
                msg=target_msg,
                # 失败时原子累加 Facebook 失败次数，成功时保持原值。
                increment_fb_fail_num=should_increment_fb_fail_num,
                # 失败时原子累加 Vinted 失败次数，成功时保持原值。
                increment_vt_fail_num=should_increment_vt_fail_num,
                # 透传当前任务对应的注册状态字段更新参数。
                **update_kwargs,
            )
            # 记录落库结果，便于后续排查是否命中记录。
            self.log.info(
                f"{log_label}结果已回写 t_user",
                email_account=self.user_email,
                status=target_status,
                status_field=status_field,
                register_status=target_register_status,
                increment_fb_fail_num=should_increment_fb_fail_num,
                increment_vt_fail_num=should_increment_vt_fail_num,
                msg=target_msg,
                affected_rows=affected_rows,
            )
        # 捕获数据库更新异常并记录，不向外抛出。
        except Exception as exc:
            # 记录完整异常栈，便于定位 DB 层问题。
            self.log.exception(
                f"回写{log_label}结果到 t_user 失败",
                email_account=self.user_email,
                status=target_status,
                status_field=status_field,
                register_status=target_register_status,
                increment_fb_fail_num=should_increment_fb_fail_num,
                increment_vt_fail_num=should_increment_vt_fail_num,
                msg=target_msg,
                error=str(exc),
            )

    # 定义“回写 Facebook 结果到 t_user”的方法。
    def _update_fb_result_to_db(self, success: bool, reason: str = "") -> None:
        # 复用通用回写逻辑，保持 Facebook 原有状态语义不变。
        self._update_result_to_db(
            success=success,
            reason=reason,
            status_field="fb_status",
            success_status_value=1,
            failure_status_value=2,
            increment_fb_fail_num=True,
            log_label="Facebook",
        )

    # 定义“按轮询查找并点击”的通用方法，支持传入 Poco 节点列表。
    def poco_find_or_click(
        self,
        nodes: list[Any],
        desc: str,
        sleep_interval: float | None = None,
        expected_package: str | None = None,
    ) -> bool:
        # 当调用方未传节点时直接返回失败。
        if not nodes:
            # 记录参数错误日志，方便排查调用点问题。
            self.log.error("poco_find_or_click 未传入节点", target=desc)
            # 返回 False 表示本次调用失败。
            return False

        # 解析总超时秒数：未传时默认最多等待 5 秒。
        timeout_sec = 5.0 if sleep_interval is None else float(sleep_interval)
        # 兜底修正非法超时值，避免负数造成死循环。
        if timeout_sec < 0:
            # 负数超时重置为 0。
            timeout_sec = 0.0
        # 记录轮询开始时间，后续计算总耗时与剩余时间。
        started_at = time.monotonic()
        # 计算本次轮询截止时间点。
        deadline_at = started_at + timeout_sec
        # 初始化轮询计数器，便于日志排查。
        attempt = 0
        # 保存当前可用的节点列表，连接重建后会按 query 重新绑定。
        current_nodes = list(nodes)

        # 在超时前持续按 1 秒间隔轮询。
        while True:
            # 进入新一轮轮询时递增计数。
            attempt += 1
            # 当前预留 expected_package 参数，但暂不在这里强制中断主流程。
            # _ = str(expected_package or "").strip()
            # 标记本轮是否发生了连接恢复。
            recovered_in_round = False
            # 逐个遍历传入的候选节点。
            for node_index, node in enumerate(current_nodes):
                # 使用异常保护 exists 查询，避免查询异常导致流程中断。
                try:
                    # 当前节点存在时尝试立即点击。
                    if bool(node.exists()):
                        # 调用统一安全点击方法，命中后直接返回。
                        if self._safe_click(node, f"{desc}-候选{node_index}", sleep_interval=None):
                            # 计算当前总耗时毫秒，包含查询与轮询等待。
                            elapsed_ms = int((time.monotonic() - started_at) * 1000)
                            # 记录命中日志，包含命中轮次和节点索引。
                            self.log.info(
                                "poco_find_or_click 命中并点击成功",
                                target=desc,
                                timeout_sec=timeout_sec,
                                attempt=attempt,
                                elapsed_ms=elapsed_ms,
                                node_index=node_index,
                            )
                            # 点击成功后立即返回 True。
                            return True
                # 捕获 exists 查询异常并统一处理。
                except Exception as exc:
                    # 记录异常并尝试恢复 Poco 连接。
                    recovered = self._handle_safe_action_exception("poco_find_or_click", f"{desc}-候选{node_index}", exc)
                    # 连接恢复成功时，当前轮直接重绑全部节点并重新开始扫描。
                    if recovered:
                        # 使用新 Poco 重新绑定全部节点，避免继续复用旧代理。
                        current_nodes = [self._rebind_poco_node(current_node) for current_node in current_nodes]
                        # 标记当前轮已恢复。
                        recovered_in_round = True
                        # 跳出当前 for 循环，进入下一轮重新扫描。
                        break
                    # 恢复失败且属于连接异常时，直接终止当前任务并让 worker 重建运行时。
                    self._raise_if_disconnect_unrecovered("poco_find_or_click", f"{desc}-候选{node_index}", exc, recovered)
            # 当前轮发生过连接恢复时，直接进入下一轮重新扫描。
            if recovered_in_round:
                continue
            # 计算当前距离截止时间的剩余秒数。
            remaining_sec = deadline_at - time.monotonic()
            # 超时后退出轮询循环。
            if remaining_sec <= 0:
                break
            # 每次最多等待 1 秒，确保“每秒查一次”且不超过总超时。
            sleep(min(1.0, remaining_sec))
        # 计算最终总耗时毫秒，包含查询与等待时间。
        elapsed_ms = int((time.monotonic() - started_at) * 1000)
        # 所有轮次都未命中时记录失败日志。
        self.log.error(
            "poco_find_or_click 未命中",
            target=desc,
            timeout_sec=timeout_sec,
            attempt=attempt,
            elapsed_ms=elapsed_ms,
            candidates=len(nodes),
        )
        # 返回 False 表示未找到可点击节点。
        return False

    # 定义单次循环逻辑，封装每轮清理动作。
    def mojiwang_run_one_loop(self, loop_index: int) -> None:
        sleep(1)
        # 从当前任务实例中拿到可用的 Poco 对象。
        poco = self._require_poco()
        # 把从 0 开始的索引转换成人类可读的轮次编号。
        round_no = loop_index + 1
        # 记录循环开始日志。
        self.log.info("开始执行清理循环", round_no=round_no, total_rounds=self.mojiwang_loop_count)
        # 定位“清理按钮”控件节点。
        wipe_button = poco(self.mojiwang_wipe_button_id)
        # 如果 5 秒内都没点到清理按钮。
        if not self._wait_and_click_node(wipe_button, f"清理按钮-第{round_no}轮"):
            # 记录跳过日志并结束本轮。
            self.log.error("未找到清理按钮，跳过本轮", round_no=round_no)
            # 直接返回，避免继续找“任务结束提示”。
            return

        # 中文模式：按 ID + 文本定位。
        done_msg = poco(self.mojiwang_done_msg_id, text=self.mojiwang_done_msg_text)

        # 若在超时前成功点击“任务结束提示”。
        if self._wait_and_click_node(done_msg, f"任务结束返回提示-第{round_no}轮"):
            # 记录成功日志。
            self.log.info("已点击任务结束返回提示", round_no=round_no)
            # 点击成功后结束本轮。
            return
        # 若没出现则记录警告，继续下一轮。
        self.log.error("未出现任务结束返回提示", round_no=round_no)
        
    # 定义“抹机王全部循环动作”的方法。
    def mojiwang_run_all(self) -> None:
        # 短暂等待 1 秒，让系统完成进程状态切换。
        sleep(1)
        # 重新启动插件应用，进入待操作页面。
        start_app(self.mojiwang_packge)
        # 记录插件应用启动成功。
        self.log.info("已启动应用,循环次数", package=self.mojiwang_packge, num=self.mojiwang_loop_count)
        # 按设定次数循环执行清理流程。
        for loop_index in range(self.mojiwang_loop_count):
            # 短暂等待 1 秒
            sleep(1)
            # 调用单轮方法执行“清理并返回”动作。
            self.mojiwang_run_one_loop(loop_index)

        # 等待操作完
        sleep(3)
        # 全部循环结束后停止插件应用。
        stop_app(self.mojiwang_packge)
        # 记录任务结束日志。
        self.log.info("任务结束，已停止应用", package=self.mojiwang_packge)

    # 定义 Nekobox 全流程方法（带 defer 风格收尾）。
    def nekobox_run_all(self, mode_index: int | None = None) -> bool:

        # 从当前任务实例中拿到可用的 Poco 对象。
        poco = self._require_poco()
        # 稍等 1 秒，避免紧接上一步操作导致界面状态不稳定。
        sleep(1)
        # 启动 Nekobox 应用。
        start_app(self.nekobox_package)
        # 记录启动成功日志。
        self.log.info("已启动应用", package=self.nekobox_package)
        # 用 try/finally 模拟 Go defer：主流程在 try，收尾放 finally。
        try:
            # 等待页面加载完成，避免节点还没出现就查找。
            sleep(1)
            # 定位顶部分组容器的直接子项。
            parent = poco("moe.nb4a:id/group_tab").child("android.widget.LinearLayout")
            # 先安全等待父节点出现，避免直接 exists/click 触发连接异常中断。
            if not self._safe_wait_exists(parent, 3, "Nekobox 模式选择父节点"):
                # 记录错误日志。
                self.log.error("未找到 Nekobox 模式选择父节点，无法继续", package=self.nekobox_package)
                # 本轮提前结束，finally 仍会执行收尾。
                return False
            # 取到 group_tab 下一层所有可点击子节点（订阅/移动等）。
            tab_children = parent.children()
            # 至少需要两个分组节点才满足后续点击。
            if len(tab_children) < 2:
                # 记录错误日志。
                self.log.error("Nekobox 订阅和代理找不到,至少 2 个分组，订阅放第一个，移动和动态放第二个分组", package=self.nekobox_package)
                # 本轮提前结束，finally 仍会执行收尾。
                return False
            # 点击第二个分组（索引从 0 开始，1 表示第二个）。
            if not self._safe_click(tab_children[1], "Nekobox 第二分组", sleep_interval=1):
                # 点击失败时记录错误并结束本轮，避免后续链路连锁失败。
                self.log.error("点击 Nekobox 第二分组失败，结束本轮", package=self.nekobox_package)
                # 本轮提前结束，finally 仍会执行收尾。
                return False
            # 定位配置列表容器。
            parent = poco("android.widget.FrameLayout").child("android.widget.LinearLayout").offspring("moe.nb4a:id/fragment_holder").offspring("moe.nb4a:id/configuration_list").child("moe.nb4a:id/content")
            # 安全等待配置列表父节点，避免连接波动时直接崩溃。
            if not self._safe_wait_exists(parent, 3, "Nekobox 配置列表父节点"):
                # 记录错误日志。
                self.log.error("未找到 Nekobox 配置列表父节点，无法继续", package=self.nekobox_package)
                # 本轮提前结束，finally 仍会执行收尾。
                return False
            # 取配置列表下一层的模式节点集合。
            mode_children = parent.children()
            # 一个模式节点都没有时直接按失败返回，避免后续索引越界。
            if len(mode_children) == 0:
                # 记录空列表错误日志。
                self.log.error("Nekobox 模式节点为空，无法继续", package=self.nekobox_package)
                # 本轮提前结束，finally 仍会执行收尾。
                return False
            # 未传入固定索引时，按配置范围安全随机一个模式索引。
            if mode_index is None:
                # 计算当前轮安全随机后的模式索引。
                mode_index = self._resolve_safe_proxy_mode_index(len(mode_children))
            # 没有得到可用索引时按失败返回。
            if mode_index is None:
                # 记录错误日志。
                self.log.error("Nekobox 模式索引解析失败，结束本轮", package=self.nekobox_package, total=len(mode_children))
                # 本轮提前结束，finally 仍会执行收尾。
                return False
            # 传入固定索引时仍做一次硬保护，避免调试调用越界。
            if mode_index < 0 or mode_index >= len(mode_children):
                # 记录越界错误日志。
                self.log.error("Nekobox 模式索引越界", package=self.nekobox_package, mode_index=mode_index, total=len(mode_children))
                # 本轮提前结束，finally 仍会执行收尾。
                return False
            # 按最终安全索引点击目标模式节点。
            if not self._safe_click(mode_children[mode_index], f"Nekobox 模式节点-{mode_index}", sleep_interval=1):
                # 点击失败时记录错误并结束本轮。
                self.log.error("点击 Nekobox 模式节点失败，结束本轮", package=self.nekobox_package, mode_index=mode_index)
                # 本轮提前结束，finally 仍会执行收尾。
                return False
            # 判断 stats 节点是否存在。
            start_button_node = poco("android.widget.FrameLayout").child("android.widget.LinearLayout").offspring("moe.nb4a:id/stats")
            # 使用安全等待判断代理是否已经启动。
            start_button_bool = self._safe_wait_exists(start_button_node, 1.5, "Nekobox 运行状态节点")
            # stats 存在时认为代理已在运行。
            if start_button_bool:
                # 记录已运行状态。
                self.log.info("代理已经启动了", package=self.nekobox_package)
            # stats 不存在时尝试点击启动按钮。
            else:
                # 记录准备启动日志。
                self.log.info("代理未启动，正在启动", package=self.nekobox_package)
                # 先定位启动按钮节点，避免重复查询。
                fab = poco("moe.nb4a:id/fab")
                # 按钮存在才执行点击。
                if self._safe_wait_exists(fab, 2, "Nekobox 启动按钮"):
                    # 点击启动代理按钮。
                    self._safe_click(fab, "Nekobox 启动按钮", sleep_interval=0.5)
                # 启动按钮不存在时记录警告。
                else:
                    # 记录按钮缺失日志。
                    self.log.error("未找到代理启动按钮", package=self.nekobox_package)
            # 预留观察/生效等待时间，后续可按需要调整。
            sleep(2)
            # 主流程走到这里视为 Nekobox 步骤成功完成。
            return True
        # 无论 try 内成功、return 或抛异常，都会执行这里。
        finally:
            # 强制停止 Nekobox，保证流程收尾一致。
            # stop_app(self.nekobox_package)
            home()
            # 记录收尾停止日志。
            # self.log.info("任务结束，已停止应用", package=self.nekobox_package)

    # 定义“获取 Facebook 验证码”的复用方法（带重试）。
    def _fetch_facebook_code(self, retry_times: int = 5, wait_seconds: int = 15) -> str | None:
        # 校验 client_id 是否存在，缺失时直接返回失败。
        if not self.user_info.get("client_id"):
            # 记录 client_id 缺失错误。
            self.log.error("client_id 为空，无法获取验证码", user_email=self.user_email)
            # 记录失败原因，供外层写入 t_user.msg。
            self._facebook_fail("client_id 为空，无法获取验证码")
            # 返回空值表示获取失败。
            return None

        # 校验 email_access_key 是否存在，缺失时直接返回失败。
        if not self.user_info.get("email_access_key"):
            # 记录 email_access_key 缺失错误。
            self.log.error("email_access_key 为空，无法获取验证码", user_email=self.user_email)
            # 记录失败原因，供外层写入 t_user.msg。
            self._facebook_fail("email_access_key 为空，无法获取验证码")
            # 返回空值表示获取失败。
            return None

        # 初始化成功标记，默认失败。
        ok = False
        # 初始化验证码变量，默认空。
        fb_code = None
        # 按重试次数循环拉取验证码。
        for attempt in range(retry_times):
            # 每次重试前等待固定秒数，给邮件系统同步时间。
            sleep(wait_seconds)
            # 使用异常保护邮箱验证码拉取，避免接口异常导致流程崩溃。
            try:
                # 调用邮箱接口拉取验证码。
                ok, fb_code = getfackbook_code(
                    # 传入当前账号 client_id。
                    client_id=self.user_info["client_id"],
                    # 传入当前账号邮箱。
                    email_name=self.user_email,
                    # 传入当前账号 refresh_token。
                    refresh_token=self.user_info["email_access_key"],
                )
            # 捕获接口异常并按失败处理。
            except Exception as exc:
                # 记录接口异常日志。
                self.log.exception("获取验证码接口异常", user_email=self.user_email, attempt=attempt + 1, error=str(exc))
                # 当前轮次按失败处理。
                ok, fb_code = False, None
            # 当拉取成功且验证码非空时结束重试。
            if ok and fb_code:
                # 记录本次命中重试轮次。
                self.log.info("获取验证码成功", attempt=attempt + 1, retry_times=retry_times)
                # 退出重试循环。
                break
            # 记录当前轮拉取失败日志。
            self.log.warning("获取验证码失败，准备重试", attempt=attempt + 1, retry_times=retry_times)

        # 当最终仍失败时返回空。
        if not ok or not fb_code:
            # 记录最终失败日志。
            self.log.error("获取验证码失败，无法继续", user_email=self.user_email)
            # 记录失败原因，供外层写入 t_user.msg。
            self._facebook_fail("获取验证码失败：邮箱未收到验证码或解析失败")
            # 返回空值表示失败。
            return None

        # 返回验证码字符串给调用方复用。
        return str(fb_code)

    # 定义 Facebook 全流程方法，包含节点查询和点击的安全兜底。
    def facebook_run_all(self) -> bool:
        # 重置本轮 Facebook 失败原因，避免串到历史失败信息。
        self._reset_facebook_error_reason()
        # 稍等 1 秒，避免紧接上一步导致页面状态不稳定。
        sleep(1)
        # 先清理相关应用状态，保证流程从干净环境开始。 调试
        # self.clear_all()
        # 获取当前任务实例中的 Poco 对象。
        poco = self._require_poco()
        # 定义当前方法内的步骤封装，统一“失败后处理弹框并仅重试该步骤一次”。
        def _run_step_or_fail(step_desc: str, fail_reason: str, action: Any) -> bool:
            # 调用统一封装执行步骤，失败时内部会自动写入失败原因并返回 False。
            return self._facebook_action_or_fail(
                poco=poco,
                step_desc=step_desc,
                fail_reason=fail_reason,
                action=action,
            )
        # 启动 Facebook 应用。
        start_app(self.facebook_package)
        # 记录启动成功日志。
        self.log.info("已启动应用", package=self.facebook_package)
        # 按设备语言读取“开始按钮”文案。
        start_desc = FACEBOOK_START_UP.get(self.device_lang)
        # 如果当前语言没有配置启动文案。
        if not start_desc:
            # 记录跳过原因。
            self.log.info("当前语言不支持 Facebook 自动化操作，跳过", device_lang=self.device_lang)
            # 返回失败并记录具体错误原因。
            return self._facebook_fail(f"当前语言不支持 Facebook 自动化操作: {self.device_lang}")
        # 初始化“创建账号候选按钮”列表（兼容 v1/v2 文案）。
        create_user_nodes: list[Any] = []
        # 读取 v1 按钮文案并清理空白字符。
        create_user_text_v1 = str(FACEBOOK_CREATE_USER_BUTTON.get(self.device_lang, "")).strip()
        # v1 文案非空时加入候选列表。
        create_user_nodes.append(poco(text=create_user_text_v1))
        # 读取 v2 按钮文案并清理空白字符。
        create_user_text_v2 = str(FACEBOOK_CREATE_USER_BUTTONV2.get(self.device_lang, "")).strip()
        # v2 文案非空时加入候选列表。
        create_user_nodes.append(poco(text=create_user_text_v2))

        # 记录是否已经进入“创建账号”分支。
        entered_create_user_flow = False
        # 候选按钮列表非空时执行 or 逻辑查找点击。
        if create_user_nodes:
            create_user_nodes.append(poco("com.android.permissioncontroller:id/permission_allow_button"))
            # 最多等待 30 秒，命中任一按钮就点击并返回 True。
            # 循环两次可能有其他的弹窗干扰，第一次点击后可能需要等待界面稳定后再查找第二次。
            for attempt in range(2):
                entered_create_user_flow = self.poco_find_or_click(
                    nodes=create_user_nodes,
                    desc="Create New Facebook Account 按钮(v1/v2)",
                    sleep_interval=30,
                    expected_package=self.facebook_package,
                )
                # 候选按钮列表为空时记录提示。
                if not entered_create_user_flow:
                   break
        else:
            # 记录当前语言未配置 v1/v2 文案。
            self.log.error("创建账号按钮文案为空，跳过 v1/v2 匹配", device_lang=self.device_lang)
            # 返回失败并记录具体错误原因。
            return self._facebook_fail("创建账号按钮文案为空（v1/v2 均未配置）")

        # 命中创建账号分支后继续执行下一页流程。
        if entered_create_user_flow:

            # 定位“创建账号第 2 页”按钮。
            create_user_page2_node = poco(FACEBOOK_CREATE_USER_BUTTON_PAGE2[self.device_lang])
            # 等待第 2 页按钮出现。
            if not _run_step_or_fail(
                step_desc="等待 Create New Facebook Account 按钮2",
                fail_reason="未找到 Create New Facebook Account 按钮2",
                action=lambda: self._safe_wait_exists(create_user_page2_node, 70, "Create New Facebook Account 按钮2"),
            ):
                # 步骤失败且重试后仍失败时，直接结束当前流程。
                return False
            # 点击第 2 页按钮。
            self._safe_click(create_user_page2_node, "Create New Facebook Account 按钮2", sleep_interval=2)
        # 未命中创建账号按钮时走启动按钮分支。
        else:
            # 定位“Get started / Démarrer”按钮节点。
            start_node = poco(text=start_desc)
            # 安全等待启动按钮出现。
            if self._safe_wait_exists(start_node, 50, "Facebook 启动按钮"):
                # 点击启动按钮并记录日志。
                self._safe_click(start_node, "Facebook 启动按钮")
                # 按钮未出现时记录信息。
            else:
                # 记录跳过启动按钮。
                self.log.info("未找到启动按钮，跳过点击", start_desc=start_desc)



        # 定位系统权限允许按钮。
        allow_button = poco("com.android.permissioncontroller:id/permission_allow_button")
        # 安全等待权限按钮。
        if self._safe_wait_exists(allow_button, 2, "系统权限允许按钮"):
            # 点击权限按钮后等待 1 秒。
            self._safe_click(allow_button, "系统权限允许按钮", sleep_interval=1)
        # 给页面一个短暂缓冲，确保你手动或前序动作已把焦点放到 first name。
        sleep(1)
        # 如果 first name 为空或缺失。
        if not self.user_first_name:
            # 记录错误日志，包含账号信息
            self.log.error("First name 为空，无法输入", user_email=self.user_email)
            # 返回失败并记录具体错误原因。
            return self._facebook_fail("First name 为空，无法输入")

        # 直接向当前焦点输入 first name（不依赖节点）。
        if not _run_step_or_fail(
            step_desc="输入 First name",
            fail_reason="First name 焦点输入失败",
            action=lambda: self._safe_input_on_focused(self.user_first_name, "First name-当前焦点"),
        ):
            # 记录失败并结束流程。
            self.log.info("First name 焦点输入失败，跳过后续操作")
            # 输入失败时返回失败并记录原因。
            return False
        # 读取当前语言的 last name 占位文案，用于点击聚焦输入框。
        last_name_desc = FACEBOOK_LAST_NAME_INPUT.get(self.device_lang)
        
        # 聚焦 Last name 输入框
        # 记录是否已成功把焦点切到 last name 输入框。
        focused_last_name = False
        # 只有配置了文案才尝试节点点击聚焦。
        if last_name_desc:
            # 根据占位文案定位 last name 区域节点。
            last_name_node = poco(text=last_name_desc)
            # 等待 last name 节点出现。
            if self._safe_wait_exists(last_name_node, 2, "Last name 输入框节点"):
                # 先点击 last name 节点聚焦。
                if self._safe_click(last_name_node, "Last name 输入框-点击聚焦", sleep_interval=0.6):
                    # 标记聚焦成功。
                    focused_last_name = True

        # 如果还没成功聚焦 last name。
        if not focused_last_name:
            # 通过步骤封装重试一次 last name 聚焦动作。
            if not _run_step_or_fail(
                step_desc="聚焦 Last name 输入框节点",
                fail_reason="Last name 输入框节点不可点击",
                action=lambda: (
                    bool(last_name_desc)
                    and self._safe_wait_exists(poco(text=last_name_desc), 2, "Last name 输入框节点-重试")
                    and self._safe_click(poco(text=last_name_desc), "Last name 输入框-点击聚焦-重试", sleep_interval=0.6)
                ),
            ):
                # 步骤失败且重试后仍失败时，直接结束当前流程。
                return False
            # 重试成功后标记聚焦完成。
            focused_last_name = True

        # 无论哪种聚焦方式都额外等待一会儿，确保焦点稳定后再输入。
        sleep(0.8)
        # 如果 last name 为空或缺失。
        if not self.user_last_name:
            # 记录错误日志，包含账号信息
            self.log.error("Last name 为空，无法输入", user_email=self.user_email)
            # 返回失败并记录具体错误原因。
            return self._facebook_fail("Last name 为空，无法输入")
        # 继续向当前焦点输入 last name（不依赖节点）。
        if not _run_step_or_fail(
            step_desc="输入 Last name",
            fail_reason="Last name 焦点输入失败",
            action=lambda: self._safe_input_on_focused(self.user_last_name, "Last name-当前焦点"),
        ):
            # 记录失败并结束流程。
            self.log.info("Last name 焦点输入失败，结束本轮输入")
            # 输入失败时返回失败并记录原因。
            return False
        # 输入完成后稍等，确保输入事件处理完毕
        sleep(0.5)




        # 根据占位文案定位 last name 区域节点。
        next_node = poco(text=FACEBOOK_FIRST_LAST_NAME_NEXT[self.device_lang])
        # 等待 last name 节点出现。
        if not _run_step_or_fail(
            step_desc="等待名字页 next 输入点",
            fail_reason="未找到 next 输入点",
            action=lambda: self._safe_wait_exists(next_node, 1, "next输入点"),
        ):
            # 步骤失败且重试后仍失败时，直接结束当前流程。
            return False

        # 先点击 last name 节点聚焦
        self._safe_click(next_node, "next输入点点击", sleep_interval=2)

        if self._safe_wait_exists(poco(text=FACEBOOK_FIRST_LAST_NAME_NEXT[self.device_lang]), 2, "输入名字后继续找到 next 说明需要确认名称了"):
            if not _run_step_or_fail(
                step_desc="点击名字确认页 deep next 节点",
                fail_reason="未找到 next 输入点v2（深层路径）或点击失败",
                action=lambda: self._safe_click_facebook_next_v2_deep(poco),
            ):
                # 步骤失败且重试后仍失败时，直接结束当前流程。
                return False



        year = datetime.now().year

        # 根据占位文案定位 last name 区域节点
        year_node = poco(text=str(year))
        # 等待 last name 节点出现。
        if not _run_step_or_fail(
            step_desc=f"等待年份输入点-{year}",
            fail_reason=f"未找到年份输入点: {year}",
            action=lambda: self._safe_wait_exists(year_node, 5, "year输入点:" + str(year)),
        ):
            # 步骤失败且重试后仍失败时，直接结束当前流程。
            return False
        # 先点击 last name 节点聚焦
        self._safe_click(year_node, "year输入点点击", sleep_interval=2)


        # 继续向当前焦点输入 last name（不依赖节点）。
        # 1993 到 1998 随机数
        year_num = random.randint(1993, 2002)
        if not _run_step_or_fail(
            step_desc="输入年份",
            fail_reason="年份输入失败",
            action=lambda: self._safe_input_on_focused(str(year_num), "年份", True),
        ):
            # 步骤失败且重试后仍失败时，直接结束当前流程。
            return False

        # 先点击 last name 节点聚焦
        self._safe_click(poco(text=FACEBOOK_YEAR_SET[self.device_lang]), "年份 set 点击", sleep_interval=2)

        self._safe_click(poco(text=FACEBOOK_FIRST_LAST_NAME_NEXT[self.device_lang]), "年份 set后下一页", sleep_interval=4)  #


        # 根据占位文案定位 男性 输入节点
        gender_node = poco(text=FACEBOOK_GENDER_MALE[self.device_lang])
        # 等待 男性 输入节点 出现。
        if not _run_step_or_fail(
            step_desc="等待性别选择节点（男性）",
            fail_reason="未找到性别选择节点（男性）",
            action=lambda: self._safe_wait_exists(gender_node, 2, "性别找不到"),
        ):
            # 步骤失败且重试后仍失败时，直接结束当前流程。
            return False

        # 点击 男性 输入节点 聚焦并选择
        self._safe_click(gender_node, "性别-男性-点击", sleep_interval=2)


        self._safe_click(poco(text=FACEBOOK_FIRST_LAST_NAME_NEXT[self.device_lang]), "设置性别后下一页", sleep_interval=2)


        email_node = poco(text=FACEBOOK_SELECT_EMAIL_SIGN_UP[self.device_lang])
        # 等待选择邮箱注册按钮出现。
        if not _run_step_or_fail(
            step_desc="等待选择邮箱注册按钮",
            fail_reason="未找到选择邮箱注册按钮",
            action=lambda: self._safe_wait_exists(email_node, 30, "选择邮箱注册按钮"),
        ):
            # 步骤失败且重试后仍失败时，直接结束当前流程。
            return False
        # 点击选择邮箱注册按钮
        self._safe_click(email_node, "选择邮箱注册按钮", sleep_interval=2)
        # 定位邮箱输入框
        email_input_node = poco(text=FACEBOOK_EMAIL_INPUT[self.device_lang])
        # 等待邮箱输入框出现。
        if not _run_step_or_fail(
            step_desc="等待邮箱输入框",
            fail_reason="邮箱输入框未出现",
            action=lambda: self._safe_wait_exists(email_input_node, 4, "邮箱输入框"),
        ):
            # 记录错误日志，包含账号信息
            self.log.error("邮箱输入框未出现，无法继续输入", user_email=self.user_email)
            # 步骤失败且重试后仍失败时，直接结束当前流程。
            return False

        # 点击邮箱输入框聚焦
        self._safe_click(email_input_node,"邮箱输入框-点击聚焦", sleep_interval=1)

        # 向当前焦点输入邮箱地址。
        if not _run_step_or_fail(
            step_desc="输入邮箱",
            fail_reason="邮箱输入失败",
            action=lambda: self._safe_input_on_focused(self.user_email, "邮箱输入框-当前焦点", True),
        ):
            # 步骤失败且重试后仍失败时，直接结束当前流程。
            return False


        self._safe_click(poco(text=FACEBOOK_FIRST_LAST_NAME_NEXT[self.device_lang]), "提交邮箱下一页", sleep_interval=2)

        # 这里判断是否有账号登录

        if self._safe_wait_exists(poco(FACEBOOK_ACCOUNT_HELP[self.device_lang]), 5, "帮助登录的界面了"):
            self._safe_click(poco(FACEBOOK_ACCOUNT_HELP[self.device_lang]), "帮助登录的界面了-点击", sleep_interval=2)

            # if not self.poco_find_or_click(poco,"登录其他账号",  2):
            #     # 记录错误日志，包含账号信息
            #     self.log.error("未找到登录其他账号按钮", user_email=self.user_email)
            #     # 步骤失败且重试后仍失败时，直接结束当前流程。
            #     return False
        # else:
            # 定位密码输入框
            # facebook_input_password_node = poco(text=FACEBOOK_INPUT_PASSWORD[self.device_lang])
            # 等待密码输入框出现。
        if not _run_step_or_fail(
                step_desc="等待密码输入框",
                fail_reason="密码输入框未出现",
                action=lambda: self._safe_wait_exists(poco(text=FACEBOOK_INPUT_PASSWORD[self.device_lang]), 7, "密码输入框"),
        ):
            # 记录错误日志，包含账号信息
            self.log.error("密码输入框未出现，无法继续输入", user_email=self.user_email)
            # 步骤失败且重试后仍失败时，直接结束当前流程。
            return False


        # 点击密码输入框聚焦
        self._safe_click(poco(text=FACEBOOK_INPUT_PASSWORD[self.device_lang]),"密码输入框-点击聚焦", sleep_interval=1)
        # 向当前焦点输入密码。
        if not _run_step_or_fail(
            step_desc="输入 Facebook 密码",
            fail_reason="密码输入失败",
            action=lambda: self._safe_input_on_focused(self.pwd, "密码输入框-当前焦点", True),
        ):
            # 步骤失败且重试后仍失败时，直接结束当前流程。
            return False

        # self.poco_find_or_click(nodes=[],"提交密码下一页")
        self._safe_click(poco(text=FACEBOOK_FIRST_LAST_NAME_NEXT[self.device_lang]), "提交密码下一页", sleep_interval=2)

        if self._safe_wait_exists(poco(text=FACEBOOK_CREATE_PASSWORD_PAGE[self.device_lang]), 5, "提交密码后帮助登录的界面了") and self._safe_wait_exists(poco(text=FACEBOOK_FIRST_LAST_NAME_NEXT[self.device_lang]), 5, "提交密码后帮助登录的界面了") :
            for i in range(3):
                if not  self._safe_click(poco(text=FACEBOOK_ACCOUNT_HELP[self.device_lang]), "提交密码后帮助登录的界面了-循环点击"+str(i), sleep_interval=2):
                    break

        # 先判断接受按钮防止等待太久
        access_node = poco(text=FACEBOOK_FINAL_CREATE_USER_BUTTON[self.device_lang])

        if not self._safe_wait_exists(access_node, 7, "创建接受账号按钮v0"):
            # 这块有个弹框稍后处理
            facebook_later_node = poco(text=FACEBOOK_LATER_BUTTON[self.device_lang])
            if  self._safe_wait_exists(facebook_later_node, 20, "稍后按钮0"):
                self._safe_click(facebook_later_node, "稍后按钮0", sleep_interval=2)

            # 确认最后信息

            access_node = poco(text=FACEBOOK_FINAL_CREATE_USER_BUTTON[self.device_lang])
            if not _run_step_or_fail(
                step_desc="等待创建接受账号按钮",
                fail_reason="未找到创建接受账号按钮",
                action=lambda: self._safe_wait_exists(access_node, 5, "创建接受账号按钮"),
            ):
                # 步骤失败且重试后仍失败时，直接结束当前流程。
                return False

            self._safe_click(access_node, "创建账号按钮", sleep_interval=5)
        else:
            self._safe_click(access_node, "创建账号按钮v0", sleep_interval=5)
            # 可能失败了再重试 3次
            for i in range(3):
                if not self._safe_wait_exists(poco(text=FACEBOOK_FINAL_CREATE_USER_BUTTON[self.device_lang]), 2, "创建账号按钮v0-循环确认"+str(i)):
                    break
                self._safe_click(poco(text=FACEBOOK_FINAL_CREATE_USER_BUTTON[self.device_lang]), "创建账号按钮v0-循环点击"+str(i), sleep_interval=2)


        if  self._safe_wait_exists(poco(text=FACEBOOK_REFRESH_FONT_BUTTON[self.device_lang]), 70, "再次刷新按钮"):
            self._safe_click(poco(text=FACEBOOK_REFRESH_FONT_BUTTON[self.device_lang]), "刷新验证码按钮", sleep_interval=3)

        # 初始化验证码缓存变量，供不同分支共用。
        cached_fb_code: str | None = None


        if  self._safe_wait_exists(poco(text=FACEBOOK_REFRESH_FONT_BUTTON[self.device_lang]), 5, "再次刷新按钮v2"):
            self._safe_click(poco(text=FACEBOOK_REFRESH_FONT_BUTTON[self.device_lang]), "刷新验证码按钮v2", sleep_interval=3)

        # 验证码输入
        email_node = poco(text=FACEBOOK_EMAIL_CODE_INPUT[self.device_lang])
        if not _run_step_or_fail(
            step_desc="等待验证码输入框",
            fail_reason="未找到验证码输入框",
            action=lambda: self._safe_wait_exists(email_node, 15, "验证码输入框"),
        ):
            # 步骤失败且重试后仍失败时，直接结束当前流程。
            return False

        self._safe_click(email_node, "验证码输入框-点击聚焦", sleep_interval=1)

        # 如果当前分支还没有缓存验证码，则走统一获取方法。
        if not cached_fb_code:
            # 调用复用方法拉取验证码。
            cached_fb_code = self._fetch_facebook_code()
        # 拉取失败时结束流程。
        if not cached_fb_code:
            # 返回失败并记录具体错误原因。
            return self._facebook_fail("获取验证码失败")

        if not _run_step_or_fail(
            step_desc="输入 Facebook 验证码",
            fail_reason="输入验证码失败",
            action=lambda: self._safe_input_on_focused(cached_fb_code, "输入 fb code", False),
        ):
            # 步骤失败且重试后仍失败时，直接结束当前流程。
            return False



        self._safe_click(poco(text=FACEBOOK_FIRST_LAST_NAME_NEXT[self.device_lang]), "提交验证码确认", sleep_interval=3)

        # 进入“忽略/稍后/下一步”连续处理循环。
        for i in range(14):
            # 第 0 轮给更长等待时间，后续轮次使用常规等待时间。
            current_sleep_interval = 10 if i == 0 else 5
            # 每轮按候选顺序尝试：命中任一节点就点击，并进入下一轮。
            matched = self.poco_find_or_click(
                nodes=[
                    poco(text=FACEBOOK_IGNORE_BUTTON[self.device_lang]),
                    poco(text=FACEBOOK_LATER_BUTTON[self.device_lang]),
                    poco(text=FACEBOOK_POPUP_IGNORE_BUTTON[self.device_lang]),
                    poco(text=FACEBOOK_FIRST_LAST_NAME_NEXT[self.device_lang]),
                    poco(text=FACEBOOK_CONTINUE_EMAIL_SIGN_UP_BUTTON[self.device_lang]),
                    poco("com.android.permissioncontroller:id/permission_allow_button"),
                    poco(text=FACEBOOK_ACCEPT_ALL_COOKIE_BUTTON[self.device_lang]),
                ],
                desc=f"忽略链路候选all-{i}",
                sleep_interval=current_sleep_interval,
            )
            # 当前轮一个都没命中时，结束忽略链路循环。
            if not matched:
                break

        if self._safe_wait_exists(poco(FACEBOOK_SUBMIT_AFTER[self.device_lang]),1,"被风控了出现了,"+ FACEBOOK_SUBMIT_AFTER[self.device_lang]):
            # 命中风控页时单独回写 status=4，便于后续筛选和人工处理。
            return self._facebook_fail("被风控了出现了,"+ FACEBOOK_SUBMIT_AFTER[self.device_lang], target_status=4)



    #     allow_button = poco("com.android.permissioncontroller:id/permission_allow_button")
    # # 安全等待权限按钮。
    #     if self._safe_wait_exists(allow_button, 10, "系统权限允许按钮v2"):
    #     # 点击权限按钮后等待 1 秒。
    #         self._safe_click(allow_button, "系统权限允许按钮", sleep_interval=2)


        # 执行头像相册随机选图逻辑（跳过索引 0，随机范围 1..min(9, x)）。
        if not self.facebook_select_img():
            # 返回失败并记录具体错误原因（优先复用选图方法内已设置原因）。
            return self._facebook_fail(self.facebook_error_reason or "头像相册随机选图失败")

        # 循环 2 次
        for i in range(2):
            # 选择到了成功则退出
            if self.facebook_again_upload():
                break


        # 循环 5 次，处理“下一步 + 忽略”弹层。
        # for i in range(12):
        #     # 每轮先尝试点击“上传了图片下一步了”按钮：每 1 秒查一次，最多 5 次。
        #     sleep_interval = 20 if i == 0 else 3
        #     if not self.poco_find_or_click(
        #         nodes=[poco(text=FACEBOOK_FIRST_LAST_NAME_NEXT[self.device_lang]),poco(text=FACEBOOK_IGNORE_BUTTON[self.device_lang]),poco(text=FACEBOOK_FINAL_CONFIRM_BUTTON[self.device_lang]),poco(text=FACEBOOK_FINAL_CONFIRM_BUTTONV2[self.device_lang])],
        #         desc=f"上传了图片下一步了-{i}",
        #         sleep_interval=sleep_interval,
        #     ):
        #         break

        # 走到这里表示 Facebook 主流程已完成关键步骤。
        return True


    # 定义“Facebook 头像相册随机选图”的方法。
    def facebook_select_img(self) -> bool:
        # 获取当前任务实例中的 Poco 对象。
        poco = self._require_poco()
        # 用 try/except 保护整个选图流程，确保异常可追踪。
        # 初始化“前置弹框是否命中”的标记。
        tmp_bool = False
        try:

            # 先尝试处理“稍后”弹框，命中即点击，未命中不影响主流程。
            # self.poco_find_or_click(
            #     nodes=[poco(text=FACEBOOK_LATER_BUTTON[self.device_lang])],
            #     desc="稍后按钮0",
            #     sleep_interval=2,
            # )
            # # 预先定位“接受 cookie”按钮节点。
            # cookie_button = poco(text=FACEBOOK_ACCEPT_ALL_COOKIE_BUTTON[self.device_lang])
            # # 预先定位系统权限允许按钮节点。
            # allow_button = poco("com.android.permissioncontroller:id/permission_allow_button")
            # # 合并查找并点击前置弹框（cookie/权限），兼容连续弹出多个弹框。
            # for round_index in range(3):
            #     # 每轮命中任一候选就点击。
            #     if not self.poco_find_or_click(
            #         nodes=[cookie_button, allow_button],
            #         desc=f"头像流程前置弹框候选-{round_index}",
            #         sleep_interval=2,
            #     ):
            #         # 当前轮无命中时结束循环。
            #         break
            #     # 记录当前流程命中过前置弹框。
            #     tmp_bool = True

            menu_tab_node = poco(desc=FACEBOOK_MENU_TAB_DESC[self.device_lang])
            if not self._safe_wait_exists(menu_tab_node,5,"三条杆菜单"):
                # 返回失败并记录具体错误原因。
                if not tmp_bool:
                    return self._facebook_fail("未找到 Facebook 三条杆菜单入口")
                return True

            self._safe_click(menu_tab_node, "三条杆菜单", sleep_interval=5)
            # 查找头像
            avatar_node = poco(FACEBOOK_PROFILE_PHOTO_BUTTON[self.device_lang])
            if not self._safe_wait_exists(avatar_node, 5, "首页头像按钮"):
                # 返回失败并记录具体错误原因。
                self._facebook_fail("未找到首页头像按钮")
                return False

            self._safe_click(avatar_node, "首页头像按钮", sleep_interval=3)


            self.poco_find_or_click(poco(FACEBOOK_PROFILE_PHOTO_BUTTON_4[self.device_lang]), "首页头像按钮第二步", sleep_interval=3)

            keyevent("BACK")

            self._safe_keyevent("BACK", "检测到Démarrer, 退回一页")

            # 点击停止资料按钮弹框
            self.poco_find_or_click(
                nodes=[poco("android:id/button1")],
                desc="停止资料按钮",
                sleep_interval=3,
            )

            return True


            #
            # # 初始化“是否已通过弹框直接进入相册页面”的标记。
            # opened_album_directly = False
            # # 定位“添加图片”弹框按钮节点。
            # facebook_add_photo_popup_node = poco(text=FACEBOOK_ADD_PHOTO_POPUP[self.device_lang],)
            # # 如果弹框按钮出现，则点击后直接进入相册授权流程。
            # if self.poco_find_or_click(
            #     nodes=[facebook_add_photo_popup_node,poco(text=FACEBOOK_START_UP[self.device_lang])],
            #     desc="弹框跳转添加图片",
            #     sleep_interval=5,
            # ):
            #     # 标记当前已通过弹框进入相册。
            #     opened_album_directly = True
            #     # 记录直达分支日志，方便后续排查页面分支。
            #     self.log.info("命中添加图片弹框，直接进入相册授权流程")
            #
            # # 如果没有命中弹框直达，则走常规头像二级入口流程。
            # if not opened_album_directly:
            #     # 先合并查找一次头像入口忽略按钮（命中即点击，未命中直接继续）。
            #     self.poco_find_or_click(
            #         nodes=[poco(text=FACEBOOK_IGNORE_BUTTON[self.device_lang])],
            #         desc="头像入口忽略按钮",
            #         sleep_interval=3,
            #     )
            #
            #
            # else:
            #     # todo 返回
            #     keyevent("BACK")
            #     self._safe_keyevent("BACK", "检测到Démarrer, 退回一页")
            #
            #     sleep(1)
            #
            #     # todo 继续完善 有个弹框
            #     keyevent("BACK")
            #     self._safe_keyevent("BACK", "检测到Démarrer, 退回一页")
            #
            #
            # # 定位头像二级入口节点。
            # avatar_nodev2 = poco(FACEBOOK_PROFILE_PHOTO_BUTTON_2[self.device_lang])
            # # 等待头像二级入口出现。
            # if not self._safe_wait_exists(avatar_nodev2, 5, "首页头像按钮v2"):
            #     # 返回失败并记录具体错误原因。
            #     self._facebook_fail("未找到首页头像按钮v2")
            #     return True
            #
            # # 点击头像二级入口。
            # self._safe_click(avatar_nodev2, "首页头像按钮v2", sleep_interval=3)
            #
            # # 点了头像后，有个打开相册的按钮。
            # facebook_profile_photo_bottom_node = poco(text=FACEBOOK_PROFILE_PHOTO_BOTTOM_BUTTON[self.device_lang])
            # # 等待打开底部相册按钮出现。
            # if not self._safe_wait_exists(facebook_profile_photo_bottom_node, 5, "打开底部相册找不到"):
            #     # 返回失败并记录具体错误原因。
            #     self._facebook_fail("未找到打开底部相册按钮")
            #     return True
            #
            # # 点击打开底部相册按钮。
            # self._safe_click(facebook_profile_photo_bottom_node, "点击首页头像按钮", sleep_interval=2)
            #
            #
            #
            # # 预先定位“相册授权”按钮。
            # facebook_album_auth_button_node = poco(text=FACEBOOK_ALBUM_AUTH_BUTTON[self.device_lang])
            # # 预先定位“系统确认”按钮。
            # autoriser_node = poco(text=FACEBOOK_AUTORISER_AUTH_BUTTON[self.device_lang])
            # system_confirm_button_node = poco("android:id/button1")
            # # 预先定位“系统权限允许”按钮。
            # allow_button = poco("com.android.permissioncontroller:id/permission_allow_button")
            # # 合并查找授权相关弹层，命中即点击，最多处理 4 轮。
            # for round_index in range(4):
            #     # 每轮命中任一候选就点击。
            #     if not self.poco_find_or_click(
            #         nodes=[facebook_album_auth_button_node, system_confirm_button_node, allow_button,autoriser_node],
            #         desc=f"相册授权弹层候选-{round_index}",
            #         sleep_interval=2,
            #     ):
            #         # 当前轮无命中时结束循环。
            #         break
            #
            #
            # # 查找 Facebook 图库页面内的 GridView 节点 这里找相框了
            # grid_nodes = poco("com.facebook.katana:id/(name removed)").offspring("android.widget.GridView")
            # # 当没有找到 GridView 时记录错误并返回失败。
            # if len(grid_nodes) == 0:
            #     # 记录节点缺失，便于排查页面结构变化。
            #     self.log.error("未找到 Facebook 图库 GridView 节点")
            #     # 返回失败并记录具体错误原因。
            #     self._facebook_fail("未找到 Facebook 图库 GridView 节点")
            #     return True
            # # 取第一个 GridView 作为图片列表容器。
            # grid_view = grid_nodes[0]
            # # 读取 GridView 的全部直接子节点。
            # all_items = grid_view.children()
            # # 计算当前子节点总数。
            # total_items = len(all_items)
            # # 记录节点统计信息，便于问题回溯。
            # self.log.info("Facebook 图库节点统计", total_items=total_items)
            # # 当总节点数小于等于 1 时，表示没有可选图片。
            # if total_items <= 1:
            #     # 记录错误信息，说明只有索引 0 这个非图片节点。
            #     self.log.error("当前 GridView 中除了索引 0 以外没有照片可供选择", total_items=total_items)
            #     # 返回失败并记录具体错误原因。
            #     self._facebook_fail(f"图库可选照片不足：total_items={total_items}")
            #     return True
            # # 计算真实图片数量（排除索引 0）。
            # photo_count = total_items - 1
            # # 计算最大可随机索引（最多为 9）。
            # max_random_index = min(9, photo_count)
            # # 在 1 到最大可选索引之间随机生成一个索引。
            # random_index = random.randint(1, max_random_index)
            # # 根据随机索引拿到目标图片节点。
            # target_item = all_items[random_index]
            # # 记录本次随机范围和命中索引。
            # self.log.info(
            #     "Facebook 随机命中图片索引",
            #     photo_count=photo_count,
            #     random_index=random_index,
            #     selectable_range=f"1..{max_random_index}",
            # )
            # # 优先直接点击随机命中的图片节点。
            # if not self._safe_click(target_item, f"Facebook 随机图片节点-索引{random_index}", sleep_interval=1):
            #     # 返回失败并记录具体错误原因。
            #     self._facebook_fail(f"点击随机图片失败：index={random_index}")
            #     return True
            #
            #
            # self.log.info("Facebook 随机图片点击完成", random_index=random_index)
            #
            # for round_index in range(4):
            #     # 尝试点击“注册确认相片”按钮，命中即点击，未命中则继续返回成功。
            #     if not self.poco_find_or_click(
            #         nodes=[poco(FACEBOOK_CONFIRM_PHOTO_BUTTON[self.device_lang]),poco(text=FACEBOOK_FIRST_LAST_NAME_NEXT[self.device_lang]),poco(text=FACEBOOK_FINAL_CONFIRM_BUTTON[self.device_lang]),poco(text=FACEBOOK_IGNORE_BUTTON[self.device_lang])],
            #         desc="注册确认相片有就点击",
            #         sleep_interval=2,
            #     ):
            #         # 当前轮无命中时结束循环。
            #         break

            # 返回 True 表示选图成功。
            return True
        # 捕获任意异常并记录堆栈。
        except Exception as exc:
            # 记录异常详情，满足“每个错误需要日志记录”要求。
            self.log.exception("Facebook 选图异常", error=str(exc))
            # 返回失败并记录具体错误原因。
            return self._facebook_fail(self._build_failure_msg(exc, prefix="Facebook 选图异常"))

        # 定义“Facebook 头像相册随机选图”的方法。
    def facebook_again_upload(self) -> bool:
        # 获取当前任务实例中的 Poco 对象。
        poco = self._require_poco()
        stop_app(self.facebook_package)
        sleep(1)
        start_app(self.facebook_package)
        sleep(1)
        # menu_tab_node = poco(desc=FACEBOOK_MENU_TAB_DESC[self.device_lang])
        # if not self._safe_wait_exists(menu_tab_node,15,"三条杆菜单"):
        #     # 返回失败并记录具体错误原因。
        #     return False

        if not self.poco_find_or_click(
            nodes=[poco(desc=FACEBOOK_MENU_TAB_DESC[self.device_lang]),poco(desc=FACEBOOK_MENU_TAB_USER[self.device_lang])],
            desc="三条杆菜单v2",
            sleep_interval=5,
        ):
            # 通过 user.png 做菜单入口图片兜底，未命中时按失败返回。
            if not self._safe_click_image_template(
                "通过 user.png 点击三条杆菜单入口",
                "images",
                "fr",
                "facebook",
                "user.png",
                timeout_sec=10,
                interval_sec=2,
                optional=True,
                resolution=(1080, 2340),
            ):
                # 图片未命中时记录错误日志，便于后续继续调模板。
                self.log.error("未找到三条杆菜单入口图片")
                return False




        # 循环 2 次
        for i in range(2):
            if not self.poco_find_or_click(
                nodes=[
                    poco(FACEBOOK_PROFILE_PHOTO_BUTTON[self.device_lang]),
                    poco(FACEBOOK_PROFILE_PHOTO_BUTTON_2[self.device_lang]),
                    poco(FACEBOOK_PROFILE_PHOTO_BUTTON_4[self.device_lang]),
                    poco(FACEBOOK_PROFILE_PHOTO_BUTTON_3[self.device_lang]),
                    ],
                    desc="首页头像按钮v2",
                    sleep_interval=5,
            ):
                break

        if self._safe_wait_exists(poco(FACEBOOK_START_UP[self.device_lang]), 5, desc="检测到Démarrer"):
            keyevent("BACK")

            self._safe_keyevent("BACK", "检测到Démarrer, 退回一页")

            # 循环 2 次
            for i in range(2):
                if not self.poco_find_or_click(
                        nodes=[
                            poco(FACEBOOK_PROFILE_PHOTO_BUTTON[self.device_lang]),
                            poco(FACEBOOK_PROFILE_PHOTO_BUTTON_2[self.device_lang]),
                            poco(FACEBOOK_PROFILE_PHOTO_BUTTON_4[self.device_lang]),
                            poco(FACEBOOK_PROFILE_PHOTO_BUTTON_3[self.device_lang]),
                        ],
                        desc="首页头像按钮v3",
                        sleep_interval=10,
                ):
                    break

        # 通过 camera.png 做“进入相册/相机入口”的图片兜底。
        self._safe_click_image_template(
                "通过 camera.png 点击跳转相册",
                "images",
                "fr",
                "facebook",
                "camera.png",
                timeout_sec=10,
                interval_sec=2,
                optional=True,
                record_pos=(-0.359, -0.469),
                resolution=(1080, 2340),
        )

        if not self.poco_find_or_click(poco(FACEBOOK_PROFILE_PHOTO_BOTTOM_BUTTON[self.device_lang]), " 点击跳转相册", sleep_interval=3):

            # 图片兜底也未命中时记录错误日志。
            self.log.error("未找到打开底部相册按钮")
            # 通过 choose_img.png 做“选择图片”入口图片兜底，并把预测区域放在下半屏附近。
            if not self._safe_click_image_template(
                    "通过 choose_img.png 点击选择图片入口",
                    "images",
                    "fr",
                    "facebook",
                    "choose_img.png",
                    timeout_sec=5,
                    interval_sec=1,
                    optional=True,
                    record_pos=(0.0, 0.542),
                    resolution=(1080, 2340),
            ):
                # 图片未命中时记录错误日志，便于后续继续调模板。
                self.log.error("未找到选择图片入口图片")
                return False
            # 返回 False 表示当前步骤失败。

        # 预先定位“相册授权”按钮。
        # facebook_album_auth_button_node =
        # # 预先定位“系统确认”按钮。
        # autoriser_node =
        # system_confirm_button_node =
        # # 预先定位“系统权限允许”按钮。
        # allow_button =
        # # 合并查找授权相关弹层，命中即点击，最多处理 4 轮。
        for round_index in range(4):
            # 每轮命中任一候选就点击。
            if not self.poco_find_or_click(
                    nodes=[poco(text=FACEBOOK_ALBUM_AUTH_BUTTON[self.device_lang]), poco(text=FACEBOOK_AUTORISER_AUTH_BUTTON[self.device_lang]), poco("android:id/button1"),poco("com.android.permissioncontroller:id/permission_allow_button")],
                    desc=f"相册授权弹层候选-{round_index}",
                    sleep_interval=10,
            ):
                # 当前轮无命中时结束循环。
                break

        # 尝试使用 autoriser.png 作为相册授权按钮的可选图片兜底。
        if self._safe_click_image_template(
            "通过 autoriser.png 点击相册授权入口",
            "images",
            "fr",
            "facebook",
            "autoriser.png",
            timeout_sec=20,
            interval_sec=3,
            optional=True,
            record_pos=(0.001, 0.366),
            resolution=(1080, 2340),
        ):
            # 图片兜底点击成功时，再补跑一轮授权按钮候选，兼容点击后又出现系统确认弹框。
            for round_index in range(2):
                # 每轮命中任一候选就点击。
                if not self.poco_find_or_click(
                        nodes=[poco(text=FACEBOOK_AUTORISER_AUTH_BUTTON[self.device_lang]), poco("android:id/button1"),poco("com.android.permissioncontroller:id/permission_allow_button")],
                        desc=f"相册授权弹层候选-{round_index}",
                        sleep_interval=5,
                ):
                    # 当前轮无命中时结束循环。
                    break


        # 查找 Facebook 图库页面内的 GridView 节点 这里找相框了
        grid_nodes = poco("com.facebook.katana:id/(name removed)").offspring("android.widget.GridView")
        # 当没有找到 GridView 时记录错误并返回失败。
        if len(grid_nodes) == 0:
            # 记录节点缺失，便于排查页面结构变化。
            self.log.error("未找到 Facebook 图库 GridView 节点")
            # 返回失败并记录具体错误原因。
            self._facebook_fail("未找到 Facebook 图库 GridView 节点")
            return False
        # 取第一个 GridView 作为图片列表容器。
        grid_view = grid_nodes[0]
        # 读取 GridView 的全部直接子节点。
        all_items = grid_view.children()
        # 计算当前子节点总数。
        total_items = len(all_items)
        # 记录节点统计信息，便于问题回溯。
        self.log.info("Facebook 图库节点统计v2", total_items=total_items)
        # 当总节点数小于等于 1 时，表示没有可选图片。
        if total_items <= 1:
            # 记录错误信息，说明只有索引 0 这个非图片节点。
            self.log.error("当前 GridView 中除了索引 0 以外没有照片可供选择", total_items=total_items)
            # 返回失败并记录具体错误原因。
            self._facebook_fail(f"图库可选照片不足：total_items={total_items}")
            return False
        # 计算真实图片数量（排除索引 0）。
        photo_count = total_items - 1
        # 计算最大可随机索引（最多为 9）。
        max_random_index = min(9, photo_count)
        # 在 1 到最大可选索引之间随机生成一个索引。
        random_index = random.randint(1, max_random_index)
        # 根据随机索引拿到目标图片节点。
        target_item = all_items[random_index]
        # 记录本次随机范围和命中索引。
        self.log.info(
            "Facebook 随机命中图片索引",
            photo_count=photo_count,
            random_index=random_index,
            selectable_range=f"1..{max_random_index}",
        )
        # 优先直接点击随机命中的图片节点。
        if not self._safe_click(target_item, f"Facebook 随机图片节点-索引{random_index}", sleep_interval=1):
            # 返回失败并记录具体错误原因。
            self._facebook_fail(f"点击随机图片失败：index={random_index}")
            return False


        self.log.info("Facebook 随机图片点击完成", random_index=random_index)

        for round_index in range(4):
            # 尝试点击“注册确认相片”按钮，命中即点击，未命中则继续返回成功。
            if not self.poco_find_or_click(
                    nodes=[poco(FACEBOOK_CONFIRM_PHOTO_BUTTON[self.device_lang]),poco(text=FACEBOOK_FIRST_LAST_NAME_NEXT[self.device_lang]),poco(text=FACEBOOK_FINAL_CONFIRM_BUTTON[self.device_lang]),poco(text=FACEBOOK_IGNORE_BUTTON[self.device_lang])],
                    desc="注册确认相片有就点击",
                    sleep_interval=2,
            ):
                # 当前轮无命中时结束循环。
                break


        # 记录头像重新上传流程完成日志，避免把 logger 当函数调用导致直接抛异常。
        self.log.info("Facebook 头像重新上传流程完成")
        return True

    # 定义“执行任务前公共准备流程”的方法。
    def _run_common_setup_flow(self) -> None:
        # 获取并校验当前 worker 进程初始化好的 Poco 实例。
        self._require_poco()
        # 记录当前任务感知到的上下文信息。
        self.log.info(
            "任务开始",
            serial=self.device_serial,
            device_locale=self.device_locale,
            device_lang=self.device_lang,
            email_account=self.user_email,
            register_mode=self.register_mode,
            mojiwang_run_num=self.mojiwang_loop_count,
            fb_delete_num=self.fb_delete_num,
            vt_delete_num=self.vt_delete_num,
            setting_fb_del_num=self.setting_fb_del_num,
            worker_loop_seq=self.worker_loop_seq,
        )
        # 唤醒设备屏幕，避免黑屏导致后续操作失败。
        wake()
        # 回到系统桌面，保证任务从一致状态开始。
        home()
        # 记录回桌面动作完成。
        self.log.info("已回到桌面")
        # 记录共享前置阶段完成，应用数据清理由任务自身独立处理。
        self.log.info("共享前置流程完成，等待执行注册方式对应的应用清理", register_mode=self.register_mode)

    # 定义“执行一轮完整任务”的公开方法。
    def run_once(self) -> None:
        # 重置本轮任务结果缓存，避免串到下一轮任务。
        self._reset_task_result_state()
        # 重置本轮设备连接异常标记，避免串到下一轮任务。
        self._runtime_disconnect_detected = False
        # 初始化 Facebook 成功标记，默认失败。
        facebook_ok = False
        # 标记本轮是否需要把异常继续抛出给 worker 做运行时重建。
        should_reraise = False
        # 保存需要继续抛出的原始异常对象。
        reraised_exc: Exception | None = None
        # 使用异常保护整轮任务，避免异常导致进程崩溃。
        try:
            # 执行所有任务共用的前置准备流程。
            self._run_common_setup_flow()
            # 执行 Facebook 独立应用清理，避免误清理 Vinted 包。
            self._run_facebook_cleanup_flow()
            # 执行共享设备准备流程（抹机王 + 代理）。
            self._run_shared_device_prepare_flow()
            # 执行 Facebook 全流程，并返回是否成功完成。
            facebook_ok = self.facebook_run_all()
        # 捕获所有异常并转换为可落库的失败原因。
        except Exception as exc:
            # 记录完整异常日志，便于排查真实堆栈。
            self.log.exception("run_once 执行异常", error=str(exc))
            # 生成具体失败原因文本，供写入 t_user.msg。
            self._set_task_result_failure(reason=self._build_failure_msg(exc, prefix="run_once 异常"), target_status=self.task_result_status)
            # 标记本轮 Facebook 结果为失败。
            facebook_ok = False
            # 连接类异常让 worker 触发 reinit_runtime，避免任务层吞错后带病继续。
            if self._is_poco_disconnect_error(exc) or isinstance(exc, (BrokenPipeError, ConnectionResetError, TimeoutError, OSError)):
                # 标记本轮检测到设备连接异常，供收尾阶段跳过 status=3。
                self._runtime_disconnect_detected = True
                # 记录将要升级处理的异常类型。
                self.log.warning("检测到运行时连接异常，准备抛给 worker 进行重建", error_type=type(exc).__name__)
                # 打开继续抛出标记。
                should_reraise = True
                # 保存要继续抛出的异常对象。
                reraised_exc = exc
        # 无论是否异常都执行状态回写，保证账号状态有结果。
        finally:
            # Facebook 成功时写入 status=2, fb_status=1。
            if facebook_ok:
                # 回写成功状态并清空 msg。
                self._update_fb_result_to_db(success=True, reason="")
            # Facebook 失败时写入 status=3/4, fb_status=2, msg=具体错误原因。
            else:
                # 设备连接异常场景下，不把账号打成失败状态，避免误判账号问题。
                if self._runtime_disconnect_detected:
                    # 记录跳过失败落库日志，便于后续排查。
                    self.log.warning(
                        "检测到设备连接异常，跳过账号失败状态回写",
                        user_email=self.user_email,
                        reason=str(self.task_result_reason or "").strip(),
                    )
                # 非连接异常仍按原逻辑写入失败状态。
                else:
                    # 组装最终失败原因（优先使用流程内记录的具体原因）。
                    final_reason = str(self.task_result_reason or "").strip()
                    # 失败原因为空时给出统一兜底文案。
                    if final_reason == "":
                        # 使用兜底失败原因，避免 msg 为空。
                        final_reason = "Facebook 注册失败：流程未完成，未命中成功条件"
                    # 回写失败状态和详细错误原因。
                    self._update_fb_result_to_db(success=False, reason=final_reason)
            # 关闭任务内数据库连接，避免每轮 run_once 产生连接堆积。
            try:
                # 主动关闭当前任务实例持有的 UserDB 连接。
                self.user_db.close()
            # 关闭失败只记日志，不影响主流程。
            except Exception as exc:
                # 记录关闭异常，便于后续排查。
                self.log.exception("关闭任务内 user_db 失败", error=str(exc))
            # 非连接类异常时保留尾部等待；连接类异常由 worker 立即接管恢复。
            if (not should_reraise) and (not self._runtime_disconnect_detected):
                # 任务尾部等待 30 秒，给外部观察或下轮衔接留时间。
                sleep(30)
        # 连接类异常在任务收尾后继续抛出给 worker，触发统一恢复流程。
        # 当流程未成功且本轮检测到设备连接异常，但没有显式异常抛出时，也主动抛给 worker 做重建。
        if (not facebook_ok) and self._runtime_disconnect_detected and not should_reraise:
            # 打开继续抛出标记，触发 worker 侧 reinit_runtime。
            should_reraise = True
            # 构造可重试的连接异常对象，确保 worker 立即走重建分支。
            reraised_exc = ConnectionResetError(
                "TransportDisconnected: 检测到设备连接异常，已跳过 status=3 回写并请求 worker 重建运行时"
            )
        # 连接类异常在任务收尾后继续抛出给 worker，触发统一恢复流程。
        if should_reraise and reraised_exc is not None:
            # 继续抛出原始异常，保留完整类型和错误上下文。
            raise reraised_exc


# 保留模块级函数入口，统一通过 task_context 透传设备信息。
def run_once(task_context: TaskContext) -> None:
    # 创建任务类实例并执行一轮完整流程。
    OpenSettingsTask(task_context=task_context).run_once()
