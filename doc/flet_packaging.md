# Flet 打包说明（AutoVT）

本文按当前仓库结构编写：入口脚本是根目录 `main.py`，依赖由 `uv` 管理，Flet 版本为 `0.80.5`。

## 1. 先做环境检查

```bash
cd /Users/admin/go/src/go_cookies/autovt
uv sync
uv run flet doctor
```

## 1.1 你这次报错的根因（exit code 72）

报错关键字：

- `xcrun: error: unable to find utility "xcodebuild"`
- `Process exited abnormally with exit code 72`

结论：当前机器没有可用的完整 Xcode 开发环境（仅有 Command Line Tools 不够）。

按顺序执行下面命令修复：

```bash
# 1) 先确认 Xcode 是否安装在 /Applications
ls -ld /Applications/Xcode.app

# 2) 切换开发者目录到完整 Xcode
sudo xcode-select --switch /Applications/Xcode.app/Contents/Developer

# 3) 首次初始化（必须）
sudo xcodebuild -runFirstLaunch

# 4) 接受协议（未接受会继续失败）
sudo xcodebuild -license accept

# 5) 验证 xcodebuild 是否可用
xcrun --find xcodebuild
xcodebuild -version
```

如果第 1 步不存在 `Xcode.app`，先去 App Store 安装 Xcode 完整版（不是 `xcode-select --install` 那个精简工具链）。

## 1.2 macOS 打包一条龙（可直接复制）

```bash
cd /Users/admin/go/src/go_cookies/autovt
uv sync
uv run flet doctor
uv run flet build macos . \
  --project autovt \
  --product "AutoVT" \
  --org com.autovt \
  --bundle-id com.autovt.app \
  --arch arm64 \
  --output build/macos-release \
  --yes -v
```

说明：

1. `.`：明确使用当前目录作为应用路径。
2. `--arch arm64`：Apple Silicon 机器建议先打单架构，速度更快。
3. `--yes`：自动确认下载/安装提示（比如首次下载 Flutter SDK）。
4. `--output`：统一输出到固定目录，方便你找包。

产物一般在：

1. `build/macos-release/`（你指定的输出目录）
2. 或默认 `build/macos/`（没传 `--output` 时）

## 2. 两种打包方式怎么选

1. `flet pack`：桌面快速打包（底层 PyInstaller），适合先出可执行文件验证。
2. `flet build`：官方跨平台构建（macOS / Windows / Linux / Android / iOS / Web），适合正式发布。

官方建议也优先使用 `flet build`（可定制项更多，发布更标准）：
- https://flet.dev/docs/cookbook/packaging-desktop-app/

## 3. 快速桌面打包（推荐先用这个）

### macOS

```bash
uv run flet pack main.py -n AutoVT -i assets/icon.icns --yes
```

### Windows

```bash
uv run flet pack main.py -n AutoVT -i assets/icon.ico --yes
```

### Linux

```bash
uv run flet pack main.py -n AutoVT -i assets/icon.png --yes
```

打包产物默认在 `dist/` 目录。

注意：
- `build/` 目录是 PyInstaller 临时构建目录。
- 像 `build/AutoVT/AutoVT.pkg` 这种文件并不是 macOS 安装包（不能双击安装），它是内部压缩产物。
- 真正可运行的是 `dist/AutoVT.app`。

## 4. 正式构建（flet build）

### macOS 示例

```bash
uv run flet build macos . \
  --project autovt \
  --product "AutoVT" \
  --org com.autovt \
  --bundle-id com.autovt.app \
  --arch arm64 \
  --output build/macos-release \
  --yes
```

### Windows 示例

```bash
uv run flet build windows . \
  --project autovt \
  --product "AutoVT 管理后台" \
  --org com.autovt \
  --yes
```

### Android APK 示例

```bash
uv run flet build apk . \
  --project autovt \
  --product "AutoVT 管理后台" \
  --org com.autovt \
  --arch arm64 \
  --yes
```

构建产物默认在 `build/<平台>/` 目录。

参考（官方）：
- CLI `build`：https://docs.flet.dev/cli/flet-build/
- 发布说明总览：https://docs.flet.dev/publish/

## 5. App 名称在哪里替换

你要区分 3 个“名称”：

1. 页面标题（运行时窗口标题）：
   - `autovt/gui/app.py:60`
   - 当前是 `self.page.title = "AutoVT 管理后台"`
2. 页面头部文案（界面内大标题）：
   - `autovt/gui/app.py:151`
   - 当前是 `ft.Text("AutoVT 管理后台", ...)`
3. 打包元数据名称（安装包/应用信息）：
   - 打包命令参数：`--project`、`--product`（`flet build`）
   - 或 `-n`（`flet pack`）
   - 也可以写入 `pyproject.toml` 的 `[tool.flet]`（见下一节）

## 6. 图标和启动图在哪里替换

### 6.1 `flet pack`（桌面）

图标直接由参数 `-i` 指定：

1. macOS：用 `.icns`
2. Windows：用 `.ico`
3. Linux：用 `.png`

### 6.2 `flet build`（跨平台）

建议在“应用路径”的 `assets` 目录放资源：

1. `assets/icon.png`：应用图标（用于构建流程生成平台图标）
2. `assets/splash_android.png`：Android 启动画面（可选）

当前项目入口在根目录（`main.py`），所以建议放在：

1. `assets/icon.png`
2. `assets/splash_android.png`

注意：项目里的 `images/` 目录是业务自动化图片，不是 Flet 打包图标目录。

## 7. 推荐补充到 pyproject（可选）

为了避免每次命令都写一堆参数，可在 `pyproject.toml` 增加：

```toml
[tool.flet]
org = "com.autovt"
product = "AutoVT 管理后台"
company = "AutoVT"

[tool.flet.app]
path = "."
```

之后命令可以简化为：

```bash
uv run flet build macos . --yes
```

## 8. 你当前遇到的问题（对应修复）

### 8.1 Finder 图标变了，但 Dock 还是 Flet 默认图标

常见原因：

1. `icon.icns` 尺寸层级不完整（macOS 可能回退默认图标）。
2. Dock 图标缓存未刷新。
3. 使用 `flet pack` 时，部分视觉元数据不如 `flet build` 完整。

你当前仓库里的 `assets/icon.icns` 实测只包含两层：`32x32`、`64x64`，缺少常用层级（`16/128/256/512/1024`），建议重做。

### 8.2 推荐的 macOS 图标制作流程

先准备一张 `1024x1024` PNG：`assets/icon.png`，再生成完整 `icon.icns`：

```bash
cd /Users/admin/go/src/go_cookies/autovt
mkdir -p /tmp/autovt.iconset
sips -z 16 16     assets/icon.png --out /tmp/autovt.iconset/icon_16x16.png
sips -z 32 32     assets/icon.png --out /tmp/autovt.iconset/icon_16x16@2x.png
sips -z 32 32     assets/icon.png --out /tmp/autovt.iconset/icon_32x32.png
sips -z 64 64     assets/icon.png --out /tmp/autovt.iconset/icon_32x32@2x.png
sips -z 128 128   assets/icon.png --out /tmp/autovt.iconset/icon_128x128.png
sips -z 256 256   assets/icon.png --out /tmp/autovt.iconset/icon_128x128@2x.png
sips -z 256 256   assets/icon.png --out /tmp/autovt.iconset/icon_256x256.png
sips -z 512 512   assets/icon.png --out /tmp/autovt.iconset/icon_256x256@2x.png
sips -z 512 512   assets/icon.png --out /tmp/autovt.iconset/icon_512x512.png
sips -z 1024 1024 assets/icon.png --out /tmp/autovt.iconset/icon_512x512@2x.png
iconutil -c icns /tmp/autovt.iconset -o assets/icon.icns
```

然后重新打包：

```bash
uv run flet pack main.py -n AutoVT -i assets/icon.icns --yes
```

最后刷新 Dock 缓存（可选）：

```bash
killall Dock
```

### 8.3 Dock 名称怎么改

1. `flet pack`：用 `-n AutoVT`。
2. `flet build`：用 `--product "AutoVT 管理后台"`。
3. 运行时窗口标题：改 `autovt/gui/app.py` 里的 `self.page.title`。

## 9. 常见问题

1. 打包后不是我想要的名称：优先检查 `--product` / `-n` 是否传入。
2. 图标没生效：检查格式是否匹配平台（mac=`.icns`，win=`.ico`，linux=`.png`）。
3. `flet build` 失败：先执行 `uv run flet doctor`，再按提示补齐 Flutter / Xcode / Android SDK。
4. `Generated app icons ✅` 后失败：图标已生成不代表构建完成，继续看后续日志里真实失败点（你这次就是 Xcode 缺失）。
5. `10 packages have newer versions...`：这是依赖提示，不是本次失败原因，可先忽略。
6. `CocoaPods out of date`：通常是警告，不一定阻塞 macOS 构建；先把 `xcodebuild` 问题修好再处理。
