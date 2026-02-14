# -*- encoding=utf8 -*-  # 声明源码编码为 UTF-8，保证中文和注释正常。
__author__ = "admin"  # 标记脚本作者。

import gc  # 导入垃圾回收模块，用于退出前主动回收代理对象。
import os  # 导入 os 模块，用于读取环境变量控制输出级别。
import sys  # 导入 sys 模块，用于读取命令行参数。
import traceback  # 导入 traceback 模块，用于格式化异常信息。
from typing import Any  # 导入 Any 类型，便于做对象类型标注。

from autovt.adb import list_online_serials  # 导入在线设备查询方法，用于自动选设备。
from autovt.logs import setup_logging  # 导入日志初始化方法，方便看调试日志。
from autovt.runtime import create_poco  # 导入创建 Poco 的方法，供任务方法使用。
from autovt.runtime import get_poco  # 导入获取 Poco 的方法，供退出时清理。
from autovt.runtime import setup_device  # 导入设备初始化方法，连接手机。
from autovt.tasks.task_context import TaskContext  # 导入任务上下文对象，保持与 worker 调用一致。
from autovt.tasks.open_settings import OpenSettingsTask  # 导入你要调试的方法所在任务类。

_POCO_CREATED = False  # 记录本进程是否创建过 Poco，避免无意义清理报错。


def safe_print(*args: object) -> None:  # 定义安全打印函数，避免 ASCII 控制台中文报错。
    text = " ".join(str(arg) for arg in args)  # 把多个参数拼成一行文本。
    try:  # 先尝试正常打印。
        print(text)  # 输出完整文本。
    except UnicodeEncodeError:  # 如果控制台编码不支持中文则进入降级分支。
        fallback = text.encode("ascii", errors="backslashreplace").decode("ascii")  # 转成 ASCII 可显示格式。
        print(fallback)  # 输出降级后的文本，保证脚本不中断。


def resolve_serial() -> str:  # 定义设备号解析方法，默认自动选择第一台在线设备。
    serials = list_online_serials()  # 读取当前 adb 在线设备列表。
    if not serials:  # 如果没有在线设备。
        raise RuntimeError("未检测到在线设备，请先连接手机并确认 adb devices 可见")  # 抛出明确错误提示。
    if len(serials) > 1:  # 如果有多台设备在线。
        safe_print("检测到多台设备，默认使用第一台:", serials[0])  # 打印提醒信息。
    return serials[0]  # 返回第一台设备作为调试目标。


def normalize_locale(raw: str) -> str:  # 定义语言归一化方法，统一多来源 locale 格式。
    value = (raw or "").strip()  # 清理空格和换行，避免误判空值。
    if not value or value.lower() in {"null", "none"}:  # 空值或无效占位值统一视为 unknown。
        return "unknown"  # 返回 unknown 表示本次没有识别到有效语言。
    value = value.replace("_", "-")  # 把 en_US 统一转换成 en-US。
    if "," in value:  # 如果系统返回多语言串（例如 en-US,zh-CN）。
        value = value.split(",", 1)[0].strip()  # 只取第一项主语言并去掉空格。
    return value  # 返回标准化后的语言值。


def read_device_locale() -> str:  # 定义设备语言读取方法，拿不到有效值就直接抛错。
    from airtest.core.api import device  # 延迟导入 device，避免模块导入阶段触发额外副作用。

    adb = device().adb  # 从当前 Airtest 连接设备中获取 adb 客户端。
    candidates = [  # 按兼容顺序尝试多个系统字段读取语言。
        "settings get system system_locales",  # Android 新版多语言字段。
        "getprop persist.sys.locale",  # 常见 ROM 持久化语言字段。
        "getprop ro.product.locale",  # 部分设备只读语言字段。
    ]
    for cmd in candidates:  # 逐个命令尝试读取。
        raw = str(adb.shell(cmd)).strip()  # 执行 adb shell 并清理结果文本。
        locale = normalize_locale(raw)  # 对读取结果做统一归一化。
        if locale != "unknown":  # 一旦识别到有效语言立即返回。
            safe_print("识别到设备语言:", locale, "来源命令:", cmd)  # 打印命中语言和来源命令。
            return locale  # 返回有效语言值。
    raise RuntimeError("读取设备语言失败，TaskContext 必须包含有效 device_locale/device_lang")  # 三个字段都失败时直接抛错阻断。


def parse_int_arg(index: int, default_value: int) -> int:  # 定义整数参数解析方法（用于可选方法参数）。
    if len(sys.argv) <= index:  # 如果命令行没有这个位置的参数。
        return default_value  # 返回默认值。
    try:  # 尝试把参数转成整数。
        return int(sys.argv[index])  # 转换成功则返回整数。
    except ValueError as exc:  # 转换失败进入异常分支。
        raise RuntimeError(f"参数位置 {index} 需要整数，当前值: {sys.argv[index]}") from exc  # 抛出可读错误。


def run_target_method(task: OpenSettingsTask, method_name: str) -> None:  # 定义方法分发器，根据方法名调用目标方法。
    if method_name in {"run_once", "all"}:  # 默认或 all 都执行完整单轮。
        task.run_once()  # 执行完整流程一次。
        return  # 当前分支结束后返回。
    if method_name == "clear_all":  # 只跑清理方法。
        task.clear_all()  # 执行一次清理流程。
        return  # 当前分支结束后返回。
    if method_name == "mojiwang_run_all":  # 只跑抹机王全流程。
        task.mojiwang_run_all()  # 执行抹机王方法。
        return  # 当前分支结束后返回。

    if method_name == "facebook_run_all":  # 只跑 Facebook 全流程。
        task.facebook_run_all()  # 执行 Facebook 方法。
        return  # 当前分支结束后返回。

    if method_name == "mojiwang_run_one_loop":  # 只跑抹机王某一轮。
        loop_index = parse_int_arg(2, 0)  # 读取第2个参数作为 loop_index，默认 0。
        task.mojiwang_run_one_loop(loop_index)  # 执行指定轮次。
        return  # 当前分支结束后返回。
    if method_name == "nekobox_run_all":  # 只跑 Nekobox 方法。
        mode_index = parse_int_arg(2, 0)  # 读取第2个参数作为 mode_index，默认 0（动态）。
        task.nekobox_run_all(mode_index)  # 执行指定模式。
        return  # 当前分支结束后返回。
    raise RuntimeError(
        "不支持的方法: "
        f"{method_name}，可用方法: run_once/all, clear_all, mojiwang_run_all, facebook_run_all, mojiwang_run_one_loop, nekobox_run_all"
    )  # 抛出可用方法列表，便于快速修正命令。


def cleanup_poco() -> None:  # 定义退出清理方法，避免解释器关闭阶段出现代理析构噪音。
    if not _POCO_CREATED:  # 如果本次没有创建 Poco。
        return  # 直接返回，不做清理。
    try:  # 尝试获取 Poco 实例。
        poco: Any = get_poco()  # 读取当前进程中的 Poco 对象。
    except Exception:  # 如果获取失败。
        return  # 直接返回，避免二次报错。
    try:  # 尝试调用官方停止方法。
        poco.stop_running()  # 停止 PocoService 保活线程并清理 adb forward。
    except Exception as exc:  # 如果停止失败。
        safe_print("poco stop_running failed:", exc)  # 打印失败信息方便排查。
    gc.collect()  # 主动触发垃圾回收，减少退出阶段噪音。


def main() -> None:  # 定义主函数，串起初始化、执行、清理流程。
    global _POCO_CREATED  # 声明要修改模块级变量。
    method_name = sys.argv[1] if len(sys.argv) > 1 else "run_once"  # 默认不传参数时执行 run_once（全流程一次）。
    serial = resolve_serial()  # 自动选择调试设备 serial。
    setup_logging(process_role="debug", serial=serial)  # 初始化日志系统。
    setup_device(serial=serial, script_file=__file__, log_subdir=f"debug/{serial}")  # 初始化设备连接。
    create_poco()  # 创建 Poco 实例。
    _POCO_CREATED = True  # 标记 Poco 已创建，允许退出时清理。
    locale = read_device_locale()  # 先读取当前设备语言，保证上下文是有效值。
    task_context = TaskContext.from_serial_locale(serial=serial, device_locale=locale)  # 用 serial+locale 构建任务上下文对象。
    task_context.ensure_required()  # 强制校验上下文必填字段，缺失时立即抛错停止调试。
    task = OpenSettingsTask(task_context=task_context)  # 创建任务实例（统一通过上下文对象传参）。
    safe_print(  # 打印本次调试入口信息，确认设备和语言上下文。
        "开始调试方法:",
        method_name,
        "serial:",
        task_context.serial,
        "locale:",
        task_context.device_locale,
        "lang:",
        task_context.device_lang,
    )
    run_target_method(task, method_name)  # 执行目标方法。


def run_with_global_guard() -> int:  # 定义全局兜底运行方法，统一处理未捕获异常并返回退出码。
    try:  # 进入主流程执行区。
        main()  # 执行主函数。
        return 0  # 正常执行完成时返回 0。
    except KeyboardInterrupt:  # 捕获用户手动中断（Ctrl+C）。
        safe_print("收到中断信号，程序已安全退出。")  # 打印中断提示。
        return 130  # 约定返回 130 表示被中断。
    except Exception as exc:  # 捕获所有未处理异常，避免直接抛 Traceback 导致体验差。
        safe_print("程序异常退出:", type(exc).__name__, str(exc))  # 打印异常摘要。
        show_traceback = os.getenv("AUTOVT_SHOW_TRACEBACK", "0").strip().lower() in {"1", "true", "yes"}  # 读取是否显示详细堆栈的开关。
        if show_traceback:  # 开关开启时才打印完整堆栈，便于深度排查。
            safe_print("异常堆栈如下：")  # 打印堆栈标题。
            safe_print(traceback.format_exc())  # 输出完整堆栈文本到终端。
        else:  # 默认只给简短提示，避免初学场景输出过多信息。
            safe_print("如需查看完整堆栈，请设置环境变量 AUTOVT_SHOW_TRACEBACK=1 后重试。")  # 提示如何开启堆栈输出。
        return 1  # 异常退出时返回非 0 退出码。
    finally:  # 无论成功失败都执行清理。
        cleanup_poco()  # 执行 Poco 资源清理。


if __name__ == "__main__":  # 脚本直接运行时进入这里。
    sys.exit(run_with_global_guard())  # 调用全局兜底方法并按退出码结束进程。
