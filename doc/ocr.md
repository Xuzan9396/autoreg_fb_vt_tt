# OCR 安装与用法

## 安装

在项目根目录执行：

```bash
cd /Users/admin/go/src/autovt
uv sync
```

如果只想手动补 OCR 相关依赖，可执行：

```bash
cd /Users/admin/go/src/autovt
uv add paddlepaddle>=3.2.0 paddleocr==2.7.3 standard-imghdr>=3.13.0
uv sync
```

## 用法

在 `autovt/ocr` 目录单独测试单图识别：

```bash
cd /Users/admin/go/src/autovt/autovt/ocr
uv run python test.py --image /Users/admin/go/src/autovt/autovt/ocr/screen.png --lang ch --dump-json
```

按包含关系查找文本并返回中心点击坐标：

```bash
cd /Users/admin/go/src/autovt/autovt/ocr
uv run python test.py --image /Users/admin/go/src/autovt/autovt/ocr/screen.png --lang ch --find-text 田 --min-score 0.5
uv run python test.py --image /Users/admin/go/src/autovt/autovt/ocr/screen2.png --lang fr --find-text "Cette Page n'est pas disponible" --min-score 0.5



```

常用参数：

- `--image`：待识别图片路径（必填）
- `--lang`：识别语言，默认 `ch`
- `--dump-json`：打印完整 JSON 结果
- `--output`：把 JSON 结果写入指定文件
- `--find-text`：按“包含”关系查找目标文本并输出中心点击坐标
- `--min-score`：文本匹配最小置信度阈值
