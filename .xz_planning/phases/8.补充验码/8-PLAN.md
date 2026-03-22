# 版本 8: 补充验码

> 创建时间: 2026-03-22 11:40:17
> 最后更新: 2026-03-22 11:43:04
> 状态: 待执行

## 需求描述
/Users/admin/go/src/autovt/autovt/tasks/vinted.py 465 行追加下面逻辑，参考该文件使用的方法，下面只是大概流程：

- 点击接受，查找点击，最多等待 40s
  `poco(text="Accepter tout").click()`
- 点击验证码框架，最多等待 10s
  `poco("fr.vinted:id/view_input_value").click()`
- 获取 vinted 验证码，参考 /Users/admin/go/src/autovt/autovt/emails/test_vt.py，如果没获取成功验证码，重试 5 次，每次等待 15s，然后输入粘贴
- 提交验证码，等待 10s
  `poco("fr.vinted:id/verify_code_button").click()`

## 技术方案
沿用现有 VintedTask 的安全封装，在 `vinted.py` 内补两个 Vinted 专用 helper：

1. 复用 `autovt.emails.getvinted_code()` 增加 `_fetch_vinted_code()`，按现有 Facebook 取码模式做 5 次重试、15 秒等待和失败日志落库，但不重复校验外层导入阶段已保证的账号字段。
2. 增加 `_finish_vinted_email_verify()`，统一处理“Accepter tout -> 点击验证码框 -> 粘贴/输入验证码 -> 点击提交”这段 UI 流程，并通过 `poco_find_or_click`、`_safe_wait_click`、`_try_click_vinted_paste`、`_safe_input_on_focused` 完成稳定化。
3. 主流程 `vinted_run_all()` 在滑块后串接该 helper，失败时通过 `_vinted_fail()` 统一终止。

稳定性取舍：
- `Accepter tout` 视为可能出现的弹层，先等待最多 40 秒命中；未出现时记录日志后继续，不把“无弹层”误判为失败。
- 验证码输入和提交是必经步骤，未命中时按失败处理并写错误日志。

## 文件变更清单

**修改:**
- `autovt/fr_desc.py:1-20` — 增加 Vinted 验证码流程相关常量
- `autovt/tasks/vinted.py:24-35` — 增加验证码流程所需导入
- `autovt/tasks/vinted.py:181-221` — 增加 Vinted 取码与提交流程 helper
- `autovt/tasks/vinted.py:455-466` — 在注册主流程末尾串接验证码步骤
- `/Users/admin/go/src/go_cookies/autovt/doc/project_structure.md:78-84` — 同步说明 Vinted 邮箱验证码流程已纳入主链路

**依赖:**
- `autovt.emails.getvinted_code` — 拉取并解析最新 Vinted 邮件验证码
- 无新增第三方依赖

## Todolist

- [x] 1. 补充 Vinted 验证码定位常量

  **Files:**
  - Modify: `autovt/fr_desc.py:1-20`

  ```text
  change details:
  修改: autovt/fr_desc.py:1-20 (现: 只定义注册入口、表单输入框、提交按钮和粘贴文案常量)
  - 新增 “Accepter tout” 文案常量映射，供 poco 文本点击复用
  - 新增验证码输入框资源 ID 常量 `fr.vinted:id/view_input_value`
  - 新增验证码提交按钮资源 ID 常量 `fr.vinted:id/verify_code_button`
  ```
----------------------
- [x] 2. 在 VintedTask 中接入 Vinted 取码入口

  **Files:**
  - Modify: `autovt/tasks/vinted.py:24-35`
  - Modify: `autovt/tasks/vinted.py:181-221`

  ```text
  change details:
  修改: autovt/tasks/vinted.py:24-35 (现: 只导入 Vinted 表单相关常量和 OpenSettingsTask)
  - 新增 `from autovt.emails import getvinted_code`
  - 新增验证码流程常量导入，保持 locator 集中管理

  修改: autovt/tasks/vinted.py:181-221 (现: 只有 `_focus_and_input_vinted_field()`，后面直接进入 `vinted_slider()`)
  - 新增 `_fetch_vinted_code(retry_times=5, wait_seconds=15)` 方法
  - 复用 `getvinted_code()` 做 5 次重试，每次固定等待 15 秒
  - 每次失败都记录 warning/exception，最终失败写入明确原因
  ```
----------------------
- [x] 3. 增加 Vinted 验证码界面提交流程 helper

  **Files:**
  - Modify: `autovt/tasks/vinted.py:181-221`

  ```text
  change details:
  修改: autovt/tasks/vinted.py:181-221 (现: helper 仅覆盖普通字段输入，不含邮箱验证码页面处理)
  - 新增 `_finish_vinted_email_verify(poco)` 方法
  - 先用安全方法等待并点击 “Accepter tout”，最长 40 秒，未出现仅记日志继续
  - 再用安全方法等待并点击验证码输入框，最长 10 秒
  - 调用 `_fetch_vinted_code()` 获取验证码
  - 输入阶段优先复用 `_try_click_vinted_paste()`，失败再回退 `_safe_input_on_focused()`
  - 最后用 `_safe_wait_click()` 点击验证码提交按钮，最长 10 秒
  - 各失败分支都调用 `_vinted_fail()` 或记录错误日志，保证收尾状态可回写
  ```
----------------------
- [x] 4. 串接 Vinted 注册主流程末尾的验证码步骤

  **Files:**
  - Modify: `autovt/tasks/vinted.py:455-466`

  ```text
  change details:
  修改: autovt/tasks/vinted.py:455-466 (现: 提交注册后只执行滑块，465 行仍是 `# todo 处理验证码流程`)
  - 保留现有“提交注册 -> 滑块”流程
  - 在滑块后调用 `_finish_vinted_email_verify(poco)`
  - 验证码流程失败时直接返回 `_vinted_fail(...)`
  - 成功时补充验证码提交成功日志，再 `return True`
  ```
----------------------
- [x] 5. 同步项目结构文档

  **Files:**
  - Modify: `/Users/admin/go/src/go_cookies/autovt/doc/project_structure.md:78-84`

  ```text
  change details:
  修改: /Users/admin/go/src/go_cookies/autovt/doc/project_structure.md:78-84 (现: emails 模块描述偏 Facebook，Vinted 任务描述只写到滑块校验)
  - 补充 `autovt/emails/emails.py` 同时提供 `getvinted_code(...)`
  - 更新 `autovt/tasks/vinted.py` 描述为“提交注册 -> 滑块 -> 邮箱验证码输入与提交”完整流程
  - 强调验证码失败也会记录详细日志并回写失败原因
  ```

## 总结

共 5 条任务，涉及 3 个文件（新建 0 个，修改 3 个），预计改动约 70-110 行。

1. 扩 locator 常量，避免在 `vinted.py` 内硬编码验证码页面控件。
2. 复用现有邮箱拉码链路，增加 Vinted 专用取码 helper，保证重试和日志行为一致。
3. 用现有安全点击/输入能力把验证码页面封装成独立 helper，降低主流程复杂度。
4. 把 465 行 TODO 替换成真正的后置验码链路，失败时仍走现有 `_vinted_fail()` 收口。
5. 同步外部项目结构文档，避免代码和维护文档描述不一致。

## 变更记录
- 2026-03-22 11:40:17 初始创建
- 2026-03-22 11:41:07 完成 #1 补充 Vinted 验证码定位常量
- 2026-03-22 11:41:43 完成 #2 在 VintedTask 中接入 Vinted 取码入口
- 2026-03-22 11:42:16 完成 #3 增加 Vinted 验证码界面提交流程 helper
- 2026-03-22 11:42:34 完成 #4 串接 Vinted 注册主流程末尾的验证码步骤
- 2026-03-22 11:43:04 完成 #5 同步项目结构文档
