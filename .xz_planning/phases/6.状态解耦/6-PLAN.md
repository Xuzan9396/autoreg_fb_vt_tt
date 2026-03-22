# 版本 6: 状态解耦

> 创建时间: 2026-03-22 10:22:25
> 最后更新: 2026-03-22 10:37:29
> 状态: 待执行

## 需求描述
运行的时候 fb 和 vinted 取的状态不一样，fb 取 `status=0` 并且 `fb_status=0`，vinted 取 `status=0` 并且 `vinted_status=0`。小状态独立；同一邮箱后续可通过手动把 `status` 改回 `0` 再跑另一套注册。  
状态回写规则改成：
- 成功时：`status=2`，并把当前注册方式对应的小状态写成 `1`
- 失败时：`status=3/4`，并把当前注册方式对应的小状态写成 `2`
- 另一个未执行的平台小状态不应被误改

## 技术方案
当前代码只有一条合理改法：保持现有 `register_mode` 分流结构不变，在账号分配层新增“按当前注册方式对应小状态过滤”的领取逻辑；在 Facebook/Vinted 各自的收尾回写中统一使用“成功写 `1`、失败写 `2`”的小状态语义，同时保留总状态 `status=2/3/4` 的现有主流程控制。这样同一邮箱是否能再被某模式领走，完全由“`status` 是否被人工改回 `0`”和“该模式小状态是否仍为 `0`”共同决定，不会再出现 FB/Vinted 互相串状态。

## 文件变更清单

**新建:**
- 无

**修改:**
- `autovt/userdb/user_db.py:907-980` — 把账号领取条件从“只看 `status=0`”改成“同时看当前模式小状态=0”
- `autovt/multiproc/worker.py:41-48, 712-750` — 把当前 `register_mode` 对应的小状态字段透传到账号领取流程与等待日志
- `autovt/tasks/open_settings.py:2095-2106, 3398-3421` — 把 Facebook 失败回写的小状态从 `0` 改成 `2`
- `autovt/tasks/vinted.py:508-565` — 把 Vinted 失败回写从“保留原值”改成显式写 `vinted_status=2`
- `/Users/admin/go/src/go_cookies/autovt/doc/project_structure.md:229-231, 297-298, 314-319` — 同步账号领取条件与 FB/Vinted 小状态语义说明

**依赖:**
- 无新增依赖

## Todolist

- [x] 1. 给账号领取逻辑增加“按当前注册方式小状态=0”过滤

  **Files:**
  - Modify: `autovt/userdb/user_db.py:907-980`
  - Modify: `autovt/multiproc/worker.py:41-48`
  - Modify: `autovt/multiproc/worker.py:712-750`

  ```text
  change details:
  修改: autovt/userdb/user_db.py:907-980 (现: claim_user_for_device() 只按 status=0 和 device 为空领取账号，不区分 fb_status/vinted_status)
  - 把领取方法改成支持传入当前注册方式对应的小状态字段名
  - 在候选账号查询 SQL 中保留“status=0 AND (device='' OR device IS NULL)”条件
  - 在此基础上追加“当前小状态字段 = 0”的过滤条件
  - 保持 BEGIN IMMEDIATE 事务、device 绑定和 status=1 占用逻辑不变
  - 保持异常安全和并发抢占保护不变

  修改: autovt/multiproc/worker.py:41-48 (现: REGISTER_MODE_STATUS_FIELD_MAP 只用于重试判断)
  - 继续复用 facebook->fb_status、vinted->vinted_status 的映射
  - 明确该映射同时用于“领取账号筛选”和“状态重试判断”

  修改: autovt/multiproc/worker.py:712-750 (现: 固定调用 user_db.claim_user_for_device(serial)，等待日志只提示无 status=0 账号)
  - 改为把当前 status_field_name 传给账号领取方法
  - 让 facebook 模式只从 fb_status=0 的可用池领号
  - 让 vinted 模式只从 vinted_status=0 的可用池领号
  - 保持 device 为空校验，避免多设备抢同一邮箱
  ```

----------------------

- [x] 2. 统一 Facebook 失败时的小状态回写为 2

  **Files:**
  - Modify: `autovt/tasks/open_settings.py:2095-2106`
  - Modify: `autovt/tasks/open_settings.py:3398-3421`

  ```text
  change details:
  修改: autovt/tasks/open_settings.py:2095-2106 (现: _update_fb_result_to_db() 成功写 fb_status=1，失败写 fb_status=0)
  - 保持成功时 status=2、fb_status=1 的现有逻辑
  - 把失败时传给通用回写函数的 failure_status_value 从 0 改成 2
  - 保持 increment_fb_fail_num=True，不影响 Facebook 失败累计次数

  修改: autovt/tasks/open_settings.py:3398-3421 (现: 注释与收尾分支说明写“Facebook 失败时写 status=3/4, fb_status=0”)
  - 同步注释和日志语义为“Facebook 失败时写 status=3/4, fb_status=2”
  - 保持设备断连时跳过失败回写的保护逻辑不变
  ```

----------------------

- [x] 3. 统一 Vinted 失败时的小状态回写为 2

  **Files:**
  - Modify: `autovt/tasks/vinted.py:508-565`

  ```text
  change details:
  修改: autovt/tasks/vinted.py:508-565 (现: 成功时通过 _update_result_to_db() 写 vinted_status=1；失败时只更新 status/msg，显式保留原有 vinted_status)
  - 保持成功时 status=2、vinted_status=1 的现有逻辑
  - 把失败分支改成显式写入 vinted_status=2，而不是保留旧值
  - 保持 final_reason 生成、msg 截断、email_account 为空兜底和设备断连跳过回写的保护逻辑
  - 优先复用现有通用回写函数，避免 Facebook/Vinted 两套状态语义再次分叉
  ```

----------------------

- [x] 4. 同步项目结构文档中的账号领取与状态语义

  **Files:**
  - Modify: `/Users/admin/go/src/go_cookies/autovt/doc/project_structure.md:229-231`
  - Modify: `/Users/admin/go/src/go_cookies/autovt/doc/project_structure.md:297-298`
  - Modify: `/Users/admin/go/src/go_cookies/autovt/doc/project_structure.md:314-319`

  ```text
  change details:
  修改: /Users/admin/go/src/go_cookies/autovt/doc/project_structure.md:229-231 (现: claim_user_for_device() 只描述从 status=0 且 device 为空的账号池领取)
  - 补充账号领取会根据 register_mode 额外要求 fb_status=0 或 vinted_status=0
  - 说明同一邮箱是否能再次进入某模式，取决于手动把 status 改回 0 后，对应小状态是否仍为 0

  修改: /Users/admin/go/src/go_cookies/autovt/doc/project_structure.md:297-298 (现: 状态文案只写 0/1/2 枚举，未说明与总 status 的协同关系)
  - 补充 fb_status/vinted_status 的业务语义：0 未注册、1 成功、2 失败
  - 补充 status=2/3/4 时只更新当前注册方式对应的小状态，另一平台小状态保持原值

  修改: /Users/admin/go/src/go_cookies/autovt/doc/project_structure.md:314-319 (现: worker 领取与重试描述仍按全局 status=0 和 fb_status!=1 叙述)
  - 改成按 register_mode 领取当前模式可执行账号
  - 改成按当前 register_mode 对应的小状态判断是否继续重试
  - 保持 status=0/1/2/3/4 的总状态说明与实际代码一致
  ```

## 总结

共 4 条任务，涉及 5 个文件（新建 0 个，修改 5 个），预计改动约 35 到 60 行。

1. 改 `user_db + worker` 的账号领取条件，让 FB 和 Vinted 真正按各自小状态独立筛号。
2. 改 Facebook 收尾回写规则，失败时把 `fb_status` 统一写成 `2`，不再回到 `0`。
3. 改 Vinted 收尾回写规则，失败时把 `vinted_status` 显式写成 `2`，不再保留旧值。
4. 同步外部项目结构文档，记录“按模式领取 + 按模式回写”的新语义，避免后续维护再次误判。

## 变更记录
- 2026-03-22 10:22:25 初始创建
- 2026-03-22 10:30:20 完成 #1 给账号领取逻辑增加“按当前注册方式小状态=0”过滤
- 2026-03-22 10:36:14 完成 #2 统一 Facebook 失败时的小状态回写为 2
- 2026-03-22 10:36:46 完成 #3 统一 Vinted 失败时的小状态回写为 2
- 2026-03-22 10:37:29 完成 #4 同步项目结构文档中的账号领取与状态语义
