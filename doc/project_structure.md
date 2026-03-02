# 项目目录说明（多进程版）
uv run python -m compileall autovt/gui/app.py autovt/userdb/user_db.py 语法检查
当前项目只保留一套多进程架构，不再兼容旧的单进程入口。

## 目录结构

```text
autovt/
├── .github/
│   └── workflows/
│       └── flet-macos-tag.yml
├── autovt/
│   ├── __init__.py
│   ├── adb.py
│   ├── auth/
│   │   ├── __init__.py
│   │   └── login_service.py
│   ├── cli.py
│   ├── gui/
│   │   ├── __init__.py
│   │   └── app.py
│   ├── logs.py
│   ├── runtime.py
│   ├── settings.py
│   ├── userdb/
│   │   ├── __init__.py
│   │   └── user_db.py
│   ├── multiproc/
│   │   ├── __init__.py
│   │   ├── manager.py
│   │   └── worker.py
│   └── tasks/
│       ├── __init__.py
│       ├── task_context.py
│       └── open_settings.py
├── images/
│   └── fr/
│       └── 抹机王/
│           ├── tpl1770223525363.png
│           └── tpl1770225509350.png
├── log/
├── doc/
│   ├── project_structure.md
│   └── flet_packaging.md
├── main.py
└── README.md
```

## 模块职责

- `main.py`：主入口（默认 GUI），支持 `--mode cli` 回退命令行模式。
- `autovt/gui/app.py`：Flet GUI 主控层（登录页 + 三 Tab（设备列表/账号列表/全局设置）+ 设备操作按钮 + 账号 CRUD 分页 + 自动刷新监控）。
- `autovt/auth/login_service.py`：登录服务模块；对齐 Go 版登录协议（AES-GCM + `/bit_login`），并提供本地账号密码缓存（下次启动自动回填）。
- `autovt/gui/__init__.py`：GUI 包导出入口（`run_gui`）。
- `autovt/cli.py`：命令行交互层（用于 `--mode cli` 回退场景）。
- `autovt/logs.py`：统一日志初始化（终端+文件 JSON、日志级别、第三方 debug 开关）。
- `autovt/multiproc/manager.py`：主进程生命周期管理。
- `autovt/multiproc/worker.py`：单设备子进程执行循环。
- `autovt/runtime.py`：子进程内 Airtest/Poco 初始化，并维护“进程内 Poco 单例”（`create_poco()` / `get_poco()`）；`setup_device()` 会把解析出的 `adb_path` 注入设备 URI，避免被外部常驻 adb 进程劫持，并记录 `auto_setup/create_poco` 耗时日志。
- `autovt/adb.py`：ADB 设备发现和设备 URI 组装（默认优先项目内置 `adb/mac` 与 `adb/windows`，并支持 `AUTOVT_ADB_BIN` 覆盖，兼容打包后 PATH 缺失场景）；`build_device_uri()` 支持传入 `adb_path` 强制 Airtest 走指定 adb；`list_online_serials()` 已增加 `adb devices` 超时与 `kill-server/start-server` 自愈，避免 adb 冲突导致 GUI 卡住。
- `autovt/emails/emails.py`：邮箱验证码主入口，提供 `getfackbook_code(client_id, email_name, refresh_token, is_debug=False)`，负责刷新 token、拉取邮件、提取验证码。
- `autovt/emails/fackbook_code.py`：Facebook 验证码解析规则模块，支持从邮件列表或调试 HTML（`autovt/emails/test.html`）提取“最新验证码”。
- `autovt/userdb/user_db.py`：跨平台本地用户库封装（默认 `user.db`，自动建 `t_user` + `t_config`，并提供账号分页查询、CRUD、状态更新、配置读写）。
- `autovt/tasks/task_context.py`：任务上下文对象（`TaskContext`，统一承载设备 serial/locale/lang，并通过 `extras` 扩展自定义字段）。
- `autovt/tasks/open_settings.py`：单轮业务动作（`OpenSettingsTask` 类 + `run_once(task_context)` 严格必传上下文）；`_safe_wait_exists/_safe_click/_safe_input_on_focused` 增加统一异常兜底，捕捉 Poco/ADB 断连（如 `TransportDisconnected`、`device not found`）并尝试自动重建 `Poco`，避免流程直接崩溃。
- `autovt/settings.py`：项目配置（日志、图片、adb、循环间隔、容错参数）。
- `test.py`：单方法快速调试入口（可直接调 `OpenSettingsTask` 指定方法）；退出清理时对 `poco.stop_running()` 增加超时保护，避免 `Ctrl+C` 后 cleanup 阶段再次卡住。
- `.github/workflows/flet-macos-tag.yml`：GitHub Actions 打包流水线（推送 tag 后自动执行 `macOS + Windows` 的 `flet pack(PyInstaller)` 并上传 Release 产物）。

其中 ADB 相关关键项：
- `ADB_SERVER_ADDR`：ADB Server 地址（如 `127.0.0.1:5037`）。
- `CAP_METHOD`：截图方式（推荐 `JAVACAP`，可减少 `minicap` 初始化报错）。
- `TOUCH_METHOD`：触控方式（如 `MAXTOUCH` / `ADBTOUCH`）。

## 日志说明

- JSON 日志目录（运行期）：
- macOS：`~/Library/Application Support/AutoVT/log/json/`
- Windows：`%APPDATA%\\AutoVT\\log\\json\\`（无 APPDATA 时回退 LOCALAPPDATA）
- Linux：`$XDG_STATE_HOME/autovt/log/json/`（无 XDG_STATE_HOME 时回退 `~/.local/state/autovt/log/json/`）
- 终端输出：JSON（stderr）
- 开关生效位置：`autovt/logs.py` 的 `_configure_third_party_debug()`
- 关键开关（`autovt/settings.py`）：
- `LOG_LEVEL`：主日志级别
- `ENABLE_AIRTEST_DEBUG`：是否放开 Airtest/Poco DEBUG 噪音

也可用环境变量临时覆盖：

- `AUTOVT_LOG_LEVEL=DEBUG`
- `AUTOVT_AIRTEST_DEBUG=1`（仅源码运行生效；打包运行 `.app/.exe` 永久关闭，环境变量无效）
- `AUTOVT_AIRTEST_SAVE_IMAGE=1`（临时开启 Airtest 截图落盘，默认关闭）
- `AUTOVT_POCO_SCREENSHOT_EACH_ACTION=1`（临时开启 Poco 每步截图，默认关闭）

## 启动流程（当前代码）

### 1) 主入口阶段（`main.py`）

1. 解析启动参数（默认走 GUI，`--mode cli` 走命令行）。
2. 初始化 manager 侧日志（`setup_logging(process_role="manager")`）。
3. 根据模式进入：
   - GUI：`autovt/gui/app.py:run_gui()`
   - CLI：`autovt/cli.py:run_console()`

### 2) GUI 启动阶段（`autovt/gui/app.py`）

1. 创建 `DeviceProcessManager`（进程管理器）：
   - 内部会创建 `UserDB` 并 `connect()`，用于状态展示和停机释放账号。
2. 创建 GUI 自己的 `UserDB` 并 `connect()`：
   - 供账号列表/设置页 CRUD 使用。
3. 登录成功后构建 3 个 Tab：
   - 设备列表、账号列表、全局设置。
4. 启动设备监控循环（定时刷新设备状态和日志）。
5. 用户点击“启动设备/启动全部”后，`manager.start_worker()` 拉起子进程。

### 3) CLI 启动阶段（`autovt/cli.py`）

1. 创建 `DeviceProcessManager`。
2. 进入 REPL 循环读取命令（`start/stop/status/pause/resume`）。
3. 命令最终都转到 manager 执行。

### 4) 子进程 worker 启动阶段（`autovt/multiproc/worker.py`）

1. 子进程初始化独立日志。
2. 子进程创建独立 `UserDB` 并 `connect()`（用于抢占账号和读配置）。
3. 运行时初始化：
   - `setup_device()` 建立设备连接。
   - `create_poco()` 创建 Poco。
   - 读取设备 locale，构建 `TaskContext`。
4. 进入主循环：
   - 先处理命令（`stop/pause/resume/run_once`）。
   - 自动模式下每轮先领取账号，再执行 `tasks/open_settings.py:run_once()`。

## 停止流程（当前代码）

### 1) 单设备停止（`manager.stop_worker`）

1. 主进程发送 `stop` 命令 + 设置 `stop_event`。
2. 等待优雅退出（grace timeout）。
3. 超时则 `terminate`，仍超时再 `kill`（强制兜底）。
4. 回收进程句柄和队列句柄。
5. 调用 `release_user_for_device(serial)` 释放账号占用：
   - `status=1 -> 0`
   - `status=2/3` 保持不变
   - `device` 清空

### 2) 全部停止（`manager.stop_all`）

1. 并发给所有 worker 发 stop。
2. 统一等待优雅退出。
3. 对仍存活进程并发 `terminate`，必要时再 `kill`。
4. 逐个 worker 释放账号占用并回收句柄。

### 3) 进程退出兜底（worker finally）

1. worker 在 `finally` 里再次执行 `release_user_for_device(serial)`，避免异常退出造成账号残留绑定。
2. 关闭子进程自己的 `UserDB` 连接。
3. 上报 `stopped` 事件。

### 4) 应用退出（GUI/CLI）

1. GUI 退出时执行 `_shutdown()`：
   - `manager.stop_all()`
   - `manager.close()`
   - `user_db.close()`
2. CLI 退出时在 `finally`：
   - `manager.stop_all()`
   - `manager.close()`

## SQLite DB 都做了什么（`autovt/userdb/user_db.py`）

### 1) 数据库位置与连接

1. 跨平台解析用户配置目录（Windows/macOS/Linux）。
2. 默认数据库文件：`user.db`（应用目录 `vinted_android` 下）。
3. 每次 `connect()` 会设置 PRAGMA：
   - `busy_timeout=5000`
   - `journal_mode=WAL`
   - `synchronous=NORMAL`
   - `foreign_keys=ON`

### 2) 建表与迁移

1. 自动建 `t_user` 和 `t_config`。
2. 兼容旧库自动补字段：
   - `fb_status`
   - `client_id`
   - `device`
3. 自动补默认配置：
   - `t_config.mojiwang_run_num=3`（缺失才写入）。
   - `t_config.status_23_retry_max_num=0`（缺失才写入，表示默认不重试）。

### 3) 索引

1. `t_user.status`
2. `t_user.fb_status`
3. `t_user.device`
4. `t_user.update_at`
5. `t_config.update_at`

### 4) 账号分配与并发锁

1. `claim_user_for_device(device)` 使用 `BEGIN IMMEDIATE` 事务抢占账号。
2. 抢占规则：
   - 从 `status=0` 且 `device` 为空的账号池中按 `id ASC` 领取一条。
   - 更新为 `status=1` + `device=<serial>`。
3. 释放规则（`release_user_for_device`）：
   - `status=1 -> 0`；
   - `status=2/3` 不改状态；
   - 统一清空 `device`。

### 5) 业务读写能力

1. `t_user`：
   - 新增、修改、删除、按条件分页查询、按设备反查账号。
   - 新增/编辑校验必填：`email_account/email_pwd/client_id/email_access_key/first_name/last_name/pwd/status`。
2. `t_config`：
   - 读取单项、读取 map、更新配置。
   - `mojiwang_run_num` 限制为 `1~100`。
   - `status_23_retry_max_num` 限制为 `0~5`。

## 扩展建议

后续新增业务时，优先在 `autovt/tasks/` 新建任务文件，保持 `worker` 不改或少改。  
如果要切换语言图片目录，只改 `autovt/settings.py` 中 `LOCALE` 和 `FEATURE_NAME`。
Flet 打包与图标/名称替换说明见 `doc/flet_packaging.md`。

## GUI 功能映射（当前版）

- 登录：默认 `admin / 123456`
- 顶部 Tab：`设备列表`、`账号列表`、`全局设置`（默认设备列表）
- 设备 Tab 全局按钮：`刷新设备`、`启动全部`、`停止全部`、`暂停全部`、`恢复全部`
- 设备 Tab 单设备按钮：`启动`、`停止`、`暂停`、`恢复`、`重启`
- 设备 Tab 列表状态：每台设备展示 `online`、`pid`、`alive`、`state`、`detail`
- 设备 Tab 日志框：只展示 `component=task.open_settings` 的日志（即 `get_logger("task.open_settings")` 输出，来自 `log/json/*.jsonl`），最新 100 条，黑底白字并自动滚动到最新，过滤 traceback 纯文本行
- 设备 Tab 日志框：支持鼠标拖选复制，并提供“清空日志/复制日志”按钮（清空仅删除 `task.open_settings` 日志）
- 设备检测：默认加载 `adb devices`，并以固定间隔自动轮询 USB 插拔变化
- 账号 Tab：读取 `t_user` 并展示账号列表卡片（`id DESC`，每页 `20` 条）
- 账号 Tab：支持 `新增/编辑/删除/刷新` 与上一页/下一页分页切换
- 账号 Tab：支持筛选（`status/fb_status/vinted_status/titok_status`）与 `email_account` 关键字搜索
- 账号 Tab：新增/编辑必填字段：`email_account`（唯一）、`email_pwd`、`client_id`、`email_access_key`、`first_name`、`last_name`、`pwd`、`status`
- 账号 Tab：列表展示 `device`（设备 ID）字段，仅展示，不在新增/编辑弹窗中填写
- 账号 Tab：新增/编辑弹窗支持 `一键识别并填充`
- 一键识别格式（固定 4 段）：`email----email_pwd----client_id----email_access_key`（第三段自动填充 `client_id`）
- 一键识别授权码清洗：自动去除密钥中的换行和空白，兼容长密钥粘贴换行场景
- 账号 Tab：`email_access_key` 列表展示时只显示前 10 位，其余 `...`
- 账号 Tab 状态文案：
- `fb_status/vinted_status/titok_status`：`0=未注册`、`1=成功`、`2=失败`
- `status`：`0=未使用`、`1=正在使用`、`2=已经使用`、`3=账号问题`
- 设置 Tab：读取 `t_config` 并支持编辑 `mojiwang_run_num`、`status_23_retry_max_num`
- `mojiwang_run_num` 规则：仅允许 `1~100` 整数
- `status_23_retry_max_num` 规则：仅允许 `0~5` 整数（`0`=不重试，`1`=重试 1 次，`3`=重试 3 次，最大 `5` 次）
- 设置 Tab 的 `status_23_retry_max_num` 输入框在 Flet UI 层已加输入限制：仅允许输入 `0~5` 单个数字
- 登录页：默认走加密 API 登录；当环境变量 `GITXUZAN_LOGIN=1` 时跳过 API 登录校验（任意账号密码可登录）
- 登录页：登录成功后会写入本地缓存，重新打开软件自动回填上次账号密码
- 登录页：`401 Unauthorized` 按“账号或密码错误”处理，只打印告警日志，不输出异常堆栈
- `t_config` 默认值：`mojiwang_run_num=3`、`status_23_retry_max_num=0`（缺失时自动补齐）
- GUI 已去掉：`once/run_once` 单轮手动触发入口

## 多设备账号分配规则（当前版）

- 每个 worker 子进程在执行任务前，会从 `t_user` 原子领取一条 `status=0` 账号，并设置为：`status=1`、`device=<serial>`
- 账号领取使用 SQLite 事务写锁（`BEGIN IMMEDIATE`）保证并发安全，避免多设备抢到同一账号
- 同一时刻每条 `t_user` 只会被一个设备占用（通过 `status+device` 双条件控制）
- 当当前账号仍为 `status=1` 时，worker 会持续复用同一账号执行，不会切换新账号
- 当当前账号变为 `status=2/3` 时，worker 会按 `status_23_retry_max_num` 对同一账号执行对应次数的“额外重试”（例如配置 `3` 就额外重试 `3` 次）；超过上限后才释放并切换新账号
- 若无可用账号（无 `status=0`），worker 进入 `waiting` 状态并睡眠等待，不执行自动化任务
- 当后续有新可用账号写入后，worker 会自动继续领取并执行任务
- 停止设备时释放规则：
- 若账号当前 `status=1`，停止后回收为 `status=0`，并清空 `device`
- 若账号当前 `status=2/3`，停止后保持状态不变，仅清空 `device`
- 设备列表 UI 支持展示当前设备占用邮箱（从 `t_user.device` 反查）

## test.py 快速调试

- 默认执行完整单轮（运行一次后自动停止）：`python test.py`
- 指定执行完整单轮：`python test.py run_once`
- 只跑清理：`python test.py clear_all`
- 只调抹机王：`python test.py mojiwang_run_all`
- 只调 Facebook：`python test.py facebook_run_all`
- 只调 Nekobox：`python test.py nekobox_run_all 0`（`0=动态`，`1=移动`）
- 只跑抹机王某一轮：`python test.py mojiwang_run_one_loop 0`
- Facebook 头像随机选图：`OpenSettingsTask.facebook_select_img()` 在头像相册里固定跳过索引 `0`（非图片），并按 `1..min(9, x)` 随机点击（`x=图片数量`）
- Facebook 头像随机选图分支：若命中“添加图片”弹框，会直接进入相册授权步骤；未命中时才走 `首页头像按钮v2` + `打开底部相册` 的常规路径

## test.py 全局异常兜底

- `test.py` 使用 `run_with_global_guard()` 统一捕获未处理异常，避免脚本直接崩溃。
- 正常结束返回码为 `0`，异常返回码为 `1`，手动中断（Ctrl+C）返回码为 `130`。
- 无论成功或失败都会执行 `cleanup_poco()`，确保 PocoService 和资源得到清理。
- 默认仅输出简要异常；若需完整堆栈，可临时加 `AUTOVT_SHOW_TRACEBACK=1`。

## Poco 实例说明（多进程隔离）

- 每个 `worker` 子进程都会独立执行 `setup_device()` 和 `create_poco()`。
- 每个 `worker` 子进程初始化成功后会读取一次设备语言（如 `en-US`），并更新该设备的 `TaskContext`。
- `TaskContext` 的 `serial/device_locale/device_lang` 为必填字段；缺失或 `unknown` 时会记录 `fatal` 并停止该子进程。
- `create_poco()` 创建的实例只保存在该进程内存，不会跨进程共享。
- 任务层（如 `autovt/tasks/open_settings.py`）通过 `get_poco()` 获取“当前进程”的实例，并接收 `worker` 透传的 `TaskContext`（必须有效）。
- 如果 `get_poco()` 报错“Poco 尚未初始化”，说明任务执行早于初始化流程，需要先检查 `worker` 启动日志。
- 如果运行期出现“Poco 未初始化/为空/不存在”，`worker` 会记录 `fatal` 日志并停止该子进程，避免继续空转。
- `nekobox_run_all()` 使用 `try/finally` 实现 defer 风格收尾，确保任何中断路径都会执行统一收尾逻辑。
