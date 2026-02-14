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
    # 创建主控管理器（负责子进程生命周期）。
    manager = DeviceProcessManager(loop_interval_sec=loop_interval_sec)
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
                if len(args) == 1 and args[0] == "all":
                    for msg in manager.start_all():
                        print(msg)
                else:
                    for serial in args:
                        print(manager.start_worker(serial))
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
                for msg in manager.restart_worker(args[0]):
                    print(msg)
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
        for msg in manager.stop_all():
            print(msg)
            log.info("停止子进程结果", message=msg)
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
