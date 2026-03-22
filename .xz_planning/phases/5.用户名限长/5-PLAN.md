# 版本 5: 用户名限长

> 创建时间: 2026-03-22 10:00:53
> 最后更新: 2026-03-22 10:03:24
> 状态: 待执行

## 需求描述
优化一个 _build_vinted_username /Users/admin/go/src/autovt/autovt/tasks/vinted.py，不能超过 18 个字符，如果超过了则截断后缀保持 18 个以下。

## 技术方案
当前代码只有一条合理改法：保留 `_build_vinted_username()` 现有的 `email_pwd + 4 位随机数` 生成方式不变，在最终返回前统一做长度上限控制；当拼接结果超过 `18` 个字符时，直接从尾部截断到 `18` 个字符以内，并记录一条长度裁剪日志。同时同步外部项目结构文档，补充这一生成规则，避免文档与实际行为不一致。

## 文件变更清单

**新建:**
- 无

**修改:**
- `autovt/tasks/vinted.py:58-77` — 给 Vinted 用户名增加 18 字符上限和超长截断日志
- `/Users/admin/go/src/go_cookies/autovt/doc/project_structure.md:83-83` — 补充 Vinted 用户名长度限制说明

**依赖:**
- 无新增依赖

## Todolist

- [x] 1. 给 Vinted 用户名生成逻辑增加长度上限

  **Files:**
  - Modify: `autovt/tasks/vinted.py:58-77`

  ```text
  change details:
  修改: autovt/tasks/vinted.py:58-77 (现: 直接读取 email_pwd，追加 4 位随机尾号后返回，无长度上限处理)
  - 保留 `email_pwd` 为空时记录错误日志并返回 `None` 的现有兜底逻辑
  - 保留 `random.randint(1000, 9999)` 的随机尾号生成方式
  - 在 `email_pwd + random_suffix` 拼接完成后新增长度判断
  - 当最终用户名长度大于 `18` 时，对最终结果执行尾部截断，保证返回值长度不超过 `18`
  - 新增一条信息日志，记录“发生过截断”以及截断前后长度，便于后续排查
  - 保持返回类型 `str | None` 和调用方 `vinted_run_all()` 的使用方式不变
  ```

----------------------

- [x] 2. 同步项目结构文档中的 Vinted 用户名规则

  **Files:**
  - Modify: `/Users/admin/go/src/go_cookies/autovt/doc/project_structure.md:83-83`

  ```text
  change details:
  修改: /Users/admin/go/src/go_cookies/autovt/doc/project_structure.md:83-83 (现: 仅描述 Vinted 注册主流程、滑块识别和失败日志，未说明用户名长度限制)
  - 在 `autovt/tasks/vinted.py` 的职责说明中补充 `_build_vinted_username()` 已增加 `18` 字符上限
  - 明确说明超长时会按尾部截断处理，保持文档与代码行为一致
  ```

## 总结

共 2 条任务，涉及 2 个文件（新建 0 个，修改 2 个），预计改动约 8 到 15 行。

1. 调整 `autovt/tasks/vinted.py` 的用户名生成函数，保持现有生成方式不变，只在返回前增加统一的 18 字符限制和截断日志。
2. 同步外部项目结构文档，记录 Vinted 用户名长度上限规则，避免后续维护时只看文档却误判行为。

## 变更记录
- 2026-03-22 10:00:53 初始创建
- 2026-03-22 10:02:57 完成 #1 给 Vinted 用户名生成逻辑增加长度上限
- 2026-03-22 10:03:24 完成 #2 同步项目结构文档中的 Vinted 用户名规则
