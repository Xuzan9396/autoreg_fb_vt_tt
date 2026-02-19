# 导入参数解析库，用于支持 GUI/CLI 模式切换。
import argparse
# 导入多进程模块，用于 frozen 场景下正确接管子进程启动。
import multiprocessing as mp

# 导入默认 worker 循环间隔配置。
from autovt.settings import WORKER_LOOP_INTERVAL_SEC


# 解析主入口参数。
def parse_args() -> argparse.Namespace:
    # 创建参数解析器。
    parser = argparse.ArgumentParser(description="autovt 主入口（默认 GUI）")
    # 添加运行模式参数。
    parser.add_argument(
        # 参数名。
        "--mode",
        # 仅允许 gui 或 cli。
        choices=["gui", "cli"],
        # 默认使用 GUI。
        default="gui",
        # 参数帮助说明。
        help="运行模式：gui 或 cli（默认 gui）",
    )
    # 添加 worker 循环间隔参数。
    parser.add_argument(
        # 参数名。
        "--interval",
        # 参数类型。
        type=float,
        # 默认值使用 settings 配置。
        default=WORKER_LOOP_INTERVAL_SEC,
        # 参数帮助说明。
        help="worker 每轮任务完成后的等待秒数",
    )
    # 返回解析结果。
    return parser.parse_args()


# 主函数：根据模式分发到 GUI 或 CLI。
def main() -> None:
    # 尽早调用 freeze_support：官方推荐在冻结程序里尽早执行，避免子进程误走主程序逻辑。
    mp.freeze_support()

    # 延后导入重型模块：确保子进程在 freeze_support 分流后，不会先触发 GUI/日志初始化副作用。
    # 导入命令行主循环函数，作为可选回退模式。
    from autovt.cli import run_console
    # 导入 GUI 启动函数，作为默认入口模式。
    from autovt.gui import run_gui
    # 导入日志初始化和日志对象工厂。
    from autovt.logs import get_logger, setup_logging

    # 创建 main 模块日志对象（放在延后导入后初始化）。
    log = get_logger("main")
    # 解析启动参数。
    args = parse_args()
    # 初始化主进程日志配置。
    setup_logging(process_role="manager")
    # 记录启动参数日志。
    log.info("主入口启动", mode=args.mode, interval=args.interval)

    # 用户显式指定 CLI 模式时走命令行主循环。
    if args.mode == "cli":
        # 启动命令行交互主控。
        run_console(loop_interval_sec=args.interval)
        # CLI 结束后返回。
        return

    # 默认启动 GUI 主控。
    run_gui(loop_interval_sec=args.interval)


# 仅在直接执行 main.py 时触发启动逻辑。
if __name__ == "__main__":
    # 执行主入口函数。
    main()
    
