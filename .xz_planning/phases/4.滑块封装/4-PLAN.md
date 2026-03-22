# 版本 4: Vinted滑块

> 创建时间: 2026-03-22 09:22:24  
> 最后更新: 2026-03-22 09:40:04  
> 状态: 待执行

## 需求描述
用户要求把现有 Vinted 滑块代码封装成独立方法，写到 [autovt/tasks/vinted.py](/Users/admin/go/src/autovt/autovt/tasks/vinted.py)；滑块图片使用 [images/fr/vinted/slider.png](/Users/admin/go/src/autovt/images/fr/vinted/slider.png)；执行时先找图，最多等待 10 秒，找到后再滑；方法返回 `True/False` 且补充成功/失败日志；方法需能在 [test.py](/Users/admin/go/src/autovt/test.py) 单独测试；并同步更新外部文档 [project_structure.md](/Users/admin/go/src/go_cookies/autovt/doc/project_structure.md)，同时核对 [flet-macos-tag.yml](/Users/admin/go/src/autovt/.github/workflows/flet-macos-tag.yml) 是否已把该图片目录打包进去。

## 技术方案
当前代码库已经有一条明确做法：继续沿用 `VintedTask(OpenSettingsTask)` 的结构，在 [vinted.py](/Users/admin/go/src/autovt/autovt/tasks/vinted.py) 内新增独立 `vinted_slider` 方法，复用父类已有的图片资源路径解析和异常恢复风格，先构建 `slider.png` 对应 `Template`，最多等待 10 秒命中起点，再执行贝塞尔轨迹滑动；方法内部统一记录 `info/warning/exception` 日志，失败时返回 `False`，必要时截图辅助排查。`test.py` 已补独立调试分发入口；新增方案已选择 A，把滑块作为注册提交后的正式步骤接入 `vinted_run_all()` 主流程，成功条件收紧为“提交成功且滑块成功”。

已核对 workflow：  
[.github/workflows/flet-macos-tag.yml](/Users/admin/go/src/autovt/.github/workflows/flet-macos-tag.yml):110-114 当前 macOS 已打包整个 `images/` 目录。  
[.github/workflows/flet-macos-tag.yml](/Users/admin/go/src/autovt/.github/workflows/flet-macos-tag.yml):272-276 当前 Windows 也已打包整个 `images/` 目录。  
因此 `images/fr/vinted/slider.png` 已覆盖，本版本无需修改 workflow，只需在文档中同步说明。

## 文件变更清单

**修改:**
- [autovt/tasks/vinted.py](/Users/admin/go/src/autovt/autovt/tasks/vinted.py):4-14 — 改滑块方法所需导入（现: 只有注册流程相关导入）
- [autovt/tasks/vinted.py](/Users/admin/go/src/autovt/autovt/tasks/vinted.py):190-200 — 在 `vinted_run_all()` 前插入独立滑块方法（现: `_focus_and_input_vinted_field()` 结束后直接进入主注册流程，尚无滑块方法）
- [test.py](/Users/admin/go/src/autovt/test.py):29-32 — 增加 `VintedTask` 导入（现: 仅导入 `OpenSettingsTask`）
- [test.py](/Users/admin/go/src/autovt/test.py):230-243 — 增加 `vinted_slider` 方法分发和可用方法提示（现: `nekobox_run_all` 后直接抛不支持方法）
- [test.py](/Users/admin/go/src/autovt/test.py):353-367 — 按方法名实例化 `OpenSettingsTask` 或 `VintedTask`（现: 固定实例化 `OpenSettingsTask`）
- [/Users/admin/go/src/go_cookies/autovt/doc/project_structure.md](/Users/admin/go/src/go_cookies/autovt/doc/project_structure.md):43-47 — 补 `images/fr/vinted/slider.png` 目录树（现: 仅列出 `抹机王` 图片）
- [/Users/admin/go/src/go_cookies/autovt/doc/project_structure.md](/Users/admin/go/src/go_cookies/autovt/doc/project_structure.md):81-84 — 同步 Vinted 滑块方法、`test.py` 单测入口和 workflow 打包说明（现: 仅描述 Vinted 注册流程和旧版调试入口）
- [autovt/tasks/vinted.py](/Users/admin/go/src/autovt/autovt/tasks/vinted.py):431-443 — 把滑块接入提交注册后的主流程（现: 提交成功后直接返回 True）
- [/Users/admin/go/src/go_cookies/autovt/doc/project_structure.md](/Users/admin/go/src/go_cookies/autovt/doc/project_structure.md):83-86 — 同步主流程已接入滑块校验（现: 仅描述存在独立滑块方法）

**依赖:**
- 无新增三方依赖，继续使用现有 `airtest` 能力

## Todolist

- [x] 1. 补齐 Vinted 滑块方法所需导入

  **Files:**
  - Modify: [vinted.py](/Users/admin/go/src/autovt/autovt/tasks/vinted.py):4-14

```text
change details:
修改: /Users/admin/go/src/autovt/autovt/tasks/vinted.py:4-14 (现: 只有 random / Any / set_clipboard / sleep / start_app 等注册流程基础导入)
- 新增滑块轨迹需要的数学和 Airtest 导入
- 保持注释风格与现有文件一致，每个导入块上方补中文说明
- 不引入新包，只使用项目已安装的 airtest 能力
```

- [x] 2. 封装滑块图片查找与起点识别

  **Files:**
  - Modify: [vinted.py](/Users/admin/go/src/autovt/autovt/tasks/vinted.py):190-200

```text
change details:
修改: /Users/admin/go/src/autovt/autovt/tasks/vinted.py:190-200 (现: `_focus_and_input_vinted_field()` 结束后直接进入 `vinted_run_all()`，没有独立滑块方法)
- 新增 `vinted_slider(self) -> bool` 方法
- 通过父类 `_build_asset_template("images", "fr", "vinted", "slider.png", ...)` 构建模板
- 最多等待 10 秒查找滑块图片，找到后记录起点坐标和屏幕分辨率
- 未找到时记录 warning 日志并返回 False
```

- [x] 3. 封装贝塞尔轨迹滑动与失败兜底

  **Files:**
  - Modify: [vinted.py](/Users/admin/go/src/autovt/autovt/tasks/vinted.py):190-200

```text
change details:
修改: /Users/admin/go/src/autovt/autovt/tasks/vinted.py:190-200 (现: 该位置尚无滑块执行逻辑)
- 在 `vinted_slider()` 内生成拟人化贝塞尔轨迹点
- 使用 Airtest 设备对象执行 `swipe_along` 完成滑动
- 成功时记录轨迹点数量、目标终点、耗时并返回 True
- 异常时记录完整 exception 日志，失败截图，并返回 False
- 整体逻辑不直接改动 `vinted_run_all()`，先保持独立可测
```

- [x] 4. 给 test.py 增加独立调试入口

  **Files:**
  - Modify: [test.py](/Users/admin/go/src/autovt/test.py):29-32
  - Modify: [test.py](/Users/admin/go/src/autovt/test.py):230-243
  - Modify: [test.py](/Users/admin/go/src/autovt/test.py):353-367

```text
change details:
修改: /Users/admin/go/src/autovt/test.py:29-32 (现: 仅导入 `OpenSettingsTask`)
- 新增 `VintedTask` 导入

修改: /Users/admin/go/src/autovt/test.py:230-243 (现: 只支持 open_settings 相关方法和 nekobox)
- 增加 `vinted_slider` 方法分发
- 更新“不支持的方法”提示，把 `vinted_slider` 列进可用方法

修改: /Users/admin/go/src/autovt/test.py:353-367 (现: 固定 `task = OpenSettingsTask(...)`)
- 按 `method_name` 判断实例化 `VintedTask` 或 `OpenSettingsTask`
- 保持原有 serial / locale / cleanup 逻辑不变
- 允许直接执行 `uv run python test.py vinted_slider`
```

- [x] 5. 同步结构文档并注明 workflow 已覆盖打包

  **Files:**
  - Modify: [/Users/admin/go/src/go_cookies/autovt/doc/project_structure.md](/Users/admin/go/src/go_cookies/autovt/doc/project_structure.md):43-47
  - Modify: [/Users/admin/go/src/go_cookies/autovt/doc/project_structure.md](/Users/admin/go/src/go_cookies/autovt/doc/project_structure.md):81-84

```text
change details:
修改: /Users/admin/go/src/go_cookies/autovt/doc/project_structure.md:43-47 (现: images 目录树只列 `抹机王` 图片)
- 补充 `images/fr/vinted/slider.png` 路径

修改: /Users/admin/go/src/go_cookies/autovt/doc/project_structure.md:81-84 (现: 只描述 Vinted 注册流程、旧 test.py 入口、workflow 通用打包说明)
- 追加 `vinted.py` 新增独立滑块方法说明
- 追加 `test.py` 可单独调 `vinted_slider` 的说明
- 标注 workflow 已覆盖整个 `images/` 目录，本次无需改 `.github/workflows/flet-macos-tag.yml`
```

- [x] 6. 接入 Vinted 主流程滑块校验

  **Files:**
  - Modify: [vinted.py](/Users/admin/go/src/autovt/autovt/tasks/vinted.py):431-443
  - Modify: [/Users/admin/go/src/go_cookies/autovt/doc/project_structure.md](/Users/admin/go/src/go_cookies/autovt/doc/project_structure.md):83-86

```text
change details:
修改: /Users/admin/go/src/autovt/autovt/tasks/vinted.py:431-443 (现: 点击提交注册按钮后仅记录“Vinted 注册表单已提交”并直接 return True)
- 在提交注册按钮成功后调用 `self.vinted_slider()`
- 滑块执行前记录“注册后开始处理滑块”的日志
- `vinted_slider()` 返回 False 时，按注册失败处理并返回 `_vinted_fail("Vinted 注册失败：提交后滑块处理失败")`
- 只有提交成功且滑块处理成功时，才保留最终成功返回 True
- 保持现有异常兜底和日志风格，不改 `run_once()` 收尾逻辑

修改: /Users/admin/go/src/go_cookies/autovt/doc/project_structure.md:83-86 (现: 文档只说明存在独立 `vinted_slider()` 方法)
- 补充 `vinted_run_all()` 已在注册提交后正式接入滑块校验
- 标明主流程成功条件已变为“提交成功 + 滑块成功”
```

## 总结
共 6 条任务，涉及 4 个文件，其中修改 4 个、核实 1 个无需改动，预计改动约 105 到 160 行。

1. 在 `VintedTask` 内补一个独立滑块方法，先找图再滑，完整返回 `True/False`。
2. 轨迹执行保持拟人化贝塞尔滑动，并加成功、失败、异常截图日志。
3. `test.py` 增加独立调试入口，便于先验证滑块再决定是否接入主流程。
4. 外部项目结构文档同步滑块图片、单测入口和打包覆盖结论。
5. workflow 已确认同时覆盖 macOS 和 Windows 的 `images/` 打包，无需改文件。
6. 把 `vinted_slider()` 正式接入 `vinted_run_all()` 提交后的主流程，注册成功条件变为“提交成功且滑块成功”。

## 变更记录
- 2026-03-22 09:22:24 初始创建
- 2026-03-22 09:28:01 完成 #1 补齐 Vinted 滑块方法所需导入
- 2026-03-22 09:28:41 完成 #2 封装滑块图片查找与起点识别
- 2026-03-22 09:29:29 完成 #3 封装贝塞尔轨迹滑动与失败兜底
- 2026-03-22 09:29:52 完成 #4 给 test.py 增加独立调试入口
- 2026-03-22 09:30:24 完成 #5 同步结构文档并注明 workflow 已覆盖打包
- 2026-03-22 09:39:08 新增，接入主流程， 注册后接入
- 2026-03-22 09:40:04 完成 #6 接入 Vinted 主流程滑块校验
