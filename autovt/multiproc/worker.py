from __future__ import annotations

import multiprocessing as mp
import queue
import time
import traceback
from collections.abc import Callable
from typing import Any

from autovt.adb import safe_path_part
from autovt.logs import apply_third_party_log_policy, get_logger, setup_logging
from autovt.settings import (
    WORKER_INIT_RETRY_DELAY_SEC,
    WORKER_MAX_CONSECUTIVE_UNKNOWN_ERRORS,
    WORKER_MAX_INIT_RETRIES,
    WORKER_RECOVER_RETRY_DELAY_SEC,
)
from autovt.tasks.task_context import TaskContext
from autovt.userdb import (
    STATUS_23_RETRY_MAX,
    STATUS_23_RETRY_MAX_DEFAULT,
    STATUS_23_RETRY_MAX_KEY,
    STATUS_23_RETRY_MIN,
    UserDB,
)


def _normalize_locale(raw: str) -> str:
    # 清理原始字符串，避免空格和换行干扰判断。
    value = (raw or "").strip()
    # 空值或无效占位值统一归一为 unknown。
    if not value or value.lower() in {"null", "none"}:
        # 返回 unknown，表示本次未识别出有效语言。
        return "unknown"
    # 把 en_US 这种下划线格式转换为 en-US 统一格式。
    value = value.replace("_", "-")
    # 如果是多语言串（例如 en-US,zh-CN），优先取第一项。
    if "," in value:
        # 截取第一个语言并清理空格。
        value = value.split(",", 1)[0].strip()
    # 返回归一化后的语言值。
    return value


def _read_device_locale(log) -> str:
    # 读取设备语言属于运行期能力，放到 try 里避免影响主流程。
    try:
        # 延迟导入 device，避免主进程加载 airtest 依赖。
        from airtest.core.api import device

        # 从当前进程已连接设备里拿到 adb 客户端。
        adb = device().adb
        # 依次尝试多个系统字段，提高不同 ROM 兼容性。
        candidates = [
            # Android 新版常用多语言字段。
            "settings get system system_locales",
            # 厂商 ROM 常见持久化字段。
            "getprop persist.sys.locale",
            # 部分设备只提供只读 locale 字段。
            "getprop ro.product.locale",
        ]
        # 逐个命令尝试读取语言。
        for cmd in candidates:
            # 执行 adb shell 并转成字符串结果。
            raw = str(adb.shell(cmd)).strip()
            # 对读取结果做标准化处理。
            locale = _normalize_locale(raw)
            # 命中有效语言时立即返回。
            if locale != "unknown":
                # 记录本次命中来源和语言值。
                log.info("识别到设备语言", locale=locale, cmd=cmd)
                # 返回识别到的语言。
                return locale
    # 读取中任意异常都降级为 unknown，不中断 worker。
    except Exception as exc:
        # 记录降级原因，便于排查。
        log.warning("读取设备语言失败，使用 unknown", error=str(exc))
    # 三个字段都未命中时记录提示日志。
    log.warning("未识别到有效设备语言，使用 unknown")
    # 返回 unknown 作为统一降级值。
    return "unknown"


def _build_task_context(
    serial: str,
    locale: str,
    user_info: dict[str, Any] | None = None,
    config_map: dict[str, str] | None = None,
) -> TaskContext:
    # 根据 serial + locale 构建任务上下文对象，并把 t_user/t_config 运行数据透传给任务层。
    ctx = TaskContext.from_serial_locale(serial=serial, device_locale=locale)
    ctx.user_info = dict(user_info or {})
    ctx.config_map = {str(k): str(v) for k, v in dict(config_map or {}).items()}
    return ctx


def _emit(queue_out: mp.Queue, serial: str, state: str, detail: str, **extra: Any) -> None:
    # 子进程把状态变化（ready/running/error/...）发回主进程。
    event = {
        "serial": serial,
        "state": state,
        "detail": detail,
        "time": time.time(),
    }
    if extra:
        # 允许附带扩展字段（例如 email_account），主进程可按需使用。
        event.update(extra)
    try:
        queue_out.put(event)
    except Exception:
        # 主进程退出或队列不可用时，避免子进程因上报失败崩溃。
        pass


def _sleep_with_stop(stop_event: mp.Event, sec: float) -> None:
    # 可中断 sleep：每 0.1 秒检查一次 stop_event，保证能快速停机。
    end_at = time.time() + max(0.0, sec)
    while not stop_event.is_set() and time.time() < end_at:
        time.sleep(0.1)


def _read_status_23_retry_limit(config_map: dict[str, str]) -> int:
    # 从 t_config 映射读取“status=2/3 同账号最大重试次数”配置，并做 0~5 边界保护。
    # 读取配置原始值，缺失时回退默认值 0。
    raw_value = str(config_map.get(STATUS_23_RETRY_MAX_KEY, STATUS_23_RETRY_MAX_DEFAULT)).strip()
    # 尝试解析整数。
    try:
        # 转成整数，便于后续范围校验。
        parsed_value = int(raw_value)
    # 非法值（如空串或非数字）时回退默认值。
    except Exception:
        # 返回默认值 0（不重试）。
        return int(STATUS_23_RETRY_MAX_DEFAULT)
    # 小于最小值时回退下限。
    if parsed_value < STATUS_23_RETRY_MIN:
        # 返回最小值 0。
        return STATUS_23_RETRY_MIN
    # 大于最大值时截断到上限。
    if parsed_value > STATUS_23_RETRY_MAX:
        # 返回最大值 5。
        return STATUS_23_RETRY_MAX
    # 返回合法重试次数。
    return parsed_value


def _is_retryable_runtime_error(exc: Exception, airtest_errors: dict[str, Any]) -> bool:
    # StopIteration: 常见于 javacap 流中断，通常可通过重连恢复。
    if isinstance(exc, StopIteration):
        return True
    # 常见 IO/连接中断错误。
    if isinstance(exc, (ConnectionResetError, BrokenPipeError, TimeoutError, OSError)):
        return True

    # Airtest 设备连接类错误。
    retryable_names = (
        "AdbError",
        "AdbShellError",
        "DeviceConnectionError",
        "NoDeviceError",
        "ScreenError",
        "MinicapError",
        "MinitouchError",
    )
    for name in retryable_names:
        cls = airtest_errors.get(name)
        if cls and isinstance(exc, cls):
            return True
    return False


def _is_target_not_found(exc: Exception, airtest_errors: dict[str, Any]) -> bool:
    # 识图未找到属于业务可预期错误，单独处理即可。
    cls = airtest_errors.get("TargetNotFoundError")
    return bool(cls and isinstance(exc, cls))


def _is_fatal_poco_error(exc: Exception) -> bool:
    # Poco 实例不可用（未初始化/为空/不存在）属于配置级错误，直接停止子进程。
    if not isinstance(exc, RuntimeError):
        return False
    detail = str(exc)
    # 只对明确包含 Poco 的错误文案触发致命停止，避免误伤其他 RuntimeError。
    return "Poco" in detail and any(token in detail for token in ("未初始化", "为空", "不存在"))


def _is_fatal_task_context_error(exc: Exception) -> bool:
    # TaskContext 缺少必填字段属于配置级错误，应该直接停止子进程避免空转。
    if not isinstance(exc, RuntimeError):
        return False
    detail = str(exc)
    return "TaskContext" in detail and "缺少必填字段" in detail


def _load_airtest_error_types() -> dict[str, Any]:
    """
    延迟加载 Airtest 错误类型。
    这样 manager 进程导入 worker 模块时不会强依赖 airtest。
    """
    try:
        from airtest.core.error import (  # type: ignore
            AdbError,
            AdbShellError,
            DeviceConnectionError,
            MinicapError,
            MinitouchError,
            NoDeviceError,
            ScreenError,
            TargetNotFoundError,
        )
    except Exception:
        return {}

    return {
        "AdbError": AdbError,
        "AdbShellError": AdbShellError,
        "DeviceConnectionError": DeviceConnectionError,
        "NoDeviceError": NoDeviceError,
        "ScreenError": ScreenError,
        "MinicapError": MinicapError,
        "MinitouchError": MinitouchError,
        "TargetNotFoundError": TargetNotFoundError,
    }


def _init_runtime_with_retry(
    *,
    serial: str,
    stop_event: mp.Event,
    event_queue: mp.Queue,
    log,
    setup_device: Callable[..., None],
    create_poco: Callable[[], None],
) -> bool:
    """
    初始化运行时，支持重试。
    返回 True 表示初始化完成，False 表示被 stop 打断。
    """
    attempt = 0
    while not stop_event.is_set():
        attempt += 1
        try:
            # Airtest import 时会把 logger 调到 DEBUG，这里每次初始化前都回压一次。
            airtest_debug = apply_third_party_log_policy()
            log.info("已应用第三方日志策略", airtest_debug=airtest_debug, attempt=attempt)

            setup_device(
                serial=serial,
                script_file=__file__,
                log_subdir=f"workers/{safe_path_part(serial)}",
            )
            create_poco()

            _emit(event_queue, serial, "ready", "初始化完成")
            log.info("运行时初始化成功", serial=serial, attempt=attempt)
            return True
        except KeyboardInterrupt:
            # Ctrl+C 传到子进程时，优雅退出，避免 traceback 污染日志。
            _emit(event_queue, serial, "stopping", "收到 KeyboardInterrupt")
            log.warning("初始化阶段收到 KeyboardInterrupt，准备退出")
            stop_event.set()
            return False
        except Exception as exc:
            detail = "".join(traceback.format_exception_only(type(exc), exc)).strip()
            _emit(event_queue, serial, "recovering", f"初始化失败: {detail}")
            log.error("运行时初始化失败", serial=serial, attempt=attempt, error=detail)

            if WORKER_MAX_INIT_RETRIES > 0 and attempt >= WORKER_MAX_INIT_RETRIES:
                _emit(
                    event_queue,
                    serial,
                    "fatal",
                    f"初始化连续失败 {attempt} 次，超过上限，停止 worker",
                )
                log.error(
                    "初始化超过最大重试次数，worker 将退出",
                    max_retries=WORKER_MAX_INIT_RETRIES,
                )
                return False

            _sleep_with_stop(stop_event, WORKER_INIT_RETRY_DELAY_SEC)
    return False


def _handle_run_error(
    *,
    exc: Exception,
    serial: str,
    event_queue: mp.Queue,
    stop_event: mp.Event,
    log,
    airtest_errors: dict[str, Any],
    reinit_runtime: Callable[[], bool],
) -> tuple[str, int]:
    """
    运行期错误分类处理。
    返回 (action, unknown_delta)：
    - action: continue/recover/stop
    - unknown_delta: 未知错误计数增量
    """
    detail = "".join(traceback.format_exception_only(type(exc), exc)).strip()

    if _is_fatal_task_context_error(exc):
        _emit(event_queue, serial, "fatal", f"任务上下文无效，停止 worker: {detail}")
        log.error("任务上下文无效，停止 worker", error=detail)
        stop_event.set()
        return "stop", 0

    if _is_fatal_poco_error(exc):
        _emit(event_queue, serial, "fatal", f"Poco 不可用，停止 worker: {detail}")
        log.error("Poco 不可用，停止 worker", error=detail)
        stop_event.set()
        return "stop", 0

    if _is_target_not_found(exc, airtest_errors):
        _emit(event_queue, serial, "warning", f"目标未找到: {detail}")
        log.warning("目标未找到（业务错误）", error=detail)
        return "continue", 0

    if _is_retryable_runtime_error(exc, airtest_errors):
        _emit(event_queue, serial, "recovering", f"可恢复错误，准备重连: {detail}")
        log.warning("可恢复运行时错误，开始重初始化", error=detail)
        ok = reinit_runtime()
        if not ok:
            # stop_event 可能已被置位，交由外层退出。
            return "stop", 0
        _sleep_with_stop(stop_event, WORKER_RECOVER_RETRY_DELAY_SEC)
        return "recover", 0

    # 未知错误：先记录，但不立即退出。
    _emit(event_queue, serial, "error", f"未知错误: {detail}")
    log.exception("未知运行时错误")
    return "continue", 1


def worker_main(
    serial: str,
    loop_interval_sec: float,
    stop_event: mp.Event,
    command_queue: mp.Queue,
    event_queue: mp.Queue,
) -> None:
    """
    单设备子进程入口。
    每个子进程只负责一台手机，避免线程共享全局状态导致冲突。
    """
    # 每个子进程单独初始化日志（单独文件 + 终端 JSON）。
    setup_logging(process_role="worker", serial=serial)
    log = get_logger("worker")
    log.info("worker 进程启动", serial=serial, loop_interval_sec=loop_interval_sec)

    # 子进程内独立数据库连接：用于原子分配 t_user、读取 t_config 映射。
    user_db = UserDB()
    user_db.connect()

    # 延迟导入运行时模块，避免主控进程被设备依赖拖住。
    from autovt.runtime import create_poco, setup_device

    # 导入“单轮任务函数”，worker 通过循环重复调用它。
    from autovt.tasks.open_settings import run_once

    # 延迟加载 Airtest 异常类型映射。
    airtest_errors = _load_airtest_error_types()
    # 子进程内缓存任务上下文对象。
    task_context = _build_task_context(serial=serial, locale="unknown")

    # 当前设备绑定的一条账号记录。
    assigned_user: dict[str, Any] | None = None
    # 记录当前账号在 status=2/3 下已执行的重试次数。
    assigned_status_23_retry_count = 0
    # 标记是否处于“无可用账号等待中”，避免重复刷屏日志。
    waiting_for_user = False

    def _ensure_assigned_user(config_map: dict[str, str]) -> dict[str, Any] | None:
        """确保当前设备拿到一条可运行账号（status=1），并支持 status=2/3 同账号重试。"""
        nonlocal assigned_user, assigned_status_23_retry_count

        # 读取 status=2/3 同账号最大重试次数配置。
        retry_limit = _read_status_23_retry_limit(config_map)

        # 优先刷新当前内存账号，避免每轮重复抢占。
        if assigned_user is not None:
            # 读取当前内存账号主键。
            user_id = int(assigned_user.get("id", 0))
            # 从数据库读取最新账号状态。
            latest = user_db.get_user_by_id(user_id) if user_id > 0 else None
            # 账号仍绑定到当前设备时继续判断状态。
            if latest is not None and str(latest.get("device", "")).strip() == serial:
                # 读取数据库中的最新 status。
                current_status = int(latest.get("status", 0))
                # 读取邮箱用于日志追踪。
                email_account = str(latest.get("email_account", "")).strip()
                # status=1 表示“仍在使用中”，继续跑同一个账号，不切换。
                if current_status == 1:
                    # 更新本地缓存为最新记录。
                    assigned_user = dict(latest)
                    # 回到运行中时清空 2/3 重试计数。
                    assigned_status_23_retry_count = 0
                    # 返回当前账号，继续执行任务。
                    return assigned_user
                # status=2/3 时按配置决定是否继续同账号重试。
                if current_status in {2, 3}:
                    # 未超过最大重试次数时继续复用同账号。
                    if assigned_status_23_retry_count < retry_limit:
                        # 进入一次新的重试轮次并累加计数。
                        assigned_status_23_retry_count += 1
                        # 更新本地缓存为最新记录。
                        assigned_user = dict(latest)
                        # 记录“同账号重试”日志，便于排查。
                        log.info(
                            "账号状态为 2/3，继续复用当前账号重试",
                            serial=serial,
                            user_id=user_id,
                            status=current_status,
                            email_account=email_account,
                            retry_index=assigned_status_23_retry_count,
                            retry_limit=retry_limit,
                        )
                        # 返回当前账号，让任务继续重试。
                        return assigned_user
                    # 重试达到上限时释放设备绑定，准备切换新账号。
                    user_db.clear_device_by_user_id(user_id)
                    # 记录释放日志，明确为什么切账号。
                    log.info(
                        "账号状态为 2/3 且重试已达上限，释放设备绑定",
                        serial=serial,
                        user_id=user_id,
                        status=current_status,
                        email_account=email_account,
                        retry_count=assigned_status_23_retry_count,
                        retry_limit=retry_limit,
                    )
                    # 清空当前账号缓存。
                    assigned_user = None
                    # 清空当前账号的重试计数。
                    assigned_status_23_retry_count = 0
                # 其他状态视为不可运行，释放绑定后重新分配。
                else:
                    # 清空设备绑定，避免遗留占用。
                    user_db.clear_device_by_user_id(user_id)
                    log.info(
                        "当前账号状态不可运行，释放设备绑定",
                        serial=serial,
                        user_id=user_id,
                        status=current_status,
                        email_account=email_account,
                    )
                    # 清空当前账号缓存。
                    assigned_user = None
                    # 清空重试计数。
                    assigned_status_23_retry_count = 0
            # 当前缓存账号已不在本设备上，清空本地缓存并重新领取。
            else:
                # 清空当前账号缓存。
                assigned_user = None
                # 清空重试计数，避免串到下一条账号。
                assigned_status_23_retry_count = 0

        # 兜底：检查数据库里是否仍有绑定到本设备的账号（可能来自进程重启恢复）。
        # 按设备反查当前绑定账号。
        bound_row = user_db.get_user_by_device(serial)
        # 存在绑定账号时按状态分支处理。
        if bound_row is not None:
            # 读取绑定账号主键。
            bound_user_id = int(bound_row.get("id", 0))
            # 读取绑定账号状态。
            bound_status = int(bound_row.get("status", 0))
            # 读取绑定邮箱用于日志追踪。
            bound_email = str(bound_row.get("email_account", "")).strip()
            # 绑定且运行中时直接复用。
            if bound_status == 1:
                # 写回当前账号缓存。
                assigned_user = dict(bound_row)
                # 清空 2/3 重试计数。
                assigned_status_23_retry_count = 0
                # 返回绑定账号。
                return assigned_user
            # 绑定账号处于 2/3 状态时按配置决定是否继续同账号重试。
            if bound_status in {2, 3}:
                # 未超过上限则继续同账号重试。
                if assigned_status_23_retry_count < retry_limit:
                    # 累加重试次数。
                    assigned_status_23_retry_count += 1
                    # 写回当前账号缓存。
                    assigned_user = dict(bound_row)
                    log.info(
                        "发现设备绑定账号处于 2/3，继续复用当前账号重试",
                        serial=serial,
                        user_id=bound_user_id,
                        status=bound_status,
                        email_account=bound_email,
                        retry_index=assigned_status_23_retry_count,
                        retry_limit=retry_limit,
                    )
                    # 返回绑定账号进入重试。
                    return assigned_user
                # 达上限后释放绑定，允许分配新账号。
                user_db.clear_device_by_user_id(bound_user_id)
                log.info(
                    "设备绑定账号处于 2/3 且重试达上限，释放绑定等待新账号",
                    serial=serial,
                    user_id=bound_user_id,
                    status=bound_status,
                    email_account=bound_email,
                    retry_count=assigned_status_23_retry_count,
                    retry_limit=retry_limit,
                )
                # 重试结束后重置计数器。
                assigned_status_23_retry_count = 0
                # 清空账号缓存，进入新分配流程。
                assigned_user = None
            # 非 1/2/3 状态绑定视为遗留，先清掉 device 再参与新分配。
            else:
                # 清理遗留绑定。
                user_db.clear_device_by_user_id(bound_user_id)
                log.info(
                    "清理设备遗留绑定",
                    serial=serial,
                    user_id=bound_user_id,
                    status=bound_status,
                    email_account=bound_email,
                )
                # 清空计数器。
                assigned_status_23_retry_count = 0
                # 清空缓存。
                assigned_user = None

        # 核心分配：事务加锁领取一条 status=0 的账号，并置为 status=1 + device=serial。
        # 尝试领取一条未使用账号。
        assigned_user = user_db.claim_user_for_device(serial)
        # 没有可分配账号时返回空，让上层进入等待态。
        if assigned_user is None:
            return None
        # 把 sqlite Row 转成字典缓存。
        assigned_user = dict(assigned_user)
        # 新账号分配成功后重置重试计数。
        assigned_status_23_retry_count = 0
        # 返回新分配账号。
        return assigned_user

    def _prepare_task_context() -> TaskContext | None:
        """为本轮执行准备任务上下文：注入一条 t_user + 全量 t_config 映射。"""
        nonlocal waiting_for_user, task_context

        try:
            # 读取 t_config 全量 key->val 映射（内部会补默认值）。
            config_map = user_db.get_config_map()
        except Exception as exc:
            # 配置读取失败时回退默认值，保证 worker 不中断。
            config_map = {
                "mojiwang_run_num": "3",
                STATUS_23_RETRY_MAX_KEY: STATUS_23_RETRY_MAX_DEFAULT,
            # 回退默认配置，确保任务循环可继续运行。
            }
            log.exception("读取 t_config 失败，使用默认配置", error=str(exc), fallback_config=config_map)

        # 结合配置（含重试次数）拿到当前可运行账号。
        current_user = _ensure_assigned_user(config_map)
        # 无可用账号时进入等待态，不执行任务。
        if current_user is None:
            if not waiting_for_user:
                _emit(event_queue, serial, "waiting", "无可用账号(status=0) 或重试结束，等待中")
                log.info("无可用账号(status=0) 或重试结束，worker 进入等待", serial=serial)
            waiting_for_user = True
            return None

        # 把最新账号数据和配置映射写回任务上下文。
        task_context.user_info = dict(current_user)
        task_context.config_map = {str(k): str(v) for k, v in config_map.items()}

        email_account = str(current_user.get("email_account", "")).strip()
        # 从等待态恢复时上报一次“已拿到账号”。
        if waiting_for_user:
            _emit(event_queue, serial, "running", f"已分配账号: {email_account or '-'}", email_account=email_account)
            log.info("等待结束，已分配账号", serial=serial, email_account=email_account)
        waiting_for_user = False
        return task_context

    def reinit_runtime() -> bool:
        # 需要修改外层 task_context 缓存变量。
        nonlocal task_context
        ok = _init_runtime_with_retry(
            serial=serial,
            stop_event=stop_event,
            event_queue=event_queue,
            log=log,
            setup_device=setup_device,
            create_poco=create_poco,
        )
        # 只有初始化成功时才读取一次设备语言。
        if ok:
            # 读取本设备当前语言。
            locale = _read_device_locale(log)
            task_context = _build_task_context(
                serial=serial,
                locale=locale,
                user_info=task_context.user_info,
                config_map=task_context.config_map,
            # 更新子进程上下文缓存，保留账号和配置信息。
            )
            # 严格校验上下文字段，缺失时直接判定为致命错误并停止子进程。
            try:
                # 强制要求 serial/device_locale/device_lang 都是有效值。
                task_context.ensure_required()
            # 校验失败时进入致命分支。
            except Exception as exc:
                # 格式化异常摘要便于日志和事件上报。
                detail = "".join(traceback.format_exception_only(type(exc), exc)).strip()
                # 向主进程上报 fatal 状态。
                _emit(event_queue, serial, "fatal", f"任务上下文无效，停止 worker: {detail}")
                # 记录上下文校验失败详情，便于快速定位问题。
                log.error(
                    "任务上下文校验失败，停止 worker",
                    serial=task_context.serial,
                    device_locale=task_context.device_locale,
                    device_lang=task_context.device_lang,
                    error=detail,
                )
                # 设置停止信号，通知主循环尽快退出。
                stop_event.set()
                # 返回 False，调用方会走 worker 退出路径。
                return False
            # 打日志确认上下文缓存变更。
            log.info(
                "worker 任务上下文已更新",
                serial=task_context.serial,
                device_locale=task_context.device_locale,
                device_lang=task_context.device_lang,
            )
        return ok

    # 启动时先初始化运行时。
    if not reinit_runtime():
        _emit(event_queue, serial, "stopped", "初始化失败或被停止")
        log.warning("worker 启动失败，直接退出")
        try:
            user_db.close()
        except Exception:
            pass
        return

    paused = False
    unknown_error_count = 0

    try:
        # 主循环：直到收到 stop。
        while not stop_event.is_set():
            # 先处理控制命令（stop/pause/resume/run_once）。
            while True:
                try:
                    command = command_queue.get_nowait()
                except queue.Empty:
                    break
                except (EOFError, OSError) as exc:
                    # 命令队列异常时不崩溃，直接进入恢复逻辑。
                    detail = "".join(traceback.format_exception_only(type(exc), exc)).strip()
                    _emit(event_queue, serial, "recovering", f"命令队列异常: {detail}")
                    log.error("命令队列异常", error=detail)
                    if not reinit_runtime():
                        stop_event.set()
                        break
                    continue

                if command == "stop":
                    stop_event.set()
                    _emit(event_queue, serial, "stopping", "收到 stop 命令")
                    log.info("收到 stop 命令")
                    break

                if command == "pause":
                    paused = True
                    _emit(event_queue, serial, "paused", "已暂停")
                    log.info("worker 已暂停")
                    continue

                if command == "resume":
                    paused = False
                    _emit(event_queue, serial, "running", "已恢复")
                    log.info("worker 已恢复")
                    continue

                if command == "run_once":
                    # 手动执行前先准备账号和配置上下文。
                    runtime_context = _prepare_task_context()
                    # 无可用账号时不执行任务。
                    if runtime_context is None:
                        continue

                    email_account = str(runtime_context.user_info.get("email_account", "")).strip()
                    try:
                        run_once(task_context=runtime_context)
                        _emit(event_queue, serial, "running", f"手动执行 1 轮完成 | email={email_account or '-'}", email_account=email_account)
                        log.info(
                            "手动执行一轮任务完成",
                            serial=runtime_context.serial,
                            device_locale=runtime_context.device_locale,
                            device_lang=runtime_context.device_lang,
                            email_account=email_account,
                        )
                        unknown_error_count = 0
                    except KeyboardInterrupt:
                        _emit(event_queue, serial, "stopping", "手动执行时收到 KeyboardInterrupt")
                        log.warning("手动执行时收到 KeyboardInterrupt，准备退出")
                        stop_event.set()
                        break
                    except Exception as exc:
                        action, unknown_delta = _handle_run_error(
                            exc=exc,
                            serial=serial,
                            event_queue=event_queue,
                            stop_event=stop_event,
                            log=log,
                            airtest_errors=airtest_errors,
                            reinit_runtime=reinit_runtime,
                        )
                        unknown_error_count += unknown_delta
                        if action == "stop":
                            stop_event.set()
                            break
                    continue

                _emit(event_queue, serial, "unknown", f"未知命令: {command}")
                log.warning("收到未知命令", command=command)

            if stop_event.is_set():
                break

            if paused:
                _sleep_with_stop(stop_event, 0.2)
                continue

            # 自动轮询执行前先准备账号和配置上下文。
            runtime_context = _prepare_task_context()
            # 无可用账号时等待下一轮，不执行任务。
            if runtime_context is None:
                _sleep_with_stop(stop_event, loop_interval_sec)
                continue

            email_account = str(runtime_context.user_info.get("email_account", "")).strip()
            try:
                run_once(task_context=runtime_context)
                _emit(event_queue, serial, "running", f"自动执行 1 轮完成 | email={email_account or '-'}", email_account=email_account)
                log.info(
                    "自动执行一轮任务完成",
                    serial=runtime_context.serial,
                    device_locale=runtime_context.device_locale,
                    device_lang=runtime_context.device_lang,
                    email_account=email_account,
                )
                unknown_error_count = 0
            except KeyboardInterrupt:
                _emit(event_queue, serial, "stopping", "自动执行时收到 KeyboardInterrupt")
                log.warning("自动执行时收到 KeyboardInterrupt，准备退出")
                stop_event.set()
                break
            except Exception as exc:
                action, unknown_delta = _handle_run_error(
                    exc=exc,
                    serial=serial,
                    event_queue=event_queue,
                    stop_event=stop_event,
                    log=log,
                    airtest_errors=airtest_errors,
                    reinit_runtime=reinit_runtime,
                )
                unknown_error_count += unknown_delta

                # 未知错误连续触发过多时，主动做一次全量重初始化再继续。
                if unknown_error_count >= WORKER_MAX_CONSECUTIVE_UNKNOWN_ERRORS:
                    _emit(
                        event_queue,
                        serial,
                        "recovering",
                        f"连续未知错误达到阈值 {WORKER_MAX_CONSECUTIVE_UNKNOWN_ERRORS}，准备重初始化",
                    )
                    log.error(
                        "连续未知错误达到阈值，执行重初始化",
                        unknown_error_count=unknown_error_count,
                    )
                    unknown_error_count = 0
                    if not reinit_runtime():
                        stop_event.set()
                        break

                if action == "stop":
                    stop_event.set()
                    break

            _sleep_with_stop(stop_event, loop_interval_sec)
    except KeyboardInterrupt:
        # 兜底捕获，防止 Ctrl+C 在子进程打印长 traceback。
        _emit(event_queue, serial, "stopping", "worker 主循环收到 KeyboardInterrupt")
        log.warning("worker 主循环收到 KeyboardInterrupt")
    except BaseException:
        # 最外层兜底，确保任何未预期异常都不会直接爆栈退出。
        _emit(event_queue, serial, "fatal", "worker 遇到未捕获致命异常")
        log.exception("worker 未捕获致命异常")
    finally:
        # 退出前释放本设备占用账号：status=1 回退 0；status=2/3 保持不变，仅清空 device。
        try:
            released = user_db.release_user_for_device(serial)
            if released > 0:
                log.info("worker 退出前已释放设备占用账号", serial=serial, released=released)
        except Exception as exc:
            log.exception("worker 退出释放设备占用账号失败", serial=serial, error=str(exc))
        try:
            user_db.close()
        except Exception:
            log.exception("worker 关闭 user_db 失败", serial=serial)

        _emit(event_queue, serial, "stopped", "子进程已退出")
        log.info("worker 已退出")
