# autovt

git tag -a v0.0.9 -m "修改" &&  git push origin v0.0.9

https://www.fakenamegenerator.com/gen-random-us-fr.php
名字生成器
Airtest 安卓自动化多设备项目（多进程主控版）。

## 启动

先激活虚拟环境，再运行主控（默认 GUI）：

```bash
uv run python main.py
```

## GUI 主控（默认）

启动后先进入登录页，默认账号密码：

- 账号：`admin`
- 密码：`123456`

登录后主控页支持：

- 顶部 3 个 Tab：`设备列表` / `账号列表` / `全局设置`
- 默认打开 `设备列表` Tab，并展示 `adb devices` 在线设备
- `设备列表`：`刷新设备`、`启动全部`、`停止全部`、`暂停全部`、`恢复全部`
- `设备列表`：每台设备独立操作 `启动` / `停止` / `暂停` / `恢复` / `重启`
- `设备列表`：状态列表展示 `online`、`pid`、`alive`、`state`、`detail`
- `设备列表`：底部日志框只展示 `self.log = get_logger("task.open_settings")` 输出日志（`component=task.open_settings`），最新 100 条，黑底白字并自动滚动到最新
- `设备列表`：日志支持鼠标拖选复制，并提供“清空日志/复制日志”按钮（清空仅删除 `task.open_settings` 日志）
- 自动监控 USB 拔插：设备变化时自动刷新并提示
- `账号列表`：读取 `t_user` 并展示账号卡片列表（`ID 倒序`、`20 条/页` 分页）
- `账号列表`：支持账号 `新增/编辑/删除/刷新`，新增和编辑都做必填校验
- `账号列表`：支持筛选（`status/fb_status/vinted_status/titok_status`）和邮箱关键字搜索
- `账号列表`：支持一键识别填充（固定 4 段：`email----email_pwd----client_id----email_access_key`）
- `账号列表`：`email_access_key` 在列表中只展示前 10 位，其余显示 `...`
- `账号列表`：`device` 字段仅在列表展示，不在新增/编辑弹窗中填写
- `设备列表`：支持展示每台设备当前占用的邮箱（按 `t_user.device=<serial>` 反查）
- `账号列表`：状态文案
- `fb_status/vinted_status/titok_status`：`0=未注册`、`1=成功`、`2=失败`
- `status`：`0=未使用`、`1=正在使用`、`2=已经使用`、`3=账号问题`
- `全局设置`：已接入 `t_config`，可编辑 `mojiwang_run_num`、`status_23_retry_max_num`

说明：GUI 中已去掉 `once/run_once` 手动单轮执行入口。

## CLI 回退模式（可选）

如果你临时还要使用命令行模式，可用：

```bash
uv run python main.py --mode cli
```

CLI 可用命令定义在 `autovt/cli.py`。

## 文档

目录结构和维护说明见 `doc/project_structure.md`。
Flet 打包与图标/名称替换说明见 `doc/flet_packaging.md`。

## mac 本地测试打包（推荐）

先在项目根目录执行（`/Users/admin/go/src/autovt`）：

```bash
# 1) 安装依赖
uv sync

# 2) 解析 poco Android 资源目录（确保 pocoservice-debug.apk 被打进包）
POCO_ANDROID_LIB_DIR="$(uv run python -c 'from pathlib import Path; import poco; print((Path(poco.__file__).resolve().parent / "drivers" / "android" / "lib").as_posix())')"

# 3) 执行打包（mac 仅打 adb/mac）
uv run \
  --python 3.13 \
  --with "flet==0.80.5" \
  --with "flet-cli==0.80.5" \
  --with "flet-desktop==0.80.5" \
  --with pyinstaller \
  python -m flet_cli.cli pack main.py \
  -n "AutoVT" \
  --product-name "AutoVT" \
  -i assets/icon.icns \
  --add-data "assets:assets" \
  --add-data "images:images" \
  --add-data "adb/mac:adb/mac" \
  --add-data "${POCO_ANDROID_LIB_DIR}:poco/drivers/android/lib" \
  --yes -v
```

打包产物：

- `dist/AutoVT.app`

## 日志（loguru）

项目已使用 `loguru`，同时输出到终端和文件，格式为 JSON。

- 终端：JSON 输出到 stderr
- 文件：`log/json/*.jsonl`
- 每条日志都包含：时间、级别、消息、`file/line/function`、进程上下文
- 主进程日志：`log/json/manager.jsonl`
- 子进程日志：`log/json/<设备serial>.jsonl`

### 控制日志级别

- 默认级别：`INFO`（见 `autovt/settings.py` 的 `LOG_LEVEL`）
- 临时切换：

```bash
AUTOVT_LOG_LEVEL=DEBUG uv run python main.py
```

### 控制 Airtest/Poco DEBUG 噪音

- 默认关闭 Airtest/Poco DEBUG（见 `autovt/settings.py` 的 `ENABLE_AIRTEST_DEBUG=False`）
- 开关逻辑在：`autovt/logs.py` 的 `apply_third_party_log_policy()`
- 临时打开：

```bash
AUTOVT_AIRTEST_DEBUG=1 uv run python main.py
```

## 容错与恢复

worker 已按错误类型做单独处理，默认不会因为单次异常直接崩溃：

- `TargetNotFoundError`：按业务告警处理，继续下一轮
- `StopIteration` / 连接中断 / ADB 设备错误：自动重初始化设备并重试
- 连续未知错误：达到阈值后自动做一次完整重初始化
- `Ctrl+C`：子进程优雅退出，避免长 traceback 污染终端

关键配置在 `autovt/settings.py`：

- `WORKER_INIT_RETRY_DELAY_SEC`
- `WORKER_RECOVER_RETRY_DELAY_SEC`
- `WORKER_MAX_CONSECUTIVE_UNKNOWN_ERRORS`
- `WORKER_MAX_INIT_RETRIES`（`0` 表示无限重试）

## 用户库（`user.db`）

项目新增了跨平台本地数据库封装：`autovt/userdb/user_db.py`。

- 默认路径（严格对齐 Go 的 `os.UserConfigDir` 规则）：
- macOS：`~/Library/Application Support/vinted_android/user.db`
- Windows：`%APPDATA%\\vinted_android\\user.db`
- Linux/Unix：优先 `XDG_CONFIG_HOME/vinted_android/user.db`（且 `XDG_CONFIG_HOME` 必须是绝对路径），否则 `~/.config/vinted_android/user.db`
- 关键环境变量缺失时会抛错（例如 Windows 无 `%APPDATA%`，或 Unix 无 `XDG_CONFIG_HOME/HOME`）。
- 首次连接会自动创建 `t_user` 表。
- `t_user` 字段补充：`fb_status`（`0=未注册`，`1=成功`，`2=失败`）、`client_id`（新增/编辑必填）、`device`（仅列表展示）。
- `t_user` 账号页默认按 `id DESC` 分页读取（每页 `20` 条）。
- 账号新增/修改必填字段：`email_account`（唯一）、`email_pwd`、`client_id`、`email_access_key`、`first_name`、`last_name`、`pwd`、`status`。
- 多设备并发分配：worker 在任务前原子领取一条 `status=0` 账号，并更新为 `status=1 + device=<serial>`。
- 并发安全：领取使用 SQLite 事务写锁（`BEGIN IMMEDIATE`），同一账号不会被多个设备同时领取。
- 账号复用策略：当当前账号仍为 `status=1` 时持续复用同一账号，不会切换新账号。
- 账号重试策略：当当前账号变为 `status=2/3` 时，按 `status_23_retry_max_num` 对同一账号继续重试；达到上限后才释放并切换新账号。
- 无可用账号时：worker 进入等待态（`waiting`），睡眠轮询，直到有新 `status=0` 账号可用再自动继续。
- 停机释放规则：`status=1` 回退为 `0` 并清空 `device`；`status=2/3` 保持不变，仅清空 `device`。
- 首次连接会自动创建 `t_config(key,val,desc,update_at)`，并写入默认项：
- `key=mojiwang_run_num`
- `val=3`（可改为 `1~100`）
- `desc=抹机玩抹机次数: 1 到 100 填写值`
- `key=status_23_retry_max_num`
- `val=0`（可改为 `0~5`，`0` 表示不重试）
- `desc=账号 status=2/3 时同账号最大重试次数: 0 到 5 填写值`

示例：

```python
from autovt.userdb import UserDB
from autovt.userdb import UserRecord

db = UserDB()  # 默认自动解析 user.db 路径并连接。
db.connect()  # 建立连接并自动建表。

db.upsert_user(
    UserRecord(
        email_account="demo@example.com",
        email_pwd="mail_pwd",
        email_access_key="mail_access_key",
        client_id="9e5f94bc-e8a4-4e73-b8be-63364c29d753",
        first_name="Tom",
        last_name="Lee",
        pwd="vt_pwd",
    )
)
row = db.get_user_by_email("demo@example.com")
print(row)
```

### 运行 UserDB 单元测试

```bash
uv run python -m unittest -v tests/test_user_db.py
```
