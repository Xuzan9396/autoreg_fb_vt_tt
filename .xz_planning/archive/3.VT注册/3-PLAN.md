# 版本 3: Vinted注册流程

> 创建时间: 2026-03-22 00:31:47
> 最后更新: 2026-03-22 09:14:48
> 状态: 已归档

## 需求描述
完成 `/Users/admin/go/src/autovt/autovt/tasks/vinted.py` 里的 `vinted_run_all`，把流程写到 `start_app(self.vinted_package)` 后面，按用户给出的粗略步骤实现 Vinted 注册；实现时优先复用 `/Users/admin/go/src/autovt/autovt/tasks/open_settings.py` 里的安全方法，不直接裸调 `poco(...).click()`；把 Vinted 的多语言定义新增到 `/Users/admin/go/src/autovt/autovt/fr_desc.py`，组织方式参考 `/Users/admin/go/src/autovt/autovt/desc.py`；并同步更新文档 `/Users/admin/go/src/go_cookies/autovt/doc/project_structure.md`。输入数据来自 `t_user`，其中用户名取 `email_pwd + 1000~9999 随机四位`，邮箱取 `email_account`，密码取 `pwd`，每个失败点都要记日志。

## 技术方案
唯一合理方案：在 `VintedTask` 内补 Vinted 专用安全流程，直接复用 `OpenSettingsTask` 已有的 `_require_poco()`、`poco_find_or_click()`、`_safe_wait_click()`、`_safe_click()`、`_safe_input_on_focused()` 和通用失败回写能力，不改动 `open_settings.py` 公共基类，降低 Facebook/设置页现有流程回归风险；Vinted 页面文案单独放到新文件 `autovt/fr_desc.py`，避免继续堆到 `autovt/desc.py` 里混杂 Facebook 常量。

## 文件变更清单

**新建:**
- `autovt/fr_desc.py` — 定义 Vinted 注册页法语/英文文案、正则、粘贴候选文本映射

**修改:**
- `autovt/tasks/vinted.py:3-10` — 补充 Vinted 流程所需导入（现: 仅有 `sleep/start_app/OpenSettingsTask/TaskContext` 的骨架导入）
- `autovt/tasks/vinted.py:15-20` — 将 `vinted_run_all()` 从占位实现改为完整注册流程，并在该区域附近新增 Vinted 专用辅助方法（现: 只 `start_app(self.vinted_package)` 后直接 `return True`）
- `/Users/admin/go/src/go_cookies/autovt/doc/project_structure.md:79-80` — 同步 Vinted 模块职责说明（现: 文档写明 `vinted_run_all()` 仍是占位骨架）

**依赖:**
- 无新增第三方依赖
- 复用现有 `airtest` / `poco` / `OpenSettingsTask` 安全能力
- 使用 Python 标准库 `random` 生成 4 位随机尾号

## Todolist

- [x] 1. 创建 Vinted 文案配置文件

  **Files:**
  - Create: `autovt/fr_desc.py`

  ```text
  change details:
  新建: autovt/fr_desc.py
  - 定义 VINTED_SHOW_REGISTRATION_OPTIONS_BUTTON：注册入口按钮资源/说明
  - 定义 VINTED_EMAIL_ACTION_BUTTON：邮箱注册入口说明
  - 定义 VINTED_USERNAME_INPUT：用户名输入框正则文案映射
  - 定义 VINTED_EMAIL_INPUT：邮箱输入框文案映射
  - 定义 VINTED_PASSWORD_INPUT：密码输入框正则文案映射
  - 定义 VINTED_TERMS_AND_CONDITIONS：勾选说明
  - 定义 VINTED_EMAIL_REGISTER_SIGN_UP：提交注册按钮说明
  - 定义 VINTED_PASTE_BUTTON：系统“粘贴/Coller/Paste”候选文案
  ```

----------------------

- [x] 2. 给 `vinted.py` 补充导入和 Vinted 辅助方法

  **Files:**
  - Modify: `autovt/tasks/vinted.py:3-10`
  - Modify: `autovt/tasks/vinted.py:15-20`

  ```text
  change details:
  修改: autovt/tasks/vinted.py:3-10 (现: 只有 Airtest 启动/等待和任务类导入, 改后: 增加 random 与 Vinted 文案模块导入)
  - 新增 random 导入，用于生成 1000~9999 的随机尾号
  - 新增 autovt.fr_desc 导入，读取 Vinted 文案配置

  修改: autovt/tasks/vinted.py:15-20 (现: vinted_run_all 只有启动应用后直接返回 True)
  - 在该区域附近新增 _build_vinted_username()，从 t_user.email_pwd 拼接 4 位随机数
  - 在该区域附近新增 Vinted 输入辅助方法，统一处理“点击聚焦 -> 可选点击粘贴按钮 -> _safe_input_on_focused”
  - 所有辅助方法统一记录 info/error 日志，失败时返回 False，不吞掉异常上下文
  ```

----------------------

- [x] 3. 实现 Vinted 注册入口点击流程

  **Files:**
  - Modify: `autovt/tasks/vinted.py:15-20`

  ```text
  change details:
  修改: autovt/tasks/vinted.py:15-20 (现: start_app 后没有任何页面动作)
  - start_app(self.vinted_package) 后增加页面稳定等待
  - 通过 self._require_poco() 获取 Poco 实例
  - 使用 self.poco_find_or_click(...) 点击 fr.vinted:id/show_registration_options_button，等待 10 秒
  - 使用 self.poco_find_or_click(...) 点击 fr.vinted:id/email_action_button，等待 5 秒
  - 每一步失败都记录明确日志，并通过 _set_task_result_failure 写入可读失败原因
  ```

----------------------

- [x] 4. 实现用户名、邮箱、密码输入与勾选提交

  **Files:**
  - Modify: `autovt/tasks/vinted.py:15-20`

  ```text
  change details:
  修改: autovt/tasks/vinted.py:15-20 (现: 没有任何表单输入和提交逻辑)
  - 点击用户名输入框：优先用 poco(textMatches=...) 或文案候选定位，调用 _safe_click 聚焦
  - 用户名输入值使用 t_user.email_pwd + 4位随机数
  - 点击邮箱输入框后，输入 t_user.email_account
  - 点击密码输入框后，输入 t_user.pwd
  - 三个输入步骤都走统一辅助方法：必要时点击“粘贴/Coller/Paste”，最终调用 _safe_input_on_focused
  - 使用 self.poco_find_or_click(...) 或 _safe_click(...) 勾选 fr.vinted:id/terms_and_conditions_checkbox
  - 使用 self.poco_find_or_click(...) 或 _safe_wait_click(...) 点击 fr.vinted:id/email_register_sign_up
  - 对空值、节点未命中、输入失败分别记录 error 日志并返回 False
  ```

----------------------

- [x] 5. 收尾 Vinted 成功/失败判定并同步文档

  **Files:**
  - Modify: `autovt/tasks/vinted.py:15-20`
  - Modify: `/Users/admin/go/src/go_cookies/autovt/doc/project_structure.md:79-80`

  ```text
  change details:
  修改: autovt/tasks/vinted.py:15-20 (现: 主流程没有成功条件、失败原因和完成日志)
  - 为 vinted_run_all 增加成功日志与统一返回 True/False
  - 对用户名构造失败、账号字段为空、注册按钮未命中等场景设置 task_result_reason
  - 保持异常交给 run_once 外层统一兜底，避免破坏现有状态回写逻辑

  修改: /Users/admin/go/src/go_cookies/autovt/doc/project_structure.md:79-80 (现: 文档描述 vinted_run_all 仍为占位逻辑)
  - 把 vinted.py 描述更新为“已实现邮箱注册入口、表单输入、勾选提交”
  - 补充 autovt/fr_desc.py 的职责说明，注明其承载 Vinted 法语/英文页面文案
  ```

----------------------

- [x] 6. 调整 Vinted 失败状态回写

  **Files:**
  - Modify: `autovt/tasks/vinted.py:349-387`

  ```text
  change details:
  修改: autovt/tasks/vinted.py:349-387 (现: Vinted 成功写 status=2,vinted_status=1，失败写 status=3/4,vinted_status=2)
  - 保持成功分支继续写入 vinted_status=1
  - 失败分支改为直接调用 user_db.update_status(...)，只更新 status 与 msg
  - 失败分支不再通过 _update_result_to_db(..., status_field="vinted_status") 回写 vinted_status=2
  - 保持设备断连场景继续跳过失败回写
  - 日志中明确记录“失败仅更新 status/msg，保留 vinted_status 原值”
  ```

## 总结

共 6 条任务，涉及 3 个文件（新建 1 个，修改 2 个），预计改动约 130 行。

1. 创建 Vinted 独立文案模块，承载法语/英文输入框、按钮和粘贴候选文本。
2. 在 `VintedTask` 内补齐用户名生成与安全输入辅助，避免直接裸调 Poco 点击和输入。
3. 按用户给定顺序实现“注册入口 -> 邮箱入口 -> 三个字段输入 -> 勾选 -> 提交”的完整流程。
4. 所有步骤失败都写日志并设置可读失败原因，继续复用现有 `run_once()` 状态回写。
5. 更新外部项目结构文档，去掉“Vinted 仍是骨架”的过期说明。
6. 调整 Vinted 失败回写语义，失败时仅更新 `status/msg`，保留原有 `vinted_status`。

## 变更记录
- 2026-03-22 00:31:47 初始创建
- 2026-03-22 00:35:14 完成 #1 创建 Vinted 文案配置文件
- 2026-03-22 00:36:28 完成 #2 给 `vinted.py` 补充导入和 Vinted 辅助方法
- 2026-03-22 00:36:28 完成 #3 实现 Vinted 注册入口点击流程
- 2026-03-22 00:36:28 完成 #4 实现用户名、邮箱、密码输入与勾选提交
- 2026-03-22 00:38:24 完成 #5 收尾 Vinted 成功/失败判定并同步文档
- 2026-03-22 08:44:48 追加 #6 调整 Vinted 失败状态回写
- 2026-03-22 08:45:55 完成 #6 调整 Vinted 失败状态回写
- 2026-03-22 09:14:48 归档完成
