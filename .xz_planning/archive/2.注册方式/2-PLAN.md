# 版本 2: 注册方式

> 创建时间: 2026-03-21 22:50:33
> 最后更新: 2026-03-22 09:14:48
> 状态: 已归档

## 需求描述
设备列表页新增“注册方式”选择，放在“启动全部”前面，启动时默认空；可选值为“选择注册方式 / facebook注册 / vinted注册”。
未选择 facebook 或 vinted 时，点击启动要报错提示“选择注册方式”。
新增 Vinted 注册任务文件 `autovt/tasks/vinted.py`，继承 `OpenSettingsTask`，并保持 `wake() / home() / clear_all() / mojiwang_run_all() / nekobox_run_all()` 这一段公共流程一致；新增 `self.vinted_run_all()` 空骨架，后续由开发者单独补实现。
任务成功时，Vinted 路线需要把 `t_user.vinted_status` 更新为 `1`；启动跑任务时，账号分配与重试判断要按当前选择的注册方式走对应状态字段。

## 技术方案
只有一种合理做法：把“注册方式”作为设备页的临时 UI 状态传到 `manager -> worker -> task_context.extras`，worker 再按该模式切换任务入口与状态字段。
这样可以满足“启动默认空、不持久化、界面先校验、任务层再兜底”，同时让 `VintedTask` 直接复用 `OpenSettingsTask` 的安全点击、异常日志和公共前置流程。

## 文件变更清单

**新建:**
- `autovt/tasks/vinted.py` — 新增 `VintedTask`、`vinted_run_all()`、`run_once(task_context)`

**修改:**
- `autovt/gui/device_tab.py:40-70,123-141,142-159,498-510` — 增加注册方式下拉、默认空值、启动校验和模式透传
- `autovt/multiproc/manager.py:593-612,616-649,651-656,978-980` — 启动/重启接口增加注册方式参数并做兜底校验
- `autovt/multiproc/worker.py:423-430,463-470,472-539,578-679,681-720,845-901,914-920` — 按注册方式分发任务入口，并把重试判断从固定 `fb_status` 改成当前模式字段
- `autovt/tasks/open_settings.py:76-153,1962-2008,3240-3280,3300-3324` — 抽公共流程与通用结果回写，保留 Facebook 现有逻辑
- `autovt/userdb/user_db.py:1709-1775` — 扩展状态更新接口，支持回写 `vinted_status`
- `/Users/admin/go/src/go_cookies/autovt/doc/project_structure.md:38-41,59-69,76-78,117-120` — 同步新增 `vinted.py`、注册方式启动链路与任务说明

**依赖:**
- 无新增第三方依赖，继续使用现有 `uv`、Flet、Airtest、SQLite

## Todolist

- [x] 1. 设备页加入注册方式下拉与空值默认

  **Files:**
  - Modify: `autovt/gui/device_tab.py:40-70`
  - Modify: `autovt/gui/device_tab.py:123-141`

  ```text
  change details:
  修改: autovt/gui/device_tab.py:40-70 (现: DeviceTab 只保存日志区/列表控件状态)
  - 新增注册方式下拉框字段与当前选择值缓存
  - 默认值保持空，对应“选择注册方式”

  修改: autovt/gui/device_tab.py:123-141 (现: 顶部操作区只有“刷新设备/启动全部/停止全部”等按钮)
  - 在“启动全部”前插入 Dropdown
  - 选项固定为：空、facebook注册、vinted注册
  ```

- [x] 2. 启动前统一校验注册方式并透传到按钮回调

  **Files:**
  - Modify: `autovt/gui/device_tab.py:142-159`
  - Modify: `autovt/gui/device_tab.py:498-510`

  ```text
  change details:
  修改: autovt/gui/device_tab.py:142-159 (现: 顶部“启动全部”直接调用 self.manager.start_all)
  - 增加“未选择则弹提示并中断”的包装方法
  - 启动全部时把 register_mode 传给 manager.start_all(...)

  修改: autovt/gui/device_tab.py:498-510 (现: 单设备“启动/重启”直接调用 start_worker/restart_worker)
  - 单设备启动/重启也复用同一注册方式
  - 保证顶部启动和卡片启动行为一致
  ```

- [x] 3. manager 启动接口支持注册方式参数与兜底校验

  **Files:**
  - Modify: `autovt/multiproc/manager.py:593-612`
  - Modify: `autovt/multiproc/manager.py:651-656`
  - Modify: `autovt/multiproc/manager.py:978-980`

  ```text
  change details:
  修改: autovt/multiproc/manager.py:593-612 (现: start_worker(serial) 只传 serial 给 worker_main)
  - start_worker 增加 register_mode 参数
  - 非 facebook/vinted 时直接返回明确错误文本，避免空模式启动

  修改: autovt/multiproc/manager.py:651-656 (现: start_all() 逐台调用 start_worker(serial))
  - start_all 增加 register_mode 参数并向下透传

  修改: autovt/multiproc/manager.py:978-980 (现: restart_worker 停止后直接 start_worker(serial))
  - restart_worker 同步接收 register_mode，避免重启丢失当前选择
  ```

- [x] 4. worker 改成按注册方式分配状态字段与任务入口

  **Files:**
  - Modify: `autovt/multiproc/worker.py:423-430`
  - Modify: `autovt/multiproc/worker.py:463-470,472-539,578-679`
  - Modify: `autovt/multiproc/worker.py:681-720,845-901`

  ```text
  change details:
  修改: autovt/multiproc/worker.py:423-430 (现: 启动时只导入 autovt.tasks.open_settings.run_once)
  - 增加按 register_mode 选择 facebook/vinted 任务入口

  修改: autovt/multiproc/worker.py:463-470,472-539,578-679 (现: 同账号重试和绑定判断固定使用 fb_status)
  - 抽“当前注册状态字段名”变量
  - facebook 模式读 fb_status，vinted 模式读 vinted_status

  修改: autovt/multiproc/worker.py:681-720,845-901 (现: task_context 只注入 user/config，执行 imported_run_once)
  - 把 register_mode 写入 task_context.extras
  - 执行时按模式调用对应任务模块
  ```

- [x] 5. 扩展数据库状态更新接口，支持 Vinted 成功回写

  **Files:**
  - Modify: `autovt/userdb/user_db.py:1709-1775`

  ```text
  change details:
  修改: autovt/userdb/user_db.py:1709-1775 (现: update_status 仅支持更新 status/fb_status/msg/fb_fail_num)
  - 增加可选 vinted_status 参数
  - 保持原有 Facebook 调用兼容，不影响现有接口
  ```

- [x] 6. 抽取 OpenSettingsTask 公共前置流程与通用结果回写

  **Files:**
  - Modify: `autovt/tasks/open_settings.py:76-153`
  - Modify: `autovt/tasks/open_settings.py:1962-2008`
  - Modify: `autovt/tasks/open_settings.py:3240-3280,3300-3324`

  ```text
  change details:
  修改: autovt/tasks/open_settings.py:76-153 (现: __init__ 里只有 Facebook 结果字段与公共配置缓存)
  - 增加注册方式读取与公共结果字段定义
  - 保留现有日志、防断连、safe click 方法不变

  修改: autovt/tasks/open_settings.py:1962-2008 (现: _update_fb_result_to_db 只写 fb_status)
  - 抽成可被子类复用的通用回写方法
  - Facebook 继续走 fb_status，Vinted 走 vinted_status

  修改: autovt/tasks/open_settings.py:3240-3280,3300-3324 (现: run_once 直接写死 facebook_run_all + Facebook 收尾)
  - 抽公共前置步骤：wake/home/clear_all/mojiwang_run_all/nekobox_run_all
  - Facebook 路线继续复用现有成功/失败日志和异常收尾
  ```

- [x] 7. 新建 VintedTask 骨架并同步项目文档

  **Files:**
  - Create: `autovt/tasks/vinted.py`
  - Modify: `/Users/admin/go/src/go_cookies/autovt/doc/project_structure.md:38-41,59-69,76-78,117-120`

  ```text
  change details:
  新建: autovt/tasks/vinted.py
  - 定义 VintedTask(OpenSettingsTask)
  - 定义 vinted_run_all() 空方法，先写日志占位
  - 定义 run_once(task_context)，复用公共前置流程并在成功时回写 vinted_status=1

  修改: /Users/admin/go/src/go_cookies/autovt/doc/project_structure.md:38-41,59-69,76-78,117-120 (现: tasks 目录只有 open_settings.py，启动流程说明里没有注册方式分流)
  - 增加 vinted.py 到目录结构
  - 补充设备页注册方式选择、worker 分流、VintedTask 说明
  ```

- [x] 8. 拆分公共前置流程，移除 Vinted 路径中的 Facebook 专属清理

  **Files:**
  - Modify: `autovt/tasks/open_settings.py:1198-1268,3318-3345`
  - Modify: `autovt/tasks/vinted.py:24-42`
  - Modify: `/Users/admin/go/src/go_cookies/autovt/doc/project_structure.md:68-78`

  ```text
  change details:
  修改: autovt/tasks/open_settings.py:1198-1268 (现: clear_all 同时清理 Vinted、Facebook、设置页 Facebook 账号，并按 fb_delete_num / setting_fb_del_num 执行 Facebook 专属动作)
  - 拆分成“纯公共清理步骤”和“Facebook 专属清理步骤”
  - Vinted 路径不得再执行 Facebook clear/uninstall/install/setting_clean_fb 相关逻辑
  - Facebook 路径继续保留 fb_delete_num 与 setting_fb_del_num 的现有行为

  修改: autovt/tasks/open_settings.py:3318-3345 (现: _run_common_setup_flow 内固定执行 clear_all -> mojiwang_run_all -> nekobox_run_all)
  - 让 _run_common_setup_flow 只保留真正公共的 wake/home/抹机王/代理前置
  - Facebook 任务在自己的 run_once 中显式调用 Facebook 专属清理
  - 避免 Vinted 继承后误跑 Facebook 清理链路

  修改: autovt/tasks/vinted.py:24-42 (现: VintedTask.run_once 直接调用 _run_common_setup_flow)
  - 改为调用拆分后的“无 Facebook 副作用”的公共前置流程
  - 保证 Vinted 启动前只执行 Vinted 需要的清理步骤

  修改: /Users/admin/go/src/go_cookies/autovt/doc/project_structure.md:68-78 (现: 文档描述公共前置流程可被 Facebook 与 Vinted 共用)
  - 补充说明公共前置流程已与 Facebook 专属清理拆分
  - 说明 Vinted 路径不会再触发 fb_delete_num / setting_fb_del_num
  ```

- [x] 9. 拆分 Facebook 与 Vinted 的应用数据清理，保持包级独立

  **Files:**
  - Modify: `autovt/tasks/open_settings.py:1199-1275,3323-3372`
  - Modify: `autovt/tasks/vinted.py:27-46`
  - Modify: `/Users/admin/go/src/go_cookies/autovt/doc/project_structure.md:68-78`

  ```text
  change details:
  修改: autovt/tasks/open_settings.py:1199-1275 (现: clear_all 仍固定清理 vinted app 数据，Facebook 专属清理单独拆出，但 Facebook 路径启动前仍会经过 Vinted 包清理)
  - 继续拆成“共享前置步骤”和“按包独立的数据清理步骤”
  - 抹机王与代理前置保持共享
  - Facebook 注册路径只能清理 Facebook 相关包与设置页 Facebook 账号，不得清理 Vinted app 数据
  - Vinted 注册路径只能清理 Vinted app 数据，不得触发 Facebook clear/uninstall/install/setting_clean_fb

  修改: autovt/tasks/open_settings.py:3323-3372 (现: _run_common_setup_flow 内仍调用 clear_all，随后 Facebook run_once 再执行 Facebook 专属清理)
  - 让 _run_common_setup_flow 只保留 wake/home/抹机王/代理等真正共享步骤
  - 新增 Facebook 独立应用清理入口，在 Facebook run_once 中显式调用
  - 保证“共享步骤可复用、包数据清理独立”

  修改: autovt/tasks/vinted.py:27-46 (现: VintedTask.run_once 只调用 _run_common_setup_flow，未显式声明自己的 app 数据清理入口)
  - 增加 Vinted 独立应用清理调用
  - 保证 Vinted 任务只处理 fr.vinted 包，不受 Facebook 注册流程影响

  修改: /Users/admin/go/src/go_cookies/autovt/doc/project_structure.md:68-78 (现: 文档只说明 Vinted 不再触发 Facebook 专属清理)
  - 补充说明 Facebook 与 Vinted 两个包的数据清理完全独立
  - 说明抹机王与代理步骤属于共享前置，应用数据清理按注册方式分别执行
  ```

## 总结
共 9 条任务，涉及 6 个文件修改 + 1 个新文件，预计改动约 170 到 280 行。
核心是把“注册方式”做成启动时的必选临时参数，并让 worker/task 的状态判断从固定 `fb_status` 改成按模式切换。
新增的后续任务用于把公共前置流程继续拆细，并把 Facebook 与 Vinted 的包数据清理完全解耦。

## 变更记录
- 2026-03-21 22:50:33 初始创建
- 2026-03-21 22:57:57 完成 #1 设备页加入注册方式下拉与空值默认
- 2026-03-21 22:59:04 完成 #2 启动前统一校验注册方式并透传到按钮回调
- 2026-03-21 22:59:49 完成 #3 manager 启动接口支持注册方式参数与兜底校验
- 2026-03-21 23:00:48 完成 #4 worker 改成按注册方式分配状态字段与任务入口
- 2026-03-21 23:01:22 完成 #5 扩展数据库状态更新接口，支持 Vinted 成功回写
- 2026-03-21 23:03:01 完成 #6 抽取 OpenSettingsTask 公共前置流程与通用结果回写
- 2026-03-21 23:05:09 完成 #7 新建 VintedTask 骨架并同步项目文档
- 2026-03-21 23:07:50 新增 #8 拆分公共前置流程，移除 Vinted 路径中的 Facebook 专属清理
- 2026-03-21 23:10:24 完成 #8 拆分公共前置流程，移除 Vinted 路径中的 Facebook 专属清理
- 2026-03-21 23:21:44 新增 #9 拆分 Facebook 与 Vinted 的应用数据清理，保持包级独立
- 2026-03-21 23:24:53 完成 #9 拆分 Facebook 与 Vinted 的应用数据清理，保持包级独立
- 2026-03-22 09:14:48 归档完成
