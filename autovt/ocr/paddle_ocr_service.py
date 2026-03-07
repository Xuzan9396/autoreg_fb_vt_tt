"""PaddleOCR 服务封装。"""

from __future__ import annotations

# 导入 inspect，用于按构造函数签名做新旧版本参数兼容。
import inspect
# 导入 json，用于序列化 OCR 结果给调试和测试使用。
import json
# 导入路径对象，统一处理图片路径。
from pathlib import Path
# 导入 Any，便于表达动态结构的 OCR 返回值。
from typing import Any

# 导入项目统一日志方法，保证异常进入统一日志链路。
from autovt.logs import get_logger

# 创建 OCR 模块日志对象。
log = get_logger("ocr.paddle")


class PaddleOcrService:
    """PaddleOCR 识别服务。"""

    def __init__(
        self,
        lang: str = "ch",
        use_doc_orientation_classify: bool = False,
        use_doc_unwarping: bool = False,
        use_textline_orientation: bool = False,
    ) -> None:
        # 保存语言参数，便于日志和后续实例重建使用。
        self._lang = str(lang or "ch").strip() or "ch"
        # 保存文档方向分类参数。
        self._use_doc_orientation_classify = bool(use_doc_orientation_classify)
        # 保存文档去扭曲参数。
        self._use_doc_unwarping = bool(use_doc_unwarping)
        # 保存文本行方向分类参数。
        self._use_textline_orientation = bool(use_textline_orientation)
        # 初始化 PaddleOCR 引擎实例。
        self._engine = self._build_engine()

    def _build_engine(self) -> Any:
        """构建 PaddleOCR 引擎，并兼容不同版本参数。"""
        try:
            # 延迟导入 PaddleOCR，避免模块导入时硬依赖失败直接打断整个程序。
            from paddleocr import PaddleOCR
        except Exception as exc:
            # 记录导入失败异常，便于排查依赖安装问题。
            log.exception("导入 PaddleOCR 失败", error=str(exc))
            # 继续抛出异常，让调用方明确感知初始化失败。
            raise

        # 读取构造函数签名，避免传入当前版本不支持的参数。
        init_sig = inspect.signature(PaddleOCR)
        # 提取所有支持参数名称集合。
        supported_names = set(init_sig.parameters.keys())
        # 初始化构造参数字典。
        kwargs: dict[str, Any] = {}
        # 新旧版本都常见支持 lang 参数。
        if "lang" in supported_names:
            # 注入识别语言参数。
            kwargs["lang"] = self._lang
        # 新版支持文档方向分类参数时注入。
        if "use_doc_orientation_classify" in supported_names:
            # 注入文档方向分类开关。
            kwargs["use_doc_orientation_classify"] = self._use_doc_orientation_classify
        # 新版支持文档去扭曲参数时注入。
        if "use_doc_unwarping" in supported_names:
            # 注入文档去扭曲开关。
            kwargs["use_doc_unwarping"] = self._use_doc_unwarping
        # 新版支持文本行方向参数时注入。
        if "use_textline_orientation" in supported_names:
            # 注入文本行方向开关。
            kwargs["use_textline_orientation"] = self._use_textline_orientation
        # 旧版通常使用 use_angle_cls 控制方向分类。
        if "use_angle_cls" in supported_names and "use_doc_orientation_classify" not in kwargs:
            # 旧版场景下优先开启角度分类，提升识别稳定性。
            kwargs["use_angle_cls"] = True
        # 支持 show_log 参数时关闭 Paddle 内部控制台噪音。
        if "show_log" in supported_names:
            # 关闭 Paddle 内部冗余日志输出。
            kwargs["show_log"] = False

        try:
            # 根据兼容参数创建 PaddleOCR 实例。
            engine = PaddleOCR(**kwargs)
        except Exception as exc:
            # 记录引擎构建失败日志，附带参数便于排查版本兼容问题。
            log.exception("初始化 PaddleOCR 引擎失败", kwargs=kwargs, error=str(exc))
            # 抛出异常交由上层决定如何处理。
            raise

        # 记录引擎创建成功日志。
        log.info("初始化 PaddleOCR 引擎成功", lang=self._lang, kwargs=kwargs)
        # 返回构建完成的引擎对象。
        return engine

    def recognize_image(self, image_path: str | Path) -> dict[str, Any]:
        """识别单张图片并返回标准结果。"""
        # 复用通用识别入口，兼容路径和资源对象两类输入。
        return self.recognize(image_source=image_path)

    def recognize(self, image_source: Any) -> dict[str, Any]:
        """识别图片资源并返回标准结果。"""
        # 解析输入资源，统一成 OCR 引擎可消费的入参。
        image_input, image_ref = self._normalize_image_source(image_source=image_source)
        # 执行 OCR 并拿到原始结果。
        raw_result = self._run_ocr(image_input=image_input, image_ref=image_ref)
        # 从原始结果中提取纯文本列表。
        texts = self._extract_texts(raw_result)
        # 把原始结果转成可 JSON 序列化结构。
        json_safe_raw = self._to_json_safe(raw_result)
        # 记录识别完成日志。
        log.info("OCR 识别完成", image_ref=image_ref, text_count=len(texts))
        # 返回标准化识别结果。
        return {
            "image_path": image_ref,
            "texts": texts,
            "count": len(texts),
            "raw": json_safe_raw,
        }

    def find_text_click_point(
        self,
        image_source: Any,
        target_text: str,
        min_score: float = 0.0,
    ) -> dict[str, Any]:
        """在 OCR 结果中查找包含目标文本的项，并返回可点击中心坐标。"""
        # 先做一次 OCR 识别，得到结构化结果。
        ocr_result = self.recognize(image_source=image_source)
        # 基于识别结果执行文本查找并返回点击点。
        return self.find_text_click_point_from_result(
            ocr_result=ocr_result,
            target_text=target_text,
            min_score=min_score,
        )

    def find_text_click_point_from_result(
        self,
        ocr_result: dict[str, Any],
        target_text: str,
        min_score: float = 0.0,
    ) -> dict[str, Any]:
        """基于已有 OCR 结果查找包含目标文本的项，并返回可点击中心坐标。"""
        # 规整目标文本，避免空白输入导致误判。
        normalized_target = str(target_text or "").strip()
        # 目标文本为空时直接报错并记录日志。
        if normalized_target == "":
            # 记录参数错误日志。
            log.error("目标文本为空，无法执行 OCR 文本匹配")
            # 抛出参数异常给调用方。
            raise ValueError("target_text 不能为空")
        # 确保识别结果是字典结构，避免调用方传错类型。
        if not isinstance(ocr_result, dict):
            # 记录参数类型错误日志。
            log.error("OCR 结果类型错误", result_type=str(type(ocr_result)))
            # 抛出参数异常提示调用方。
            raise ValueError("ocr_result 必须为 dict")
        # 从 OCR 原始结构中提取候选框和文本。
        candidates = self._extract_candidates(ocr_result.get("raw"))
        # 初始化命中结果容器。
        matched_candidates: list[dict[str, Any]] = []
        # 遍历候选项并筛选包含目标文本的结果。
        for candidate in candidates:
            # 读取候选文本。
            candidate_text = str(candidate.get("text") or "")
            # 读取候选置信度。
            candidate_score = float(candidate.get("score") or 0.0)
            # 非包含关系直接跳过。
            if normalized_target not in candidate_text:
                continue
            # 低于阈值的结果直接跳过。
            if candidate_score < float(min_score):
                continue
            # 把命中结果加入容器，后续按分数挑选最佳项。
            matched_candidates.append(candidate)
        # 无命中结果时返回 found=False。
        if len(matched_candidates) == 0:
            # 记录未命中日志，便于任务排查。
            log.info(
                "OCR 文本未命中",
                target_text=normalized_target,
                image_ref=ocr_result.get("image_path"),
                min_score=float(min_score),
            )
            # 返回未命中结构。
            return {
                "found": False,
                "target_text": normalized_target,
                "point": None,
                "text": "",
                "score": 0.0,
                "box": [],
                "image_path": ocr_result.get("image_path"),
            }
        # 按置信度挑选最佳命中项，保证同图多命中时优先高可信结果。
        best_candidate = max(matched_candidates, key=lambda item: float(item.get("score") or 0.0))
        # 计算最佳候选框的中心点坐标。
        center_point = self._calculate_center_point(best_candidate.get("box"))
        # 记录命中日志，便于复盘点击坐标来源。
        log.info(
            "OCR 文本命中",
            target_text=normalized_target,
            matched_text=best_candidate.get("text"),
            score=float(best_candidate.get("score") or 0.0),
            point=center_point,
            image_ref=ocr_result.get("image_path"),
        )
        # 返回命中结构，其中 point 可直接用于 Airtest touch((x, y))。
        return {
            "found": True,
            "target_text": normalized_target,
            "point": center_point,
            "text": str(best_candidate.get("text") or ""),
            "score": float(best_candidate.get("score") or 0.0),
            "box": best_candidate.get("box") or [],
            "image_path": ocr_result.get("image_path"),
        }

    def contains_text_with_point(
        self,
        image_source: Any,
        target_text: str,
        min_score: float = 0.0,
    ) -> tuple[bool, tuple[int, int] | None]:
        """返回“是否命中 + 中心点坐标”的轻量结果。"""
        # 调用详细匹配方法统一处理识别与坐标计算逻辑。
        result = self.find_text_click_point(
            image_source=image_source,
            target_text=target_text,
            min_score=min_score,
        )
        # 返回布尔命中状态和可点击坐标点。
        return bool(result.get("found")), result.get("point")

    def _normalize_image_source(self, image_source: Any) -> tuple[Any, str]:
        """把图片输入统一转换为 OCR 可处理的资源。"""
        # 直接传字符串或 Path 时按文件路径处理。
        if isinstance(image_source, (str, Path)):
            # 展开并规范化绝对路径。
            resolved_path = Path(image_source).expanduser().resolve()
            # 路径不存在时记录日志并抛错。
            if not resolved_path.exists():
                # 记录路径不存在错误。
                log.error("OCR 图片不存在", image_path=str(resolved_path))
                # 抛出文件不存在异常。
                raise FileNotFoundError(f"OCR 图片不存在: {resolved_path}")
            # 路径不是普通文件时记录日志并抛错。
            if not resolved_path.is_file():
                # 记录路径类型错误。
                log.error("OCR 图片路径不是文件", image_path=str(resolved_path))
                # 抛出运行时异常提示调用方。
                raise RuntimeError(f"OCR 图片路径不是文件: {resolved_path}")
            # 返回 OCR 可直接消费的图片路径字符串和日志标识。
            return str(resolved_path), str(resolved_path)
        # 传入 Airtest snapshot 返回对象时，优先识别其中的 screen 路径。
        if isinstance(image_source, dict):
            # 提取 snapshot 风格的 screen 字段。
            screen_path = image_source.get("screen")
            # screen 字段存在时递归按路径解析。
            if isinstance(screen_path, (str, Path)):
                # 复用路径处理逻辑并返回结果。
                return self._normalize_image_source(screen_path)
            # 提取通用 image 字段，兼容直接传内存图片对象。
            inline_image = image_source.get("image")
            # image 字段存在时直接作为 OCR 输入。
            if inline_image is not None:
                # 返回内存图片对象和日志标识。
                return inline_image, "<snapshot:image>"
            # 资源字典未包含可识别字段时记录错误并抛错。
            log.error("OCR 资源字典缺少可识别字段", keys=list(image_source.keys()))
            # 抛出参数异常提示调用方。
            raise ValueError("OCR 资源字典必须包含 'screen' 或 'image' 字段")
        # 空输入直接报错，避免误触发底层异常。
        if image_source is None:
            # 记录空输入错误。
            log.error("OCR 图片资源为空")
            # 抛出参数异常。
            raise ValueError("image_source 不能为空")
        # 其他对象按内存资源透传给 OCR 引擎（如 numpy.ndarray/PIL 图像）。
        return image_source, f"<memory:{type(image_source).__name__}>"

    def _run_ocr(self, image_input: Any, image_ref: str) -> Any:
        """执行 OCR 推理并返回原始结果。"""

        try:
            # 新版本优先走 predict 接口。
            if hasattr(self._engine, "predict"):
                # 执行新版预测接口并得到原始结果。
                raw_result = self._engine.predict(image_input)
            # 旧版本回退到 ocr 接口。
            elif hasattr(self._engine, "ocr"):
                # 执行旧版 OCR 接口并得到原始结果。
                raw_result = self._engine.ocr(image_input, cls=True)
            else:
                # 当前引擎没有可用接口时抛出明确错误。
                raise RuntimeError("当前 PaddleOCR 版本不包含可用的识别接口（predict/ocr）")
        except Exception as exc:
            # 记录 OCR 执行失败日志，便于排查模型和环境异常。
            log.exception("执行 OCR 识别失败", image_ref=image_ref, error=str(exc))
            # 抛出异常由上层处理。
            raise
        # 返回原始 OCR 推理结果。
        return raw_result

    def _extract_candidates(self, raw_result: Any) -> list[dict[str, Any]]:
        """从 OCR 原始结果中提取候选文本框。"""
        # 把输入结果转成 JSON 安全结构，方便统一递归处理。
        normalized = self._to_json_safe(raw_result)
        # 初始化候选容器。
        sink: list[dict[str, Any]] = []
        # 递归提取候选项。
        self._collect_candidates(node=normalized, sink=sink)
        # 返回提取出的候选项列表。
        return sink

    def _collect_candidates(self, node: Any, sink: list[dict[str, Any]]) -> None:
        """递归提取候选文本、置信度和多边形框。"""
        # 字典节点先处理常见新结构，再递归其子节点。
        if isinstance(node, dict):
            # 提取新版结构中的文本列表。
            rec_texts = node.get("rec_texts")
            # 提取新版结构中的分数列表。
            rec_scores = node.get("rec_scores")
            # 提取新版结构中的检测框列表。
            rec_boxes = node.get("dt_polys") or node.get("det_polys") or node.get("rec_polys")
            # 命中新版批量字段时按索引配对提取候选项。
            if isinstance(rec_texts, list):
                # 遍历全部文本并配对分数和坐标框。
                for index, text in enumerate(rec_texts):
                    # 读取当前索引的分数。
                    score_value = rec_scores[index] if isinstance(rec_scores, list) and index < len(rec_scores) else 0.0
                    # 读取当前索引的检测框。
                    box_value = rec_boxes[index] if isinstance(rec_boxes, list) and index < len(rec_boxes) else []
                    # 追加当前候选项到容器。
                    self._append_candidate(sink=sink, text=text, score=score_value, box=box_value)
            # 提取单条结构里的文本字段。
            direct_text = node.get("text")
            # 提取单条结构里的分数字段。
            direct_score = node.get("score")
            # 提取单条结构里的框字段。
            direct_box = node.get("box") or node.get("points") or node.get("polygon") or node.get("poly")
            # 命中单条结构时追加候选项。
            if direct_text is not None and direct_box is not None:
                # 追加单条候选项到容器。
                self._append_candidate(sink=sink, text=direct_text, score=direct_score, box=direct_box)
            # 继续递归全部子节点，覆盖更深层嵌套结构。
            for value in node.values():
                # 递归处理当前子节点。
                self._collect_candidates(node=value, sink=sink)
            # 当前分支处理完成后返回。
            return
        # 列表或元组节点处理旧版 [box, [text, score]] 结构。
        if isinstance(node, (list, tuple)):
            # 命中旧版结构时直接追加候选项。
            if (
                len(node) >= 2
                and self._is_polygon_points(node[0])
                and isinstance(node[1], (list, tuple))
                and len(node[1]) >= 1
                and isinstance(node[1][0], str)
            ):
                # 读取旧版结构文本值。
                old_text = node[1][0]
                # 读取旧版结构分数值。
                old_score = node[1][1] if len(node[1]) >= 2 else 0.0
                # 读取旧版结构框坐标。
                old_box = node[0]
                # 追加旧版候选项到容器。
                self._append_candidate(sink=sink, text=old_text, score=old_score, box=old_box)
            # 递归遍历当前序列全部元素。
            for item in node:
                # 递归处理当前元素。
                self._collect_candidates(node=item, sink=sink)
            # 当前分支处理完成后返回。
            return

    def _append_candidate(self, sink: list[dict[str, Any]], text: Any, score: Any, box: Any) -> None:
        """追加候选项到容器。"""
        # 规整文本值。
        normalized_text = str(text or "").strip()
        # 空文本直接跳过。
        if normalized_text == "":
            # 空文本无需入库，直接返回。
            return
        # 规整分数值。
        normalized_score = self._safe_float(score)
        # 规整候选框坐标。
        normalized_box = self._normalize_polygon_points(box)
        # 候选框无效时直接跳过。
        if len(normalized_box) == 0:
            # 无坐标无法计算点击点，直接返回。
            return
        # 把候选项写入容器。
        sink.append(
            {
                "text": normalized_text,
                "score": normalized_score,
                "box": normalized_box,
            }
        )

    def _normalize_polygon_points(self, box: Any) -> list[list[float]]:
        """把任意框结构归一为 [[x, y], ...]。"""
        # 先转成 JSON 安全结构，兼容 numpy/paddle tensor 等对象。
        normalized_box = self._to_json_safe(box)
        # 非序列结构直接返回空列表。
        if not isinstance(normalized_box, (list, tuple)):
            # 返回空坐标，表示无法用于点击。
            return []
        # 初始化坐标点容器。
        points: list[list[float]] = []
        # 遍历当前框中的全部点。
        for point in normalized_box:
            # 非二维点直接跳过。
            if not isinstance(point, (list, tuple)) or len(point) < 2:
                continue
            # 提取 x 坐标。
            x_value = self._safe_float(point[0])
            # 提取 y 坐标。
            y_value = self._safe_float(point[1])
            # 把归一化坐标写入容器。
            points.append([x_value, y_value])
        # 点数不足时视为无效框。
        if len(points) == 0:
            # 返回空框结果。
            return []
        # 返回归一化后的坐标框。
        return points

    def _is_polygon_points(self, value: Any) -> bool:
        """判断输入是否为可用的多边形点列表。"""
        # 先归一化坐标框。
        points = self._normalize_polygon_points(value)
        # 有至少三个点时认为是可用多边形。
        return len(points) >= 3

    def _calculate_center_point(self, box: Any) -> tuple[int, int] | None:
        """计算多边形框中心点。"""
        # 归一化输入框为标准点列表。
        points = self._normalize_polygon_points(box)
        # 无有效点时返回空坐标。
        if len(points) == 0:
            # 返回空值提示调用方不可点击。
            return None
        # 累加全部点的 x 值。
        sum_x = sum(float(item[0]) for item in points)
        # 累加全部点的 y 值。
        sum_y = sum(float(item[1]) for item in points)
        # 计算中心 x（四舍五入）。
        center_x = int(round(sum_x / float(len(points))))
        # 计算中心 y（四舍五入）。
        center_y = int(round(sum_y / float(len(points))))
        # 返回中心点坐标，可直接传给 Airtest touch。
        return center_x, center_y

    def _safe_float(self, value: Any, default: float = 0.0) -> float:
        """安全地把输入转换为浮点数。"""
        try:
            # 尝试直接转换为浮点数。
            return float(value)
        except Exception:
            # 转换失败时返回默认值。
            return float(default)

    def _extract_texts(self, raw_result: Any) -> list[str]:
        """从 OCR 原始结构中递归提取文本。"""
        # 先把结果转为可递归的基础结构。
        normalized = self._to_json_safe(raw_result)
        # 初始化文本收集容器。
        buffer: list[str] = []
        # 递归提取文本。
        self._collect_texts(normalized, buffer)
        # 使用集合跟踪去重，避免重复文本污染结果。
        seen: set[str] = set()
        # 初始化去重后文本列表。
        deduped: list[str] = []
        # 遍历提取到的所有文本。
        for text in buffer:
            # 清理文本首尾空白。
            clean_text = str(text or "").strip()
            # 空文本直接跳过。
            if clean_text == "":
                continue
            # 已出现过则跳过，保留首次顺序。
            if clean_text in seen:
                continue
            # 把文本加入去重集合。
            seen.add(clean_text)
            # 把文本写入最终输出列表。
            deduped.append(clean_text)
        # 返回去重后的文本列表。
        return deduped

    def _collect_texts(self, node: Any, sink: list[str]) -> None:
        """递归收集文本字段。"""
        # 字符串节点直接加入收集器。
        if isinstance(node, str):
            # 记录字符串节点文本。
            sink.append(node)
            # 当前分支处理完成，直接返回。
            return
        # 字典节点按 key/value 继续递归。
        if isinstance(node, dict):
            # 遍历全部键值对。
            for key, value in node.items():
                # 先递归处理值，覆盖通用结构。
                self._collect_texts(value, sink)
                # 额外识别常见文本键，优先提取其值。
                low_key = str(key).strip().lower()
                # 命中文本相关字段时再次抽取，提升兼容性。
                if low_key in {"text", "texts", "rec_text", "rec_texts", "transcription"}:
                    # 递归处理文本字段内容。
                    self._collect_texts(value, sink)
            # 字典分支处理完成，直接返回。
            return
        # 列表或元组节点逐项递归。
        if isinstance(node, (list, tuple)):
            # 兼容旧版输出 [box, [text, score]] 结构。
            if (
                len(node) >= 2
                and isinstance(node[1], (list, tuple))
                and len(node[1]) >= 1
                and isinstance(node[1][0], str)
            ):
                # 直接提取旧版结构中的文本值。
                sink.append(str(node[1][0]))
            # 继续遍历递归全部子节点。
            for item in node:
                # 递归处理当前子节点。
                self._collect_texts(item, sink)
            # 列表分支处理完成，直接返回。
            return

    def _to_json_safe(self, node: Any) -> Any:
        """把任意对象转换为 JSON 友好结构。"""
        # 基础类型直接返回。
        if node is None or isinstance(node, (str, int, float, bool)):
            # 返回原始基础值。
            return node
        # 路径对象统一转字符串。
        if isinstance(node, Path):
            # 返回路径字符串表示。
            return str(node)
        # 字典对象递归转换 key/value。
        if isinstance(node, dict):
            # 返回递归转换后的字典。
            return {str(key): self._to_json_safe(value) for key, value in node.items()}
        # 序列对象递归转换每个元素。
        if isinstance(node, (list, tuple, set)):
            # 返回递归转换后的列表。
            return [self._to_json_safe(item) for item in node]
        # 对象实现 to_dict 时优先使用该方法。
        if hasattr(node, "to_dict") and callable(getattr(node, "to_dict")):
            try:
                # 调用 to_dict 并继续递归转换。
                return self._to_json_safe(node.to_dict())
            except Exception:
                # 转换失败时继续尝试其他兼容路径。
                pass
        # 对象实现 json() 时尝试直接读取 JSON 文本。
        if hasattr(node, "json"):
            try:
                # 提取 json 属性值或方法返回值。
                raw_json = node.json() if callable(getattr(node, "json")) else node.json
                # 字符串 JSON 反序列化后递归转换。
                if isinstance(raw_json, str):
                    return self._to_json_safe(json.loads(raw_json))
                # 非字符串 JSON 对象继续递归转换。
                return self._to_json_safe(raw_json)
            except Exception:
                # 该路径失败时继续尝试兜底方案。
                pass
        # 普通对象带 __dict__ 时按属性递归转换。
        if hasattr(node, "__dict__"):
            try:
                # 把对象属性字典递归转换。
                return self._to_json_safe(vars(node))
            except Exception:
                # 属性读取失败时回退到字符串兜底。
                pass
        # 最终兜底使用 repr，保证结果可序列化。
        return repr(node)
