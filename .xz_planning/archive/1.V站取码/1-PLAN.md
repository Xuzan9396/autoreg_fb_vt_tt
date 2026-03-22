# 版本 1: V站取码

> 创建时间: 2026-03-21 22:25:03
> 最后更新: 2026-03-22 09:14:48
> 状态: 已归档

## 需求描述
`/Users/admin/go/src/autovt/autovt/emails/test_vt.py ,这个完善下，提取 vinted 的邮件， 实际提取的是 6 位验证码，例如 /Users/admin/go/src/autovt/autovt/emails/test.html 226754 , 完善下提取，然后新建一个 getvinted_code`

## 技术方案
已选方案 A。

在现有 `autovt/emails/` 目录中新增独立的 Vinted 解析模块，保持 Facebook/Vinted 各自的邮件识别和验证码提取规则分离；同时把 `emails.py` 里重复度高的“刷新 token -> 拉邮件 -> 调试落盘 -> 调解析器”流程抽成内部公共方法，让 `getfackbook_code()` 和新建的 `getvinted_code()` 共用同一套稳定日志和错误处理逻辑。这样本次先补 Vinted，后续再接别的邮件平台时也不需要继续复制整段取信流程。

## 文件变更清单

**新建:**
- `/Users/admin/go/src/autovt/autovt/emails/vinted_code.py` — Vinted 邮件识别、6 位验证码提取、离线 HTML 调试解析

**修改:**
- `/Users/admin/go/src/autovt/autovt/emails/emails.py:9-19` — 增加 Vinted 解析导入与公共流程所需类型导入
- `/Users/admin/go/src/autovt/autovt/emails/emails.py:25-36` — 扩展公共流程辅助类型/返回规范
- `/Users/admin/go/src/autovt/autovt/emails/emails.py:110-137` — 把当前 Facebook 入口开头改造成可复用的公共入口参数校验
- `/Users/admin/go/src/autovt/autovt/emails/emails.py:138-161` — 把刷新 token 流程抽到公共方法
- `/Users/admin/go/src/autovt/autovt/emails/emails.py:162-169` — 保留 access_token 空值兜底并并入公共流程
- `/Users/admin/go/src/autovt/autovt/emails/emails.py:170-183` — 把拉邮件异常处理抽到公共方法
- `/Users/admin/go/src/autovt/autovt/emails/emails.py:184-201` — 把错误结果落盘与失败返回抽到公共方法
- `/Users/admin/go/src/autovt/autovt/emails/emails.py:202-218` — 把成功结果调试落盘与日志收口抽到公共方法
- `/Users/admin/go/src/autovt/autovt/emails/emails.py:219-248` — 让 Facebook 入口变成公共方法包装器，并新增 `getvinted_code`
- `/Users/admin/go/src/autovt/autovt/emails/__init__.py:1-5` — 导出 `getvinted_code`
- `/Users/admin/go/src/autovt/autovt/emails/test_vt.py:7-18` — 导入入口从 Facebook 切换到 Vinted
- `/Users/admin/go/src/autovt/autovt/emails/test_vt.py:20-37` — 调试脚本改为调用 `getvinted_code`
- `/Users/admin/go/src/autovt/doc/project_structure.md:20-41` — 目录树补充 `autovt/emails/`
- `/Users/admin/go/src/autovt/doc/project_structure.md:58-79` — 模块职责补充 `emails.py`、`fackbook_code.py`、`vinted_code.py`、`test_vt.py`

**依赖:**
- 无新增第三方依赖，继续复用标准库、Outlook 拉信能力与现有 `loguru` 日志体系

## Todolist

- [x] 1. 创建 Vinted 专用解析模块

  **Files:**
  - Create: `/Users/admin/go/src/autovt/autovt/emails/vinted_code.py`

  ```text
  change details:
  新建: autovt/emails/vinted_code.py
  - 定义 Vinted 邮件识别关键词、6 位验证码正则和 section/html 提取正则
  - 定义 VintedCodeCandidate 数据结构，保存 code、mail_dt、subject、mail_from、source
  - 定义 _safe_text()、_to_plain_text()、_parse_mail_datetime() 基础清洗方法
  - 定义 _is_vinted_mail()、_extract_code_from_subject()、_extract_code_from_body()、_build_candidate_from_mail()
  - 定义 extract_latest_vinted_code()
  - 定义 extract_latest_vinted_code_from_html_text()
  - 定义 extract_latest_vinted_code_from_html_file()
  - 规则重点: 仅接受 6 位纯数字验证码，并优先命中 Vinted 发件人/主题/正文语义，避免误抓 Microsoft 等其他邮件中的数字
  ```

----------------------
- [x] 2. 在邮件入口模块中补齐 Vinted 解析导入和公共流程骨架

  **Files:**
  - Modify: `/Users/admin/go/src/autovt/autovt/emails/emails.py:9-19`
  - Modify: `/Users/admin/go/src/autovt/autovt/emails/emails.py:25-36`
  - Modify: `/Users/admin/go/src/autovt/autovt/emails/emails.py:110-137`

  ```text
  change details:
  修改: autovt/emails/emails.py:9-19 (现: 只导入 Any、Facebook 解析器、Outlook 拉信方法和 logger)
  - 新增公共流程需要的 Callable 等类型导入
  - 新增 from autovt.emails.vinted_code import extract_latest_vinted_code

  修改: autovt/emails/emails.py:25-36 (现: 只有 _normalize_bool_payload() 一个结果规范化方法)
  - 保留现有返回规范
  - 补一个内部公共流程的解析器类型约定，便于 Facebook/Vinted 入口共用

  修改: autovt/emails/emails.py:110-137 (现: getfackbook_code() 开头直接做 Facebook 专用日志和参数校验)
  - 抽成内部公共入口方法的函数头与参数校验
  - 让业务名/日志文案/解析函数通过参数传入，而不是写死 Facebook
  ```

----------------------
- [x] 3. 抽取共享的 token 刷新、拉信和调试落盘流程

  **Files:**
  - Modify: `/Users/admin/go/src/autovt/autovt/emails/emails.py:138-161`
  - Modify: `/Users/admin/go/src/autovt/autovt/emails/emails.py:162-169`
  - Modify: `/Users/admin/go/src/autovt/autovt/emails/emails.py:170-183`
  - Modify: `/Users/admin/go/src/autovt/autovt/emails/emails.py:184-201`
  - Modify: `/Users/admin/go/src/autovt/autovt/emails/emails.py:202-218`

  ```text
  change details:
  修改: autovt/emails/emails.py:138-161 (现: getfackbook_code() 内直接刷新 access_token 并记录 Facebook 日志)
  - 把 token 刷新步骤并入公共方法
  - 日志消息从写死的 Facebook 改为可复用文案

  修改: autovt/emails/emails.py:162-169 (现: 读取 access_token 并做空值兜底)
  - 保留空 token 保护
  - 统一放到公共方法里，避免 Vinted 再复制一份

  修改: autovt/emails/emails.py:170-183 (现: getfackbook_code() 内直接调用 get_mail_info() 并处理异常)
  - 抽成公共“拉邮件”步骤
  - 保证异常时统一打错误日志并返回可读错误文本

  修改: autovt/emails/emails.py:184-201 (现: mail_info 为 dict 时写调试 HTML、记日志、返回失败)
  - 保留当前失败落盘能力
  - 放到公共方法，供 Facebook/Vinted 共用

  修改: autovt/emails/emails.py:202-218 (现: 拉信成功后可选写 test.html 调试快照)
  - 保留成功结果的 HTML 快照输出
  - 让 Vinted 调试同样复用这套落盘逻辑
  ```

----------------------
- [x] 4. 收口 Facebook 包装器，并新增 `getvinted_code` 对外入口

  **Files:**
  - Modify: `/Users/admin/go/src/autovt/autovt/emails/emails.py:219-248`

  ```text
  change details:
  修改: autovt/emails/emails.py:219-248 (现: getfackbook_code() 末尾直接调用 extract_latest_fackbook_code() 并返回 Facebook 成功日志)
  - 把当前 Facebook 解析尾部改成调用内部公共流程 + extract_latest_fackbook_code()
  - 新增 getvinted_code(client_id, email_name, refresh_token, is_debug=False)
  - 新入口复用公共流程，并传入 extract_latest_vinted_code()
  - Vinted 成功日志要记录 code_length、parse_elapsed_ms、total_elapsed_ms
  ```

----------------------
- [x] 5. 导出新入口并修正 Vinted 调试脚本

  **Files:**
  - Modify: `/Users/admin/go/src/autovt/autovt/emails/__init__.py:1-5`
  - Modify: `/Users/admin/go/src/autovt/autovt/emails/test_vt.py:7-18`
  - Modify: `/Users/admin/go/src/autovt/autovt/emails/test_vt.py:20-37`

  ```text
  change details:
  修改: autovt/emails/__init__.py:1-5 (现: 只导出 getfackbook_code)
  - 新增 getvinted_code 导出
  - 更新 __all__，保证 from autovt.emails import getvinted_code 可直接使用

  修改: autovt/emails/test_vt.py:7-18 (现: 注释和导入都指向 getfackbook_code)
  - 导入改成 getvinted_code
  - 直跑兜底分支同步改成导入 getvinted_code
  - 修正注释中错误的 Facebook 描述

  修改: autovt/emails/test_vt.py:20-37 (现: main() 中调用 getfackbook_code，is_debug=True)
  - 改成调用 getvinted_code
  - 保留现有 client_id/email_name/refresh_token 参数透传方式
  - 保留终端 print 输出，方便人工直接查看提取出的 6 位验证码
  ```

----------------------
- [x] 6. 同步项目结构文档中的邮件模块说明

  **Files:**
  - Modify: `/Users/admin/go/src/autovt/doc/project_structure.md:20-41`
  - Modify: `/Users/admin/go/src/autovt/doc/project_structure.md:58-79`

  ```text
  change details:
  修改: doc/project_structure.md:20-41 (现: autovt 目录树中没有 emails/ 目录)
  - 在目录树中补充 autovt/emails/
  - 标出 emails.py、fackbook_code.py、vinted_code.py、test_vt.py 等关键文件

  修改: doc/project_structure.md:58-79 (现: 模块职责只写了 gui、cli、logs、multiproc、tasks 等，未覆盖邮件模块)
  - 新增 autovt/emails/emails.py 职责说明
  - 新增 autovt/emails/fackbook_code.py 与 autovt/emails/vinted_code.py 的职责说明
  - 新增 autovt/emails/test_vt.py 的调试用途说明
  ```

## 总结

共 6 条任务，涉及 5 个文件（新建 1 个，修改 4 个），预计改动约 140 到 220 行。

1. 新增独立的 Vinted 解析模块，专门处理 Vinted 邮件识别和 6 位验证码提取。
2. 把现有 `emails.py` 中的公共取信流程抽出来，避免 Facebook/Vinted 各复制一套。
3. 保持 Facebook 解析器不和 Vinted 规则混写，降低后续维护和误判风险。
4. 把 `test_vt.py` 真正改成 Vinted 调试脚本，和文件名语义一致。
5. 同步更新 `/Users/admin/go/src/autovt/doc/project_structure.md`，避免目录文档继续落后于代码结构。

## 变更记录
- 2026-03-21 22:25:03 初始创建
- 2026-03-21 22:38:08 完成 #1 创建 Vinted 专用解析模块
- 2026-03-21 22:38:58 完成 #2 在邮件入口模块中补齐 Vinted 解析导入和公共流程骨架
- 2026-03-21 22:39:57 完成 #3 抽取共享的 token 刷新、拉信和调试落盘流程
- 2026-03-21 22:41:19 完成 #4 收口 Facebook 包装器，并新增 `getvinted_code` 对外入口
- 2026-03-21 22:42:12 完成 #5 导出新入口并修正 Vinted 调试脚本
- 2026-03-21 22:43:02 完成 #6 同步项目结构文档中的邮件模块说明
- 2026-03-22 09:14:48 归档完成
