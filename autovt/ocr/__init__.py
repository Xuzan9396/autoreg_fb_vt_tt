"""OCR 模块导出。"""

# 导出 PaddleOCR 服务类，供外部按统一入口调用。
from autovt.ocr.paddle_ocr_service import PaddleOcrService

__all__ = ["PaddleOcrService"]
