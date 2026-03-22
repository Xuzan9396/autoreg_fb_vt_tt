# 版本 10: 设备页VT按钮

> 创建时间: 2026-03-22 12:32:44
> 最后更新: 2026-03-22 12:38:27
> 状态: 待执行

## 需求描述
设备列表增加一键卸载 VT、一键安装 VT，设备列表单设备卡片里也要增加对应按钮。当前已经有一键删除 FB、一键安装 FB，以及单设备删除 FB、安装 FB，可以参考同样模式，主要落在 `autovt/gui/device_tab.py`。

## 技术方案
沿用现有 Facebook 按钮和 `DeviceProcessManager` 的对称实现，在 `manager.py` 平移出 Vinted 包名、安装包路径解析、单设备安装/卸载、批量安装/卸载方法，然后在 `device_tab.py` 顶部操作区和单设备卡片按钮区各补两颗 VT 按钮。安装包继续走外置 `apks/vinted.apk`，设备运行中时维持与 Facebook 相同的禁止安装/卸载保护，并同步更新项目结构文档说明。

## 文件变更清单

**修改:**
- `autovt/gui/device_tab.py:160-176` — 顶部工具栏新增“`一键删除VT` / `一键安装VT`”按钮（现: 这里只有 FB 批量按钮和输入法按钮）
- `autovt/gui/device_tab.py:591-608` — 单设备卡片新增“`删除VT` / `安装VT`”按钮（现: 这里只有 FB 和输入法按钮）
- `autovt/multiproc/manager.py:32-39` — 新增 Vinted 包名和 `apks/vinted.apk` 相对路径常量（现: 只有 Facebook / Yosemite 常量）
- `autovt/multiproc/manager.py:325-353` — 新增 `_resolve_vinted_apk_path()`（现: 只有 `_resolve_facebook_apk_path()` 和 `_resolve_yosemite_apk_path()`）
- `autovt/multiproc/manager.py:446-538` — 参照 Facebook 逻辑新增 `uninstall_vinted_for_device()`、`install_vinted_for_device()`、`uninstall_vinted_all()`、`install_vinted_all()`（现: 只有 Facebook 对应方法）
- `doc/project_structure.md:72-72` — 更新 GUI 主控说明，补设备页 VT 安装/卸载按钮（现: 只写 FB + 输入法）
- `doc/project_structure.md:80-80` — 更新 manager 说明，补 Vinted 批量安装/卸载能力（现: 只写 Facebook + Yosemite）
- `/Users/admin/go/src/go_cookies/autovt/doc/project_structure.md:63-63` — 同步 GUI 主控说明，补 VT 按钮
- `/Users/admin/go/src/go_cookies/autovt/doc/project_structure.md:72-72` — 同步 manager 能力说明，补 VT 安装/卸载

**依赖:**
- 无新增第三方依赖

## Todolist

- [x] 1. 补齐 manager 的 Vinted 包常量和 apk 路径解析

  **Files:**
  - Modify: `autovt/multiproc/manager.py:32-39`
  - Modify: `autovt/multiproc/manager.py:325-353`

  ```text
  change details:
  修改: autovt/multiproc/manager.py:32-39 (现: 只定义 FACEBOOK_PACKAGE_NAME、FACEBOOK_APK_RELATIVE_PATH、YOSEMITE_PACKAGE_NAME、YOSEMITE_APK_RELATIVE_PATH)
  - 新增 VINTED_PACKAGE_NAME = "fr.vinted"
  - 新增 VINTED_APK_RELATIVE_PATH = Path("apks") / "vinted.apk"

  修改: autovt/multiproc/manager.py:325-353 (现: 只有 _resolve_facebook_apk_path() 解析 facebook.apk)
  - 新增 _resolve_vinted_apk_path()
  - 候选路径顺序与 _resolve_facebook_apk_path() 保持一致
  - 报错文案改为 vinted.apk
  ```
----------------------
- [x] 2. 实现 manager 的单设备 Vinted 安装/卸载动作

  **Files:**
  - Modify: `autovt/multiproc/manager.py:446-518`

  ```text
  change details:
  修改: autovt/multiproc/manager.py:446-518 (现: 这里是 uninstall_facebook_for_device() / install_facebook_for_device())
  - 新增 uninstall_vinted_for_device(serial)
  - 新增 install_vinted_for_device(serial)
  - 运行中设备继续禁止操作，返回文案与 Facebook 逻辑一致，只替换为 VT/Vinted
  - 卸载前先 force-stop fr.vinted
  - 安装时使用 apks/vinted.apk，继续沿用 -r -d
  - success / 未安装 / 执行异常 / 非 success 的日志与返回文案保持当前风格
  ```
----------------------
- [x] 3. 实现 manager 的批量 Vinted 安装/卸载动作

  **Files:**
  - Modify: `autovt/multiproc/manager.py:520-538`

  ```text
  change details:
  修改: autovt/multiproc/manager.py:520-538 (现: 这里只有 uninstall_facebook_all() / install_facebook_all())
  - 新增 uninstall_vinted_all()
  - 新增 install_vinted_all()
  - 无在线设备时继续返回“未检测到在线设备（adb devices 为空）”
  - 批量方法内部逐台复用单设备 Vinted 方法，不重复写 adb 逻辑
  ```
----------------------
- [x] 4. 在设备页顶部增加 VT 批量按钮

  **Files:**
  - Modify: `autovt/gui/device_tab.py:160-176`

  ```text
  change details:
  修改: autovt/gui/device_tab.py:160-176 (现: 顶部有“一键删除FB”“一键安装FB”“一键安装输入法”)
  - 在 FB 批量按钮旁新增“一键删除VT”
  - 在 FB 批量按钮旁新增“一键安装VT”
  - on_click 分别调用 manager.uninstall_vinted_all / manager.install_vinted_all
  - _run_action 标题文案保持与现有风格一致
  ```
----------------------
- [x] 5. 在单设备卡片增加 VT 按钮

  **Files:**
  - Modify: `autovt/gui/device_tab.py:591-608`

  ```text
  change details:
  修改: autovt/gui/device_tab.py:591-608 (现: 单设备卡片有“删除FB”“安装FB”“安装输入法”)
  - 新增“删除VT”按钮
  - 新增“安装VT”按钮
  - on_click 分别调用 manager.uninstall_vinted_for_device(serial) / manager.install_vinted_for_device(serial)
  - 按钮位置和图标风格与 Facebook 按钮保持一致
  ```
----------------------
- [x] 6. 同步项目结构文档

  **Files:**
  - Modify: `doc/project_structure.md:72-72`
  - Modify: `doc/project_structure.md:80-80`
  - Modify: `/Users/admin/go/src/go_cookies/autovt/doc/project_structure.md:63-63`
  - Modify: `/Users/admin/go/src/go_cookies/autovt/doc/project_structure.md:72-72`

  ```text
  change details:
  修改: doc/project_structure.md:72-72 (现: GUI 说明只写 Facebook 批量/单设备按钮和输入法按钮)
  - 补充设备页支持 Vinted 安装/卸载批量按钮和单设备按钮
  - 补充包名 fr.vinted 和安装包 apks/vinted.apk

  修改: doc/project_structure.md:80-80 (现: manager 说明只写 install_facebook_all / uninstall_facebook_all 和 Yosemite)
  - 补充 install_vinted_all / uninstall_vinted_all / install_vinted_for_device / uninstall_vinted_for_device

  修改: /Users/admin/go/src/go_cookies/autovt/doc/project_structure.md:63-63, 72-72
  - 对外部同步文档做同样更新
  - 保持两份文档描述一致
  ```

## 总结

共 6 条任务，涉及 4 个文件（修改 4 个，无新建），预计改动约 90 行。

1. 在 `manager.py` 增加 Vinted 包常量和 `vinted.apk` 路径解析。
2. 在 manager 内平移出单设备与批量的 Vinted 安装/卸载动作。
3. 在 `device_tab.py` 顶部工具栏新增两颗 VT 批量按钮。
4. 在设备卡片按钮区新增两颗 VT 单设备按钮。
5. 继续复用现有 `_run_action`、ADB 返回文案和“运行中禁止操作”保护，不引入新交互模式。
6. 同步两份项目结构文档，避免功能有了但文档没跟上。

## 变更记录
- 2026-03-22 12:32:44 初始创建
- 2026-03-22 12:35:21 完成 #1 补齐 manager 的 Vinted 包常量和 apk 路径解析
- 2026-03-22 12:35:59 完成 #2 实现 manager 的单设备 Vinted 安装/卸载动作
- 2026-03-22 12:36:28 完成 #3 实现 manager 的批量 Vinted 安装/卸载动作
- 2026-03-22 12:37:02 完成 #4 在设备页顶部增加 VT 批量按钮
- 2026-03-22 12:37:32 完成 #5 在单设备卡片增加 VT 按钮
- 2026-03-22 12:38:27 完成 #6 同步项目结构文档
