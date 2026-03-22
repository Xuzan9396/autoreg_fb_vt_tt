"""设备刷新协调器。"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from autovt.logs import get_logger
from autovt.multiproc.manager import DeviceProcessManager
from autovt.settings import JSON_LOG_DIR

log = get_logger("gui.device_refresh")
# 设备日志面板默认最多保留 100 条记录。
DEVICE_LOG_MAX_LINES = 100
# 单轮最多回看最近 6 个日志文件，避免历史文件过多时拖慢刷新。
DEVICE_LOG_SCAN_MAX_FILES = 6
# 单文件最多回读 200 行，优先保证“看最新”。
DEVICE_LOG_TAIL_PER_FILE = 200
# 单文件尾读最多扫描 256KB，避免大文件整文件扫盘。
DEVICE_LOG_TAIL_MAX_BYTES = 256 * 1024
# Tab 切回设备页时，2.5 秒内允许直接回放最新快照。
SNAPSHOT_REPLAY_MAX_AGE_MS = 2500


@dataclass(slots=True)
class RefreshMetrics:
    """刷新阶段耗时与诊断指标。"""

    # adb 在线设备读取耗时。
    adb_elapsed_ms: int = 0
    # manager.status 快照耗时。
    status_elapsed_ms: int = 0
    # 日志读盘耗时。
    log_read_elapsed_ms: int = 0
    # 请求进入独立串行线程后的排队耗时。
    queue_wait_elapsed_ms: int = 0
    # 本轮总耗时。
    total_elapsed_ms: int = 0
    # 是否命中协调器快照回放。
    cache_hit: bool = False
    # 当前快照年龄。
    snapshot_age_ms: int = 0
    # 本轮扫描的日志文件数。
    scanned_file_count: int = 0
    # 本轮尾读累计扫描字节数。
    scanned_bytes: int = 0
    # 日志尾读阶段耗时。
    tail_read_elapsed_ms: int = 0
    # 命中过滤条件的日志行数。
    filtered_line_count: int = 0


@dataclass(slots=True)
class DeviceRefreshSnapshot:
    """设备页消费的统一快照。"""

    # 当前在线设备 serial 集合。
    online_serials: set[str] = field(default_factory=set)
    # manager.status 返回的原始状态行。
    status_rows: list[dict[str, str | int | float]] = field(default_factory=list)
    # 设备页日志记录列表。
    log_records: list[tuple[str, str]] = field(default_factory=list)
    # 本轮刷新指标。
    metrics: RefreshMetrics = field(default_factory=RefreshMetrics)
    # 刷新失败时的人类可读错误。
    error_text: str = ""
    # 最近一次成功或降级快照时间戳。
    refreshed_at: float = 0.0


class DeviceRefreshCoordinator:
    """把设备页的 adb/status/logs 读取收敛到单一串行协调器。"""

    def __init__(self, manager: DeviceProcessManager) -> None:
        self._manager = manager
        self._snapshot_lock = threading.RLock()
        self._lifecycle_lock = threading.RLock()
        self._executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="autovt-device-refresh",
        )
        self._started = False
        self._closed = False
        self._active_future: Future[DeviceRefreshSnapshot] | None = None
        self._active_source = ""
        self._last_snapshot = DeviceRefreshSnapshot()
        self._log_follow_latest = True

    def start(self) -> None:
        """启动协调器。"""
        # 使用生命周期锁保护启动状态。
        with self._lifecycle_lock:
            # 已关闭时拒绝再次启动，避免使用已 shutdown 的执行器。
            if self._closed:
                raise RuntimeError("DeviceRefreshCoordinator 已关闭")
            # 已启动时直接返回，保证幂等。
            if self._started:
                return
            # 标记协调器已启动。
            self._started = True
        # 记录启动日志，便于排查生命周期。
        log.info("设备刷新协调器已启动")

    def close(self) -> None:
        """关闭协调器并等待串行线程退出。"""
        # 使用生命周期锁保护关闭状态。
        with self._lifecycle_lock:
            # 已关闭时直接返回，保证幂等。
            if self._closed:
                return
            # 标记协调器进入关闭态。
            self._closed = True
        # 关闭独立执行器，等待当前刷新安全收尾。
        self._executor.shutdown(wait=True, cancel_futures=False)
        # 输出关闭日志，便于定位退出链路。
        log.info("设备刷新协调器已关闭")

    def get_snapshot(self) -> DeviceRefreshSnapshot:
        """读取最近一次快照。"""
        # 使用快照锁保护读操作。
        with self._snapshot_lock:
            # 返回复制后的快照，避免调用方误改内部状态。
            return self._clone_snapshot(self._last_snapshot)

    def mark_log_follow_latest(self, follow_latest: bool) -> None:
        """记录当前日志面板是否保持跟随最新。"""
        # 使用快照锁保护共享状态。
        with self._snapshot_lock:
            # 统一保存布尔值，供日志诊断使用。
            self._log_follow_latest = bool(follow_latest)

    async def request_refresh(
        self,
        source: str,
        force_refresh: bool = False,
        allow_cached_replay: bool = False,
    ) -> DeviceRefreshSnapshot:
        """请求一次串行刷新，必要时复用最近快照。"""
        # 未显式启动时自动补启动，简化接入方调用链路。
        if not self._started:
            self.start()
        # 已关闭时直接返回最后快照，避免退出过程再起新线程任务。
        if self._closed:
            return self._build_degraded_snapshot(
                message="设备刷新协调器已关闭，返回最近快照",
                metrics=RefreshMetrics(cache_hit=True),
            )

        # 允许快照回放时，优先尝试直接返回最近可用结果。
        if allow_cached_replay:
            cached_snapshot = self._try_replay_snapshot(source=source)
            if cached_snapshot is not None:
                return cached_snapshot

        # 命中进行中的刷新任务时，直接合并到同一 future，避免排队堆积。
        active_future = self._active_future
        if active_future is not None and not active_future.done():
            # 记录“本轮并入上一轮”的协调日志。
            log.info(
                "设备刷新请求并入进行中的任务",
                source=source,
                running_source=self._active_source,
            )
            # 等待上一轮结束后直接复用结果。
            return await asyncio.wrap_future(active_future)

        # 获取当前事件循环，用于把独立串行任务挂到后台执行器。
        loop = asyncio.get_running_loop()
        # 记录本次请求时间，供后台线程计算排队耗时。
        requested_at = time.monotonic()
        # 提交到独立单线程执行器，避免和全局 to_thread 线程池互抢。
        future = self._executor.submit(
            self._run_refresh_sync,
            requested_at,
            str(source or "").strip(),
            bool(force_refresh),
        )
        # 记录当前活跃 future，供后续请求合并。
        self._active_future = future
        # 记录当前活跃来源，方便诊断。
        self._active_source = str(source or "").strip()
        try:
            # 等待后台刷新完成并返回快照。
            snapshot = await asyncio.wrap_future(future, loop=loop)
            # 返回复制后的快照，避免调用方误改缓存对象。
            return self._clone_snapshot(snapshot)
        finally:
            # 仅在当前 future 仍是活跃项时才清理标记，避免覆盖后续任务。
            if self._active_future is future:
                self._active_future = None
                self._active_source = ""

    async def clear_logs(self) -> int:
        """在协调器独立执行器内清理 open_settings 日志。"""
        # 未启动时自动补启动，保持接口幂等。
        if not self._started:
            self.start()
        # 已关闭时直接拒绝清理，避免退出流程误写文件。
        if self._closed:
            raise RuntimeError("DeviceRefreshCoordinator 已关闭，无法清理日志")
        # 获取当前事件循环。
        loop = asyncio.get_running_loop()
        # 把日志清理放到独立串行线程执行，避免和刷新逻辑并发触盘。
        cleared_count = await asyncio.wrap_future(
            self._executor.submit(self._clear_open_settings_logs_sync),
            loop=loop,
        )
        # 返回清理条数给 UI 展示。
        return int(cleared_count)

    def _try_replay_snapshot(self, source: str) -> DeviceRefreshSnapshot | None:
        """在短时间内直接回放最近快照，避免切页又触发一次 IO。"""
        # 读取最近快照副本，避免后续年龄计算受并发写影响。
        snapshot = self.get_snapshot()
        # 没有可用快照时直接返回空值。
        if snapshot.refreshed_at <= 0:
            return None
        # 计算当前快照年龄。
        snapshot_age_ms = int(max(0.0, time.time() - snapshot.refreshed_at) * 1000)
        # 快照过旧时不回放，交给后台线程做真实刷新。
        if snapshot_age_ms > SNAPSHOT_REPLAY_MAX_AGE_MS:
            return None
        # 构造“命中回放”的指标副本。
        metrics = RefreshMetrics(
            cache_hit=True,
            snapshot_age_ms=snapshot_age_ms,
        )
        # 记录快照回放日志，方便区分真实刷新和直接复用。
        log.debug(
            "设备刷新协调器回放最近快照",
            source=source,
            snapshot_age_ms=snapshot_age_ms,
            online_count=len(snapshot.online_serials),
            status_count=len(snapshot.status_rows),
            log_count=len(snapshot.log_records),
        )
        # 返回带缓存命中标记的新快照。
        return self._clone_snapshot(snapshot, metrics=metrics)

    def _run_refresh_sync(self, requested_at: float, source: str, force_refresh: bool) -> DeviceRefreshSnapshot:
        """在独立串行线程中执行完整刷新。"""
        # 记录本轮执行实际开始时间，用于计算排队耗时。
        started_at = time.monotonic()
        # 预置指标对象，后续逐步填充阶段耗时。
        metrics = RefreshMetrics(
            queue_wait_elapsed_ms=int(max(0.0, started_at - requested_at) * 1000),
        )
        try:
            # 读取在线设备列表，并把来源透传给 adb 诊断日志。
            adb_started_at = time.monotonic()
            online_serials = set(
                self._manager.list_online_devices(
                    force_refresh=force_refresh,
                    source=source or "coordinator",
                )
            )
            metrics.adb_elapsed_ms = int((time.monotonic() - adb_started_at) * 1000)

            # 读取进程状态快照。
            status_started_at = time.monotonic()
            status_rows = self._manager.status()
            metrics.status_elapsed_ms = int((time.monotonic() - status_started_at) * 1000)

            # 读取最新日志快照。
            log_started_at = time.monotonic()
            log_records, log_diagnostics = self._load_latest_log_records(limit=DEVICE_LOG_MAX_LINES)
            metrics.log_read_elapsed_ms = int((time.monotonic() - log_started_at) * 1000)
            metrics.scanned_file_count = int(log_diagnostics.get("scanned_file_count", 0) or 0)
            metrics.scanned_bytes = int(log_diagnostics.get("scanned_bytes", 0) or 0)
            metrics.tail_read_elapsed_ms = int(log_diagnostics.get("tail_read_elapsed_ms", 0) or 0)
            metrics.filtered_line_count = int(log_diagnostics.get("filtered_line_count", 0) or 0)
            metrics.total_elapsed_ms = int((time.monotonic() - started_at) * 1000)

            # 组装成功快照。
            snapshot = DeviceRefreshSnapshot(
                online_serials=online_serials,
                status_rows=status_rows,
                log_records=log_records,
                metrics=metrics,
                error_text="",
                refreshed_at=time.time(),
            )
            # 回写快照缓存，供后续界面回放和失败降级使用。
            self._set_snapshot(snapshot)
            # 按耗时高低输出告警或调试日志。
            self._log_refresh_result(snapshot=snapshot, source=source)
            # 返回当前成功快照。
            return snapshot
        except Exception as exc:
            # 刷新失败时补齐总耗时，方便定位卡在哪一段。
            metrics.total_elapsed_ms = int((time.monotonic() - started_at) * 1000)
            # 记录异常堆栈和阶段耗时。
            log.exception(
                "设备刷新协调器执行失败，降级返回最近快照",
                source=source,
                queue_wait_elapsed_ms=metrics.queue_wait_elapsed_ms,
                adb_elapsed_ms=metrics.adb_elapsed_ms,
                status_elapsed_ms=metrics.status_elapsed_ms,
                log_read_elapsed_ms=metrics.log_read_elapsed_ms,
                total_elapsed_ms=metrics.total_elapsed_ms,
            )
            # 返回带错误说明的降级快照，避免界面闪空。
            return self._build_degraded_snapshot(
                message=str(exc),
                metrics=metrics,
            )

    def _build_degraded_snapshot(self, message: str, metrics: RefreshMetrics) -> DeviceRefreshSnapshot:
        """刷新失败时沿用最近一次可用快照。"""
        # 读取最近快照副本。
        last_snapshot = self.get_snapshot()
        # 计算旧快照年龄，方便 UI 打日志诊断。
        if last_snapshot.refreshed_at > 0:
            metrics.snapshot_age_ms = int(max(0.0, time.time() - last_snapshot.refreshed_at) * 1000)
        # 没有历史快照时返回空快照，但仍保留错误信息。
        if last_snapshot.refreshed_at <= 0:
            degraded_snapshot = DeviceRefreshSnapshot(
                online_serials=set(),
                status_rows=[],
                log_records=[],
                metrics=metrics,
                error_text=message,
                refreshed_at=time.time(),
            )
        else:
            # 有历史快照时沿用旧数据，仅刷新错误信息和指标。
            degraded_snapshot = self._clone_snapshot(
                last_snapshot,
                metrics=metrics,
                error_text=message,
            )
        # 记录降级使用旧快照的明确日志。
        log.warning(
            "设备刷新协调器使用旧快照降级",
            error_text=message,
            snapshot_age_ms=metrics.snapshot_age_ms,
            online_count=len(degraded_snapshot.online_serials),
            status_count=len(degraded_snapshot.status_rows),
            log_count=len(degraded_snapshot.log_records),
        )
        # 返回降级快照。
        return degraded_snapshot

    def _set_snapshot(self, snapshot: DeviceRefreshSnapshot) -> None:
        """写入最近快照缓存。"""
        # 使用快照锁保护写操作。
        with self._snapshot_lock:
            # 保存快照副本，避免外部引用继续修改。
            self._last_snapshot = self._clone_snapshot(snapshot)

    def _log_refresh_result(self, snapshot: DeviceRefreshSnapshot, source: str) -> None:
        """统一输出协调器阶段日志。"""
        # 读取指标对象，缩短后续字段访问链路。
        metrics = snapshot.metrics
        # 判断是否超过告警阈值。
        level_method = log.warning if metrics.total_elapsed_ms >= 1500 else log.debug
        # 输出统一阶段日志，便于和 UI 应用耗时拼接分析。
        level_method(
            "设备刷新协调器完成",
            source=source,
            follow_latest=self._log_follow_latest,
            queue_wait_elapsed_ms=metrics.queue_wait_elapsed_ms,
            adb_elapsed_ms=metrics.adb_elapsed_ms,
            status_elapsed_ms=metrics.status_elapsed_ms,
            log_read_elapsed_ms=metrics.log_read_elapsed_ms,
            tail_read_elapsed_ms=metrics.tail_read_elapsed_ms,
            total_elapsed_ms=metrics.total_elapsed_ms,
            scanned_file_count=metrics.scanned_file_count,
            scanned_bytes=metrics.scanned_bytes,
            filtered_line_count=metrics.filtered_line_count,
            online_count=len(snapshot.online_serials),
            status_count=len(snapshot.status_rows),
            log_count=len(snapshot.log_records),
        )

    @staticmethod
    def _clone_snapshot(
        snapshot: DeviceRefreshSnapshot,
        metrics: RefreshMetrics | None = None,
        error_text: str | None = None,
    ) -> DeviceRefreshSnapshot:
        """复制快照，避免 UI 直接持有内部缓存对象。"""
        # 复制指标对象，保证调用方修改不影响缓存。
        source_metrics = metrics or snapshot.metrics
        # 手动复制 slots dataclass，避免依赖 __dict__。
        target_metrics = RefreshMetrics(
            adb_elapsed_ms=source_metrics.adb_elapsed_ms,
            status_elapsed_ms=source_metrics.status_elapsed_ms,
            log_read_elapsed_ms=source_metrics.log_read_elapsed_ms,
            queue_wait_elapsed_ms=source_metrics.queue_wait_elapsed_ms,
            total_elapsed_ms=source_metrics.total_elapsed_ms,
            cache_hit=source_metrics.cache_hit,
            snapshot_age_ms=source_metrics.snapshot_age_ms,
            scanned_file_count=source_metrics.scanned_file_count,
            scanned_bytes=source_metrics.scanned_bytes,
            tail_read_elapsed_ms=source_metrics.tail_read_elapsed_ms,
            filtered_line_count=source_metrics.filtered_line_count,
        )
        # 返回完整副本。
        return DeviceRefreshSnapshot(
            online_serials=set(snapshot.online_serials),
            status_rows=[dict(row) for row in snapshot.status_rows],
            log_records=list(snapshot.log_records),
            metrics=target_metrics,
            error_text=snapshot.error_text if error_text is None else str(error_text),
            refreshed_at=float(snapshot.refreshed_at),
        )

    @staticmethod
    def _parse_text_payload(raw_line: str) -> str | None:
        """从 JSONL 行中提取 text 字段。"""
        # 先标准化原始行文本。
        raw = str(raw_line or "").strip()
        # 空行直接返回空值。
        if raw == "":
            return None
        try:
            # 解析结构化 JSON 日志。
            obj = json.loads(raw)
        except Exception:
            # 非 JSON 行直接丢弃。
            return None
        # 仅接受对象结构。
        if not isinstance(obj, dict):
            return None
        # 没有 text 字段时直接跳过。
        if "text" not in obj:
            return None
        # 返回 text 文本。
        return str(obj.get("text", "")).strip()

    @staticmethod
    def _extract_message_text(text_payload: str) -> str:
        """把日志 text 字段转换成 UI 展示正文。"""
        # 统一标准化日志文本。
        payload = str(text_payload or "").strip()
        # 空值直接返回空字符串。
        if payload == "":
            return ""
        # 命中标准前缀格式时，仅保留消息正文。
        if " - " in payload:
            payload = payload.split(" - ", 1)[1].strip()
        # 把多行消息压成单行，避免列表高度频繁抖动。
        return " ".join(payload.splitlines()).strip()

    @staticmethod
    def _extract_sort_key(text_payload: str, fallback_index: int) -> str:
        """为日志记录提取稳定排序键。"""
        # 读取原始文本。
        raw = str(text_payload or "")
        # 命中标准时间前缀时，直接用毫秒级时间片做排序键。
        if len(raw) >= 23 and raw[4:5] == "-" and raw[7:8] == "-" and raw[10:11] == " ":
            return raw[:23]
        # 否则回退到输入顺序，保证排序稳定。
        return f"zzzz-{int(fallback_index):09d}"

    @staticmethod
    def _extract_display_time(text_payload: str) -> str:
        """提取日志展示时间。"""
        # 读取原始文本。
        raw = str(text_payload or "").strip()
        # 标准时间前缀命中时返回 HH:MM:SS.mmm。
        if len(raw) >= 23 and raw[4:5] == "-" and raw[7:8] == "-" and raw[10:11] == " ":
            return raw[11:23]
        # 非标准行返回占位时间。
        return "--:--:--.---"

    @staticmethod
    def _is_open_settings_log(text_payload: str) -> bool:
        """判断是否属于 task.open_settings 组件日志。"""
        # 统一读取日志文本。
        payload = str(text_payload or "")
        # 仅保留 open_settings 相关日志。
        return "component=task.open_settings" in payload or 'component="task.open_settings"' in payload

    def _load_latest_log_records(self, limit: int) -> tuple[list[tuple[str, str]], dict[str, Any]]:
        """读取最新日志快照，并返回附加诊断信息。"""
        # 记录尾读流程起点。
        tail_started_at = time.monotonic()
        # 定位运行期 JSON 日志目录。
        log_dir = Path(JSON_LOG_DIR)
        # 日志目录不存在时直接返回空结果。
        if not log_dir.exists():
            return [], {
                "scanned_file_count": 0,
                "scanned_bytes": 0,
                "tail_read_elapsed_ms": 0,
                "filtered_line_count": 0,
            }

        # 收集所有可展示日志记录。
        entries: list[tuple[str, str, str]] = []
        # 统计本轮扫描的日志文件数。
        scanned_file_count = 0
        # 统计本轮尾读累计扫描字节数。
        scanned_bytes = 0
        # 统计命中过滤条件的行数。
        filtered_line_count = 0
        # 非标准行回退索引。
        fallback_index = 0

        # 定义安全取 mtime 的小函数，避免日志轮转时 stat 抛错。
        def _safe_mtime(path: Path) -> float:
            try:
                # 返回文件 mtime。
                return float(path.stat().st_mtime)
            except Exception:
                # 异常时回退 0，保证排序稳定。
                return 0.0

        # 选出最近修改的若干个 jsonl 文件。
        selected_paths = sorted(
            [path for path in log_dir.glob("*.jsonl") if path.is_file()],
            key=_safe_mtime,
            reverse=True,
        )[:DEVICE_LOG_SCAN_MAX_FILES]

        # 遍历选中的日志文件。
        for path in selected_paths:
            try:
                # 读取当前文件尾部行和扫描字节数。
                tail_lines, bytes_read = self._tail_lines_from_end(
                    path=path,
                    max_lines=DEVICE_LOG_TAIL_PER_FILE,
                    max_bytes=DEVICE_LOG_TAIL_MAX_BYTES,
                )
                # 追加累计扫描字节数。
                scanned_bytes += bytes_read
                # 追加扫描文件数。
                scanned_file_count += 1
                # 逐行过滤并提取日志记录。
                for raw_line in tail_lines:
                    payload = self._parse_text_payload(raw_line)
                    if payload is None:
                        continue
                    if not self._is_open_settings_log(payload):
                        continue
                    message = self._extract_message_text(payload)
                    if message == "":
                        continue
                    filtered_line_count += 1
                    entries.append(
                        (
                            self._extract_sort_key(payload, fallback_index),
                            self._extract_display_time(payload),
                            message,
                        )
                    )
                    fallback_index += 1
            except Exception:
                # 单文件读取失败时仅记日志，不影响其它文件。
                log.exception("设备刷新协调器读取日志文件失败", path=str(path))

        # 按排序键升序排列，最后截取最新 N 条。
        entries.sort(key=lambda item: item[0])
        # 计算尾读耗时。
        tail_read_elapsed_ms = int((time.monotonic() - tail_started_at) * 1000)
        # 返回日志记录和本轮诊断信息。
        return (
            [(display_time, message) for _, display_time, message in entries[-max(1, int(limit)) :]],
            {
                "scanned_file_count": scanned_file_count,
                "scanned_bytes": scanned_bytes,
                "tail_read_elapsed_ms": tail_read_elapsed_ms,
                "filtered_line_count": filtered_line_count,
            },
        )

    @staticmethod
    def _tail_lines_from_end(path: Path, max_lines: int, max_bytes: int) -> tuple[list[str], int]:
        """从文件尾部按块回读，避免整文件顺序扫描。"""
        # 标准化最大行数。
        target_lines = max(1, int(max_lines))
        # 标准化最大扫描字节数。
        target_bytes = max(1, int(max_bytes))
        # 记录本轮累计读取字节数。
        read_bytes = 0
        # 记录已拼接的尾部字节块。
        chunks: list[bytes] = []
        # 保存“上一轮是否已拿到开头边界”的标记。
        reached_file_head = False

        # 以二进制只读打开文件，便于从尾部按块 seek。
        with path.open("rb") as file_obj:
            # 先跳到文件尾部，读取总大小。
            file_obj.seek(0, 2)
            file_size = file_obj.tell()
            # 记录当前还需向前扫描的游标位置。
            position = file_size
            # 反向按块扫描，直到拿到足够多的换行或命中扫描上限。
            while position > 0 and read_bytes < target_bytes:
                # 计算本轮实际块大小。
                chunk_size = min(8192, position, target_bytes - read_bytes)
                # 游标向前移动一块。
                position -= chunk_size
                # 定位到本轮块起点。
                file_obj.seek(position)
                # 读取当前块内容。
                chunk = file_obj.read(chunk_size)
                # 头插到 chunks，保持最终拼接顺序正确。
                chunks.insert(0, chunk)
                # 追加累计字节数。
                read_bytes += len(chunk)
                # 命中足够多换行后即可停止继续往前扫。
                if b"".join(chunks).count(b"\n") >= target_lines:
                    break
            # 游标退到 0 时说明已读到文件开头。
            if position == 0:
                reached_file_head = True

        # 拼接所有已读取字节块。
        combined = b"".join(chunks)
        # 没读到文件开头时，丢掉首个残缺行，避免出现半行 JSON。
        if not reached_file_head and b"\n" in combined:
            combined = combined.split(b"\n", 1)[1]
        # 解码为文本并按行切分。
        lines = combined.decode("utf-8", errors="ignore").splitlines()
        # 仅保留尾部目标行数。
        return lines[-target_lines:], read_bytes

    def _clear_open_settings_logs_sync(self) -> int:
        """清空运行期 JSON 日志里的 open_settings 记录。"""
        # 定位运行期 JSON 日志目录。
        log_dir = Path(JSON_LOG_DIR)
        # 目录不存在时直接返回 0。
        if not log_dir.exists():
            return 0
        # 统计本轮清理条数。
        cleared_count = 0
        # 遍历全部 jsonl 文件。
        for path in sorted(log_dir.glob("*.jsonl")):
            if not path.is_file():
                continue
            try:
                # 保存清理后仍需保留的日志行。
                kept_lines: list[str] = []
                with path.open("r", encoding="utf-8", errors="ignore") as file_obj:
                    for raw_line in file_obj:
                        line = raw_line.rstrip("\n")
                        payload = self._parse_text_payload(line)
                        if payload is not None and self._is_open_settings_log(payload):
                            cleared_count += 1
                            continue
                        kept_lines.append(line)
                with path.open("w", encoding="utf-8") as file_obj:
                    for line in kept_lines:
                        file_obj.write(f"{line}\n")
            except Exception:
                log.exception("设备刷新协调器清空日志文件失败", path=str(path))

        # 清理完成后同步清空最近快照中的日志列表，避免 UI 继续显示旧数据。
        with self._snapshot_lock:
            self._last_snapshot.log_records = []
            self._last_snapshot.error_text = ""
        # 返回总清理条数。
        return cleared_count
