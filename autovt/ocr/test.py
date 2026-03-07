"""OCR 单图识别测试脚本。"""

from __future__ import annotations

# 导入参数解析模块，支持命令行传参测试。
import argparse
# 导入 json 模块，支持把识别结果输出成 JSON 文本。
import json
# 导入 sys 模块，用于控制进程退出码。
import sys
# 导入路径模块，统一处理图片与输出文件路径。
from pathlib import Path

# 计算当前脚本绝对路径，便于兼容“进入目录后直接执行 test.py”。
CURRENT_FILE = Path(__file__).resolve()
# 计算项目根目录路径（.../autovt）。
PROJECT_ROOT = CURRENT_FILE.parents[2]
# 当项目根目录不在导入路径时主动补齐。
if str(PROJECT_ROOT) not in sys.path:
    # 把项目根目录加入导入路径首位。
    sys.path.insert(0, str(PROJECT_ROOT))

# 导入统一日志对象，保证异常会进入项目日志体系。
from autovt.logs import get_logger
# 导入 PaddleOCR 服务封装。
from autovt.ocr import PaddleOcrService

# 创建 OCR 测试日志对象。
log = get_logger("ocr.test")


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    # 创建命令行参数解析器。
    parser = argparse.ArgumentParser(description="PaddleOCR 单图识别测试脚本")
    # 注册待识别图片参数。
    parser.add_argument("--image", required=True, help="待识别图片路径")
    # 注册识别语言参数。
    parser.add_argument("--lang", default="ch", help="识别语言，例如 ch/en")
    # 注册是否输出完整 JSON 的开关参数。
    parser.add_argument("--dump-json", action="store_true", help="输出完整 JSON 结果")
    # 注册 JSON 输出文件路径参数。
    parser.add_argument("--output", default="", help="JSON 输出文件路径（可选）")
    # 注册按文本查找点击点参数。
    parser.add_argument("--find-text", default="", help="按包含关系查找文本并返回中心点击坐标")
    # 注册文本匹配最小分数参数。
    parser.add_argument("--min-score", type=float, default=0.0, help="文本匹配最小置信度阈值")
    # 解析并返回参数对象。
    return parser.parse_args()


def main() -> int:
    """执行 OCR 测试主流程。"""
    # 解析命令行参数。
    args = parse_args()
    # 解析输入图片路径。
    image_path = Path(str(args.image)).expanduser().resolve()
    # 图片不存在时直接失败返回。
    if not image_path.exists():
        # 记录图片不存在错误日志。
        log.error("OCR 测试图片不存在", image_path=str(image_path))
        # 输出可读错误信息到终端。
        print(f"OCR 测试图片不存在: {image_path}")
        # 返回非零退出码。
        return 2
    try:
        # 初始化 OCR 服务实例。
        service = PaddleOcrService(lang=str(args.lang or "ch"))
        # 执行图片识别并拿到结构化结果。
        result = service.recognize_image(image_path=image_path)
    except Exception as exc:
        # 记录识别流程异常日志。
        log.exception("执行 OCR 测试失败", image_path=str(image_path), error=str(exc))
        # 输出可读错误到终端。
        print(f"OCR 测试失败: {exc}")
        # 返回失败退出码。
        return 1

    # 输出识别图片路径。
    print(f"识别图片: {result['image_path']}")
    # 输出识别文本总数。
    print(f"识别文本数量: {result['count']}")
    # 遍历输出识别文本列表。
    for index, text in enumerate(result["texts"], start=1):
        # 按编号输出每一条识别文本。
        print(f"{index:03d}. {text}")

    # 只有显式要求时才输出完整 JSON。
    if bool(args.dump_json):
        # 生成 JSON 字符串。
        json_text = json.dumps(result, ensure_ascii=False, indent=2)
        # 指定了输出文件路径时写文件。
        if str(args.output or "").strip() != "":
            # 解析输出文件路径。
            output_path = Path(str(args.output)).expanduser().resolve()
            # 确保父目录存在，避免写文件失败。
            output_path.parent.mkdir(parents=True, exist_ok=True)
            # 写入 JSON 文件。
            output_path.write_text(json_text, encoding="utf-8")
            # 输出写入完成提示。
            print(f"JSON 结果已写入: {output_path}")
        else:
            # 未指定输出文件时直接打印 JSON。
            print(json_text)

    # 显式要求查找文本时，输出命中状态与中心点击坐标。
    if str(args.find_text or "").strip() != "":
        # 调用 OCR 查找方法并拿到命中结果。
        find_result = service.find_text_click_point_from_result(
            ocr_result=result,
            target_text=str(args.find_text),
            min_score=float(args.min_score),
        )
        # 输出命中状态。
        print(f"文本命中: {find_result['found']}")
        # 输出命中文本。
        print(f"命中文本: {find_result['text']}")
        # 输出命中分数。
        print(f"命中分数: {find_result['score']}")
        # 输出可点击中心点坐标。
        print(f"点击坐标: {find_result['point']}")

    # 主流程成功返回 0。
    return 0


if __name__ == "__main__":
    # 使用系统退出码返回执行结果。
    raise SystemExit(main())
