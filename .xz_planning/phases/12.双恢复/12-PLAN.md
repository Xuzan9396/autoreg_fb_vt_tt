# 版本 12: 双恢复按钮

> 创建时间: 2026-03-22 22:19:39
> 最后更新: 2026-03-22 22:42:17
> 状态: 已完成

## 需求描述

原始需求更新为：

`t_user` 表加一个 `vt_fail_num`，规则也是 `status=3、vt_fail_num<3、vinted_status!=1`。  
原来的“一键恢复”文案改成“一键恢复fb”，再加一个“一键恢复vt”。  
执行恢复时：
- FB 恢复要把 `fb_status` 改成 `0`
- VT 恢复要把 `vinted_status` 改成 `0`
- `vt_fail_num` 表示 Vinted 注册失败次数

## 技术方案

基于当前代码结构，只有一种合理做法：

把“可恢复问题账号”从当前仅支持 Facebook 的单通道逻辑，收敛成 FB / VT 两套对称能力，统一放在 `UserDB + AccountTab + 任务结果回写` 这三层里做。

当前代码现状已确认：

- 现在只有 `fb_fail_num`，没有 `vt_fail_num`
- 现在账号页只有一个“一键恢复账号问题”按钮
- 现在恢复 SQL 只命中 `status=3 and fb_fail_num<3 and fb_status!=1`
- 现在恢复后只改 `status=0`、`device=''`，并不会把 `fb_status` 改回 `0`
- 现在 Vinted 失败不会累计单独的失败次数

本次计划按以下语义实现：

- `一键恢复FB`
  只处理 `status=3 and fb_fail_num<3 and fb_status!=1`
  执行后改为 `status=0`、`fb_status=0`、`device=''`
- `一键恢复VT`
  只处理 `status=3 and vt_fail_num<3 and vinted_status!=1`
  执行后改为 `status=0`、`vinted_status=0`、`device=''`
- `vt_fail_num`
  只在 Vinted 注册失败落库时原子累加
  成功时不清零，编辑账号时也不允许人工改写

## 文件变更清单

**新建:**
- 无

**修改:**
- `autovt/userdb/user_db.py:188-208` — `UserRecord` 目前只有 `fb_fail_num`，需要补 `vt_fail_num`
- `autovt/userdb/user_db.py:306-318` — `t_user` 建表 SQL 目前没有 `vt_fail_num`
- `autovt/userdb/user_db.py:376-389` — 旧库补列逻辑目前只补 `fb_status / fb_fail_num`
- `autovt/userdb/user_db.py:728-765` — 记录校验目前只校验并回写 `fb_fail_num`
- `autovt/userdb/user_db.py:1396-1413` — 新增账号 SQL 目前只写入 `fb_fail_num`
- `autovt/userdb/user_db.py:1483-1495` — 编辑账号 SQL 目前只更新 `fb_fail_num`
- `autovt/userdb/user_db.py:1760-1833` — `update_status()` 目前只支持原子累加 `fb_fail_num`
- `autovt/userdb/user_db.py:1835-1891` — 统计/恢复方法目前只有 FB 一套
- `autovt/gui/account_tab.py:61-80` — 顶部计数控件占位目前只有一个 `retryable_problem_count_text`
- `autovt/gui/account_tab.py:203-233` — 顶部操作区目前只有一个“一键恢复账号问题”按钮和一段 FB 说明文案
- `autovt/gui/account_tab.py:424-515` — 快照读取和顶部数量回填目前只支持一个“可恢复”计数
- `autovt/gui/account_tab.py:687-746` — 列表卡片目前只展示 `fb_fail_num`
- `autovt/gui/account_tab.py:846-862` — 恢复入口目前只有一个 `_reset_retryable_problem_accounts()`
- `autovt/gui/account_tab.py:1402-1408` — 编辑弹窗当前只缓存 `fb_fail_num`
- `autovt/gui/account_tab.py:1837-1855` — 保存账号时当前只保留 `fb_fail_num` 原值
- `autovt/tasks/open_settings.py:2160-2250` — 通用结果回写目前只支持 `increment_fb_fail_num`
- `autovt/tasks/vinted.py:655-692` — Vinted 失败落库目前不会累加 `vt_fail_num`
- `doc/project_structure.md:74-91` — 本地结构文档需要同步账号页双恢复按钮、`vt_fail_num`、Vinted 失败累计规则
- `doc/project_structure.md:213-216` — 本地结构文档旧库补字段清单需要补 `vt_fail_num`
- `doc/project_structure.md:252-255` — 本地结构文档业务读写能力需要补 Vinted 失败累计规则
- `doc/project_structure.md:279-288` — 本地结构文档 GUI 功能映射需要改成 `一键恢复fb / 一键恢复vt`
- `/Users/admin/go/src/go_cookies/autovt/doc/project_structure.md:74-94` — 外部同步文档需要同步账号页双恢复按钮、`vt_fail_num`、Vinted 失败累计规则
- `/Users/admin/go/src/go_cookies/autovt/doc/project_structure.md:229-232` — 外部同步文档旧库补字段清单需要补 `vt_fail_num`
- `/Users/admin/go/src/go_cookies/autovt/doc/project_structure.md:269-272` — 外部同步文档业务读写能力需要补 Vinted 失败累计规则
- `/Users/admin/go/src/go_cookies/autovt/doc/project_structure.md:296-305` — 外部同步文档 GUI 功能映射需要改成 `一键恢复fb / 一键恢复vt`

**依赖:**
- 无新增依赖

## Todolist

- [x] 1. 在 `t_user` 数据结构和建表逻辑中加入 `vt_fail_num`

  **Files:**
  - Modify: `autovt/userdb/user_db.py:188-208`
  - Modify: `autovt/userdb/user_db.py:306-318`
  - Modify: `autovt/userdb/user_db.py:376-389`

  ```text
  change details:
  修改: autovt/userdb/user_db.py:188-208 (现: UserRecord 只有 vinted_status、fb_status、fb_fail_num，没有 vt_fail_num)
  - 给 UserRecord 增加 vt_fail_num: int = 0
  - 注释明确该字段表示 Vinted 注册失败累计次数

  修改: autovt/userdb/user_db.py:306-318 (现: t_user 建表 SQL 只有 fb_fail_num，没有 vt_fail_num)
  - 在建表 SQL 中增加 vt_fail_num INTEGER NOT NULL DEFAULT 0 CHECK (vt_fail_num >= 0)

  修改: autovt/userdb/user_db.py:376-389 (现: 旧库补列只处理 fb_status、fb_fail_num、client_id、device)
  - 旧库缺 vt_fail_num 时执行 ALTER TABLE 自动补列
  - 保持老库升级后可直接启动
  ```

----------------------

- [x] 2. 补齐 `vt_fail_num` 的校验、新增、编辑和表单保留逻辑

  **Files:**
  - Modify: `autovt/userdb/user_db.py:728-765`
  - Modify: `autovt/userdb/user_db.py:1396-1413`
  - Modify: `autovt/userdb/user_db.py:1483-1495`
  - Modify: `autovt/gui/account_tab.py:1402-1408`
  - Modify: `autovt/gui/account_tab.py:1837-1855`

  ```text
  change details:
  修改: autovt/userdb/user_db.py:728-765 (现: validate_user_record 只标准化 fb_fail_num)
  - 增加 vt_fail_num 的非负整数校验
  - 保证新增、编辑、UPSERT 统一走同一套校验

  修改: autovt/userdb/user_db.py:1396-1413 (现: create_user INSERT 字段只包含 fb_fail_num)
  - 新增账号 SQL 写入 vt_fail_num

  修改: autovt/userdb/user_db.py:1483-1495 (现: update_user_by_id UPDATE 字段只更新 fb_fail_num)
  - 编辑账号 SQL 同步更新 vt_fail_num

  修改: autovt/gui/account_tab.py:1402-1408 (现: 编辑弹窗只缓存 _editing_fb_fail_num)
  - 增加 _editing_vt_fail_num 缓存，避免编辑其他字段时把 vt_fail_num 重置为 0

  修改: autovt/gui/account_tab.py:1837-1855 (现: _collect_form_record 只把 fb_fail_num 原值带回 UserRecord)
  - 保存账号时一并保留 vt_fail_num 原值
  - 继续保持失败累计次数不允许人工编辑
  ```

----------------------

- [x] 3. 把状态回写能力扩展成同时支持 FB / VT 失败累计

  **Files:**
  - Modify: `autovt/userdb/user_db.py:1760-1833`
  - Modify: `autovt/tasks/open_settings.py:2160-2250`

  ```text
  change details:
  修改: autovt/userdb/user_db.py:1760-1833 (现: update_status 只支持 increment_fb_fail_num，原子自增也只有 fb_fail_num = fb_fail_num + 1)
  - 扩展为同时支持 vt_fail_num 原子累加
  - 保持 status、fb_status、vinted_status、msg、失败次数自增可以任意组合更新
  - 所有异常继续记录错误日志，避免库表更新失败静默吞掉

  修改: autovt/tasks/open_settings.py:2160-2250 (现: _update_result_to_db 只接收 increment_fb_fail_num，并写日志 increment_fb_fail_num)
  - 扩展通用结果回写参数，支持 Vinted 失败时透传 vt_fail_num 累加意图
  - 成功时不清零，失败时仅对应业务通道累加
  - 日志字段同步补齐 vt_fail_num 自增信息
  ```

----------------------

- [x] 4. 让 Vinted 失败时真正累计 `vt_fail_num`

  **Files:**
  - Modify: `autovt/tasks/vinted.py:655-692`

  ```text
  change details:
  修改: autovt/tasks/vinted.py:655-692 (现: Vinted 成功写 status=2/vinted_status=1，失败写 status=3或4/vinted_status=2，但不会累加 vt_fail_num)
  - 在非连接异常导致的 Vinted 失败回写里，开启 vt_fail_num 原子累加
  - 保持连接异常仍跳过失败落库，避免把断连误判成账号问题
  ```

----------------------

- [x] 5. 把账号页顶部按钮改成 `一键恢复fb / 一键恢复vt`

  **Files:**
  - Modify: `autovt/gui/account_tab.py:61-80`
  - Modify: `autovt/gui/account_tab.py:203-233`

  ```text
  change details:
  修改: autovt/gui/account_tab.py:61-80 (现: 顶部只有一个 retryable_problem_count_text 占位)
  - 增加 FB 可恢复数量文本和 VT 可恢复数量文本两个控件引用

  修改: autovt/gui/account_tab.py:203-233 (现: 顶部只有一个“一键恢复账号问题”按钮，文案说明也只有 FB 条件)
  - 原按钮文案改成“一键恢复fb”
  - 新增“一键恢复vt”按钮
  - 每个按钮右侧单独展示自己的“可恢复: N”
  - 页面说明改成同时解释 FB / VT 的恢复条件、恢复后字段变化，以及风控账号不会被处理
  ```

----------------------

- [x] 6. 扩展后台快照读取和顶部计数回填，支持 FB / VT 双计数

  **Files:**
  - Modify: `autovt/gui/account_tab.py:424-515`

  ```text
  change details:
  修改: autovt/gui/account_tab.py:424-515 (现: _load_account_page_snapshot 只查询一个 retryable_count，_apply_retryable_problem_count 也只回填一个顶部文本)
  - 后台快照一次读取 FB 可恢复数量和 VT 可恢复数量
  - 顶部回填方法拆成 FB / VT 两套，或抽成可复用通用方法
  - 查询失败时继续记录日志并做安全回退，避免按钮区因为计数异常崩掉
  ```

----------------------

- [x] 7. 在账号列表卡片中展示 `VT失败累计`，便于判断恢复按钮影响范围

  **Files:**
  - Modify: `autovt/gui/account_tab.py:687-746`

  ```text
  change details:
  修改: autovt/gui/account_tab.py:687-746 (现: 列表卡片只读取并展示 fb_fail_num)
  - 读取 vt_fail_num
  - 列表卡片新增 “VT失败累计: N”
  - 保持现有状态 pill、更新时间、设备号、备注展示结构不乱
  ```

----------------------

- [x] 8. 把恢复入口拆成 FB / VT 两条稳定链路，并补齐恢复后的状态字段重置

  **Files:**
  - Modify: `autovt/userdb/user_db.py:1835-1891`
  - Modify: `autovt/gui/account_tab.py:846-862`

  ```text
  change details:
  修改: autovt/userdb/user_db.py:1835-1891 (现: 只有 count_retryable_problem_users/reset_retryable_problem_users，条件和更新都只有 FB 一套，且恢复时不改 fb_status)
  - 提供 FB 可恢复数量统计与批量恢复方法
  - 提供 VT 可恢复数量统计与批量恢复方法
  - FB 恢复时执行 status=0、fb_status=0、device=''、update_at=当前时间
  - VT 恢复时执行 status=0、vinted_status=0、device=''、update_at=当前时间

  修改: autovt/gui/account_tab.py:846-862 (现: 只有 _reset_retryable_problem_accounts，直接调用 FB 恢复 SQL)
  - 拆成 _reset_retryable_problem_fb_accounts 和 _reset_retryable_problem_vt_accounts 两个入口
  - 成功后统一 refresh 刷新列表和两个顶部计数
  - 失败时统一记录异常日志并给出对应业务提示
  ```

----------------------

- [x] 9. 同步两份项目结构文档，保持代码与说明一致

  **Files:**
  - Modify: `doc/project_structure.md:74-91`
  - Modify: `doc/project_structure.md:213-216`
  - Modify: `doc/project_structure.md:252-255`
  - Modify: `doc/project_structure.md:279-288`
  - Modify: `/Users/admin/go/src/go_cookies/autovt/doc/project_structure.md:74-94`
  - Modify: `/Users/admin/go/src/go_cookies/autovt/doc/project_structure.md:229-232`
  - Modify: `/Users/admin/go/src/go_cookies/autovt/doc/project_structure.md:269-272`
  - Modify: `/Users/admin/go/src/go_cookies/autovt/doc/project_structure.md:296-305`

  ```text
  change details:
  修改: doc/project_structure.md:74-91 (现: 账号页与任务说明只描述 fb_fail_num 和单个“一键恢复账号问题”)
  - 改成一键恢复fb / 一键恢复vt 双按钮说明
  - 补充 vt_fail_num 与 Vinted 失败累计规则
  - 说明 FB 恢复会把 fb_status 置 0，VT 恢复会把 vinted_status 置 0

  修改: doc/project_structure.md:213-216 (现: 旧库补字段清单没有 vt_fail_num)
  - 补充 vt_fail_num 自动补列说明

  修改: doc/project_structure.md:252-255 (现: 业务读写能力只写 Facebook 失败累计)
  - 补充 Vinted 失败回写时原子累加 vt_fail_num，成功时不清零

  修改: doc/project_structure.md:279-288 (现: GUI 功能映射仍是单个“一键恢复账号问题”)
  - 改成一键恢复fb / 一键恢复vt
  - 说明两个按钮各自的命中条件与顶部数量含义

  修改: /Users/admin/go/src/go_cookies/autovt/doc/project_structure.md:74-94, 229-232, 269-272, 296-305
  - 与仓库内 project_structure.md 做同样同步，保持两份文档一致
  ```

## 总结

共 9 条任务，涉及 6 个文件（新建 0 个，修改 6 个），预计改动约 120-180 行。

1. 这次不是只改按钮文案，而是把“失败累计次数 + 一键恢复”从单 FB 模式扩成 FB / VT 对称能力。
2. 真正的关键点在于 `vt_fail_num` 入库、Vinted 失败时原子累加、恢复时把对应注册状态字段一起重置为 `0`。
3. GUI 侧会变成两个按钮、两个数量提示、两套恢复入口，同时列表卡片补 `VT失败累计`。
4. 文档会同步更新到仓库内和外部指定路径两份 `project_structure.md`。

按当前草案的默认理解：
- `一键恢复fb` 只重置 `fb_status`
- `一键恢复vt` 只重置 `vinted_status`

如果你希望任一恢复按钮都同时把 `fb_status` 和 `vinted_status` 一起清零，我再把草案改一下。

## 变更记录

- 2026-03-22 22:19:39 初始创建
- 2026-03-22 22:42:17 完成 #1 在 `t_user` 数据结构和建表逻辑中加入 `vt_fail_num`
- 2026-03-22 22:42:17 完成 #2 补齐 `vt_fail_num` 的校验、新增、编辑和表单保留逻辑
- 2026-03-22 22:42:17 完成 #3 把状态回写能力扩展成同时支持 FB / VT 失败累计
- 2026-03-22 22:42:17 完成 #4 让 Vinted 失败时真正累计 `vt_fail_num`
- 2026-03-22 22:42:17 完成 #5 把账号页顶部按钮改成 `一键恢复fb / 一键恢复vt`
- 2026-03-22 22:42:17 完成 #6 扩展后台快照读取和顶部计数回填，支持 FB / VT 双计数
- 2026-03-22 22:42:17 完成 #7 在账号列表卡片中展示 `VT失败累计`，便于判断恢复按钮影响范围
- 2026-03-22 22:42:17 完成 #8 把恢复入口拆成 FB / VT 两条稳定链路，并补齐恢复后的状态字段重置
- 2026-03-22 22:42:17 完成 #9 同步两份项目结构文档，保持代码与说明一致
