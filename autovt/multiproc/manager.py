from __future__ import annotations

import multiprocessing as mp
import os
import queue
import time
from dataclasses import dataclass, field
from pathlib import Path

try:  # 尝试导入 psutil，用于实现进程级“即时暂停/恢复”。
    import psutil  # 导入 psutil，便于直接挂起/恢复 worker 进程。
except Exception:  # psutil 不可用时降级回原有命令队列模式。
    psutil = None  # 标记为 None，后续分支里自动走兼容逻辑。

from autovt.adb import list_online_serials
from autovt.logs import get_logger
from autovt.multiproc.worker import worker_main
from autovt.settings import WORKER_STOP_FORCE_TIMEOUT_SEC, WORKER_STOP_GRACE_TIMEOUT_SEC
from autovt.userdb import UserDB

log = get_logger("manager")
WORKER_STARTUP_PROBE_SEC = 0.4  # 启动探针等待秒数：用于识别“启动即退出”的秒退进程。


def _ensure_spawn_pythonpath() -> None:
    """确保 spawn 子进程可导入 autovt 包。"""
    app_root = Path(__file__).resolve().parents[2]  # 解析应用根目录（包含 autovt 包的上一级）。
    app_root_text = str(app_root)  # 转成字符串，便于写入环境变量。
    old_pythonpath = os.environ.get("PYTHONPATH", "")  # 读取当前 PYTHONPATH（可能为空）。
    parts = [part for part in old_pythonpath.split(os.pathsep) if part.strip()]  # 拆分并清洗已有路径列表。
    if app_root_text in parts:  # 已存在时无需重复写入。
        return
    new_parts = [app_root_text, *parts]  # 把应用根目录放在最前面，保证优先导入本项目代码。
    os.environ["PYTHONPATH"] = os.pathsep.join(new_parts)  # 回写新的 PYTHONPATH，供后续 spawn 子进程继承。
    log.info("已补齐 spawn PYTHONPATH", app_root=app_root_text)


@dataclass
class WorkerHandle:
    # 设备序列号。
    serial: str
    # 子进程对象。
    process: mp.Process
    # 主进程用于通知子进程停止的事件。
    stop_event: mp.Event
    # 主进程发给子进程的命令队列。
    command_queue: mp.Queue
    # 最近一次状态（starting/running/paused/...）。
    last_state: str = "starting"
    # 最近一次状态详情。
    last_detail: str = ""
    # 最近一次状态更新时间。
    updated_at: float = field(default_factory=time.time)


class DeviceProcessManager:
    def __init__(self, loop_interval_sec: float) -> None:
        _ensure_spawn_pythonpath()  # 先保证子进程 import 路径可用，避免打包态 worker 秒退。

        # 强制使用 spawn：多平台行为更一致，尤其是 macOS。
        self._ctx = mp.get_context("spawn")
        # 子进程自动轮询间隔。
        self._loop_interval_sec = loop_interval_sec
        # 子进程 -> 主进程 的事件队列。
        self._event_queue: mp.Queue = self._ctx.Queue()
        # 当前所有运行中的 worker 句柄。
        self._workers: dict[str, WorkerHandle] = {}
        # 主进程数据库连接：用于设备状态展示账号邮箱、停机释放账号占用。
        self.user_db = UserDB()
        self.user_db.connect()
        log.info("DeviceProcessManager 初始化完成", loop_interval_sec=loop_interval_sec)

    def close(self) -> None:
        # 关闭 manager 持有的数据库连接。
        try:
            self.user_db.close()
        except Exception:
            log.exception("关闭 manager.user_db 失败")

    def list_online_devices(self) -> list[str]:
        # 从 adb 读取当前在线设备列表。
        serials = list_online_serials()
        return serials

    def _update_state(self, serial: str, state: str, detail: str, event_time: float) -> None:
        # 把事件同步到内存中的 worker 状态。
        worker = self._workers.get(serial)
        if not worker:
            return
        worker.last_state = state
        worker.last_detail = detail
        worker.updated_at = event_time

    def _release_device_account(self, serial: str, reason: str) -> None:
        # 释放设备占用账号：status=1 回退 0；status=2/3 保持不变，仅清空 device。
        try:
            released = self.user_db.release_user_for_device(serial)
            if released > 0:
                log.info("已释放设备占用账号", serial=serial, released=released, reason=reason)
        except Exception as exc:
            log.exception("释放设备占用账号失败", serial=serial, reason=reason, error=str(exc))

    def _finalize_worker_stop(
        self,
        *,
        serial: str,
        worker: WorkerHandle,
        release_account: bool,
        release_reason: str,
    ) -> None:
        # 回收句柄资源并从管理表中删除，避免内存和句柄泄漏。
        try:
            worker.command_queue.close()
        except Exception:
            pass
        if release_account:
            self._release_device_account(serial=serial, reason=release_reason)
        self._workers.pop(serial, None)

    def _cleanup_dead(self, serial: str) -> None:
        # 清理已经退出的子进程句柄，避免状态污染。
        worker = self._workers.get(serial)
        if not worker:
            return
        if worker.process.is_alive():
            return
        self._finalize_worker_stop(
            serial=serial,
            worker=worker,
            release_account=True,
            release_reason="worker_dead",
        )

    def _cleanup_all_dead(self) -> None:
        # 批量清理所有已退出 worker。
        for serial in list(self._workers.keys()):
            self._cleanup_dead(serial)

    def drain_events(self) -> list[dict[str, str | float]]:
        # 把事件队列里积压的消息一次性取完。
        events: list[dict[str, str | float]] = []
        while True:
            try:
                event = self._event_queue.get_nowait()
            except queue.Empty:
                break

            # 收集事件，供 CLI/GUI 直接输出。
            events.append(event)
            # 同步更新内部状态快照。
            self._update_state(
                serial=str(event["serial"]),
                state=str(event["state"]),
                detail=str(event["detail"]),
                event_time=float(event["time"]),
            )

        # 不在 drain_events 里自动删除 dead worker。
        # 原因：GUI 需要看到“刚退出”的状态（pid/详情/exit_code），否则会回退成“未启动”误导用户。
        return events

    def start_worker(self, serial: str) -> str:
        # 先刷新状态，避免重复启动僵尸条目。
        self.drain_events()
        self._cleanup_dead(serial)

        old = self._workers.get(serial)
        if old and old.process.is_alive():
            log.warning("设备已在运行", serial=serial, pid=old.process.pid)
            return f"{serial}: 已在运行 pid={old.process.pid}"

        # 为新子进程创建 stop 事件和命令队列。
        stop_event = self._ctx.Event()
        command_queue: mp.Queue = self._ctx.Queue()
        # 创建并启动子进程。
        process = self._ctx.Process(
            target=worker_main,
            args=(serial, self._loop_interval_sec, stop_event, command_queue, self._event_queue),
            name=f"autovt-{serial}",
            daemon=False,
        )
        process.start()
        log.info("子进程已启动", serial=serial, pid=process.pid)

        # 保存句柄，供后续 stop/restart/status 使用。
        self._workers[serial] = WorkerHandle(
            serial=serial,
            process=process,
            stop_event=stop_event,
            command_queue=command_queue,
            last_state="starting",
            last_detail=f"子进程已启动 pid={process.pid}",
            updated_at=time.time(),
        )
        # 启动后做一次短探针：如果子进程“秒退”，直接返回失败原因，避免 GUI 误显示“已启动”。
        process.join(WORKER_STARTUP_PROBE_SEC)
        if not process.is_alive():
            exit_code = process.exitcode if process.exitcode is not None else -1  # 读取退出码，便于定位秒退原因。
            detail = f"子进程启动后立即退出 exit_code={exit_code}"  # 构造统一失败详情文案。
            worker = self._workers.get(serial)  # 回读句柄，更新状态快照给 GUI 展示。
            if worker:
                worker.last_state = "fatal"  # 秒退统一标记为 fatal，方便前端颜色和文案突出显示。
                worker.last_detail = detail  # 写入失败详情。
                worker.updated_at = time.time()  # 更新时间戳，确保 UI 立即刷新到最新状态。
            log.error("子进程启动探针失败", serial=serial, pid=process.pid, exit_code=exit_code)
            return f"{serial}: 启动失败，{detail}"
        return f"{serial}: 启动成功 pid={process.pid}"

    def start_all(self) -> list[str]:
        # 启动所有在线设备对应的子进程。
        serials = self.list_online_devices()
        if not serials:
            return ["未检测到在线设备（adb devices 为空）"]
        return [self.start_worker(serial) for serial in serials]

    def _try_realtime_pause_resume(self, serial: str, worker: WorkerHandle, command: str) -> str | None:
        # 尝试使用进程级 suspend/resume 实现“尽量即时”的暂停与恢复。
        if command not in {"pause", "resume"}:  # 只处理 pause/resume，其它命令走原有队列逻辑。
            return None
        if psutil is None:  # psutil 不可用时不做即时控制，回退到队列命令模式。
            return None

        pid = int(worker.process.pid or -1)  # 读取 worker 进程 PID。
        if pid <= 0:  # PID 无效时直接回退到队列命令模式。
            return None

        try:  # 获取目标进程对象，后续执行 suspend/resume。
            proc = psutil.Process(pid)  # 构造 psutil 进程句柄。
            if command == "pause":  # 即时暂停分支：直接挂起进程。
                proc.suspend()  # 挂起 worker 进程，当前执行步骤会立即冻结。
                worker.last_state = "paused"  # 立即更新状态快照，UI 可立刻看到暂停态。
                worker.last_detail = "已即时暂停（进程挂起）"  # 更新状态详情文案。
                worker.updated_at = time.time()  # 更新时间戳用于状态列表显示。
                log.info("即时暂停成功", serial=serial, pid=pid)  # 记录即时暂停日志。
                return f"{serial}: 已即时暂停"

            proc.resume()  # 即时恢复分支：恢复被挂起的进程继续执行。
            worker.last_state = "running"  # 立即更新状态快照为运行中。
            worker.last_detail = "已即时恢复（进程继续）"  # 更新状态详情文案。
            worker.updated_at = time.time()  # 更新时间戳用于状态列表显示。
            log.info("即时恢复成功", serial=serial, pid=pid)  # 记录即时恢复日志。
            return f"{serial}: 已即时恢复"
        except Exception as exc:  # 即时控制失败时记录告警并回退到队列命令模式。
            log.warning("即时暂停/恢复失败，回退命令队列模式", serial=serial, command=command, error=str(exc))
            return None

    def send_command(self, serial: str, command: str) -> str:
        # 给指定设备子进程发送控制命令。
        self.drain_events()
        self._cleanup_dead(serial)
        worker = self._workers.get(serial)
        if not worker or not worker.process.is_alive():
            log.warning("发送命令失败，设备未运行", serial=serial, command=command)
            return f"{serial}: 未运行"

        fast_result = self._try_realtime_pause_resume(serial=serial, worker=worker, command=command)  # 优先尝试进程级即时暂停/恢复。
        if fast_result is not None:  # 命中即时暂停/恢复分支时直接返回结果。
            return fast_result

        worker.command_queue.put(command)
        log.info("命令已发送", serial=serial, command=command)
        return f"{serial}: 已发送命令 {command}"

    def send_command_all(self, command: str) -> list[str]:
        # 广播命令给所有运行中的设备。
        return [self.send_command(serial, command) for serial in sorted(self._workers.keys())]

    def _try_send_stop(self, worker: WorkerHandle, serial: str) -> None:
        # 给子进程发送 stop 命令并设置 stop_event，使用双保险提高退出成功率。
        try:
            worker.command_queue.put("stop")
        except Exception as exc:
            log.warning("发送 stop 命令失败，改用 stop_event", serial=serial, error=str(exc))
        worker.stop_event.set()

    def stop_worker(self, serial: str, timeout_sec: float | None = None) -> str:
        # 停止指定设备子进程：先优雅停止，超时再强杀。
        self.drain_events()
        worker = self._workers.get(serial)
        if not worker:
            # 即使进程句柄不存在，也尝试做一次账号释放，防止残留绑定。
            self._release_device_account(serial=serial, reason="stop_worker_without_handle")
            log.warning("停止失败，设备未运行", serial=serial)
            return f"{serial}: 未运行"

        grace_timeout_sec = (
            max(0.0, float(timeout_sec)) if timeout_sec is not None else WORKER_STOP_GRACE_TIMEOUT_SEC
        )
        if worker.process.is_alive():
            # 先优雅停止：发 stop 命令并等待短超时。
            self._try_send_stop(worker, serial=serial)
            worker.process.join(grace_timeout_sec)

        if worker.process.is_alive():
            # 超时还没退就强制 terminate。
            worker.process.terminate()
            worker.process.join(WORKER_STOP_FORCE_TIMEOUT_SEC)
            if worker.process.is_alive():
                # terminate 仍未退出时，最后使用 kill 兜底。
                worker.process.kill()
                worker.process.join(WORKER_STOP_FORCE_TIMEOUT_SEC)
                msg = f"{serial}: 超时，已强制 kill"
                log.error(
                    "子进程 terminate 后仍未退出，已 kill",
                    serial=serial,
                    grace_timeout_sec=grace_timeout_sec,
                    force_timeout_sec=WORKER_STOP_FORCE_TIMEOUT_SEC,
                )
            else:
                msg = f"{serial}: 超时，已强制终止"
                log.error(
                    "子进程停止超时，已强制终止",
                    serial=serial,
                    grace_timeout_sec=grace_timeout_sec,
                    force_timeout_sec=WORKER_STOP_FORCE_TIMEOUT_SEC,
                )
        else:
            msg = f"{serial}: 已停止"
            log.info("子进程已停止", serial=serial)

        # 回收资源并删除句柄。
        self._finalize_worker_stop(
            serial=serial,
            worker=worker,
            release_account=True,
            release_reason="stop_worker",
        )
        return msg

    def stop_all(self, timeout_sec: float | None = None) -> list[str]:
        # 停止全部子进程：并发发 stop + 统一等待，避免多设备串行超时导致总耗时过长。
        self.drain_events()
        serials = sorted(self._workers.keys())
        if not serials:
            return ["当前无运行中的设备进程"]  # 没有可停止进程时返回明确提示，避免 GUI 侧看起来“无反应”。

        grace_timeout_sec = (
            max(0.0, float(timeout_sec)) if timeout_sec is not None else WORKER_STOP_GRACE_TIMEOUT_SEC
        )

        # 第一阶段：并发发送 stop 请求。
        for serial in serials:
            worker = self._workers.get(serial)
            if not worker:
                continue
            if worker.process.is_alive():
                self._try_send_stop(worker, serial=serial)

        # 第二阶段：统一等待优雅退出。
        deadline = time.time() + grace_timeout_sec
        alive_serials = {
            serial for serial in serials if self._workers.get(serial) and self._workers[serial].process.is_alive()
        }
        while alive_serials and time.time() < deadline:
            for serial in list(alive_serials):
                worker = self._workers.get(serial)
                if not worker or not worker.process.is_alive():
                    alive_serials.discard(serial)
            if alive_serials:
                time.sleep(0.05)

        # 第三阶段：并发 terminate 仍存活的进程，并统一等待。
        alive_after_grace = {
            serial for serial in serials if self._workers.get(serial) and self._workers[serial].process.is_alive()
        }
        for serial in alive_after_grace:
            worker = self._workers.get(serial)
            if worker and worker.process.is_alive():
                worker.process.terminate()
        terminate_deadline = time.time() + WORKER_STOP_FORCE_TIMEOUT_SEC
        alive_after_terminate = set(alive_after_grace)
        while alive_after_terminate and time.time() < terminate_deadline:
            for serial in list(alive_after_terminate):
                worker = self._workers.get(serial)
                if not worker or not worker.process.is_alive():
                    alive_after_terminate.discard(serial)
            if alive_after_terminate:
                time.sleep(0.05)

        # 第四阶段：并发 kill terminate 后仍存活的进程，并统一等待。
        for serial in alive_after_terminate:
            worker = self._workers.get(serial)
            if worker and worker.process.is_alive():
                worker.process.kill()
        kill_deadline = time.time() + WORKER_STOP_FORCE_TIMEOUT_SEC
        alive_after_kill = set(alive_after_terminate)
        while alive_after_kill and time.time() < kill_deadline:
            for serial in list(alive_after_kill):
                worker = self._workers.get(serial)
                if not worker or not worker.process.is_alive():
                    alive_after_kill.discard(serial)
            if alive_after_kill:
                time.sleep(0.05)

        # 第五阶段：回收资源并产出每个设备的停止结果。
        messages: list[str] = []
        for serial in serials:
            worker = self._workers.get(serial)
            if not worker:
                continue

            if serial in alive_after_kill:
                msg = f"{serial}: 超时，kill 后仍未退出"
                log.error(
                    "stop_all kill 后仍未退出",
                    serial=serial,
                    grace_timeout_sec=grace_timeout_sec,
                    force_timeout_sec=WORKER_STOP_FORCE_TIMEOUT_SEC,
                )
            elif serial in alive_after_terminate:
                msg = f"{serial}: 超时，已强制 kill"
                log.error(
                    "stop_all terminate 后仍未退出，已 kill",
                    serial=serial,
                    grace_timeout_sec=grace_timeout_sec,
                    force_timeout_sec=WORKER_STOP_FORCE_TIMEOUT_SEC,
                )
            elif serial in alive_after_grace:
                msg = f"{serial}: 超时，已强制终止"
                log.error(
                    "stop_all 停止超时，已强制终止",
                    serial=serial,
                    grace_timeout_sec=grace_timeout_sec,
                    force_timeout_sec=WORKER_STOP_FORCE_TIMEOUT_SEC,
                )
            else:
                msg = f"{serial}: 已停止"
                log.info("stop_all 子进程已停止", serial=serial)

            self._finalize_worker_stop(
                serial=serial,
                worker=worker,
                release_account=True,
                release_reason="stop_all",
            )
            messages.append(msg)
        return messages

    def restart_worker(self, serial: str, timeout_sec: float | None = None) -> list[str]:
        # 重启：先停再启，返回两条结果信息。
        return [self.stop_worker(serial, timeout_sec=timeout_sec), self.start_worker(serial)]

    def status(self) -> list[dict[str, str | int | float]]:
        # 返回当前所有子进程状态快照，供 CLI/GUI 展示。
        self.drain_events()
        rows: list[dict[str, str | int | float]] = []
        for serial, worker in sorted(self._workers.items()):
            user_row = self.user_db.get_user_by_device(serial)  # 从 t_user.device 反查当前设备占用账号。
            email_account = str(user_row.get("email_account", "")).strip() if user_row else ""
            rows.append(
                {
                    # 设备序列号。
                    "serial": serial,
                    # 进程 PID。
                    "pid": worker.process.pid or -1,
                    # 是否存活。
                    "alive": "yes" if worker.process.is_alive() else "no",
                    # 最近状态。
                    "state": worker.last_state,
                    # 最近详情。
                    "detail": worker.last_detail,
                    # 当前设备占用邮箱。
                    "email_account": email_account,
                    # 最近更新时间戳。
                    "updated_at": worker.updated_at,
                }
            )
        return rows
