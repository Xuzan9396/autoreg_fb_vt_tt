import argparse  # 导入参数解析库，用于支持 GUI/CLI 模式切换。
import multiprocessing as mp  # 导入多进程模块，用于 frozen 场景下正确接管子进程启动。

from autovt.cli import run_console  # 导入命令行主循环函数，作为可选回退模式。
from autovt.gui import run_gui  # 导入 GUI 启动函数，作为默认入口模式。
from autovt.logs import get_logger, setup_logging  # 导入日志初始化和日志对象工厂。
from autovt.settings import WORKER_LOOP_INTERVAL_SEC  # 导入默认 worker 循环间隔配置。

log = get_logger("main")  # 创建 main 模块日志对象。


def parse_args() -> argparse.Namespace:  # 解析主入口参数。
    parser = argparse.ArgumentParser(description="autovt 主入口（默认 GUI）")  # 创建参数解析器。
    parser.add_argument(  # 添加运行模式参数。
        "--mode",  # 参数名。
        choices=["gui", "cli"],  # 仅允许 gui 或 cli。
        default="gui",  # 默认使用 GUI。
        help="运行模式：gui 或 cli（默认 gui）",  # 参数帮助说明。
    )
    parser.add_argument(  # 添加 worker 循环间隔参数。
        "--interval",  # 参数名。
        type=float,  # 参数类型。
        default=WORKER_LOOP_INTERVAL_SEC,  # 默认值使用 settings 配置。
        help="worker 每轮任务完成后的等待秒数",  # 参数帮助说明。
    )
    return parser.parse_args()  # 返回解析结果。


def main() -> None:  # 主函数：根据模式分发到 GUI 或 CLI。
    mp.freeze_support()  # 兼容打包后的多进程子进程入口，避免子进程误进入 GUI 主流程导致重复窗口。
    args = parse_args()  # 解析启动参数。
    setup_logging(process_role="manager")  # 初始化主进程日志配置。
    log.info("主入口启动", mode=args.mode, interval=args.interval)  # 记录启动参数日志。

    if args.mode == "cli":  # 用户显式指定 CLI 模式时走命令行主循环。
        run_console(loop_interval_sec=args.interval)  # 启动命令行交互主控。
        return  # CLI 结束后返回。

    run_gui(loop_interval_sec=args.interval)  # 默认启动 GUI 主控。


if __name__ == "__main__":  # 仅在直接执行 main.py 时触发启动逻辑。
    main()  # 执行主入口函数。
    
