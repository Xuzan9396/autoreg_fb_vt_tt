# Flet 打包说明（AutoVT）

本文按当前仓库结构编写：入口脚本是根目录 `main.py`，依赖由 `uv` 管理，Flet 版本为 `0.80.5`。

## 1. 先做环境检查

```bash
cd /Users/admin/go/src/autovt
uv sync
uvx --from flet==0.80.5 flet doctor
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
cd /Users/admin/go/src/autovt
uv sync
uvx --from flet==0.80.5 flet doctor
POCO_ANDROID_DIR="$(uv run python -c 'from pathlib import Path; import poco; print((Path(poco.__file__).resolve().parent / "drivers" / "android").as_posix())')"
AIRTEST_ANDROID_DIR="$(uv run python -c 'from pathlib import Path; import airtest; print((Path(airtest.__file__).resolve().parent / "core" / "android").as_posix())')"
uv flet pack main.py \
  -n AutoVT \
  -i assets/icon.icns \
  --add-data "assets:assets" \
  --add-data "images:images" \
  --add-data "adb/mac:adb/mac" \
  --add-data "${POCO_ANDROID_DIR}:poco/drivers/android" \
  --add-data "${AIRTEST_ANDROID_DIR}:airtest/core/android" \
  --yes -v
```

## 1.3 `uvx` 和 `uv run` 的区别（你这次遇到的点）

1. `uvx --from flet==0.80.5 flet ...`：
   - 每次临时准备可执行的 `flet` CLI，最稳，不依赖当前 `.venv` 里是否已有 CLI。
2. `uv run flet ...`：
   - 依赖当前项目环境里已经有可执行 `flet`，否则会报 `Failed to spawn: flet`。
3. 如果你想坚持用 `uv run`，建议写成：

```bash
uv run --with flet==0.80.5 flet pack main.py -n AutoVT -i assets/icon.icns --yes -v
```

结论：CI 和本地都建议优先 `uvx --from flet==0.80.5`，可重复性更好。

说明：

1. `--add-data "assets:assets"`：把运行时图标与静态资源一并打进包。
2. `--add-data "images:images"`：把业务模板图资源一并打进包。
3. `--add-data "adb/mac:adb/mac"`（mac）/`--add-data "adb/windows;adb/windows"`（windows）：仅打包当前平台 adb，减小体积并避免混入另一平台二进制。
4. `--add-data "${POCO_ANDROID_DIR}:poco/drivers/android"`：打包 Poco Android 整目录资源（包含 `pocoservice-debug.apk`，并覆盖后续新增资源）。
5. `--add-data "${AIRTEST_ANDROID_DIR}:airtest/core/android"`：打包 Airtest Android 整目录资源（包含 `Yosemite.apk`、`*.jar`、`stf_libs/*.so` 等依赖）。
6. `--yes`：自动确认覆盖提示，适合 CI。

产物一般在：

1. `dist/AutoVT.app`
2. `build/`（PyInstaller 临时构建目录，可忽略）

## 2. 两种打包方式怎么选

1. `flet pack`：桌面打包（底层 PyInstaller），当前项目推荐主线，稳定性更高。
2. `flet build`：Flutter 原生构建，功能更多，但你当前项目在多进程场景下问题更多，先不作为主线。

## 3. 快速桌面打包（推荐先用这个）

### macOS

```bash
uvx --from flet==0.80.5 flet pack main.py -n AutoVT -i assets/icon.icns --yes
```

### Windows

```bash
uvx --from flet==0.80.5 flet pack main.py -n AutoVT -i assets/icon.ico --yes
```

### Linux

```bash
uvx --from flet==0.80.5 flet pack main.py -n AutoVT -i assets/icon.png --yes
```

打包产物默认在 `dist/` 目录。

注意：
- `build/` 目录是 PyInstaller 临时构建目录。
- 像 `build/AutoVT/AutoVT.pkg` 这种文件并不是 macOS 安装包（不能双击安装），它是内部压缩产物。
- 真正可运行的是 `dist/AutoVT.app`。

## 4. 可选：flet build（备用方案）

### macOS 示例

```bash
uvx --from flet==0.80.5 flet build macos . \
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
uvx --from flet==0.80.5 flet build windows . \
  --project autovt \
  --product "AutoVT 管理后台" \
  --org com.autovt \
  --yes
```

### Android APK 示例

```bash
uvx --from flet==0.80.5 flet build apk . \
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

之后命令可以简化为（如果你走 `flet build` 备用方案）：

```bash
uvx --from flet==0.80.5 flet build macos . --yes
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
cd /Users/admin/go/src/autovt
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
uvx --from flet==0.80.5 flet pack main.py -n AutoVT -i assets/icon.icns --yes
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
3. `flet pack` 失败：先执行 `uvx --from flet==0.80.5 flet doctor`，再检查 `--add-data` 路径是否存在。
4. `Generated app icons ✅` 后失败：图标生成成功不代表构建完成，继续看后续真实失败点。
5. `10 packages have newer versions...`：这是依赖提示，不是本次失败原因，可先忽略。
6. `CocoaPods out of date`：通常是警告，不一定阻塞 macOS 构建；先把 `xcodebuild` 问题修好再处理。
7. `flutter/dart not on PATH`：对 `flet pack` 一般不是阻塞项。
8. Android `cmdline-tools` / `android-licenses`：做 macOS 桌面打包时可忽略。
9. Windows 打包后若报 `pocoservice-debug.apk` 不存在：属于 `poco` 资源文件未被打入包。当前 workflow 已自动解析并注入 `poco/drivers/android` 整目录，并在构建前校验 apk 存在，请使用最新 workflow 重新打 tag 构建。

### 9.1 打包后出现 2 个窗口（一个空白，一个正常）

现象：

1. 启动 `.app` 后会出现一个正常主窗口。
2. 同时出现一个空白窗口（标题常为 `AutoVT`）。

根因（多进程 + 打包场景）：

1. 项目 worker 进程使用 `multiprocessing` 的 `spawn`。
2. 打包为 `.app` 后，子进程启动时如果没有 `freeze_support()`，可能再次执行主入口。
3. 子进程误走 GUI 启动路径，会额外拉起空白窗口。

当前仓库修复：

1. `main.py` 已在 `main()` 开头加入 `mp.freeze_support()`。
2. 重新打包后，子进程会正确进入多进程分支，不再重复创建 GUI 窗口。

验证建议：

```bash
POCO_ANDROID_DIR="$(uv run python -c 'from pathlib import Path; import poco; print((Path(poco.__file__).resolve().parent / "drivers" / "android").as_posix())')"
AIRTEST_ANDROID_DIR="$(uv run python -c 'from pathlib import Path; import airtest; print((Path(airtest.__file__).resolve().parent / "core" / "android").as_posix())')"
uvx --from flet==0.80.5 flet pack main.py \
  -n AutoVT \
  -i assets/icon.icns \
  --add-data "assets:assets" \
  --add-data "images:images" \
  --add-data "adb/mac:adb/mac" \
  --add-data "${POCO_ANDROID_DIR}:poco/drivers/android" \
  --add-data "${AIRTEST_ANDROID_DIR}:airtest/core/android" \
  --yes -v
```

### 9.2 打包后提示“未找到 adb 命令”

现象：

1. `uv run python main.py` 正常。
2. 双击 `.app` 后提示 `未找到 adb 命令`。

根因：

1. 终端启动会加载你的 shell 环境（`PATH`、`ANDROID_HOME` 等）。
2. Finder 启动 `.app` 不会完整加载这些变量，导致 `adb` 命令名无法解析。

当前仓库修复（跨平台）：

1. `autovt/adb.py` 新增自动解析逻辑：
   - 优先读取 `AUTOVT_ADB_BIN`。
   - 默认优先尝试项目内置 `adb/mac/platform-tools/adb`（mac）和 `adb/windows/platform-tools/adb.exe`（windows）。
   - 自动尝试 `ANDROID_SDK_ROOT/ANDROID_HOME`。
   - 按平台尝试常见默认路径（macOS / Windows / Linux）。
   - 最后兜底 Airtest 内置 adb。
2. `autovt/runtime.py` 在设备初始化前会先执行 adb 环境初始化，保证 worker 进程也可用。

手工覆盖（推荐）：

- macOS:

```bash
export AUTOVT_ADB_BIN="/Users/admin/Library/Android/sdk/platform-tools/adb"
```

- Windows（PowerShell）:

```powershell
$env:AUTOVT_ADB_BIN="C:\Users\<用户名>\AppData\Local\Android\Sdk\platform-tools\adb.exe"
```

说明：

1. 只要设置 `AUTOVT_ADB_BIN`，应用会优先使用该路径。
2. Windows 后续也可直接复用这套机制，不需要改代码。

### 9.3 打包后出现双窗口（主窗口 + 空白窗口）

现象：

1. 启动后有一个正常主窗口。
2. 同时多出一个标题为 `AutoVT` 的空白窗口。

根因：

1. 打包运行时如果未进入 Flet embedded 模式，可能同时出现宿主窗口和额外自启窗口。

当前仓库修复：

1. `autovt/gui/app.py` 在 `run_gui()` 里会自动识别打包态（macOS `.app` / Windows `.exe`）。
2. 识别到打包态后自动设置 `FLET_PLATFORM`，避免双窗口。
3. `autovt/multiproc/manager.py` 对子进程启动增加了“秒退探针”，若子进程立即退出会直接回显 `exit_code`，方便定位。

注意：

1. 该逻辑只在打包态生效，不影响你本地 `uv run python main.py` 调试。

### 9.4 打包后如何关闭 Airtest Debug、日志在哪里

1. 打包运行（`.app` / `.exe`）：
   - Airtest/Poco debug 日志永久关闭（仅保留 warning 及以上）。
   - `AUTOVT_AIRTEST_DEBUG` 在打包态无效，不可重新开启。
2. 源码运行（`uv run python main.py`）：
   - 可用 `AUTOVT_AIRTEST_DEBUG=1` 临时开启 debug（仅建议排查问题时使用）。
3. 日志文件路径（JSONL）：
   - macOS：`~/Library/Application Support/AutoVT/log/json/`
   - Windows：`%APPDATA%\\AutoVT\\log\\json\\`
4. 常见文件：
   - `manager.jsonl`：主控进程日志
   - `<设备序列号>.jsonl`：每台设备 worker 日志

## 10. GitHub Actions（Tag 触发桌面打包）

当前仓库已新增工作流：

- `.github/workflows/flet-macos-tag.yml`

触发方式：

```bash
git tag v0.1.0
git push origin v0.1.0
```

工作流动作：

1. `build-macos`：在 `macos-14` 上执行 `flet pack`，产出 `AutoVT-macos-arm64-<tag>.zip`。
2. `build-windows`：在 `windows-latest` 上执行 `flet pack`，产出 `AutoVT-windows-x64-<tag>.zip`。
3. 两个平台都会生成对应 `.sha256` 文件并上传为 Artifacts。
4. `release` job 会汇总两个平台产物并附加到当前 tag 的 GitHub Release。
5. `adb` 资源按平台拆分打包：macOS 仅打 `adb/mac`，Windows 仅打 `adb/windows`。
6. Android 自动化依赖资源会一并打包：`poco/drivers/android` 与 `airtest/core/android` 整目录（含 `pocoservice-debug.apk`、`Yosemite.apk`）。

补充：

1. GitHub Actions 不会复用你本机 shell 环境，所以本机 `PATH` 类问题通常不会直接复现到 CI。
2. 但“代码级问题”（例如多进程入口处理不当导致双窗口）在本机和 CI 打包产物中都可能出现，因此仍需在代码里修复。
3. Windows workflow 固定 `Python 3.12`，macOS workflow 使用 `Python 3.13`。
4. 如果遇到 Windows `exit code 3221225477`（`PyInstaller.isolated._parent.SubprocessDiedError`），优先确认没有把 Windows job 改回 `Python 3.13`。
5. 当前仓库 `.python-version` 是 `3.13`，Windows job 里必须给 `uv run` 显式传 `--python`（或设置 `UV_PYTHON`），否则可能被带回 `3.13` 导致再次崩溃。
