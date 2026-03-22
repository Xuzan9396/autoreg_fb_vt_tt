# 版本 13: 滑块兼容

> 创建时间: 2026-03-22 23:37:19
> 最后更新: 2026-03-22 23:43:16
> 状态: 待执行

## 需求描述
主要处理不同手机上 `images/fr/vinted/slider.png` 找不到的问题。这个特征在图片上是唯一的，不需要复杂的定位区域，但需要兼容不同分辨率/比例的手机。

## 技术方案
只处理 `autovt/tasks/vinted.py:vinted_slider()`。
保留现有 `slider.png` 单模板资源，不加 `record_pos`，直接给模板补录制基准分辨率 `resolution=(1080, 2340)`，让 Airtest 的 `mstpl` 多尺度匹配生效；同时在 `vinted_slider()` 内增加一层轻量候选重试和详细日志，优先走“带 resolution 的多尺度模板”，必要时再回退到当前普通模板，避免不同机型直接找不到。

## 文件变更清单

**新建:**
- 无

**修改:**
- `autovt/tasks/vinted.py:355-378` — 改造滑块模板构建和找图重试逻辑
- `autovt/tasks/vinted.py:381-390` — 补滑块识别成功/失败时的分辨率与模板参数日志
- `/Users/admin/go/src/go_cookies/autovt/doc/project_structure.md:96-99` — 同步 Vinted 滑块模板的分辨率兼容策略

**依赖:**
- 无新增依赖

## Todolist

- [x] 1. 给 Vinted 滑块模板补分辨率基准参数

  **Files:**
  - Modify: `autovt/tasks/vinted.py:355-363`

  ```text
  change details:
  修改: autovt/tasks/vinted.py:355-363 (现: _build_asset_template("images", "fr", "vinted", "slider.png") 不传 resolution, 改后: 首选模板显式传 resolution=(1080, 2340))
  - 保留 slider.png 这一个模板资源
  - 不引入 record_pos，避免把查找区域卡死
  - 让 Airtest 的 mstpl 多尺度匹配在不同手机分辨率下真正生效
  ```

----------------------
- [x] 2. 给滑块识别加轻量模板候选重试

  **Files:**
  - Modify: `autovt/tasks/vinted.py:364-378`

  ```text
  change details:
  修改: autovt/tasks/vinted.py:364-378 (现: loop_find 只对一个默认模板执行一次长时间查找, 改后: 先尝试带 resolution 的模板, 失败后再回退普通模板/更宽松阈值模板)
  - 新增 slider 模板候选列表，按顺序 loop_find
  - 候选至少包含: 带 resolution 的模板
  - 可选再补 1 个回退候选: 无 resolution 或略低 threshold 的模板
  - 所有候选都失败时再返回 False，不提前把这一步打死
  ```

----------------------
- [x] 3. 补滑块查找过程日志，区分“未命中”和“断连”

  **Files:**
  - Modify: `autovt/tasks/vinted.py:381-390`
  - Modify: `autovt/tasks/vinted.py:370-378`

  ```text
  change details:
  修改: autovt/tasks/vinted.py:370-378 (现: 未找到时只记 error=str(exc), 改后: 补本次模板参数、当前屏幕分辨率、候选序号)
  - 连接断开时继续走现有 _handle_safe_action_exception/_raise_runtime_disconnect_to_worker
  - 普通未命中时单独记录“模板未命中”而不是混成连接错误
  - 把 timeout_sec 改成和实际 loop_find 一致的值，避免日志误导

  修改: autovt/tasks/vinted.py:381-390 (现: 成功日志只记 slider_start 和屏幕宽高, 改后: 同步记命中的模板配置)
  - 记录命中模板的 resolution/threshold
  - 记录当前设备 screen_width/screen_height
  - 便于后续继续调模板时知道是哪套参数生效
  ```

----------------------
- [x] 4. 同步项目结构文档

  **Files:**
  - Modify: `/Users/admin/go/src/go_cookies/autovt/doc/project_structure.md:96-99`

  ```text
  change details:
  修改: /Users/admin/go/src/go_cookies/autovt/doc/project_structure.md:96-99 (现: 只说明 vinted_slider 使用 slider.png 找图后拖动, 改后: 补充分辨率兼容和日志策略)
  - 说明 slider.png 现在会基于 1080x2340 录制分辨率做 mstpl 多尺度匹配
  - 说明不会使用 record_pos 限死区域
  - 说明失败日志会区分模板未命中和设备连接异常
  ```

## 总结

共 4 条任务，涉及 2 个文件（新建 0 个，修改 2 个），预计改动约 35-70 行。

1. 先把 `slider.png` 从“普通模板”改成“带基准分辨率的多尺度模板”。
2. 再补一层很轻的回退候选，避免个别机型只因一次模板参数不合适就直接失败。
3. 最后把日志和文档补齐，后续排查能看出到底是模板问题还是连接问题。

## 变更记录
- 2026-03-22 23:37:19 初始创建
- 2026-03-22 23:37:19 根据用户补充，范围收敛为 Vinted `slider.png` 跨手机兼容
- 2026-03-22 23:40:55 完成 #1 给 Vinted 滑块模板补分辨率基准参数
- 2026-03-22 23:41:56 完成 #2 给滑块识别加轻量模板候选重试
- 2026-03-22 23:42:47 完成 #3 补滑块查找过程日志，区分“未命中”和“断连”
- 2026-03-22 23:43:16 完成 #4 同步项目结构文档
