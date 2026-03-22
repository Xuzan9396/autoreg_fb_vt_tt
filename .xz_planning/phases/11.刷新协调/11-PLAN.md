# 版本 11: 刷新协调

> 创建时间: 2026-03-22 21:19:26
> 最后更新: 2026-03-22 21:42:14
> 状态: 已完成

## 需求描述
现在 flet 操作都很卡，每次都需要等待很久才有页面反应，不知道什么影响了；加点日志。当前日志显示设备页刷新偶发非常慢，不只是某一个 UI 操作卡，其他 UI 也会偶现卡顿。需要深度排查并优化，重点关注设备刷新、ADB 扫描、日志 GUI 展示最老且不自动滚动到最新、日志和操作不同步延迟高的问题；要求在保证代码安全稳定的前提下优化，并继续形成计划。

## 技术方案
已选择方案 B：引入“设备刷新协调器”。

核心思路：
1. 把设备页现在分散的 `adb devices`、`manager.status()`、日志文件扫描，从 `DeviceTab` 内部直接 `to_thread()` 调用，收敛到一个独立的刷新协调器中。
2. 协调器负责节流、快照缓存、阶段耗时统计、串行执行和错误兜底，避免设备页自动刷新和设备动作、日志读取互相抢默认线程池。
3. 设备页只消费“已准备好的快照”，日志面板改用 `flet.ListView`，修正“总是停在旧日志”和“不同步”的问题。
4. ADB 在线设备查询增加短 TTL 缓存和更细日志，把“函数本体耗时”和“等待/命中缓存”拆开记。
5. 文档同步说明新的刷新协调器职责和日志面板实现。

实现边界：
- 不改现有 worker/任务业务逻辑。
- 不新增第三方依赖，沿用当前 `flet~=0.80.5`。
- 不把设备刷新做成复杂消息总线，只做一个 GUI 内部协调器，避免过度设计。

Flet 依据：
- `ListView` 更适合大日志列表，支持惰性构建与自动滚动示例。
  来源: https://docs.flet.dev/controls/listview/
- `ScrollableControl`/`ListView` 适合做“跟随最新”和手动查看历史切换。
  来源: https://docs.flet.dev/controls/listview/

## 文件变更清单

**新建:**
- `autovt/gui/device_refresh_coordinator.py` — 统一设备快照、日志快照、刷新节流、耗时统计与错误隔离；包含 `DeviceRefreshCoordinator`、`DeviceRefreshSnapshot`、`RefreshMetrics`

**修改:**
- `autovt/gui/app.py:18-25` — 增加设备刷新协调器导入（现: 仅导入 DeviceTab/helpers/manager 等 GUI 依赖）
- `autovt/gui/app.py:34-65` — 在 GUI 初始化阶段创建协调器并注入 DeviceTab（现: 只创建 manager、user_db、DeviceTab/AccountTab/SettingsTab）
- `autovt/gui/app.py:154-158` — 登录成功后改为启动协调器首轮刷新而非直接设备页裸刷（现: `_build_dashboard_view()` 后直接 `device_tab.refresh(...)`）
- `autovt/gui/app.py:246-260` — Tab 切换时改为通知协调器/设备页消费最新快照（现: 切回设备页时直接触发 `device_tab.refresh()`）
- `autovt/gui/app.py:425-436` — 自动监控循环改为驱动协调器而不是直接让设备页自己并发拉数据（现: 每 5 秒直接 `self.device_tab.refresh(source="auto", ...)`）
- `autovt/gui/device_tab.py:14-17` — 增加协调器类型导入并调整依赖（现: 只依赖 helpers、manager、JSON_LOG_DIR）
- `autovt/gui/device_tab.py:37-74` — DeviceTab 构造参数与本地缓存结构改造，接入快照模型（现: 自己维护 `_cached_log_records/_last_log_load_mono_ts/_logs_follow_latest` 等状态）
- `autovt/gui/device_tab.py:96-110` — 日志区控件从 `Column` 切到 `ListView` 并保留滚动监听（现: `ft.Column(auto_scroll=False, on_scroll=...)`）
- `autovt/gui/device_tab.py:138-143` — 去掉 build 时直接异步扫盘日志，改为向协调器请求初始化快照（现: `run_task(self._refresh_logs_view_async, True)`）
- `autovt/gui/device_tab.py:401-571` — 设备页刷新主链路改成“请求协调器刷新 + 应用快照 + 输出 UI 耗时日志”，不再自行 `to_thread(adb/status/logs)`（现: `_refresh_async()` 内部直接并发读取 ADB、日志、status）
- `autovt/gui/device_tab.py:692-703` — 删除伪“尾读”实现并迁移到协调器（现: `_tail_lines()` 顺序扫完整文件）
- `autovt/gui/device_tab.py:779-881` — 日志加载/异步日志刷新逻辑迁移或瘦身，只保留展示层方法（现: `_load_latest_log_messages()`、`_refresh_logs_view_async()` 自己读文件）
- `autovt/gui/device_tab.py:883-910` — 日志渲染方法改成适配 `ListView`、修复“默认展示最老”和“跟随最新”策略（现: 每次重建 `Column.controls`）
- `autovt/adb.py:14-20` — 增加 ADB 在线设备缓存常量（现: 只有 adb timeout/recover timeout）
- `autovt/adb.py:346-535` — 为 `list_online_serials()` 增加 TTL 缓存、强制刷新开关、缓存命中/未命中日志（现: 每次都直接跑 `adb devices`）
- `autovt/multiproc/manager.py:292-295` — `list_online_devices()` 支持透传缓存/强制刷新参数（现: 只薄封装 `list_online_serials()`）
- `autovt/multiproc/manager.py:1291-1331` — `status()` 增加阶段耗时日志，并预留批量查询设备绑定邮箱的接口位（现: 只有逐设备 `get_user_by_device()`）
- `/Users/admin/go/src/go_cookies/autovt/doc/project_structure.md:70-79` — 更新 GUI 刷新协调器、设备页日志展示和 ADB 缓存说明（现: 仅描述 device_tab 直接负责刷新与日志展示）

**依赖:**
- 无新增第三方依赖
- 继续使用 `flet~=0.80.5` 的 `ListView` 能力

## Todolist

- [x] 1. 创建设备刷新协调器模块

  **Files:**
  - Create: `autovt/gui/device_refresh_coordinator.py`

  ```text
  change details:
  新建: autovt/gui/device_refresh_coordinator.py
  - 定义 DeviceRefreshSnapshot 数据结构，包含 online_serials、status_rows、log_records、metrics、error_text、refreshed_at
  - 定义 RefreshMetrics 数据结构，包含 adb_elapsed_ms、status_elapsed_ms、log_read_elapsed_ms、queue_wait_elapsed_ms、total_elapsed_ms、cache_hit 字段
  - 定义 DeviceRefreshCoordinator 类，提供 start()、close()、request_refresh()、get_snapshot()、mark_log_follow_latest() 等方法
  - 协调器内部使用独立后台执行器或串行线程，避免与全局 asyncio.to_thread 默认线程池互相抢占
  ```
----------------------
- [x] 2. 接入 GUI 主应用生命周期

  **Files:**
  - Modify: `autovt/gui/app.py:18-25`
  - Modify: `autovt/gui/app.py:34-65`
  - Modify: `autovt/gui/app.py:154-158`
  - Modify: `autovt/gui/app.py:246-260`
  - Modify: `autovt/gui/app.py:425-436`

  ```text
  change details:
  修改: autovt/gui/app.py:18-25 (现: 只导入 DeviceTab/helpers/login_view/settings_tab/manager)
  - 新增 DeviceRefreshCoordinator 导入
  - 保持现有导入顺序与 GUI 模块边界

  修改: autovt/gui/app.py:34-65 (现: __init__ 中创建 manager、user_db、device_tab/account_tab/settings_tab)
  - 创建 self.device_refresh_coordinator
  - 将协调器实例注入 DeviceTab
  - 为后续 shutdown 增加 coordinator 关闭入口

  修改: autovt/gui/app.py:154-158 (现: 登录成功后直接 build dashboard + device_tab.refresh + 启动 monitor loop)
  - 调整为 dashboard build 后先启动协调器首轮刷新
  - 设备页只应用协调器快照，不再首次进入就直接自拉数据

  修改: autovt/gui/app.py:246-260 (现: 切回设备页直接 self.device_tab.refresh)
  - 切回设备页时改成通知协调器按 tab_switch 刷新或回放最近快照
  - 保留账号页、设置页原有刷新逻辑不变

  修改: autovt/gui/app.py:425-436 (现: monitor loop 每 5 秒直接调用 device_tab.refresh)
  - 改成调度协调器 request_refresh(source="auto")
  - 追加“上一轮仍在跑则跳过/合并本轮”的退让日志
  ```
----------------------
- [x] 3. 重构设备页为“只渲染快照”

  **Files:**
  - Modify: `autovt/gui/device_tab.py:14-17`
  - Modify: `autovt/gui/device_tab.py:37-74`
  - Modify: `autovt/gui/device_tab.py:401-571`

  ```text
  change details:
  修改: autovt/gui/device_tab.py:14-17 (现: 仅导入 DeviceViewModel/get_logger/DeviceProcessManager/JSON_LOG_DIR)
  - 新增协调器类型导入
  - 清理后续不再直接使用的日志扫描依赖

  修改: autovt/gui/device_tab.py:37-74 (现: DeviceTab 自己持有日志缓存、最近读取时间、follow_latest 等状态)
  - 构造参数新增 coordinator
  - 精简本地“数据源状态”，保留纯展示态与滚动跟随态
  - 把数据获取职责从 Tab 内部迁出到协调器

  修改: autovt/gui/device_tab.py:401-571 (现: _refresh_async 内部直接 asyncio.to_thread 拉 adb/status/logs，再 page.update)
  - 改为请求协调器刷新并读取 snapshot
  - 新增“队列等待耗时 / 快照年龄 / 缓存命中 / UI 应用耗时”日志
  - 保证失败时沿用上次可用快照，避免界面闪空
  ```
----------------------
- [x] 4. 把日志面板从 Column 改成 ListView 并修正滚动行为

  **Files:**
  - Modify: `autovt/gui/device_tab.py:96-110`
  - Modify: `autovt/gui/device_tab.py:138-143`
  - Modify: `autovt/gui/device_tab.py:883-910`

  ```text
  change details:
  修改: autovt/gui/device_tab.py:96-110 (现: 日志区域使用 ft.Column(auto_scroll=False, on_scroll=...))
  - 改成 ft.ListView
  - 开启 build_controls_on_demand
  - 根据当前布局选择合适的 item_extent 或 prototype_item，降低大量日志控件重建成本

  修改: autovt/gui/device_tab.py:138-143 (现: build() 时直接 run_task 异步扫盘日志)
  - 改成请求协调器提供初始日志快照
  - 避免页面刚创建时额外启动一次独立日志读盘任务

  修改: autovt/gui/device_tab.py:883-910 (现: 每次重建 Column.controls，展示顺序虽新但滚动位置不跟随)
  - 改成适配 ListView 的日志项渲染
  - 明确“默认跟随最新；用户手动上滑后暂停跟随；再次到底部后恢复”
  - 刷新后在 follow_latest=True 时显式 scroll_to 末尾，解决“展示最老、不自动到最新”问题
  ```
----------------------
- [x] 5. 迁移日志读取到协调器并修正伪尾读

  **Files:**
  - Modify: `autovt/gui/device_tab.py:692-703`
  - Modify: `autovt/gui/device_tab.py:779-881`
  - Create: `autovt/gui/device_refresh_coordinator.py`

  ```text
  change details:
  修改: autovt/gui/device_tab.py:692-703 (现: _tail_lines() 顺序读取整个文件，再用 deque 只留尾部)
  - 删除该实现或迁移为协调器内部真正尾读
  - 不再让 DeviceTab 直接触碰日志文件

  修改: autovt/gui/device_tab.py:779-881 (现: _load_latest_log_messages() / _refresh_logs_view_async() 在 Tab 中扫描 jsonl)
  - 迁走日志读盘、日志文件筛选、排序与耗时统计
  - DeviceTab 保留纯展示与复制文本逻辑

  新建: autovt/gui/device_refresh_coordinator.py
  - 实现真正的尾部读取或受限块读取
  - 记录 scanned_file_count、scanned_bytes、tail_read_elapsed_ms、filtered_line_count
  - 统一产出最新日志快照，避免设备页和初始日志加载各扫一遍
  ```
----------------------
- [x] 6. 给 ADB 在线设备读取加缓存和诊断日志

  **Files:**
  - Modify: `autovt/adb.py:14-20`
  - Modify: `autovt/adb.py:346-535`
  - Modify: `autovt/multiproc/manager.py:292-295`
  - Modify: `autovt/multiproc/manager.py:945-950`

  ```text
  change details:
  修改: autovt/adb.py:14-20 (现: 只有 _RESOLVED_ADB_BIN、ADB_DEVICES_TIMEOUT_SEC、ADB_RECOVER_TIMEOUT_SEC)
  - 增加 ADB 在线设备缓存 TTL、最近结果缓存、缓存锁
  - 预留 force_refresh 开关

  修改: autovt/adb.py:346-535 (现: list_online_serials() 每次都直接 adb devices)
  - 支持缓存命中返回
  - 支持 force_refresh=True 时跳过缓存
  - 增加 cache_hit、snapshot_age_ms、caller/source 诊断日志
  - 保持 adb 超时恢复逻辑不变，保证安全性

  修改: autovt/multiproc/manager.py:292-295 (现: list_online_devices() 只是直接调用 list_online_serials())
  - 透传 force_refresh/source 参数给 adb 层
  - 为 GUI 协调器和批量动作提供统一入口

  修改: autovt/multiproc/manager.py:945-950 (现: start_all() 无缓存策略，直接 list_online_devices())
  - 启动全部等批量动作优先读取协调器/缓存快照
  - 手动动作需要强制刷新时再显式请求 force_refresh
  ```
----------------------
- [x] 7. 补强状态快照和协调器阶段日志

  **Files:**
  - Modify: `autovt/multiproc/manager.py:1291-1331`
  - Create: `autovt/gui/device_refresh_coordinator.py`

  ```text
  change details:
  修改: autovt/multiproc/manager.py:1291-1331 (现: status() 只返回 rows，不记录内部阶段耗时)
  - 增加 drain_events_elapsed_ms、db_open_elapsed_ms、device_lookup_elapsed_ms、row_build_elapsed_ms 日志
  - 保持返回结构兼容，避免影响现有 DeviceTab 之外的调用

  新建: autovt/gui/device_refresh_coordinator.py
  - 把 adb/status/logs 三段耗时与 queue_wait_elapsed_ms、snapshot_age_ms 统一汇总
  - 对“上一轮未完成 / 使用缓存 / 降级使用旧快照 / 本轮失败”输出明确日志
  ```
----------------------
- [x] 8. 同步项目结构文档

  **Files:**
  - Modify: `/Users/admin/go/src/go_cookies/autovt/doc/project_structure.md:70-79`

  ```text
  change details:
  修改: /Users/admin/go/src/go_cookies/autovt/doc/project_structure.md:70-79
  (现: app.py 描述 GUI 生命周期，device_tab 仍被描述为直接负责刷新与日志展示)
  - 新增 autovt/gui/device_refresh_coordinator.py 模块职责说明
  - 更新 device_tab 为“消费协调器快照 + 渲染 ListView 日志”
  - 更新 adb 在线设备缓存和 GUI 刷新协调说明
  ```

## 总结

共 8 条任务，涉及 5 个文件（新建 1 个，修改 4 个主代码文件 + 1 个文档文件），预计改动约 250-400 行。

1. 创建设备刷新协调器，把设备页最重的 IO 从 `DeviceTab` 里拆出去，形成串行、可观测、可降级的快照层。
2. GUI 主应用不再直接驱动设备页自拉数据，而是统一驱动协调器，降低自动刷新、批量动作和设备页之间的竞争。
3. 设备页切成“数据获取”和“UI 展示”两层，后续性能问题能更准确落到协调器日志，而不是都堆在 `_refresh_async`。
4. 日志区改成 `ListView`，修掉“总是看旧日志”和“不会自动跟到最新”的体验问题。
5. ADB 在线设备读取加短缓存和明确日志，减少所有设备相关操作一起被 `adb devices` 拖慢的概率。
6. `manager.status()` 继续保持兼容，但补阶段日志，为后续继续压缩卡顿来源留证据。
7. 文档同步，避免后续维护者还以为设备页是“自己并发扫 ADB + 日志 + status”。

## 变更记录
- 2026-03-22 21:42:14 完成 #8 同步项目结构文档
- 2026-03-22 21:42:14 完成 #7 补强状态快照和协调器阶段日志
- 2026-03-22 21:42:14 完成 #6 给 ADB 在线设备读取加缓存和诊断日志
- 2026-03-22 21:42:14 完成 #5 迁移日志读取到协调器并修正伪尾读
- 2026-03-22 21:42:14 完成 #4 把日志面板从 Column 改成 ListView 并修正滚动行为
- 2026-03-22 21:42:14 完成 #3 重构设备页为“只渲染快照”
- 2026-03-22 21:42:14 完成 #2 接入 GUI 主应用生命周期
- 2026-03-22 21:35:23 完成 #1 创建设备刷新协调器模块
- 2026-03-22 21:19:26 初始创建
