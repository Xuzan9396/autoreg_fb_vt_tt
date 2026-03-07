# -*- encoding=utf8 -*-
# 声明源码编码为 UTF-8，保证中文和注释正常。
# 标记脚本作者。
__author__ = "admin"

# 导入垃圾回收模块，用于退出前主动回收代理对象。
import gc
# 导入 os 模块，用于读取环境变量控制输出级别。
import os
# 导入 sys 模块，用于读取命令行参数。
import sys
# 导入线程模块，用于给 stop_running 增加超时保护，避免退出卡死。
import threading
# 导入 traceback 模块，用于格式化异常信息。
import traceback
# 导入 Any 类型，便于做对象类型标注。
from typing import Any

# 导入在线设备查询方法，用于自动选设备。
from autovt.adb import list_online_serials
# 导入日志初始化方法，方便看调试日志。
from autovt.logs import setup_logging
# 导入创建 Poco 的方法，供任务方法使用。
from autovt.runtime import create_poco
# 导入获取 Poco 的方法，供退出时清理。
from autovt.runtime import get_poco
# 导入设备初始化方法，连接手机。
from autovt.runtime import setup_device
# 导入任务上下文对象，保持与 worker 调用一致。
from autovt.tasks.task_context import TaskContext
# 导入你要调试的方法所在任务类。
from autovt.tasks.open_settings import OpenSettingsTask

# 记录本进程是否创建过 Poco，避免无意义清理报错。
_POCO_CREATED = False
# 定义 Poco 停止等待超时秒数，避免 stop_running 长时间阻塞退出。
_POCO_STOP_TIMEOUT_SEC = 5.0
# 保存原始线程异常钩子，便于非目标异常时继续走默认处理。
_ORIGINAL_THREADING_EXCEPTHOOK = threading.excepthook


# 定义安全打印函数，避免 ASCII 控制台中文报错。
def safe_print(*args: object) -> None:
    # 把多个参数拼成一行文本。
    text = " ".join(str(arg) for arg in args)
    # 先尝试正常打印。
    try:
        # 输出完整文本。
        print(text)
    # 如果控制台编码不支持中文则进入降级分支。
    except UnicodeEncodeError:
        # 转成 ASCII 可显示格式。
        fallback = text.encode("ascii", errors="backslashreplace").decode("ascii")
        # 输出降级后的文本，保证脚本不中断。
        print(fallback)


# 定义“判断异常是否属于设备断开/运行时连接中断”的方法。
def is_disconnect_error(exc: BaseException) -> bool:
    # 提取异常详情并统一转小写，便于关键字匹配。
    detail = str(exc or "").strip().lower()
    # 常见断连关键字命中即视为连接中断。
    keywords = (
        "transportdisconnected",
        "connection refused",
        "max retries exceeded",
        "failed to establish a new connection",
        "broken pipe",
        "device not found",
        "adb: device",
        "adberror",
        "adbshellerror",
        "remote end closed connection",
        "connection aborted",
        "pocoservice",
        "127.0.0.1",
    )
    # 返回是否命中任意断连关键字。
    return any(keyword in detail for keyword in keywords)


# 定义“调试模式线程异常钩子”，屏蔽 Poco 后台线程的断连噪音。
def debug_threading_excepthook(args: threading.ExceptHookArgs) -> None:
    # 提取当前线程对象，便于输出线程名。
    thread_obj = getattr(args, "thread", None)
    # 提取线程名，缺失时回退 unknown。
    thread_name = getattr(thread_obj, "name", "unknown")
    # 提取线程异常对象。
    exc_value = getattr(args, "exc_value", None)
    # Poco 后台保活线程在设备断开时常见无意义长堆栈，这里改成简短提示。
    if exc_value is not None and is_disconnect_error(exc_value):
        # 输出简短提示，说明这是设备断开导致的后台线程退出，不再打印整段 Traceback。
        safe_print("检测到后台线程连接已断开，按设备断开处理并忽略线程堆栈。", "thread:", thread_name, "error:", exc_value)
        # 直接返回，阻止默认线程异常打印。
        return
    # 非断连异常仍走 Python 默认线程异常处理，避免吞掉真实 bug。
    _ORIGINAL_THREADING_EXCEPTHOOK(args)


# 定义设备号解析方法，默认自动选择第一台在线设备。
def resolve_serial() -> str:
    # 读取当前 adb 在线设备列表。
    serials = list_online_serials()
    # 如果没有在线设备。
    if not serials:
        # 抛出明确错误提示。
        raise RuntimeError("未检测到在线设备，请先连接手机并确认 adb devices 可见")
    # 如果有多台设备在线。
    if len(serials) > 1:
        # 打印提醒信息。
        safe_print("检测到多台设备，默认使用第一台:", serials[0])
    # 返回第一台设备作为调试目标。
    return serials[0]


# 定义语言归一化方法，统一多来源 locale 格式。
def normalize_locale(raw: str) -> str:
    # 清理空格和换行，避免误判空值。
    value = (raw or "").strip()
    # 空值或无效占位值统一视为 unknown。
    if not value or value.lower() in {"null", "none"}:
        # 返回 unknown 表示本次没有识别到有效语言。
        return "unknown"
    # 把 en_US 统一转换成 en-US。
    value = value.replace("_", "-")
    # 如果系统返回多语言串（例如 en-US,zh-CN）。
    if "," in value:
        # 只取第一项主语言并去掉空格。
        value = value.split(",", 1)[0].strip()
    # 返回标准化后的语言值。
    return value


# 定义设备语言读取方法，拿不到有效值就直接抛错。
def read_device_locale() -> str:
    # 延迟导入 device，避免模块导入阶段触发额外副作用。
    from airtest.core.api import device

    # 从当前 Airtest 连接设备中获取 adb 客户端。
    adb = device().adb
    # 按兼容顺序尝试多个系统字段读取语言。
    candidates = [
        # Android 新版多语言字段。
        "settings get system system_locales",
        # 常见 ROM 持久化语言字段。
        "getprop persist.sys.locale",
        # 部分设备只读语言字段。
        "getprop ro.product.locale",
    ]
    # 逐个命令尝试读取。
    for cmd in candidates:
        # 执行 adb shell 并清理结果文本。
        raw = str(adb.shell(cmd)).strip()
        # 对读取结果做统一归一化。
        locale = normalize_locale(raw)
        # 一旦识别到有效语言立即返回。
        if locale != "unknown":
            # 打印命中语言和来源命令。
            safe_print("识别到设备语言:", locale, "来源命令:", cmd)
            # 返回有效语言值。
            return locale
    # 三个字段都失败时直接抛错阻断。
    raise RuntimeError("读取设备语言失败，TaskContext 必须包含有效 device_locale/device_lang")


# 定义整数参数解析方法（用于可选方法参数）。
def parse_int_arg(index: int, default_value: int) -> int:
    # 如果命令行没有这个位置的参数。
    if len(sys.argv) <= index:
        # 返回默认值。
        return default_value
    # 尝试把参数转成整数。
    try:
        # 转换成功则返回整数。
        return int(sys.argv[index])
    # 转换失败进入异常分支。
    except ValueError as exc:
        # 抛出可读错误。
        raise RuntimeError(f"参数位置 {index} 需要整数，当前值: {sys.argv[index]}") from exc


# 定义方法分发器，根据方法名调用目标方法。
def run_target_method(task: OpenSettingsTask, method_name: str) -> None:
    # 默认或 all 都执行完整单轮。
    if method_name in {"run_once", "all"}:
        # 执行完整流程一次。
        task.run_once()
        # 当前分支结束后返回。
        return
    # 只跑清理方法。
    if method_name == "clear_all":
        # 执行一次清理流程。
        task.clear_all()
        # 当前分支结束后返回。
        return
    # 只跑抹机王全流程。
    if method_name == "mojiwang_run_all":
        # 执行抹机王方法。
        task.mojiwang_run_all()
        # 当前分支结束后返回。
        return

    # 只跑 Facebook 全流程。
    if method_name == "facebook_run_all":
        # 执行 Facebook 方法。
        task.facebook_run_all()
        # 当前分支结束后返回。
        return

    if method_name == "facebook_select_img":
        # 执行 Facebook 选择图片方法。
        task.facebook_select_img()
        # 当前分支结束后返回。
        return

    if method_name == "facebook_again_upload":
        # 执行 Facebook 再次上传方法。
        task.facebook_again_upload()
        # 当前分支结束后返回。
        return

    # 只跑抹机王某一轮。
    if method_name == "mojiwang_run_one_loop":
        # 读取第2个参数作为 loop_index，默认 0。
        loop_index = parse_int_arg(2, 0)
        # 执行指定轮次。
        task.mojiwang_run_one_loop(loop_index)
        # 当前分支结束后返回。
        return
    # 只跑 Nekobox 方法。
    if method_name == "nekobox_run_all":
        # 读取第2个参数作为 mode_index，默认 0（动态）。
        mode_index = parse_int_arg(2, 0)
        # 执行指定模式。
        # task.nekobox_run_all(mode_index)
        task.nekobox_run_all()
        # 当前分支结束后返回。
        return
    raise RuntimeError(
        "不支持的方法: "
        f"{method_name}，可用方法: run_once/all, clear_all, mojiwang_run_all, facebook_run_all, mojiwang_run_one_loop, nekobox_run_all"
    # 抛出可用方法列表，便于快速修正命令。
    )


# 定义带超时的 Poco 停止方法，避免退出阶段卡死。
def stop_poco_with_timeout(poco: Any, timeout_sec: float) -> None:
    # 保存线程内异常对象，主线程统一处理输出。
    error_holder: list[BaseException] = []
    # 用事件通知主线程 stop_running 是否执行结束。
    done_event = threading.Event()

    # 定义线程执行函数，隔离可能阻塞的 stop_running 调用。
    def runner() -> None:
        # 在线程中调用官方清理方法。
        try:
            # 停止 PocoService 保活线程并清理 adb forward。
            poco.stop_running()
        # 捕获 BaseException，确保 KeyboardInterrupt 也被接住。
        except BaseException as exc:
            # 记录异常对象，交由主线程输出友好提示。
            error_holder.append(exc)
        # 无论成功或失败都要通知主线程结束状态。
        finally:
            # 标记本次 stop_running 处理完成。
            done_event.set()

    # 创建后台守护线程执行停止逻辑。
    worker = threading.Thread(target=runner, name="poco-stop-running", daemon=True)
    # 启动 stop_running 线程。
    worker.start()
    # 按超时时间等待线程完成，防止主流程无限阻塞。
    finished = done_event.wait(timeout_sec)
    # 超时仍未完成说明 stop_running 可能卡在 adb shell。
    if not finished:
        # 输出超时提示，保证主程序可退出。
        safe_print("poco stop_running 超时，跳过等待:", timeout_sec, "秒")
        # 直接返回，避免主线程继续阻塞。
        return
    # 没有异常说明清理成功。
    if not error_holder:
        # 直接返回。
        return
    # 读取第一条异常作为代表输出。
    exc = error_holder[0]
    # 如果是中断信号。
    if isinstance(exc, KeyboardInterrupt):
        # 输出简短提示，避免打印长 Traceback。
        safe_print("poco stop_running 被中断，已跳过。")
        # 中断场景直接返回。
        return
    # 输出异常摘要，便于排查问题。
    safe_print("poco stop_running failed:", type(exc).__name__, str(exc))


# 定义退出清理方法，避免解释器关闭阶段出现代理析构噪音。
def cleanup_poco() -> None:
    # 如果本次没有创建 Poco。
    if not _POCO_CREATED:
        # 直接返回，不做清理。
        return
    # 尝试获取 Poco 实例。
    try:
        # 读取当前进程中的 Poco 对象。
        poco: Any = get_poco()
    # 如果获取失败。
    except Exception:
        # 直接返回，避免二次报错。
        return
    # 使用超时保护执行停止逻辑，避免退出时卡住。
    stop_poco_with_timeout(poco, timeout_sec=_POCO_STOP_TIMEOUT_SEC)
    # 主动触发垃圾回收，减少退出阶段噪音。
    gc.collect()


# 定义主函数，串起初始化、执行、清理流程。
def main() -> None:
    # 声明要修改模块级变量。
    global _POCO_CREATED
    # 安装调试专用线程异常钩子，避免 Poco 后台线程在断连时刷整段堆栈。
    threading.excepthook = debug_threading_excepthook
    # 默认不传参数时执行 run_once（全流程一次）。
    method_name = sys.argv[1] if len(sys.argv) > 1 else "run_once"
    # 自动选择调试设备 serial。
    serial = resolve_serial()
    # 初始化日志系统。
    setup_logging(process_role="debug", serial=serial)
    # 初始化设备连接。
    setup_device(serial=serial, script_file=__file__, log_subdir=f"debug/{serial}")
    # 创建 Poco 实例。
    create_poco()
    # 标记 Poco 已创建，允许退出时清理。
    _POCO_CREATED = True
    # 先读取当前设备语言，保证上下文是有效值。
    locale = read_device_locale()
    # 用 serial+locale 构建任务上下文对象。
    task_context = TaskContext.from_serial_locale(serial=serial, device_locale=locale)
    # 强制校验上下文必填字段，缺失时立即抛错停止调试。
    task_context.ensure_required()
    # 模拟填充一条用户信息，供任务方法使用。

    task_context.user_info = {
        # "email_account": "CynthiaPerkins8103@hotmail.com",
        # "email_access_key": "M.C550_BAY.0.U.-Chpeon3X278tmyyLw8y*nt62My6VzvDWKwyXkeZKLUsgEAoHe9hg!Xz*T1F4bNhyXX1d4M5N3S0nE0jFfJxDG99oPuL*hPaAz4bZVG20PDNFxkKiVMQBuOv0WS9BI07mBwbsGw09qB85z35DjThngE3qfowD93sTtN98TSPg8x0qqIou4CIFDWGdAFdixOs!vMsP8FNqtvVxZgUbBlhg6j!SUpySfdV6k11Rbh5pjYbu*ixKWVS2gZoPtGKtMOWBNQ!M9XB*A2MXHL2EMpgD5U*GQvOStlzw30WML3wTRys8O9cjncQx7Jhxe2UhrGnZz9m99sYV*aTu*R3wQJkRD476!YTbUDLYRdGaPbTqcmx!udJcMo1meZfpZkq7HneMw1MTqGqFJIpNR5Cx3A4cdsRnlyABGbRNlcZ4EYyr1LA3UiXwasTEZmWgXq2EwC5bLg$$",
        # "first_name": "Vernon","last_name": "Williams",

        "email_account": "NatalieMorton7264@hotmail.com",
        "email_access_key": "M.C554_BL2.0.U.-CoSgnVOa9mugvD!ky0wy3XVN4Z91XPAub1x3mIAHzTrEykMIykPNI*ABR2Ls37MuNAN5NtUZ9980tJdXbOnBDVaXv*At7YTsEUy92DSBWVSE4CuJerJu*drOKY8Q1xK0fZr!H0OpPCiOQObMdTDYcFRs6U50!**36Fqd*cqm1mPSNg7kSMKttTW9pUZt!u51DTVYLvYRshtulfIfIC*l2O8ekIAfh3dhIlIJyGpy7YzkaOr!!DGbPfkhn5CjwydXE*in7UbPTmPVoJBB2flVaCMcqFD5bpJwpPKDBOUJCY9mM!10m!*b6tPrEtM7nNbvygqzgSLtCrBfsZOobprrPr4OXMEQCeDpbuucJ!F1uFcCmwQZNQehYksztOy4Z5t2jOiCZlbvI9IupaNSfgUf0wmPCZAihEgiB1F7my75ufekQgW3dwU*EnzFbnlhE48VHA$$",
        "first_name": "Vera","last_name": "Wootton",

        "client_id": "9e5f94bc-e8a4-4e73-b8be-63364c29d753",
        "pwd": "Xz272511272511"}
    # 创建任务实例（统一通过上下文对象传参）。
    task = OpenSettingsTask(task_context=task_context)
    # 打印本次调试入口信息，确认设备和语言上下文。
    safe_print(
        "开始调试方法:",
        method_name,
        "serial:",
        task_context.serial,
        "locale:",
        task_context.device_locale,
        "lang:",
        task_context.device_lang,
    )
    # 执行目标方法。
    run_target_method(task, method_name)


# 定义全局兜底运行方法，统一处理未捕获异常并返回退出码。
def run_with_global_guard() -> int:
    # 进入主流程执行区。
    try:
        # 执行主函数。
        main()
        # 正常执行完成时返回 0。
        return 0
    # 捕获用户手动中断（Ctrl+C）。
    except KeyboardInterrupt:
        # 打印中断提示。
        safe_print("收到中断信号，程序已安全退出。")
        # 约定返回 130 表示被中断。
        return 130
    # 调试场景下，设备断开属于外部运行时中断，改成友好提示退出。
    except Exception as exc:
        # 设备断开时输出简短提示，不再走“程序异常退出”文案。
        if is_disconnect_error(exc):
            # 输出设备断开提示。
            safe_print("检测到设备连接已断开，调试流程结束。", type(exc).__name__, str(exc))
            # 返回 0，表示已按预期收尾退出。
            return 0
        # 非断连异常继续走原有异常提示链路。
        # 打印异常摘要。
        safe_print("程序异常退出:", type(exc).__name__, str(exc))
        # 读取是否显示详细堆栈的开关。
        show_traceback = os.getenv("AUTOVT_SHOW_TRACEBACK", "0").strip().lower() in {"1", "true", "yes"}
        # 开关开启时才打印完整堆栈，便于深度排查。
        if show_traceback:
            # 打印堆栈标题。
            safe_print("异常堆栈如下：")
            # 输出完整堆栈文本到终端。
            safe_print(traceback.format_exc())
        # 默认只给简短提示，避免初学场景输出过多信息。
        else:
            # 提示如何开启堆栈输出。
            safe_print("如需查看完整堆栈，请设置环境变量 AUTOVT_SHOW_TRACEBACK=1 后重试。")
        # 异常退出时返回非 0 退出码。
        return 1
    # 无论成功失败都执行清理。
    finally:
        # 执行 Poco 资源清理。
        cleanup_poco()
        # 恢复默认线程异常钩子，避免影响其他脚本。
        threading.excepthook = _ORIGINAL_THREADING_EXCEPTHOOK


# 脚本直接运行时进入这里。
if __name__ == "__main__":
    # 调用全局兜底方法并按退出码结束进程。
    sys.exit(run_with_global_guard())
