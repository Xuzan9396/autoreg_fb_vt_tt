# 版本 9: V站重装

> 创建时间: 2026-03-22 11:58:05
> 最后更新: 2026-03-22 12:13:47
> 状态: 待执行

## 需求描述
全局配置 t_config 表 key 加个字段 vt_delete_num，这个逻辑和 fb_delete_num 一样，也是第几次安装 apk，只是在运行 vinted 注册方式的时候生效。默认 0 不删除，其他数字每隔第几次重装一次，安装包位置是 apks/vinted.apk。现有参考链路在 facebook 的 fb_delete_num、_resolve_facebook_apk_path，以及 Vinted 任务入口相关代码。

## 技术方案
沿用现有 `fb_delete_num` 的最小改动方案，新增 `vt_delete_num` 配置常量、默认值、校验与 GUI 输入框；worker 继续读取完整 `t_config` 并补齐默认值，同时补一层 `vt_delete_num` 的运行时日志；任务层复用 `OpenSettingsTask` 的安全方法，新增 `vinted.apk` 路径解析、安装方法和周期判断方法，再把 `_run_vinted_cleanup_flow()` 从“仅 stop + clear_app”升级为“先清理，再按 `worker_loop_seq % vt_delete_num == 0` 触发卸载 + 重装”。
经代码检索，`apks/vinted.apk` 已存在；`autovt/gui/device_tab.py` 当前只负责 GUI 启动/安装按钮，不在 Vinted 周期重装执行链路内，因此本需求不改它。`autovt/tasks/vinted.py` 仍通过既有 `_run_vinted_cleanup_flow()` 入口吃到新逻辑，避免把安装细节散落到子类里。

## 文件变更清单

**修改:**
- `autovt/gui/helpers.py:23-34` — 新增 `vt_delete_num` 的 GUI 常量与说明文案（现: 这里只有 `vt_pwd`、`fb_delete_num`、`setting_fb_del_num`）
- `autovt/userdb/user_db.py:39-56` — 新增 `vt_delete_num` key/desc/default 常量（现: 只有 `vt_pwd`、`fb_delete_num`、`setting_fb_del_num` 默认值）
- `autovt/userdb/user_db.py:425-458` — 在默认配置补齐逻辑里插入 `vt_delete_num=0`（现: 只插入 `vt_pwd`、`fb_delete_num`、`setting_fb_del_num`）
- `autovt/userdb/user_db.py:530-577` — 增加 `vt_delete_num` 的非负整数范围校验（现: 只校验 `vt_pwd`、`fb_delete_num`、`setting_fb_del_num`）
- `autovt/userdb/user_db.py:1678-1689` — 增加 `vt_delete_num` 的固定 desc 回填（现: desc 回填只覆盖 `vt_pwd`、`fb_delete_num`、`setting_fb_del_num`）
- `autovt/gui/settings_tab.py:13-28` — 导入新的 `vt_delete_num` 常量（现: 未导入）
- `autovt/gui/settings_tab.py:49-62` — 增加 `vt_delete_num` 输入框/描述控件引用（现: 未持有该字段）
- `autovt/gui/settings_tab.py:97-125` — 创建 `vt_delete_num` 输入框与软校验回调（现: 只有 `fb_delete_num`、`setting_fb_del_num`）
- `autovt/gui/settings_tab.py:177-183` — 调整双列布局，把 `vt_delete_num` 放进设置表单（现: 只有 `vt_pwd`、`fb_delete_num`、`setting_fb_del_num`）
- `autovt/gui/settings_tab.py:367-375` — 增加 `vt_delete_num` 输入清洗方法（现: 只有 `fb_delete_num`、`setting_fb_del_num`）
- `autovt/gui/settings_tab.py:478-548` — 刷新时回填 `vt_delete_num` 的值与描述（现: refresh 不读该字段）
- `autovt/gui/settings_tab.py:590-655` — 快照读取时补 `vt_delete_num`（现: snapshot 不读该字段）
- `autovt/gui/settings_tab.py:668-739` — 保存时校验并落库 `vt_delete_num`（现: save 不写该字段）
- `autovt/multiproc/worker.py:28-42` — 导入 `vt_delete_num` 默认值与边界常量（现: 未导入）
- `autovt/multiproc/worker.py:192-213` — 追加 `_read_vt_delete_num()` 或等价读取逻辑（现: 只有 `_read_fb_delete_num()`）
- `autovt/multiproc/worker.py:783-790` — 读取 `t_config` 失败时补 `vt_delete_num` 默认回退（现: fallback config 没有该 key）
- `autovt/multiproc/worker.py:911-914` — run 前日志补 `vt_delete_num`（现: 只打印 `fb_delete_num`）
- `autovt/tasks/open_settings.py:110-145` — 初始化阶段读取 `vt_delete_num`（现: 只读 `vt_pwd`、`fb_delete_num`、`setting_fb_del_num`）
- `autovt/tasks/open_settings.py:217-260` — 增加 `_read_vt_delete_num()`（现: 只有 `_read_fb_delete_num()` 与 `_read_setting_fb_del_num()`）
- `autovt/tasks/open_settings.py:362-419` — 增加 `_should_delete_vt_this_loop()` 与 `_resolve_vinted_apk_path()`（现: 只支持 Facebook 周期判断和 `facebook.apk` 路径解析）
- `autovt/tasks/open_settings.py:618-659` — 增加 `_safe_install_vinted_apk()`，复用现有安全安装模式（现: 只有 `_safe_install_facebook_apk()`）
- `autovt/tasks/open_settings.py:1199-1207` — 把 Vinted 清理流改成“按周期重装”入口（现: 只 stop + clear_app）
- `autovt/tasks/open_settings.py:3335-3345` — 任务开始日志补 `vt_delete_num`（现: 日志里没有这个字段）
- `autovt/tasks/vinted.py:614-623` — 调整调用点日志/注释，明确 `_run_vinted_cleanup_flow()` 已包含按周期 Vinted 重装（现: 只写“独立应用清理”）
- `doc/project_structure.md:12-13` — `apks/` 目录补 `vinted.apk`（现: 只写 `facebook.apk`）
- `doc/project_structure.md:74-74` — 设置页说明补 `vt_delete_num`（现: 无该配置）
- `doc/project_structure.md:90-90` — 任务层说明补 `vt_delete_num` 规则（现: 只有 `fb_delete_num`、`setting_fb_del_num`）
- `doc/project_structure.md:218-223` — 默认配置说明补 `t_config.vt_delete_num=0`（现: 无）
- `doc/project_structure.md:254-258` — `t_config` 规则说明补 `vt_delete_num`（现: 无）
- `/Users/admin/go/src/go_cookies/autovt/doc/project_structure.md:12-13` — 同步 `apks/` 目录补 `vinted.apk`
- `/Users/admin/go/src/go_cookies/autovt/doc/project_structure.md:65-65` — 同步设置页说明补 `vt_delete_num`
- `/Users/admin/go/src/go_cookies/autovt/doc/project_structure.md:80-84` — 同步 `user_db/open_settings/vinted` 的行为说明
- `/Users/admin/go/src/go_cookies/autovt/doc/project_structure.md:223-228` — 同步默认配置补 `t_config.vt_delete_num=0`
- `/Users/admin/go/src/go_cookies/autovt/doc/project_structure.md:260-264` — 同步 `t_config` 规则说明补 `vt_delete_num`

**依赖:**
- 无新增第三方依赖

## Todolist

- [x] 1. 补齐 `vt_delete_num` 的公共常量定义

  **Files:**
  - Modify: `autovt/gui/helpers.py:23-34`
  - Modify: `autovt/userdb/user_db.py:39-56`

  ```text
  change details:
  修改: autovt/gui/helpers.py:23-34 (现: 仅定义 vt_pwd、fb_delete_num、setting_fb_del_num 三组配置常量)
  - 新增 VT_DELETE_NUM_KEY = "vt_delete_num"
  - 新增 VT_DELETE_NUM_DESC = "0 不删除，其他数字每隔第几次重装"
  - 保持与现有 fb_delete_num 命名和说明风格一致

  修改: autovt/userdb/user_db.py:39-56 (现: userdb 仅定义 VT_PWD / FB_DELETE_NUM / SETTING_FB_DEL_NUM 的 key、desc、default)
  - 新增 VT_DELETE_NUM_KEY / VT_DELETE_NUM_DESC / VT_DELETE_NUM_DEFAULT
  - 继续复用 FB_DELETE_NUM_MIN / FB_DELETE_NUM_MAX 作为边界常量
  ```
----------------------
- [x] 2. 让数据库默认补齐并校验 `vt_delete_num`

  **Files:**
  - Modify: `autovt/userdb/user_db.py:425-458`
  - Modify: `autovt/userdb/user_db.py:530-577`
  - Modify: `autovt/userdb/user_db.py:1678-1689`

  ```text
  change details:
  修改: autovt/userdb/user_db.py:425-458 (现: connect/init 时只向 t_config 插入 vt_pwd、fb_delete_num、setting_fb_del_num 默认值)
  - 在默认配置补齐流程中插入 vt_delete_num=0
  - 缺失老库启动时自动补齐，不要求手工改库

  修改: autovt/userdb/user_db.py:530-577 (现: _normalize_config_value 只校验 fb_delete_num 与 setting_fb_del_num)
  - 新增 vt_delete_num 的空值/整数/范围校验
  - 错误文案与 fb_delete_num 语义保持一致，只把字段名改为 vt_delete_num

  修改: autovt/userdb/user_db.py:1678-1689 (现: desc 回填逻辑只覆盖 vt_pwd、fb_delete_num、setting_fb_del_num)
  - 为 vt_delete_num 增加固定描述映射
  - 避免旧数据或手工写库后 desc 丢失
  ```
----------------------
- [x] 3. 在全局设置页增加 `vt_delete_num` 输入框

  **Files:**
  - Modify: `autovt/gui/settings_tab.py:13-28`
  - Modify: `autovt/gui/settings_tab.py:49-62`
  - Modify: `autovt/gui/settings_tab.py:97-125`
  - Modify: `autovt/gui/settings_tab.py:177-183`
  - Modify: `autovt/gui/settings_tab.py:367-375`

  ```text
  change details:
  修改: autovt/gui/settings_tab.py:13-28 (现: imports 未导入 vt_delete_num 常量)
  - 导入 VT_DELETE_NUM_KEY / VT_DELETE_NUM_DESC

  修改: autovt/gui/settings_tab.py:49-62 (现: SettingsTab 只持有 vt_pwd、fb_delete_num、setting_fb_del_num 的控件引用)
  - 新增 vt_delete_num_value_input
  - 新增 vt_delete_num_desc_text

  修改: autovt/gui/settings_tab.py:97-125 (现: 这里只创建 fb_delete_num 和 setting_fb_del_num 输入框)
  - 追加 vt_delete_num 数字输入框
  - hint 文案写明“0 不删除，其他数字每隔第几次重装”
  - 绑定与 fb_delete_num 同风格的软校验

  修改: autovt/gui/settings_tab.py:177-183 (现: 双列布局没有 vt_delete_num)
  - 调整设置卡片排布，把 vt_delete_num 放进现有双列区域
  - 保持页面风格一致，不额外引入新布局模式

  修改: autovt/gui/settings_tab.py:367-375 (现: 只有 fb_delete_num / setting_fb_del_num 的输入清洗函数)
  - 新增 _sanitize_vt_delete_num_input()
  - 复用现有 _sanitize_non_negative_int_input()
  ```
----------------------
- [x] 4. 打通设置页的刷新与保存链路

  **Files:**
  - Modify: `autovt/gui/settings_tab.py:478-548`
  - Modify: `autovt/gui/settings_tab.py:590-655`
  - Modify: `autovt/gui/settings_tab.py:668-739`

  ```text
  change details:
  修改: autovt/gui/settings_tab.py:478-548 (现: refresh 只回填 vt_pwd、fb_delete_num、setting_fb_del_num、代理范围)
  - 增加 vt_delete_num 的 value 和 desc 回填
  - 刷新前置空指针校验也补上 vt_delete_num 控件

  修改: autovt/gui/settings_tab.py:590-655 (现: _load_config_snapshot 不读取 vt_delete_num)
  - 从 t_config 读取 vt_delete_num 行
  - 缺失时抛出明确错误
  - latest_update_at 计算补入 vt_delete_num.update_at
  - snapshot 返回 vt_delete_num_val / vt_delete_num_desc

  修改: autovt/gui/settings_tab.py:668-739 (现: save_config 不校验也不保存 vt_delete_num)
  - 增加 vt_delete_num 非空校验
  - 保存时调用 user_db.set_config(key=VT_DELETE_NUM_KEY, ...)
  - 保存失败日志里补充 vt_delete_num 原始输入值
  ```
----------------------
- [x] 5. 让 worker 把 `vt_delete_num` 稳定透传到任务层

  **Files:**
  - Modify: `autovt/multiproc/worker.py:28-42`
  - Modify: `autovt/multiproc/worker.py:192-213`
  - Modify: `autovt/multiproc/worker.py:783-790`
  - Modify: `autovt/multiproc/worker.py:911-914`

  ```text
  change details:
  修改: autovt/multiproc/worker.py:28-42 (现: worker 只导入 VT_PWD / FB_DELETE_NUM / SETTING_FB_DEL_NUM 相关常量)
  - 导入 VT_DELETE_NUM_KEY / VT_DELETE_NUM_DEFAULT 及边界常量

  修改: autovt/multiproc/worker.py:192-213 (现: 只有 _read_fb_delete_num(config_map))
  - 新增 _read_vt_delete_num(config_map)
  - 行为与 _read_fb_delete_num 完全一致，只改 key 和日志语义

  修改: autovt/multiproc/worker.py:783-790 (现: t_config 读失败时 fallback_config 没有 vt_delete_num)
  - fallback_config 补 vt_delete_num=0
  - 保证数据库异常时 Vinted 路径仍能稳定回退

  修改: autovt/multiproc/worker.py:911-914 (现: 任务即将执行日志只打印 fb_delete_num)
  - 日志补 vt_delete_num
  - 便于排查“第几轮触发 Vinted 重装”是否命中
  ```
----------------------
- [x] 6. 在任务基类中补 Vinted 周期重装能力

  **Files:**
  - Modify: `autovt/tasks/open_settings.py:110-145`
  - Modify: `autovt/tasks/open_settings.py:217-260`
  - Modify: `autovt/tasks/open_settings.py:362-419`
  - Modify: `autovt/tasks/open_settings.py:618-659`
  - Modify: `autovt/tasks/open_settings.py:1199-1207`
  - Modify: `autovt/tasks/open_settings.py:3335-3345`
  - Modify: `autovt/tasks/vinted.py:614-623`

  ```text
  change details:
  修改: autovt/tasks/open_settings.py:110-145 (现: __init__ 只缓存 vt_pwd、fb_delete_num、setting_fb_del_num)
  - 新增 self.vt_delete_num = self._read_vt_delete_num()
  - 保持字段读取顺序与 FB 配置一致

  修改: autovt/tasks/open_settings.py:217-260 (现: 只有 _read_fb_delete_num() 和 _read_setting_fb_del_num())
  - 新增 _read_vt_delete_num()
  - 解析规则与 fb_delete_num 保持一致，非法值统一回退 0/边界值

  修改: autovt/tasks/open_settings.py:362-419 (现: 只有 _should_delete_fb_this_loop()、_should_delete_setting_fb_this_loop()、_resolve_facebook_apk_path())
  - 新增 _should_delete_vt_this_loop()
  - 新增 _resolve_vinted_apk_path()
  - vinted.apk 候选路径顺序与 facebook.apk 保持一致，只把文件名替换为 vinted.apk

  修改: autovt/tasks/open_settings.py:618-659 (现: 只有 _safe_install_facebook_apk())
  - 新增 _safe_install_vinted_apk()
  - 继续使用类里的安全安装方法、连接异常抛出策略和安装后校验逻辑

  修改: autovt/tasks/open_settings.py:1199-1207 (现: _run_vinted_cleanup_flow() 只 stop + clear_app + 记录清理完成)
  - 保留 stop_app/clear_app
  - 命中 _should_delete_vt_this_loop() 时执行 _safe_uninstall_app(self.vinted_package) + _safe_install_vinted_apk()
  - 安装失败时抛 RuntimeError，中断本轮 Vinted 流程并写错误日志
  - 未命中时记录“本轮仅清理不重装”的日志

  修改: autovt/tasks/open_settings.py:3335-3345 (现: 任务开始日志没有 vt_delete_num)
  - 日志补 vt_delete_num，便于统一看任务上下文

  修改: autovt/tasks/vinted.py:614-623 (现: run_once 只写“Vinted 独立应用清理”)
  - 调整启动日志/注释，明确 _run_vinted_cleanup_flow() 已包含“按周期 Vinted 重装”
  - 保持真正安装逻辑仍集中在基类，避免子类重复写安全代码
  ```
----------------------
- [x] 7. 同步项目结构文档

  **Files:**
  - Modify: `doc/project_structure.md:12-13`
  - Modify: `doc/project_structure.md:74-74`
  - Modify: `doc/project_structure.md:90-90`
  - Modify: `doc/project_structure.md:218-223`
  - Modify: `doc/project_structure.md:254-258`
  - Modify: `/Users/admin/go/src/go_cookies/autovt/doc/project_structure.md:12-13`
  - Modify: `/Users/admin/go/src/go_cookies/autovt/doc/project_structure.md:65-65`
  - Modify: `/Users/admin/go/src/go_cookies/autovt/doc/project_structure.md:80-84`
  - Modify: `/Users/admin/go/src/go_cookies/autovt/doc/project_structure.md:223-228`
  - Modify: `/Users/admin/go/src/go_cookies/autovt/doc/project_structure.md:260-264`

  ```text
  change details:
  修改: doc/project_structure.md:12-13 (现: apks 目录只列出 facebook.apk)
  - 补充 vinted.apk

  修改: doc/project_structure.md:74-74 (现: settings_tab 说明没有 vt_delete_num)
  - 补充设置页支持编辑 vt_delete_num

  修改: doc/project_structure.md:90-90 (现: open_settings 行为说明只有 fb_delete_num / setting_fb_del_num)
  - 补充 vt_delete_num 在 vinted 模式按 worker_loop_seq 周期重装 vinted.apk

  修改: doc/project_structure.md:218-223 (现: 默认配置说明没有 vt_delete_num)
  - 补充 t_config.vt_delete_num=0

  修改: doc/project_structure.md:254-258 (现: t_config 规则只描述 fb_delete_num)
  - 补充 vt_delete_num 的取值范围和命中条件

  修改: /Users/admin/go/src/go_cookies/autovt/doc/project_structure.md:12-13, 65-65, 80-84, 223-228, 260-264
  - 对外部同步文档做同样更新
  - 保持两份文档描述一致，避免后续维护分叉
  ```

## 总结

共 7 条任务，涉及 8 个文件（项目内 7 个，外部同步文档 1 个；均为修改，无新建），预计改动约 160 行。

1. 配置层新增 `vt_delete_num`，让老库自动补默认值并统一做输入校验。
2. GUI 设置页新增 `vt_delete_num` 输入、刷新和保存链路，避免只能手工改库。
3. worker 侧补默认回退和日志，让运行时诊断能看到 Vinted 重装周期。
4. `OpenSettingsTask` 新增 Vinted APK 路径解析、安全安装和周期判断，继续复用现有稳定性设计。
5. Vinted 清理流升级为“默认 clear_app，命中周期再 uninstall + install(apks/vinted.apk)”。
6. `vinted.py` 保持现有调用链，只补承接日志，不把安装逻辑散到子类里。
7. 两份项目结构文档同步补 `vinted.apk`、`vt_delete_num` 默认值和运行规则。

## 变更记录
- 2026-03-22 11:58:05 初始创建
- 2026-03-22 12:07:59 完成 #1 补齐 `vt_delete_num` 的公共常量定义
- 2026-03-22 12:08:32 完成 #2 让数据库默认补齐并校验 `vt_delete_num`
- 2026-03-22 12:09:16 完成 #3 在全局设置页增加 `vt_delete_num` 输入框
- 2026-03-22 12:10:55 完成 #4 打通设置页的刷新与保存链路
- 2026-03-22 12:11:21 完成 #5 让 worker 把 `vt_delete_num` 稳定透传到任务层
- 2026-03-22 12:12:16 完成 #6 在任务基类中补 Vinted 周期重装能力
- 2026-03-22 12:13:47 完成 #7 同步项目结构文档
