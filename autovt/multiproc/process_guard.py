from __future__ import annotations

# 导入操作系统模块，用于读取当前父进程信息。
import os
# 导入线程模块，用于启动父进程存活监控线程。
import threading
# 导入时间模块，用于控制 watchdog 轮询间隔。
import time
# 导入路径对象，用于稳定比较 adb 可执行路径。
from pathlib import Path
# 导入类型工具，用于补充回调和结构化返回类型标注。
from typing import Any

# 尝试导入 psutil，用于扫描和清理本地辅助进程。
try:
    # 导入 psutil 进程工具库。
    import psutil
# 当 psutil 不可用时降级为空，调用方仍可安全执行。
except Exception:
    # 标记为 None，后续函数内部会自动跳过相关能力。
    psutil = None

# 定义 autovt 常见长生命周期辅助进程关键字。
AUTOVT_HELPER_TOKENS = (
    "pocoservice",
    "maxpresent",
    "rotationwatcher",
    "minicap",
    "minitouch",
    "javacap",
    "yosemite",
)


# 定义安全读取命令行的方法。
def _safe_cmdline(proc: Any) -> list[str]:
    # 尝试读取进程命令行。
    try:
        # 读取并过滤空片段，避免后续匹配出现脏值。
        return [str(part).strip() for part in proc.cmdline() if str(part).strip()]
    # 读取失败时返回空列表，避免扫描流程中断。
    except Exception:
        # 返回空命令行，表示本次无法识别该进程。
        return []


# 定义安全解析路径的方法。
def _safe_resolve_path(raw_path: str) -> str:
    # 原始路径为空时直接返回空字符串。
    if not str(raw_path or "").strip():
        # 返回空字符串，表示当前路径不可用。
        return ""
    # 尝试解析绝对路径，提升同一路径比较稳定性。
    try:
        # 返回解析后的绝对路径文本。
        return str(Path(raw_path).resolve())
    # 解析失败时回退原始文本，避免异常影响清理流程。
    except Exception:
        # 返回原始路径字符串。
        return str(raw_path)


# 定义从命令行中提取设备 serial 的方法。
def _extract_serial_from_cmdline(cmdline: list[str]) -> str:
    # 逐项扫描命令行参数。
    for index, part in enumerate(cmdline):
        # 命中 adb 的 -s 参数时读取后一个值作为 serial。
        if part == "-s" and index + 1 < len(cmdline):
            # 返回对应设备 serial。
            return str(cmdline[index + 1]).strip()
    # 未命中时返回空字符串。
    return ""


# 定义判断父进程是否仍存活的方法。
def is_parent_process_alive(parent_pid: int) -> bool:
    # 父进程号非法或已降到 init/launchd 时视为已失联。
    if int(parent_pid or 0) <= 1:
        # 返回 False，表示当前父进程不可作为有效生命周期源。
        return False
    # psutil 可用时优先用 psutil 做更稳定的进程探测。
    if psutil is not None:
        # 尝试读取父进程状态。
        try:
            # 构造父进程句柄。
            proc = psutil.Process(int(parent_pid))
            # 进程已退出时直接判定为不存活。
            if not proc.is_running():
                # 返回 False，表示父进程已退出。
                return False
            # 僵尸态也视为已失联，避免 worker 继续悬挂运行。
            if proc.status() == psutil.STATUS_ZOMBIE:
                # 返回 False，表示父进程已不可用。
                return False
            # 返回 True，表示父进程仍然有效。
            return True
        # 任何异常都按父进程已失联处理。
        except Exception:
            # 返回 False，表示无法确认父进程仍存活。
            return False
    # 无 psutil 时回退到 os.kill(pid, 0) 探测。
    try:
        # 发送 0 信号，只用于探测进程是否存在。
        os.kill(int(parent_pid), 0)
        # 未抛异常说明进程仍存在。
        return True
    # 探测失败时视为父进程已退出。
    except Exception:
        # 返回 False，表示父进程已失联。
        return False


# 定义收集 autovt 辅助进程的方法。
def collect_autovt_helper_processes(
    *,
    adb_bin: str,
    serial: str = "",
    orphan_only: bool = False,
) -> list[dict[str, Any]]:
    # psutil 不可用时直接返回空列表。
    if psutil is None:
        # 返回空列表，表示当前无法执行系统级进程扫描。
        return []
    # 预先解析 adb 路径，确保不同 cwd 下比较结果一致。
    adb_bin_path = _safe_resolve_path(adb_bin)
    # adb 路径为空时无法识别目标进程，直接返回。
    if adb_bin_path == "":
        # 返回空列表，避免误匹配其他外部 adb 实例。
        return []
    # 预先标准化 serial，便于后续过滤。
    expected_serial = str(serial or "").strip()
    # 初始化结果列表。
    matched_processes: list[dict[str, Any]] = []
    # 遍历系统进程。
    for proc in psutil.process_iter(attrs=["pid", "ppid"]):
        # 安全读取命令行。
        cmdline = _safe_cmdline(proc)
        # 没有命令行时无法识别，直接跳过。
        if not cmdline:
            # 当前进程不参与后续匹配。
            continue
        # 只处理项目自带 adb 拉起的本地辅助进程。
        if _safe_resolve_path(cmdline[0]) != adb_bin_path:
            # 非项目自带 adb 进程直接跳过，避免误杀其他工具。
            continue
        # 把命令行转成统一小写文本，便于关键字匹配。
        cmdline_text = " ".join(cmdline).lower()
        # 提取命中的辅助进程关键字。
        matched_tokens = [token for token in AUTOVT_HELPER_TOKENS if token in cmdline_text]
        # 未命中关键字时直接跳过，避免把普通短命 adb 命令当成残留。
        if not matched_tokens:
            # 当前 adb 进程不是我们关心的辅助进程。
            continue
        # 解析命令行里的设备 serial。
        proc_serial = _extract_serial_from_cmdline(cmdline)
        # 指定了 serial 且当前进程 serial 不匹配时跳过。
        if expected_serial and proc_serial != expected_serial:
            # 只收集当前设备对应的辅助进程。
            continue
        # 读取父进程号。
        parent_pid = int(getattr(proc, "ppid", lambda: 0)() if callable(getattr(proc, "ppid", None)) else getattr(proc, "ppid", 0) or 0)
        # 计算当前进程是否已成为孤儿。
        orphaned = parent_pid <= 1 or not is_parent_process_alive(parent_pid)
        # 仅清理孤儿模式下，非孤儿进程直接跳过。
        if orphan_only and not orphaned:
            # 当前进程仍挂在有效父进程下，不属于历史残留。
            continue
        # 组装结构化结果，供调用方统一记录日志。
        matched_processes.append(
            {
                "pid": int(getattr(proc, "pid", 0) or 0),
                "ppid": parent_pid,
                "serial": proc_serial,
                "cmdline": cmdline,
                "cmdline_text": " ".join(cmdline),
                "matched_tokens": matched_tokens,
                "orphaned": orphaned,
            }
        )
    # 返回按 pid 排序后的结果，保证日志输出稳定。
    return sorted(matched_processes, key=lambda item: int(item.get("pid", 0) or 0))


# 定义清理 autovt 辅助进程的方法。
def cleanup_autovt_helper_processes(
    *,
    adb_bin: str,
    log: Any,
    serial: str = "",
    orphan_only: bool = False,
    reason: str = "",
) -> dict[str, Any]:
    # 先收集匹配到的辅助进程。
    processes = collect_autovt_helper_processes(
        adb_bin=adb_bin,
        serial=serial,
        orphan_only=orphan_only,
    )
    # 初始化返回结构，便于调用方直接记录结果。
    result: dict[str, Any] = {
        "reason": str(reason or "").strip(),
        "serial": str(serial or "").strip(),
        "orphan_only": bool(orphan_only),
        "matched": len(processes),
        "terminated": 0,
        "killed": 0,
        "failed": 0,
        "remaining": [],
        "processes": processes,
    }
    # 未命中任何辅助进程时直接返回。
    if not processes:
        # 返回空命中结果，调用方可据此判定无需处理。
        return result
    # 初始化 psutil 进程对象列表。
    proc_objects: list[Any] = []
    # 按匹配结果逐个构造 psutil 句柄。
    for item in processes:
        # 尝试构造当前 pid 的 psutil 句柄。
        try:
            # 把可操作句柄加入待终止列表。
            proc_objects.append(psutil.Process(int(item["pid"])))
        # 已退出或不可访问时记为失败，但不打断其余进程处理。
        except Exception as exc:
            # 增加失败计数。
            result["failed"] = int(result["failed"]) + 1
            # 记录单个 pid 构造失败日志。
            log.warning(
                "构造辅助进程句柄失败",
                reason=result["reason"],
                serial=result["serial"],
                pid=int(item["pid"]),
                error=str(exc),
                cmdline=item["cmdline_text"],
            )
    # 先尝试优雅终止所有命中的辅助进程。
    for proc in proc_objects:
        # 逐个发送 terminate。
        try:
            # 发送温和终止信号。
            proc.terminate()
            # 增加 terminate 计数。
            result["terminated"] = int(result["terminated"]) + 1
        # 单个进程 terminate 失败时继续清理其他进程。
        except Exception as exc:
            # 增加失败计数。
            result["failed"] = int(result["failed"]) + 1
            # 记录 terminate 失败详情。
            log.warning(
                "终止辅助进程失败",
                reason=result["reason"],
                serial=result["serial"],
                pid=int(getattr(proc, "pid", 0) or 0),
                error=str(exc),
            )
    # 等待 terminate 阶段生效。
    try:
        # 使用 wait_procs 等待短时间退出。
        _, alive_procs = psutil.wait_procs(proc_objects, timeout=1.0)
    # 等待失败时回退为“全部仍存活”，随后直接进入 kill。
    except Exception as exc:
        # 记录等待失败日志。
        log.warning(
            "等待辅助进程 terminate 退出失败，准备直接 kill",
            reason=result["reason"],
            serial=result["serial"],
            error=str(exc),
        )
        # 把全部句柄视为仍存活。
        alive_procs = proc_objects
    # 对仍存活的辅助进程执行 kill。
    for proc in alive_procs:
        # 逐个发送 kill。
        try:
            # 强制杀死当前残留进程。
            proc.kill()
            # 增加 kill 计数。
            result["killed"] = int(result["killed"]) + 1
        # kill 失败时记日志，不中断整体流程。
        except Exception as exc:
            # 增加失败计数。
            result["failed"] = int(result["failed"]) + 1
            # 记录 kill 失败详情。
            log.warning(
                "强制结束辅助进程失败",
                reason=result["reason"],
                serial=result["serial"],
                pid=int(getattr(proc, "pid", 0) or 0),
                error=str(exc),
            )
    # 清理结束后再做一次复检，确认是否仍有残留。
    remaining_processes = collect_autovt_helper_processes(
        adb_bin=adb_bin,
        serial=serial,
        orphan_only=orphan_only,
    )
    # 写入复检结果。
    result["remaining"] = remaining_processes
    # 返回结构化清理结果。
    return result


# 定义启动父进程存活监控线程的方法。
def start_parent_watchdog(
    *,
    parent_pid: int,
    log: Any,
    stop_callback: Any,
    interval_sec: float = 1.0,
    thread_name: str = "autovt-parent-watchdog",
) -> threading.Thread:
    # 定义后台轮询函数。
    def _watchdog_loop() -> None:
        # 持续轮询父进程存活状态。
        while True:
            # 每轮先睡一小段时间，避免频繁轮询占用资源。
            time.sleep(max(0.2, float(interval_sec)))
            # 父进程仍存活时继续下一轮检测。
            if is_parent_process_alive(parent_pid):
                # 当前生命周期源仍有效，无需触发停机。
                continue
            # 记录父进程失联日志。
            log.error("检测到父进程已退出，准备触发 worker 停机", parent_pid=int(parent_pid))
            # 尝试触发调用方提供的停机回调。
            try:
                # 调用停机回调，通常用于设置 stop_event。
                stop_callback()
            # 回调失败时仅记录日志，避免线程异常静默消失。
            except Exception as exc:
                # 记录 watchdog 回调异常详情。
                log.exception("父进程 watchdog 执行停机回调失败", parent_pid=int(parent_pid), error=str(exc))
            # 触发一次即可退出监控线程。
            return
    # 创建守护线程，避免影响进程正常退出。
    thread = threading.Thread(
        target=_watchdog_loop,
        name=str(thread_name or "autovt-parent-watchdog"),
        daemon=True,
    )
    # 启动后台线程。
    thread.start()
    # 返回线程对象，便于调用方按需持有。
    return thread


# 显式导出当前模块的公开能力。
__all__ = [
    "AUTOVT_HELPER_TOKENS",
    "cleanup_autovt_helper_processes",
    "collect_autovt_helper_processes",
    "is_parent_process_alive",
    "start_parent_watchdog",
]
