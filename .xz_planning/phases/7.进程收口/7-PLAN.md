# 版本 7: 进程收口

> 创建时间: 2026-03-22 11:14:45
> 最后更新: 2026-03-22 11:24:01
> 状态: 待执行

## 需求描述
目前该 Flet 多进程程序经常泄露自动化进程。即使代码里已经做了关闭，重新执行 `uv run python main.py` 后，之前的子进程和 Airtest/Poco 相关辅助进程仍在运行，导致程序错乱。  
需要保证关闭 GUI 后能彻底关闭所有程序；源码模式下如果终端 `Ctrl+C` 或终端结束，也必须彻底关闭；但实际打包项目里没有终端，因此最终生命周期要以 GUI 为主，源码模式只作为兼容兜底。  
另外需要仔细排查并修复导致退出不一致、残留孤儿进程的问题，并把文档同步到指定地址。

## 技术方案
只有一种合理做法：把 GUI/manager 作为唯一生命周期源，补齐两层收口机制。

1. manager 启动时先清理上一轮遗留的 autovt 自有辅助进程，避免“新 GUI 接上旧残留”。
2. worker 运行时监听父进程存活，父进程消失时主动停机，不再只依赖 manager 正常发 stop。
3. stop_worker/stop_all 在杀 Python worker 后，再做一次按 serial 的辅助进程复检和强杀，确保 `adb/pocoservice/maxpresent/rotationwatcher` 不残留。
4. GUI 统一窗口关闭、`SIGINT`、`SIGTERM`、`SIGHUP` 到同一条停机链路；打包 GUI 不依赖终端，源码模式终端退出作为兼容兜底。
5. 额外修复 worker 等待态异常退出点，避免 worker 自己崩掉后留下无人接管的辅助进程。
6. 复用现有 `psutil`，不新增第三方依赖。

## 文件变更清单

**新建:**
- `autovt/multiproc/process_guard.py` — 统一封装 autovt 自有辅助进程识别、孤儿清理、父进程存活检测

**修改:**
- `autovt/multiproc/manager.py:109-130` — 初始化/关闭阶段接入孤儿清理和幂等收口
- `autovt/multiproc/manager.py:541-579` — 清理 dead worker 后补辅助进程回收
- `autovt/multiproc/manager.py:603-667` — 启动前先清掉同设备历史残留，再拉起新 worker
- `autovt/multiproc/manager.py:761-995` — stop_worker/stop_all 增加残留辅助进程复检与日志
- `autovt/multiproc/worker.py:151-161` — 保留信号策略但补父进程生命周期约束
- `autovt/multiproc/worker.py:430-494` — worker 启动时注册 parent watchdog 与辅助进程清理上下文
- `autovt/multiproc/worker.py:727-770` — 修复等待态文案/作用域问题，避免 worker 异常退出
- `autovt/multiproc/worker.py:1043-1065` — finally 阶段补自清理和完整日志
- `autovt/gui/app.py:33-62` — 增加 GUI 停机幂等标记和统一生命周期状态
- `autovt/gui/app.py:277-302` — 统一窗口关闭触发的异步停机链路
- `autovt/gui/app.py:439-459` — `_shutdown()` 改为一次性执行并补最终兜底清理
- `autovt/gui/app.py:497-580` — 把 `SIGINT/SIGTERM/SIGHUP` 统一到 GUI 停机入口
- `/Users/admin/go/src/go_cookies/autovt/doc/project_structure.md:61-72` — 更新 manager/worker/gui 生命周期职责说明
- `/Users/admin/go/src/go_cookies/autovt/doc/project_structure.md:112-188` — 更新启动/停止流程，写明 GUI 主生命周期与源码信号兜底

**依赖:**
- `psutil` — 复用现有进程树扫描与孤儿进程清理能力，不新增依赖

## Todolist

- [x] 1. 新建进程守卫模块

  **Files:**
  - Create: `autovt/multiproc/process_guard.py`

  ```text
  change details:
  新建: autovt/multiproc/process_guard.py
  - 导出 collect_autovt_helper_processes(...)，按项目自带 adb 路径 + known helper token 识别 autovt 残留进程
  - 导出 cleanup_autovt_helper_processes(...)，支持按 serial/原因清理并返回清理结果
  - 导出 is_parent_process_alive(...) / start_parent_watchdog(...) 之类的父进程存活辅助方法
  - 所有异常统一写日志，返回结构化结果，避免 manager/worker 内重复拼进程扫描代码
  ```

----------------------
- [x] 2. 给 manager 初始化和 close 接入启动清场

  **Files:**
  - Modify: `autovt/multiproc/manager.py:109-130`

  ```text
  change details:
  修改: autovt/multiproc/manager.py:109-126 (现: __init__ 只创建 ctx/queue/workers/锁并记录初始化日志)
  - 在 DeviceProcessManager 初始化完成前，先执行一次“历史孤儿进程清理”
  - 增加 manager 自身的幂等关闭标记，避免 atexit / GUI / signal 重复回收
  - 记录启动清场数量、serial、pid、cmdline 到日志

  修改: autovt/multiproc/manager.py:128-130 (现: close 仅打印“当前无常驻 SQLite 连接”调试日志)
  - 把 close 改成真正的最终收口入口
  - 在不重复 stop_all 的前提下做一次全局辅助进程兜底清理
  - 保留异常不抛出，只写错误日志
  ```

----------------------
- [x] 3. 给 manager 启动路径增加“先清旧再启动”

  **Files:**
  - Modify: `autovt/multiproc/manager.py:603-667`

  ```text
  change details:
  修改: autovt/multiproc/manager.py:603-606 (现: start_worker 只 drain_events + cleanup_dead)
  - 在启动新 worker 前，先清理当前 serial 对应的历史辅助残留
  - 若发现旧 worker 句柄已死但辅助进程仍活着，先记错误日志再清理

  修改: autovt/multiproc/manager.py:616-619 (现: old worker 还活着时直接返回“已在运行”)
  - 增加“worker 活着但辅助进程签名异常/混乱”的日志信息
  - 保持不重复启动，但把异常上下文写全

  修改: autovt/multiproc/manager.py:621-667 (现: 创建 stop_event/queue/process 后立即 start，并做秒退探针)
  - 保持原有启动逻辑
  - 启动成功日志补 lifecycle 信息，方便排查后续是谁留下的残留
  ```

----------------------
- [x] 4. 给 manager 的 stop_worker/stop_all 增加辅助进程复检

  **Files:**
  - Modify: `autovt/multiproc/manager.py:541-579`
  - Modify: `autovt/multiproc/manager.py:761-995`

  ```text
  change details:
  修改: autovt/multiproc/manager.py:541-559 (现: _finalize_worker_stop 只关闭 command_queue、释放账号并从 _workers 删除)
  - 在句柄移除前后补一次按 serial 的辅助进程兜底清理
  - 把清理结果写入 release_reason 对应日志，便于区分 stop_worker / stop_all / worker_dead

  修改: autovt/multiproc/manager.py:561-579 (现: cleanup_dead 只根据 process.is_alive() 清理句柄)
  - dead worker 发现时顺手补清辅助进程
  - 避免 Python worker 先死、helper 继续活着但 manager 误以为已干净

  修改: autovt/multiproc/manager.py:761-811 (现: _kill_worker_process_tree 仅清当前 worker 的 children(recursive=True))
  - 保留现有进程树 kill
  - 在树清理后追加 signature 级别复检，覆盖“已经脱离父子关系”的孤儿 helper

  修改: autovt/multiproc/manager.py:813-869 (现: stop_worker 结束条件只看 worker.process.is_alive())
  - 在 worker 退出后再次复检 serial 相关 helper
  - 如果复检清理了残留，返回文案改成“已停止并清理残留”
  - 如果仍有残留，记录 error 日志并把残留 pid/cmdline 打全

  修改: autovt/multiproc/manager.py:871-995 (现: stop_all 结束后逐个生成“已停止/已强制终止/已强制 kill”)
  - stop_all 第五阶段前后补全量辅助进程复检
  - 对每台设备分别汇总残留清理结果
  - 保证 GUI 显示“当前无运行中的设备进程”前，autovt 自有 helper 已经收口
  ```

----------------------
- [x] 5. 给 worker 增加父进程 watchdog 和 finally 自清理

  **Files:**
  - Modify: `autovt/multiproc/worker.py:151-161`
  - Modify: `autovt/multiproc/worker.py:430-494`
  - Modify: `autovt/multiproc/worker.py:1043-1065`

  ```text
  change details:
  修改: autovt/multiproc/worker.py:151-161 (现: worker 只忽略 SIGINT，让 manager 统一停机)
  - 保持“忽略 Ctrl+C”策略
  - 但补注释和逻辑：忽略 SIGINT 不代表允许脱离 manager 长跑
  - 后续统一由父进程 watchdog 负责在 manager 消失时停机

  修改: autovt/multiproc/worker.py:430-447 (现: worker 启动后仅标准化 register_mode、安装 SIGINT 忽略策略并写启动日志)
  - 记录启动时 parent pid
  - 启动后台 watchdog 线程，周期检测父进程是否仍存活
  - 父进程消失时写 stopping/error 日志并触发 stop_event

  修改: autovt/multiproc/worker.py:487-494 (现: 只构造 task_context 和 claim_condition_text)
  - 把当前 serial / register_mode / parent pid 等上下文同步给进程守卫模块
  - 为 finally 自清理准备可复用参数

  修改: autovt/multiproc/worker.py:1051-1065 (现: finally 只 release_user_for_device、close user_db、emit stopped)
  - 在 finally 里增加当前 worker 相关 helper 清理
  - 所有清理结果写日志
  - 保证 worker 自己退出时，也尽量把自家 adb/poco 辅助进程一起带走
  ```

----------------------
- [x] 6. 修复 worker 等待态异常退出点

  **Files:**
  - Modify: `autovt/multiproc/worker.py:727-770`

  ```text
  change details:
  修改: autovt/multiproc/worker.py:727-744 (现: _prepare_task_context 读取 t_config，失败时回退默认配置)
  - 整理等待态依赖字段的取值方式，避免闭包/作用域异常导致 worker 非预期退出
  - 保证等待态日志一定可输出，不因为文案变量问题把 worker 打崩

  修改: autovt/multiproc/worker.py:746-754 (现: 无可用账号时直接引用 claim_condition_text 上报 waiting)
  - 把 waiting 文案构造改成局部稳定值
  - 避免再次出现“无可用账号时 worker 因 NameError 退出”的情况
  - 保留详细日志，方便区分“真没账号”和“流程异常”
  ```

----------------------
- [x] 7. 统一 GUI 关闭、信号退出与幂等停机

  **Files:**
  - Modify: `autovt/gui/app.py:33-62`
  - Modify: `autovt/gui/app.py:277-302`
  - Modify: `autovt/gui/app.py:439-459`
  - Modify: `autovt/gui/app.py:497-580`

  ```text
  change details:
  修改: autovt/gui/app.py:33-62 (现: AutoVTGuiApp 只有 _closing/_action_running 状态，没有 shutdown 幂等保护)
  - 增加 shutdown_lock / shutdown_done 之类的幂等状态
  - 避免 window close、atexit、signal 多次同时进入 stop_all

  修改: autovt/gui/app.py:277-302 (现: _request_shutdown_and_close 只设置 _closing 并异步执行 _shutdown 后关窗)
  - 保持 GUI 页面触发为主入口
  - 把真正停机逻辑统一到单一方法，避免窗口关闭和信号退出走两套路径

  修改: autovt/gui/app.py:439-459 (现: _shutdown 直接 stop_all/reset_all_running_accounts/close user_db)
  - 改成“只执行一次”的停机核心方法
  - stop_all 后再调用 manager.close() 做最终兜底清理
  - 所有异常继续记错误日志，不让 GUI 半路卡死

  修改: autovt/gui/app.py:497-580 (现: run_gui 只注册 SIGINT，收到后直接 app._shutdown() + SystemExit(130))
  - 统一注册 SIGINT/SIGTERM/SIGHUP
  - 源码模式终端 Ctrl+C、终端结束都走同一条停机链路
  - 打包 GUI 仍以窗口生命周期为主，不依赖终端存在
  ```

----------------------
- [x] 8. 同步项目结构文档

  **Files:**
  - Modify: `/Users/admin/go/src/go_cookies/autovt/doc/project_structure.md:61-72`
  - Modify: `/Users/admin/go/src/go_cookies/autovt/doc/project_structure.md:112-188`

  ```text
  change details:
  修改: /Users/admin/go/src/go_cookies/autovt/doc/project_structure.md:61-72 (现: manager/worker/gui 职责只描述多进程和 stop_all，不含孤儿进程治理)
  - 补充“GUI 为主生命周期源”
  - 补充“manager 启动清理历史残留、停止后二次复检”
  - 补充“worker 监听父进程死亡并自清理”

  修改: /Users/admin/go/src/go_cookies/autovt/doc/project_structure.md:112-188 (现: 启动/停止流程只写 GUI/CLI/worker 常规流程)
  - 更新启动流程，写明 manager 初始化先清旧残留
  - 更新停止流程，写明 stop_all 后还会复检辅助进程
  - 标明源码模式支持 SIGINT/SIGTERM/SIGHUP，打包模式仍以 GUI 关窗为主
  ```

## 总结

共 8 条任务，涉及 5 个文件（新建 1 个，修改 4 个），预计改动约 220-320 行。

1. 抽出 `process_guard` 模块，单独管理 autovt 自有辅助进程识别与清理，避免 manager/worker 里散落进程扫描代码。
2. 在 manager 的初始化、启动、停止、关闭四个节点补齐“先清旧、再启动、停机后复检、close 最终兜底”的完整链路。
3. 在 worker 内部增加父进程 watchdog，让 manager/GUI 死亡时 worker 不会继续独跑。
4. 修复 worker 等待态异常退出点，减少“worker 先崩、helper 残留”的触发面。
5. 统一 GUI 页面关闭与源码终端信号退出，做到生命周期一致，但仍保持打包 GUI 不依赖终端。
6. 同步外部项目结构文档，保证后续维护者能按新生命周期模型理解代码。

## 变更记录
- 2026-03-22 11:14:45 初始创建
- 2026-03-22 11:19:52 完成 #1 新建进程守卫模块
- 2026-03-22 11:21:16 完成 #2 给 manager 初始化和 close 接入启动清场
- 2026-03-22 11:21:16 完成 #3 给 manager 启动路径增加“先清旧再启动”
- 2026-03-22 11:21:16 完成 #4 给 manager 的 stop_worker/stop_all 增加辅助进程复检
- 2026-03-22 11:22:19 完成 #5 给 worker 增加父进程 watchdog 和 finally 自清理
- 2026-03-22 11:22:19 完成 #6 修复 worker 等待态异常退出点
- 2026-03-22 11:22:55 完成 #7 统一 GUI 关闭、信号退出与幂等停机
- 2026-03-22 11:24:01 完成 #8 同步项目结构文档
