import argparse
import shlex
import time

from autovt.logs import get_logger, setup_logging
from autovt.multiproc.manager import DeviceProcessManager
from autovt.settings import WORKER_LOOP_INTERVAL_SEC

log = get_logger("cli")


HELP_TEXT = """
命令列表:
  help                         显示帮助
  devices                      查看在线设备(adb devices)
  start all                    启动所有在线设备进程
  start <serial> [serial...]   启动指定设备进程
  stop all                     停止所有设备进程
  stop <serial> [serial...]    停止指定设备进程
  restart <serial>             重启设备进程
  pause all|<serial...>        暂停自动循环
  resume all|<serial...>       恢复自动循环
  status                       查看进程状态
  quit / exit                  退出主控（会先 stop all）
""".strip()


def _print_events(manager: DeviceProcessManager) -> None:
    # 刷新并输出所有子进程事件。
    events = manager.drain_events()
    for event in events:
        # 把事件时间戳转成可读时间。
        ts = time.strftime("%H:%M:%S", time.localtime(float(event["time"])))
        print(f"[{ts}] {event['serial']} {event['state']}: {event['detail']}")
        log.info(
            "子进程事件",
            serial=event["serial"],
            state=event["state"],
            detail=event["detail"],
            event_time=event["time"],
        )


def _print_status(manager: DeviceProcessManager) -> None:
    # 打印当前所有运行中设备的状态表。
    rows = manager.status()
    if not rows:
        print("当前没有运行中的设备进程。")
        return

    print("serial | pid | alive | state | email | detail")
    for row in rows:
        print(
            f"{row['serial']} | {row['pid']} | {row['alive']} | "
            f"{row['state']} | {row.get('email_account', '')} | {row['detail']}"
        )


def _apply_command(
    manager: DeviceProcessManager,
    command: str,
    targets: list[str],
) -> None:
    # 对指定设备（或 all）发送控制命令。
    if not targets:
        print("缺少目标设备。")
        return

    if len(targets) == 1 and targets[0] == "all":
        results = manager.send_command_all(command)
    else:
        results = [manager.send_command(serial, command) for serial in targets]

    for msg in results:
        print(msg)


def _show_devices(manager: DeviceProcessManager) -> None:
    # 打印当前 adb 在线设备列表。
    serials = manager.list_online_devices()
    if not serials:
        print("当前无在线设备。")
        return

    print("在线设备:")
    for serial in serials:
        print(f"- {serial}")


def run_console(loop_interval_sec: float) -> None:
    try:
        # 创建主控管理器（负责子进程生命周期）。
        manager = DeviceProcessManager(loop_interval_sec=loop_interval_sec)
    except Exception as exc:
        # 记录主控启动失败堆栈，避免只在终端看到裸异常。
        log.exception("CLI 主控初始化失败", interval=loop_interval_sec, error=str(exc))
        # 把失败原因打印到终端，便于用户直接感知。
        print(f"主控启动失败: {exc}")
        # 直接结束当前启动流程。
        return
    print("autovt 多设备主控已启动，输入 help 查看命令。")
    log.info("主控已启动", interval=loop_interval_sec)

    try:
        # REPL 主循环：持续读取用户命令。
        while True:
            # 每轮先打印事件，避免错过子进程状态变化。
            _print_events(manager)
            # 读取一行命令。
            line = input("autovt> ").strip()
            if not line:
                continue

            # 用 shell 风格拆分参数（支持引号）。
            argv = shlex.split(line)
            cmd = argv[0].lower()
            args = argv[1:]
            log.info("收到命令", cmd=cmd, args=args)

            if cmd in {"quit", "exit"}:
                # 退出主控。
                break
            if cmd == "help":
                # 打印帮助。
                print(HELP_TEXT)
                continue
            if cmd == "devices":
                try:
                    # 查看在线设备。
                    _show_devices(manager)
                except Exception as exc:
                    print(f"读取设备失败: {exc}")
                continue
            if cmd == "start":
                # 启动设备进程：支持 all 或 serial 列表。
                if not args:
                    print("用法: start all | start <serial> [serial...]")
                    continue
                try:
                    if len(args) == 1 and args[0] == "all":
                        for msg in manager.start_all():
                            print(msg)
                    else:
                        for serial in args:
                            print(manager.start_worker(serial))
                except Exception as exc:
                    # 记录启动设备异常，避免一次失败打断整个 REPL。
                    log.exception("CLI 启动设备失败", args=args, error=str(exc))
                    # 把失败信息打印到终端，便于继续后续命令。
                    print(f"启动设备失败: {exc}")
                continue
            if cmd == "stop":
                # 停止设备进程：支持 all 或 serial 列表。
                if not args:
                    print("用法: stop all | stop <serial> [serial...]")
                    continue
                if len(args) == 1 and args[0] == "all":
                    for msg in manager.stop_all():
                        print(msg)
                else:
                    for serial in args:
                        print(manager.stop_worker(serial))
                continue
            if cmd == "restart":
                # 重启单个设备进程。
                if len(args) != 1:
                    print("用法: restart <serial>")
                    continue
                try:
                    for msg in manager.restart_worker(args[0]):
                        print(msg)
                except Exception as exc:
                    # 记录重启设备异常，避免一次失败打断整个 REPL。
                    log.exception("CLI 重启设备失败", serial=args[0], error=str(exc))
                    # 把失败信息打印到终端，便于用户继续操作。
                    print(f"重启设备失败: {exc}")
                continue
            if cmd == "pause":
                # 暂停自动循环（不会结束进程）。
                _apply_command(manager, "pause", args)
                continue
            if cmd == "resume":
                # 恢复自动循环。
                _apply_command(manager, "resume", args)
                continue
            if cmd == "status":
                # 查看当前状态。
                _print_status(manager)
                continue

            print(f"未知命令: {cmd}")
            log.warning("未知命令", cmd=cmd, args=args)
    except KeyboardInterrupt:
        # Ctrl+C 时走统一退出流程。
        print("\n收到 Ctrl+C，准备退出。")
        log.warning("收到 Ctrl+C，准备退出")
    finally:
        # 退出前先回收所有子进程，避免遗留僵尸进程。
        print("正在停止所有子进程...")
        try:
            # 执行 stop_all，并逐条输出停止结果。
            for msg in manager.stop_all():
                # 把停止结果输出到控制台。
                print(msg)
                # 记录停止结果到日志。
                log.info("停止子进程结果", message=msg)
        except Exception as exc:
            # stop_all 失败时记录日志，但继续执行后续全局释放。
            log.exception("CLI 退出清理失败（stop_all）", error=str(exc))
            # 把异常摘要打印到控制台，便于用户感知。
            print(f"停止所有子进程失败: {exc}")
        # 退出前再做一次全局账号释放，兜底回退残留的“使用中”状态。
        released = manager.reset_all_running_accounts(reason="cli_shutdown")
        # 把释放结果输出到控制台，便于确认退出清理是否完成。
        print(f"已兜底释放运行中账号: {released}")
        # 记录退出兜底释放结果到日志。
        log.info("CLI 退出兜底释放运行中账号完成", released=released)
        # 关闭 manager 持有的数据库连接和资源。
        manager.close()
        print("主控已退出。")
        log.info("主控已退出")


def parse_args() -> argparse.Namespace:
    # 解析启动参数（目前只保留循环间隔）。
    parser = argparse.ArgumentParser(description="autovt 多设备多进程主控")
    parser.add_argument(
        "--interval",
        type=float,
        default=WORKER_LOOP_INTERVAL_SEC,
        help="每轮任务完成后的等待秒数",
    )
    return parser.parse_args()


def main() -> None:
    # CLI 入口：解析参数并启动控制台。
    args = parse_args()
    setup_logging(process_role="manager")
    log.info("日志初始化已完成")
    run_console(loop_interval_sec=args.interval)
