#!/usr/bin/env bash
# patch_flet_app.sh — 修补 Flet 内嵌 Flutter 客户端的名称和图标
#
# Flet 运行时会解压 Flet.app 到 ~/.flet/client/ 目录，
# 该 .app 的 Info.plist 中 CFBundleName 默认为 "Flet"，
# 导致 macOS 菜单栏显示 "Flet" 而非自定义应用名。
#
# 用法: ./scripts/patch_flet_app.sh [APP_NAME] [ICON_ICNS_PATH]
# 示例: ./scripts/patch_flet_app.sh AutoVT assets/icon.icns

set -euo pipefail

APP_NAME="${1:-AutoVT}"
ICON_SRC="${2:-assets/icon.icns}"
FLET_VERSION=$(python -c "import flet_desktop.version; print(flet_desktop.version.version)" 2>/dev/null || echo "0.80.5")
FLET_APP_DIR="$HOME/.flet/client/flet-desktop-${FLET_VERSION}/Flet.app"

if [ ! -d "$FLET_APP_DIR" ]; then
    echo "⚠️  Flet.app 未找到: $FLET_APP_DIR"
    echo "   请先运行一次 'uv run python main.py' 让 Flet 解压客户端，然后再执行此脚本。"
    exit 1
fi

PLIST="$FLET_APP_DIR/Contents/Info.plist"
RESOURCES="$FLET_APP_DIR/Contents/Resources"

echo "🔧 修补 Flet.app (${FLET_APP_DIR})"

# 1. 修改 CFBundleName
echo "   ✏️  CFBundleName: Flet → ${APP_NAME}"
/usr/libexec/PlistBuddy -c "Set :CFBundleName ${APP_NAME}" "$PLIST"

# 2. 修改 CFBundleDisplayName (如果不存在则添加)
if /usr/libexec/PlistBuddy -c "Print :CFBundleDisplayName" "$PLIST" &>/dev/null; then
    /usr/libexec/PlistBuddy -c "Set :CFBundleDisplayName ${APP_NAME}" "$PLIST"
else
    /usr/libexec/PlistBuddy -c "Add :CFBundleDisplayName string ${APP_NAME}" "$PLIST"
fi
echo "   ✏️  CFBundleDisplayName: ${APP_NAME}"

# 3. 替换图标
if [ -f "$ICON_SRC" ]; then
    cp "$ICON_SRC" "$RESOURCES/AppIcon.icns"
    echo "   🎨 图标已替换: ${ICON_SRC} → AppIcon.icns"
else
    echo "   ⚠️  图标文件未找到: ${ICON_SRC}，跳过图标替换"
fi

# 4. 清除 macOS 图标缓存（可选，推荐重启后生效）
echo "   🗑️  清除图标缓存..."
sudo rm -rf /Library/Caches/com.apple.iconservices.store 2>/dev/null || true
killall Dock 2>/dev/null || true

echo "✅ 修补完成! 菜单栏将显示 '${APP_NAME}' 和自定义图标。"
