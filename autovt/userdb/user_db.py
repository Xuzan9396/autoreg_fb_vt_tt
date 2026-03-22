# 启用延迟注解，避免类型注解在运行时的前向引用问题。
from __future__ import annotations

# 导入 os 模块，用于读取系统环境变量和系统类型。
import os
# 导入 sqlite3 模块，用于操作本地 SQLite 数据库文件。
import sqlite3
# 导入 sys 模块，用于识别当前运行平台（darwin/windows/linux 等）。
import sys
# 导入 time 模块，用于生成秒级时间戳。
import time
# 导入 dataclass/replace，方便定义并复制用户记录结构。
from dataclasses import dataclass, replace
# 导入 Path，用于跨平台路径拼接和目录创建。
from pathlib import Path
# 导入 Any 类型，便于声明通用字典值类型。
from typing import Any

# 定义默认应用配置目录名称，保持与你的 Go 逻辑一致。
DEFAULT_APP_DIR_NAME = "vinted_android"
# 定义默认数据库文件名为 user.db。
DEFAULT_DB_FILENAME = "user.db"
# 定义用户表名常量，统一后续 SQL 语句的表名引用。
TABLE_NAME = "t_user"
# 定义全局配置表名常量，统一后续 SQL 语句引用。
CONFIG_TABLE_NAME = "t_config"
# 定义抹机王配置 key 常量。
MOJIWANG_RUN_NUM_KEY = "mojiwang_run_num"
# 定义抹机王配置描述文案常量。
MOJIWANG_RUN_NUM_DESC = "抹机玩抹机次数: 1 到 100 填写值"
# 定义抹机王默认轮次为 3（若配置不存在则自动写入）。
MOJIWANG_RUN_NUM_DEFAULT = "3"
# 定义账号 status=2/3 场景的最大重试次数配置 key 常量。
STATUS_23_RETRY_MAX_KEY = "status_23_retry_max_num"
# 定义状态重试次数配置描述文案常量。
STATUS_23_RETRY_MAX_DESC = "账号 status=2/3 时同账号重试次数: 0=不重试，1=重试一次（范围 0 到 5）"
# 定义状态重试默认次数为 0（表示不重试）。
STATUS_23_RETRY_MAX_DEFAULT = "0"
# 定义全局 vinted 密码配置 key 常量。
VT_PWD_KEY = "vt_pwd"
# 定义全局 vinted 密码配置描述文案常量。
VT_PWD_DESC = "Vinted 全局密码配置（为空时表示不启用全局密码）"
# 定义全局 vinted 密码默认值为空字符串（表示不启用全局密码）。
VT_PWD_DEFAULT = ""
# 定义 Vinted 删除控制配置 key 常量。
VT_DELETE_NUM_KEY = "vt_delete_num"
# 定义 Vinted 删除控制配置描述文案常量。
VT_DELETE_NUM_DESC = "0 不删除，1 每次都重装，2 从第2次开始每次都重装，3 从第3次开始每次都重装"
# 定义 Vinted 删除控制默认值为 0（仅清理，不重装）。
VT_DELETE_NUM_DEFAULT = "0"
# 定义 Facebook 删除控制配置 key 常量。
FB_DELETE_NUM_KEY = "fb_delete_num"
# 定义 Facebook 删除控制配置描述文案常量。
FB_DELETE_NUM_DESC = "0 不删除，1 每次都重装，2 从第2次开始每次都重装，3 从第3次开始每次都重装"
# 定义 Facebook 删除控制默认值为 0（仅清理，不重装）。
FB_DELETE_NUM_DEFAULT = "0"
# 定义设置页 Facebook 账号清理控制配置 key 常量。
SETTING_FB_DEL_NUM_KEY = "setting_fb_del_num"
# 定义设置页 Facebook 账号清理控制配置描述文案常量。
SETTING_FB_DEL_NUM_DESC = "0 不清理，其他数字每隔第几次执行设置页 Facebook 账号清理"
# 定义设置页 Facebook 账号清理控制默认值为 0（不执行设置页清理）。
SETTING_FB_DEL_NUM_DEFAULT = "0"
# 定义代理开始位置配置 key 常量。
PROXYIP_START_NUM_KEY = "proxyip_start_num"
# 定义代理开始位置配置描述文案常量。
PROXYIP_START_NUM_DESC = "代理开始位置：范围 1 到 5，填写 1 表示索引 0"
# 定义代理开始位置默认值为 1（表示索引 0）。
PROXYIP_START_NUM_DEFAULT = "1"
# 定义代理结束位置配置 key 常量。
PROXYIP_END_NUM_KEY = "proxyip_end_num"
# 定义代理结束位置配置描述文案常量。
PROXYIP_END_NUM_DESC = "代理结束位置：范围 1 到 5，且必须大于等于代理开始位置"
# 定义代理结束位置默认值为 1（表示索引 0）。
PROXYIP_END_NUM_DEFAULT = "1"
# 定义状态重试次数最小值（0=不重试）。
STATUS_23_RETRY_MIN = 0
# 定义状态重试次数最大值（5=最多重试 5 次）。
STATUS_23_RETRY_MAX = 5
# 定义代理点击范围最小值（1 表示索引 0）。
PROXYIP_NUM_MIN = 1
# 定义代理点击范围最大值（5 表示最多第 6 个位置）。
PROXYIP_NUM_MAX = 6
# 定义 Facebook 删除控制最小值（0=不删除）。
FB_DELETE_NUM_MIN = 0
# 定义 Facebook 删除控制最大值（防止异常大值）。
FB_DELETE_NUM_MAX = 10000
# 定义注册状态最小值（0=未注册）。
REGISTER_STATUS_MIN = 0
# 定义注册状态最大值（2=失败）。
REGISTER_STATUS_MAX = 2
# 定义 Facebook 失败累计次数最小值（0=从未失败）。
FB_FAIL_NUM_MIN = 0
# 定义 Facebook 失败累计次数最大值（使用 32 位有符号整型上限做保护）。
FB_FAIL_NUM_MAX = 2147483647
# 定义账号状态最小值（0=未使用）。
ACCOUNT_STATUS_MIN = 0
# 定义账号状态最大值（4=风控限制）。
ACCOUNT_STATUS_MAX = 4
# 定义 SQLite 连接超时时间（秒），用于多进程并发写时的锁等待。
SQLITE_CONNECT_TIMEOUT_SEC = 30.0
# 定义 SQLite busy_timeout（毫秒），用于降低 database is locked 报错概率。
SQLITE_BUSY_TIMEOUT_MS = 30000


# 定义当前时间戳方法，返回秒级 int 时间戳。
def now_ts() -> int:
    # 取当前 Unix 秒级时间戳并转成 int 返回。
    return int(time.time())


# 定义跨平台用户配置目录解析方法，严格对齐 Go 的 os.UserConfigDir 语义。
def get_user_config_dir() -> Path:
    # 读取当前平台标识并转小写，便于统一判断分支。
    platform_name = sys.platform.lower()
    # 如果当前是 Windows 系统（对应 Go 的 windows 分支）。
    if os.name == "nt":
        # 读取 Windows 的 APPDATA 环境变量。
        app_data = (os.environ.get("APPDATA") or "").strip()
        # 如果 APPDATA 没定义或为空。
        if app_data == "":
            # 按 Go 语义抛错，不做静默回退。
            raise EnvironmentError("%AppData% is not defined")
        # 返回 APPDATA 目录作为用户配置目录。
        return Path(app_data)
    # 如果当前是 macOS 或 iOS（对应 Go 的 darwin/ios 分支）。
    if platform_name in {"darwin", "ios"}:
        # 读取 HOME 环境变量。
        home_dir = (os.environ.get("HOME") or "").strip()
        # 如果 HOME 没定义或为空。
        if home_dir == "":
            # 按 Go 语义抛错。
            raise EnvironmentError("$HOME is not defined")
        # 返回 macOS/iOS 配置目录路径。
        return Path(home_dir) / "Library" / "Application Support"
    # 如果当前是 plan9 系统（对应 Go 的 plan9 分支）。
    if platform_name == "plan9":
        # 按 Go 行为读取小写 home 环境变量。
        home_dir = (os.environ.get("home") or "").strip()
        # 如果 home 没定义或为空。
        if home_dir == "":
            # 按 Go 语义抛错。
            raise EnvironmentError("$home is not defined")
        # 返回 plan9 的配置目录路径。
        return Path(home_dir) / "lib"
    # Unix 分支优先读取 XDG_CONFIG_HOME。
    xdg_config_home = (os.environ.get("XDG_CONFIG_HOME") or "").strip()
    # 如果 XDG_CONFIG_HOME 没定义或为空。
    if xdg_config_home == "":
        # 回退读取 HOME 环境变量。
        home_dir = (os.environ.get("HOME") or "").strip()
        # 如果 HOME 也没定义或为空。
        if home_dir == "":
            # 按 Go 语义抛错。
            raise EnvironmentError("neither $XDG_CONFIG_HOME nor $HOME are defined")
        # 返回 HOME/.config 作为配置目录。
        return Path(home_dir) / ".config"
    # 把 XDG_CONFIG_HOME 转成 Path 对象，便于做绝对路径校验。
    xdg_path = Path(xdg_config_home)
    # 如果 XDG_CONFIG_HOME 是相对路径。
    if not xdg_path.is_absolute():
        # 按 Go 语义抛错。
        raise EnvironmentError("path in $XDG_CONFIG_HOME is relative")
    # 返回合法的绝对配置目录路径。
    return xdg_path


# 定义数据库路径解析方法，返回最终 user.db 文件路径。
def resolve_user_db_path(
    # 声明应用目录名参数，默认 vinted_android。
    app_name: str = DEFAULT_APP_DIR_NAME,
    # 声明数据库文件名参数，默认 user.db。
    db_filename: str = DEFAULT_DB_FILENAME,
# 返回值是 Path 对象。
) -> Path:
    # 先获取跨平台用户配置目录。
    config_dir = get_user_config_dir()
    # 在配置目录下拼出业务应用目录。
    app_dir = config_dir / app_name
    # 自动创建目录（不存在时创建，存在时忽略）。
    app_dir.mkdir(parents=True, exist_ok=True)
    # 返回最终数据库文件完整路径。
    return app_dir / db_filename


# 使用 dataclass+slots 定义轻量用户记录结构，减少样板代码和内存开销。
@dataclass(slots=True)
# 定义 t_user 表对应的业务数据结构。
class UserRecord:
    # 邮箱账号，业务上要求唯一。
    email_account: str
    # 邮箱密码字段，默认空字符串。
    email_pwd: str = ""
    # 邮箱 access_key 字段，默认空字符串。
    email_access_key: str = ""
    # 微软 OAuth 应用 client_id 字段，新增必填。
    client_id: str = ""
    # 任务状态字段，默认 0（1=正在使用，2=已使用过，3=账号问题，4=风控限制）。
    status: int = 0
    # 名字段，默认空字符串。
    first_name: str = ""
    # 姓字段，默认空字符串。
    last_name: str = ""
    # vinted 状态字段，默认 0（1=成功，2=失败，3=成功但封号）。
    vinted_status: int = 0
    # Facebook 状态字段，默认 0（0=未注册，1=成功，2=失败）。
    fb_status: int = 0
    # Facebook 注册失败累计次数字段，默认 0。
    fb_fail_num: int = 0
    # titok 状态字段，默认 0（1=成功）。
    titok_status: int = 0
    # 业务密码字段，默认空字符串。
    pwd: str = ""
    # 设备 ID 字段，仅用于列表展示，默认空字符串。
    device: str = ""
    # 备注说明字段，默认空字符串。
    msg: str = ""
    # 创建时间戳字段，默认 0（入库时会自动补当前时间）。
    create_at: int = 0
    # 更新时间戳字段，默认 0（入库/更新时会自动补当前时间）。
    update_at: int = 0


# 定义数据库封装类，统一管理连接、建表和常用读写方法。
class UserDB:
    # 定义初始化方法，支持自定义数据库路径或默认路径。
    def __init__(
        # 当前实例自身。
        self,
        # 可选数据库路径，未传时自动走默认路径。
        db_path: str | os.PathLike[str] | None = None,
        # 可选应用目录名，默认 vinted_android。
        app_name: str = DEFAULT_APP_DIR_NAME,
        # 可选数据库文件名，默认 user.db。
        db_filename: str = DEFAULT_DB_FILENAME,
        # 可选 SQLite 连接超时（秒），未传时使用全局默认值。
        connect_timeout_sec: float = SQLITE_CONNECT_TIMEOUT_SEC,
        # 可选 SQLite busy_timeout（毫秒），未传时使用全局默认值。
        busy_timeout_ms: int = SQLITE_BUSY_TIMEOUT_MS,
    # 初始化方法不返回值。
    ) -> None:
        # 如果调用方没有传入数据库路径。
        if db_path is None:
            # 按默认规则解析路径。
            self.db_path = resolve_user_db_path(app_name=app_name, db_filename=db_filename)
        # 如果调用方显式传入数据库路径。
        else:
            # 把传入路径统一转为 Path 对象。
            self.db_path = Path(db_path)
        # 记录当前实例的 SQLite 连接超时配置（秒）。
        self._connect_timeout_sec = max(float(connect_timeout_sec), 0.1)
        # 记录当前实例的 SQLite busy_timeout 配置（毫秒）。
        self._busy_timeout_ms = max(int(busy_timeout_ms), 0)
        # 初始化连接对象缓存，首次使用时再创建连接。
        self._conn: sqlite3.Connection | None = None

    # 把 path 暴露成只读属性，调用更直观。
    @property
    # 定义数据库文件路径属性方法。
    def path(self) -> Path:
        # 返回数据库文件路径。
        return self.db_path

    # 定义连接方法，按需创建并复用 SQLite 连接。
    def connect(self) -> sqlite3.Connection:
        # 如果连接已创建。
        if self._conn is not None:
            # 直接返回已有连接，避免重复打开文件。
            return self._conn
        # 再次确保父目录存在，防止路径目录缺失。
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # 创建 SQLite 连接并绑定到当前数据库文件。
        self._conn = sqlite3.connect(str(self.db_path), timeout=self._connect_timeout_sec)
        # 设置行工厂为 Row，便于按列名读取数据。
        self._conn.row_factory = sqlite3.Row
        # 设置锁等待超时为 30 秒，降低多进程并发写时的锁冲突报错概率。
        self._conn.execute(f"PRAGMA busy_timeout={self._busy_timeout_ms};")
        # 开启 WAL 模式，提升并发读写稳定性。
        self._conn.execute("PRAGMA journal_mode=WAL;")
        # 设置 WAL 自动 checkpoint，避免 WAL 文件无限增大。
        self._conn.execute("PRAGMA wal_autocheckpoint=1000;")
        # 同步级别用 NORMAL，兼顾性能与可靠性。
        self._conn.execute("PRAGMA synchronous=NORMAL;")
        # 打开外键开关，保持行为一致性（即使当前表未用外键）。
        self._conn.execute("PRAGMA foreign_keys=ON;")
        # 连接创建后立即确保表结构已存在。
        self.ensure_schema()
        # 返回可用连接对象。
        return self._conn

    # 定义关闭连接方法，便于脚本退出前主动释放资源。
    def close(self) -> None:
        # 如果当前没有连接。
        if self._conn is None:
            # 直接返回，不做任何操作。
            return
        # 关闭 SQLite 连接。
        self._conn.close()
        # 重置连接缓存状态，避免误用已关闭连接。
        self._conn = None

    # 定义建表方法，若表不存在则自动创建。
    def ensure_schema(self) -> None:
        # 获取可用连接（首次会自动创建）。
        conn = self.connect()
        create_table_sql = f"""
        CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email_account TEXT NOT NULL UNIQUE,
            email_pwd TEXT NOT NULL DEFAULT '',
            email_access_key TEXT NOT NULL DEFAULT '',
            client_id TEXT NOT NULL DEFAULT '',
            status INTEGER NOT NULL DEFAULT 0 CHECK (status >= 0),
            first_name TEXT NOT NULL DEFAULT '',
            last_name TEXT NOT NULL DEFAULT '',
            vinted_status INTEGER NOT NULL DEFAULT 0 CHECK (vinted_status >= 0),
            fb_status INTEGER NOT NULL DEFAULT 0 CHECK (fb_status >= 0),
            fb_fail_num INTEGER NOT NULL DEFAULT 0 CHECK (fb_fail_num >= 0),
            titok_status INTEGER NOT NULL DEFAULT 0 CHECK (titok_status >= 0),
            pwd TEXT NOT NULL DEFAULT '',
            device TEXT NOT NULL DEFAULT '',
            msg TEXT NOT NULL DEFAULT '',
            create_at INTEGER NOT NULL DEFAULT 0,
            update_at INTEGER NOT NULL DEFAULT 0
        );
        """
        create_config_table_sql = f"""
        CREATE TABLE IF NOT EXISTS {CONFIG_TABLE_NAME} (
            "key" TEXT PRIMARY KEY,
            "val" TEXT NOT NULL DEFAULT '',
            "desc" TEXT NOT NULL DEFAULT '',
            update_at INTEGER NOT NULL DEFAULT 0
        );
        """
        # 使用事务上下文执行建表和索引创建，保证原子性。
        with conn:
            # 执行建表 SQL。
            conn.execute(create_table_sql)
            # 兼容旧表结构：缺字段时自动补齐（例如 fb_status）。
            self._ensure_optional_columns(conn)
            # 执行配置表建表 SQL。
            conn.execute(create_config_table_sql)
            # 确保默认配置项存在（例如 mojiwang_run_num）。
            self._ensure_default_configs(conn)
            # 创建状态索引，便于按 status 批量筛选任务数据。
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_status ON {TABLE_NAME}(status);"
            # 索引 SQL 执行结束。
            )
            # 创建 Facebook 状态索引，便于按 fb_status 查询。
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_fb_status ON {TABLE_NAME}(fb_status);"
            # 索引 SQL 执行结束。
            )
            # 创建设备字段索引，便于按 device 查询“当前占用账号”。
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_device ON {TABLE_NAME}(device);"
            # 索引 SQL 执行结束。
            )
            # 创建更新时间索引，便于按更新时间排序或查询。
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_update_at ON {TABLE_NAME}(update_at);"
            # 索引 SQL 执行结束。
            )
            # 创建配置更新时间索引，便于按更新时间查询配置变更。
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{CONFIG_TABLE_NAME}_update_at ON {CONFIG_TABLE_NAME}(update_at);"
            # 索引 SQL 执行结束。
            )

    # 定义“可选列补齐”方法，兼容旧版本表结构。
    def _ensure_optional_columns(self, conn: sqlite3.Connection) -> None:
        # 读取当前表结构字段信息。
        cursor = conn.execute(f"PRAGMA table_info({TABLE_NAME});")
        # 把字段名整理为集合，便于判断缺失列。
        exists_columns = {str(row["name"]) for row in cursor.fetchall()}
        # 旧表缺少 fb_status 列时执行补齐。
        if "fb_status" not in exists_columns:
            # 执行 ALTER TABLE 增加 fb_status 字段，并设置默认值和非空约束。
            conn.execute(
                f"ALTER TABLE {TABLE_NAME} ADD COLUMN fb_status INTEGER NOT NULL DEFAULT 0;"
            # SQL 执行结束。
            )
        # 旧表缺少 fb_fail_num 列时执行补齐。
        if "fb_fail_num" not in exists_columns:
            # 执行 ALTER TABLE 增加 fb_fail_num 字段，并设置默认值和非空约束。
            conn.execute(
                f"ALTER TABLE {TABLE_NAME} ADD COLUMN fb_fail_num INTEGER NOT NULL DEFAULT 0;"
            # SQL 执行结束。
            )
        # 旧表缺少 client_id 列时执行补齐。
        if "client_id" not in exists_columns:
            # 执行 ALTER TABLE 增加 client_id 字段，并设置默认值和非空约束。
            conn.execute(
                f"ALTER TABLE {TABLE_NAME} ADD COLUMN client_id TEXT NOT NULL DEFAULT '';"
            # SQL 执行结束。
            )
        # 旧表缺少 device 列时执行补齐。
        if "device" not in exists_columns:
            # 执行 ALTER TABLE 增加 device 字段，并设置默认值和非空约束。
            conn.execute(
                f"ALTER TABLE {TABLE_NAME} ADD COLUMN device TEXT NOT NULL DEFAULT '';"
            # SQL 执行结束。
            )

    # 定义默认配置补齐方法，确保新库可直接使用。
    def _ensure_default_configs(self, conn: sqlite3.Connection) -> None:
        # 计算并校验默认配置值。
        default_val = self._normalize_config_value(MOJIWANG_RUN_NUM_KEY, MOJIWANG_RUN_NUM_DEFAULT)
        # 插入默认配置（若 key 已存在则忽略）。
        conn.execute(
            f"""
            INSERT OR IGNORE INTO {CONFIG_TABLE_NAME} ("key", "val", "desc", update_at)
            VALUES (?, ?, ?, ?);
            """,
            # 默认配置参数。
            (MOJIWANG_RUN_NUM_KEY, default_val, MOJIWANG_RUN_NUM_DESC, now_ts()),
        # SQL 执行结束。
        )
        # 计算并校验 status=2/3 重试默认值。
        retry_default_val = self._normalize_config_value(STATUS_23_RETRY_MAX_KEY, STATUS_23_RETRY_MAX_DEFAULT)
        # 插入 status=2/3 最大重试次数默认配置（若 key 已存在则忽略）。
        conn.execute(
            f"""
            INSERT OR IGNORE INTO {CONFIG_TABLE_NAME} ("key", "val", "desc", update_at)
            VALUES (?, ?, ?, ?);
            """,
            # 默认配置参数。
            (STATUS_23_RETRY_MAX_KEY, retry_default_val, STATUS_23_RETRY_MAX_DESC, now_ts()),
        # SQL 执行结束。
        )
        # 计算并校验全局 vinted 密码默认值。
        vt_pwd_default_val = self._normalize_config_value(VT_PWD_KEY, VT_PWD_DEFAULT)
        # 插入全局 vinted 密码默认配置（若 key 已存在则忽略）。
        conn.execute(
            f"""
            INSERT OR IGNORE INTO {CONFIG_TABLE_NAME} ("key", "val", "desc", update_at)
            VALUES (?, ?, ?, ?);
            """,
            # 默认配置参数。
            (VT_PWD_KEY, vt_pwd_default_val, VT_PWD_DESC, now_ts()),
        # SQL 执行结束。
        )
        # 计算并校验 Vinted 删除控制默认值。
        vt_delete_default_val = self._normalize_config_value(VT_DELETE_NUM_KEY, VT_DELETE_NUM_DEFAULT)
        # 插入 Vinted 删除控制默认配置（若 key 已存在则忽略）。
        conn.execute(
            f"""
            INSERT OR IGNORE INTO {CONFIG_TABLE_NAME} ("key", "val", "desc", update_at)
            VALUES (?, ?, ?, ?);
            """,
            # 默认配置参数。
            (VT_DELETE_NUM_KEY, vt_delete_default_val, VT_DELETE_NUM_DESC, now_ts()),
        # SQL 执行结束。
        )
        # 计算并校验 Facebook 删除控制默认值。
        fb_delete_default_val = self._normalize_config_value(FB_DELETE_NUM_KEY, FB_DELETE_NUM_DEFAULT)
        # 插入 Facebook 删除控制默认配置（若 key 已存在则忽略）。
        conn.execute(
            f"""
            INSERT OR IGNORE INTO {CONFIG_TABLE_NAME} ("key", "val", "desc", update_at)
            VALUES (?, ?, ?, ?);
            """,
            # 默认配置参数。
            (FB_DELETE_NUM_KEY, fb_delete_default_val, FB_DELETE_NUM_DESC, now_ts()),
        # SQL 执行结束。
        )
        # 计算并校验设置页 Facebook 账号清理控制默认值。
        setting_fb_del_default_val = self._normalize_config_value(SETTING_FB_DEL_NUM_KEY, SETTING_FB_DEL_NUM_DEFAULT)
        # 插入设置页 Facebook 账号清理控制默认配置（若 key 已存在则忽略）。
        conn.execute(
            f"""
            INSERT OR IGNORE INTO {CONFIG_TABLE_NAME} ("key", "val", "desc", update_at)
            VALUES (?, ?, ?, ?);
            """,
            # 默认配置参数。
            (SETTING_FB_DEL_NUM_KEY, setting_fb_del_default_val, SETTING_FB_DEL_NUM_DESC, now_ts()),
        # SQL 执行结束。
        )
        # 计算并校验代理开始位置默认值。
        proxyip_start_default_val = self._normalize_config_value(PROXYIP_START_NUM_KEY, PROXYIP_START_NUM_DEFAULT)
        # 插入代理开始位置默认配置（若 key 已存在则忽略）。
        conn.execute(
            f"""
            INSERT OR IGNORE INTO {CONFIG_TABLE_NAME} ("key", "val", "desc", update_at)
            VALUES (?, ?, ?, ?);
            """,
            # 默认配置参数。
            (PROXYIP_START_NUM_KEY, proxyip_start_default_val, PROXYIP_START_NUM_DESC, now_ts()),
        # SQL 执行结束。
        )
        # 计算并校验代理结束位置默认值。
        proxyip_end_default_val = self._normalize_config_value(PROXYIP_END_NUM_KEY, PROXYIP_END_NUM_DEFAULT)
        # 插入代理结束位置默认配置（若 key 已存在则忽略）。
        conn.execute(
            f"""
            INSERT OR IGNORE INTO {CONFIG_TABLE_NAME} ("key", "val", "desc", update_at)
            VALUES (?, ?, ?, ?);
            """,
            # 默认配置参数。
            (PROXYIP_END_NUM_KEY, proxyip_end_default_val, PROXYIP_END_NUM_DESC, now_ts()),
        # SQL 执行结束。
        )

    # 定义配置值标准化方法，并做 key 级别校验。
    def _normalize_config_value(self, key: str, val: str) -> str:
        # 把配置值转字符串并清理空白字符。
        raw_value = str(val).strip()
        # 针对抹机王次数配置执行范围校验。
        if key == MOJIWANG_RUN_NUM_KEY:
            # 空值直接判定为非法。
            if raw_value == "":
                # 抛出明确错误提示。
                raise ValueError("mojiwang_run_num 不能为空，需填写 1 到 100 的整数")
            # 尝试把输入值解析为整数。
            try:
                # 转成整数做范围检查。
                num_value = int(raw_value)
            # 非整数输入直接报错。
            except ValueError as exc:
                # 抛出明确错误提示。
                raise ValueError("mojiwang_run_num 必须是整数，范围 1 到 100") from exc
            # 范围不在 1~100 时判定为非法。
            if not 1 <= num_value <= 100:
                # 抛出明确错误提示。
                raise ValueError("mojiwang_run_num 超出范围，必须在 1 到 100 之间")
            # 返回标准化后的整数文本。
            return str(num_value)
        # 针对 status=2/3 重试次数配置执行范围校验。
        if key == STATUS_23_RETRY_MAX_KEY:
            # 空值直接判定为非法。
            if raw_value == "":
                # 抛出明确错误提示。
                raise ValueError("status_23_retry_max_num 不能为空，需填写 0 到 5 的整数")
            # 尝试把输入值解析为整数。
            try:
                # 转成整数做范围检查。
                retry_value = int(raw_value)
            # 非整数输入直接报错。
            except ValueError as exc:
                # 抛出明确错误提示。
                raise ValueError("status_23_retry_max_num 必须是整数，范围 0 到 5") from exc
            # 范围不在 0~5 时判定为非法。
            if not STATUS_23_RETRY_MIN <= retry_value <= STATUS_23_RETRY_MAX:
                # 抛出范围错误提示。
                raise ValueError("status_23_retry_max_num 超出范围，必须在 0 到 5 之间")
            # 返回标准化后的整数文本。
            return str(retry_value)
        # 针对全局 vinted 密码配置做长度保护（允许空值）。
        if key == VT_PWD_KEY:
            # 密码过长时直接报错，避免异常超长数据写入数据库。
            if len(raw_value) > 256:
                # 抛出明确错误提示。
                raise ValueError("vt_pwd 长度不能超过 256 个字符")
            # 返回清理后的密码文本（可为空）。
            return raw_value
        # 针对 Vinted 删除控制配置执行非负整数范围校验。
        if key == VT_DELETE_NUM_KEY:
            # 空值直接判定为非法。
            if raw_value == "":
                # 抛出明确错误提示。
                raise ValueError("vt_delete_num 不能为空，需填写大于等于 0 的整数")
            # 尝试把输入值解析为整数。
            try:
                # 转成整数做范围检查。
                vt_delete_num = int(raw_value)
            # 非整数输入直接报错。
            except ValueError as exc:
                # 抛出明确错误提示。
                raise ValueError("vt_delete_num 必须是整数（0=仅清理，>0 为重装周期）") from exc
            # 范围不在允许区间时判定为非法。
            if not FB_DELETE_NUM_MIN <= vt_delete_num <= FB_DELETE_NUM_MAX:
                # 抛出范围错误提示。
                raise ValueError(f"vt_delete_num 超出范围，必须在 {FB_DELETE_NUM_MIN} 到 {FB_DELETE_NUM_MAX} 之间")
            # 返回标准化后的整数文本。
            return str(vt_delete_num)
        # 针对 Facebook 删除控制配置执行非负整数范围校验。
        if key == FB_DELETE_NUM_KEY:
            # 空值直接判定为非法。
            if raw_value == "":
                # 抛出明确错误提示。
                raise ValueError("fb_delete_num 不能为空，需填写大于等于 0 的整数")
            # 尝试把输入值解析为整数。
            try:
                # 转成整数做范围检查。
                fb_delete_num = int(raw_value)
            # 非整数输入直接报错。
            except ValueError as exc:
                # 抛出明确错误提示。
                raise ValueError("fb_delete_num 必须是整数（0=仅清理，>0 为重装周期）") from exc
            # 范围不在允许区间时判定为非法。
            if not FB_DELETE_NUM_MIN <= fb_delete_num <= FB_DELETE_NUM_MAX:
                # 抛出范围错误提示。
                raise ValueError(f"fb_delete_num 超出范围，必须在 {FB_DELETE_NUM_MIN} 到 {FB_DELETE_NUM_MAX} 之间")
            # 返回标准化后的整数文本。
            return str(fb_delete_num)
        # 针对设置页 Facebook 账号清理控制配置执行非负整数范围校验。
        if key == SETTING_FB_DEL_NUM_KEY:
            # 空值直接判定为非法。
            if raw_value == "":
                # 抛出明确错误提示。
                raise ValueError("setting_fb_del_num 不能为空，需填写大于等于 0 的整数")
            # 尝试把输入值解析为整数。
            try:
                # 转成整数做范围检查。
                setting_fb_del_num = int(raw_value)
            # 非整数输入直接报错。
            except ValueError as exc:
                # 抛出明确错误提示。
                raise ValueError("setting_fb_del_num 必须是整数（0=不清理，>0 为设置页清理周期）") from exc
            # 范围不在允许区间时判定为非法。
            if not FB_DELETE_NUM_MIN <= setting_fb_del_num <= FB_DELETE_NUM_MAX:
                # 抛出范围错误提示。
                raise ValueError(f"setting_fb_del_num 超出范围，必须在 {FB_DELETE_NUM_MIN} 到 {FB_DELETE_NUM_MAX} 之间")
            # 返回标准化后的整数文本。
            return str(setting_fb_del_num)
        # 针对代理开始位置配置执行 1~5 范围校验。
        if key == PROXYIP_START_NUM_KEY:
            # 空值直接判定为非法。
            if raw_value == "":
                # 抛出明确错误提示。
                raise ValueError("proxyip_start_num 不能为空，需填写 1 到 5 的整数")
            # 尝试把输入值解析为整数。
            try:
                # 转成整数做范围检查。
                proxyip_start_num = int(raw_value)
            # 非整数输入直接报错。
            except ValueError as exc:
                # 抛出明确错误提示。
                raise ValueError("proxyip_start_num 必须是整数，范围 1 到 6") from exc
            # 范围不在允许区间时判定为非法。
            if not PROXYIP_NUM_MIN <= proxyip_start_num <= PROXYIP_NUM_MAX:
                # 抛出范围错误提示。
                raise ValueError(f"proxyip_start_num 超出范围，必须在 {PROXYIP_NUM_MIN} 到 {PROXYIP_NUM_MAX} 之间")
            # 返回标准化后的整数文本。
            return str(proxyip_start_num)
        # 针对代理结束位置配置执行 1~5 范围校验。
        if key == PROXYIP_END_NUM_KEY:
            # 空值直接判定为非法。
            if raw_value == "":
                # 抛出明确错误提示。
                raise ValueError("proxyip_end_num 不能为空，需填写 1 到 5 的整数")
            # 尝试把输入值解析为整数。
            try:
                # 转成整数做范围检查。
                proxyip_end_num = int(raw_value)
            # 非整数输入直接报错。
            except ValueError as exc:
                # 抛出明确错误提示。
                raise ValueError("proxyip_end_num 必须是整数，范围 1 到 5") from exc
            # 范围不在允许区间时判定为非法。
            if not PROXYIP_NUM_MIN <= proxyip_end_num <= PROXYIP_NUM_MAX:
                # 抛出范围错误提示。
                raise ValueError(f"proxyip_end_num 超出范围，必须在 {PROXYIP_NUM_MIN} 到 {PROXYIP_NUM_MAX} 之间")
            # 返回标准化后的整数文本。
            return str(proxyip_end_num)
        # 其他 key 当前不做额外规则，直接返回清理后文本。
        return raw_value

    # 定义必填文本字段标准化方法。
    def _normalize_required_text(self, field_name: str, raw_value: str) -> str:
        # 把输入值转字符串并清理前后空白。
        normalized_value = str(raw_value).strip()
        # 空字符串直接判定为非法。
        if normalized_value == "":
            # 抛出带字段名的明确错误提示。
            raise ValueError(f"{field_name} 不能为空")
        # 返回标准化后的非空文本。
        return normalized_value

    # 定义可选文本字段标准化方法（允许空字符串）。
    def _normalize_optional_text(self, raw_value: str) -> str:
        # 把输入值转字符串并清理前后空白后返回。
        return str(raw_value or "").strip()

    # 定义整数范围校验方法。
    def _normalize_int_range(self, field_name: str, raw_value: int | str, min_value: int, max_value: int) -> int:
        # 尝试把输入值转成整数。
        try:
            # 把原始值转成 int。
            int_value = int(raw_value)
        # 转换失败时判定为非法整数。
        except Exception as exc:
            # 抛出明确错误提示并保留原始异常链。
            raise ValueError(f"{field_name} 必须是整数") from exc
        # 值超出范围时判定为非法输入。
        if int_value < int(min_value) or int_value > int(max_value):
            # 抛出范围错误提示。
            raise ValueError(f"{field_name} 超出范围，必须在 {int(min_value)} 到 {int(max_value)} 之间")
        # 返回通过校验的整数值。
        return int_value

    # 定义非负整数校验方法。
    def _normalize_non_negative_int(self, field_name: str, raw_value: int | str, max_value: int) -> int:
        # 复用整数范围校验方法，统一校验“非负且不超过上限”。
        return self._normalize_int_range(field_name, raw_value, FB_FAIL_NUM_MIN, max_value)

    # 定义唯一键冲突识别方法（email_account）。
    def _is_unique_email_error(self, exc: sqlite3.IntegrityError) -> bool:
        # 读取数据库异常文本并转小写，便于统一匹配。
        message = str(exc).lower()
        # 判断是否为邮箱唯一约束冲突。
        return "unique constraint failed" in message and f"{TABLE_NAME}.email_account" in message

    # 定义账号记录校验方法（新增/修改共用）。
    def validate_user_record(self, record: UserRecord) -> UserRecord:
        # 非 UserRecord 输入直接判定为非法参数。
        if not isinstance(record, UserRecord):
            # 抛出类型错误，避免后续字段访问异常。
            raise TypeError("record 必须是 UserRecord 类型")

        # 校验并标准化邮箱账号（必填）。
        normalized_email_account = self._normalize_required_text("email_account", record.email_account)
        # 校验并标准化邮箱密码（必填）。
        normalized_email_pwd = self._normalize_required_text("email_pwd", record.email_pwd)
        # 校验并标准化邮箱授权码（必填）。
        normalized_email_access_key = self._normalize_required_text("email_access_key", record.email_access_key)
        # 校验并标准化 client_id（必填）。
        normalized_client_id = self._normalize_required_text("client_id", record.client_id)
        # 校验并标准化姓（必填）。
        normalized_first_name = self._normalize_required_text("first_name", record.first_name)
        # 校验并标准化名（必填）。
        normalized_last_name = self._normalize_required_text("last_name", record.last_name)
        # 校验并标准化业务密码（必填）。
        normalized_pwd = self._normalize_required_text("pwd", record.pwd)
        # 校验并标准化账号状态（0~3）。
        normalized_status = self._normalize_int_range("status", record.status, ACCOUNT_STATUS_MIN, ACCOUNT_STATUS_MAX)
        # 校验并标准化 vt 状态（0~2）。
        normalized_vinted_status = self._normalize_int_range("vinted_status", record.vinted_status, REGISTER_STATUS_MIN, REGISTER_STATUS_MAX)
        # 校验并标准化 fb 状态（0~2）。
        normalized_fb_status = self._normalize_int_range("fb_status", record.fb_status, REGISTER_STATUS_MIN, REGISTER_STATUS_MAX)
        # 校验并标准化 Facebook 失败累计次数（0~2147483647）。
        normalized_fb_fail_num = self._normalize_non_negative_int("fb_fail_num", record.fb_fail_num, FB_FAIL_NUM_MAX)
        # 校验并标准化 tt 状态（0~2）。
        normalized_titok_status = self._normalize_int_range("titok_status", record.titok_status, REGISTER_STATUS_MIN, REGISTER_STATUS_MAX)
        # 标准化设备字段（非必填，允许为空）。
        normalized_device = str(record.device or "").strip()
        # 标准化备注字段（非必填，允许为空）。
        normalized_msg = str(record.msg or "").strip()

        # 返回标准化后的新记录对象，避免直接修改原始入参对象。
        return replace(
            # 基于原始记录复制新对象。
            record,
            # 写回标准化邮箱账号。
            email_account=normalized_email_account,
            # 写回标准化邮箱密码。
            email_pwd=normalized_email_pwd,
            # 写回标准化邮箱授权码。
            email_access_key=normalized_email_access_key,
            # 写回标准化 client_id。
            client_id=normalized_client_id,
            # 写回标准化姓。
            first_name=normalized_first_name,
            # 写回标准化名。
            last_name=normalized_last_name,
            # 写回标准化业务密码。
            pwd=normalized_pwd,
            # 写回标准化账号状态。
            status=normalized_status,
            # 写回标准化 vt 状态。
            vinted_status=normalized_vinted_status,
            # 写回标准化 fb 状态。
            fb_status=normalized_fb_status,
            # 写回标准化 Facebook 失败累计次数。
            fb_fail_num=normalized_fb_fail_num,
            # 写回标准化 tt 状态。
            titok_status=normalized_titok_status,
            # 写回标准化设备字段。
            device=normalized_device,
            # 写回标准化备注文本。
            msg=normalized_msg,
        # 返回值构造完成。
        )

    # 定义插入或更新方法（以 email_account 唯一键冲突处理）。
    def upsert_user(self, record: UserRecord) -> None:
        # 先执行必填、状态和失败次数范围校验。
        normalized_record = self.validate_user_record(record)
        # 获取可用连接。
        conn = self.connect()
        # 取当前时间戳用于默认 create_at/update_at。
        ts_now = now_ts()
        # 如果外部没传 create_at，则自动用当前时间戳。
        create_at_value = normalized_record.create_at if normalized_record.create_at > 0 else ts_now
        # 如果外部没传 update_at，则自动用当前时间戳。
        update_at_value = normalized_record.update_at if normalized_record.update_at > 0 else ts_now
        sql = f"""
        INSERT INTO {TABLE_NAME} (
            email_account,
            email_pwd,
            email_access_key,
            client_id,
            status,
            first_name,
            last_name,
            vinted_status,
            fb_status,
            fb_fail_num,
            titok_status,
            pwd,
            device,
            msg,
            create_at,
            update_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(email_account) DO UPDATE SET
            email_pwd = excluded.email_pwd,
            email_access_key = excluded.email_access_key,
            client_id = excluded.client_id,
            status = excluded.status,
            first_name = excluded.first_name,
            last_name = excluded.last_name,
            vinted_status = excluded.vinted_status,
            fb_status = excluded.fb_status,
            fb_fail_num = excluded.fb_fail_num,
            titok_status = excluded.titok_status,
            pwd = excluded.pwd,
            device = excluded.device,
            msg = excluded.msg,
            update_at = excluded.update_at;
        """
        # 组装 SQL 参数元组，按占位符顺序传入。
        params = (
            # 传入邮箱账号。
            normalized_record.email_account,
            # 传入邮箱密码。
            normalized_record.email_pwd,
            # 传入邮箱 access_key。
            normalized_record.email_access_key,
            # 传入微软 OAuth 应用 client_id。
            normalized_record.client_id,
            # 传入状态并强转为 int。
            int(normalized_record.status),
            # 传入名字段。
            normalized_record.first_name,
            # 传入姓字段。
            normalized_record.last_name,
            # 传入 vinted 状态并强转为 int。
            int(normalized_record.vinted_status),
            # 传入 Facebook 状态并强转为 int。
            int(normalized_record.fb_status),
            # 传入 Facebook 失败累计次数并强转为 int。
            int(normalized_record.fb_fail_num),
            # 传入 titok 状态并强转为 int。
            int(normalized_record.titok_status),
            # 传入业务密码。
            normalized_record.pwd,
            # 传入设备 ID（仅展示字段）。
            normalized_record.device,
            # 传入备注说明。
            normalized_record.msg,
            # 传入创建时间戳。
            int(create_at_value),
            # 传入更新时间戳。
            int(update_at_value),
        # 参数元组定义结束。
        )
        # 使用事务上下文执行写入，自动提交。
        with conn:
            # 执行 UPSERT 写入操作。
            conn.execute(sql, params)

    # 定义按邮箱查询单条记录方法。
    def get_user_by_email(self, email_account: str) -> dict[str, Any] | None:
        # 获取可用连接。
        conn = self.connect()
        # 执行查询语句并返回游标。
        cursor = conn.execute(
            # 按唯一邮箱查询一条记录。
            f"SELECT * FROM {TABLE_NAME} WHERE email_account = ? LIMIT 1;",
            # 传入邮箱参数。
            (email_account,),
        # 查询执行结束。
        )
        # 读取查询结果第一行。
        row = cursor.fetchone()
        # 如果查询不到记录。
        if row is None:
            # 返回 None 表示不存在。
            return None
        # 把 sqlite3.Row 转为普通字典返回。
        return dict(row)

    # 定义按状态批量查询方法。
    def list_users_by_status(self, status: int, limit: int = 100) -> list[dict[str, Any]]:
        # 获取可用连接。
        conn = self.connect()
        # 对 limit 做下限保护，避免传入 0 或负数。
        safe_limit = max(int(limit), 1)
        # 执行按状态查询 SQL。
        cursor = conn.execute(
            # 按 status 查询并按 id 升序返回。
            f"SELECT * FROM {TABLE_NAME} WHERE status = ? ORDER BY id ASC LIMIT ?;",
            # 传入状态值和限制数量。
            (int(status), safe_limit),
        # 查询执行结束。
        )
        # 把结果集逐行转字典后返回列表。
        return [dict(row) for row in cursor.fetchall()]

    # 定义账号列表查询方法（账号列表 Tab 使用）。
    def list_users(self, limit: int = 300, offset: int = 0) -> list[dict[str, Any]]:
        # 获取可用连接。
        conn = self.connect()
        # 对 limit 做下限保护，避免传入无效值。
        safe_limit = max(int(limit), 1)
        # 对 offset 做下限保护，避免负数偏移。
        safe_offset = max(int(offset), 0)
        # 执行列表查询 SQL。
        cursor = conn.execute(
            # 按 id 倒序查询，优先展示最新账号。
            f"SELECT * FROM {TABLE_NAME} ORDER BY id DESC LIMIT ? OFFSET ?;",
            # 传入限制数量和偏移量参数。
            (safe_limit, safe_offset),
        # SQL 执行结束。
        )
        # 把结果集逐行转字典后返回列表。
        return [dict(row) for row in cursor.fetchall()]

    # 定义按设备 serial 查询当前绑定账号方法。
    def get_user_by_device(self, device: str) -> dict[str, Any] | None:
        # 获取可用连接。
        conn = self.connect()
        # 标准化设备 serial 文本。
        safe_device = self._normalize_optional_text(device)
        # 设备 serial 为空时直接返回空。
        if safe_device == "":
            return None
        # 执行按 device 查询 SQL。
        cursor = conn.execute(
            # 按设备 serial 取一条绑定账号。
            f"SELECT * FROM {TABLE_NAME} WHERE device = ? ORDER BY id ASC LIMIT 1;",
            # 传入设备 serial 参数。
            (safe_device,),
        # SQL 执行结束。
        )
        # 读取查询结果第一行。
        row = cursor.fetchone()
        # 查询不到绑定账号时返回 None。
        if row is None:
            return None
        # 把 sqlite3.Row 转字典后返回。
        return dict(row)

    # 定义允许参与账号领取筛选的小状态字段集合。
    CLAIMABLE_REGISTER_STATUS_FIELDS = {"fb_status", "vinted_status", "titok_status"}

    # 定义“按设备领取一条可用账号（status=0 且当前模式小状态=0）”方法（事务加锁防并发冲突）。
    def claim_user_for_device(self, device: str, status_field: str) -> dict[str, Any] | None:
        # 获取可用连接。
        conn = self.connect()
        # 校验并标准化设备 serial。
        safe_device = self._normalize_required_text("device", device)
        # 标准化当前注册方式对应的小状态字段名。
        safe_status_field = str(status_field or "").strip()
        # 仅允许预设的小状态字段名参与动态 SQL，避免误传非法列名。
        if safe_status_field not in self.CLAIMABLE_REGISTER_STATUS_FIELDS:
            # 直接抛出可读错误，便于上层快速定位参数问题。
            raise ValueError(f"不支持的状态字段: {safe_status_field or '-'}")
        # 获取当前时间戳，供 update_at 写入。
        ts_now = now_ts()
        # 使用显式事务，确保“查询+更新”原子化。
        try:
            # 申请写锁，避免多个设备并发抢到同一条账号。
            conn.execute("BEGIN IMMEDIATE;")

            # 先检查当前设备是否已占用一条 status=1 的账号。
            current_row = conn.execute(
                # 查询本设备已占用账号。
                f"SELECT * FROM {TABLE_NAME} WHERE device = ? AND status = 1 ORDER BY id ASC LIMIT 1;",
                # 传入设备 serial 参数。
                (safe_device,),
            # 读取查询结果首行。
            ).fetchone()
            # 已有占用账号时直接复用，避免重复分配。
            if current_row is not None:
                # 提交事务，释放写锁。
                conn.commit()
                # 返回当前占用账号。
                return dict(current_row)

            # 清理本设备遗留的非运行态绑定（例如 status=2/3 停机后遗留 device）。
            conn.execute(
                # 仅清理非 status=1 绑定。
                f"UPDATE {TABLE_NAME} SET device = '', update_at = ? WHERE device = ? AND status != 1;",
                # 传入更新时间和设备 serial。
                (int(ts_now), safe_device),
            # SQL 执行结束。
            )

            # 从可用池里找一条“未使用、未绑定设备且当前模式未注册”的账号。
            candidate_row = conn.execute(
                f"""
                SELECT * FROM {TABLE_NAME}
                WHERE status = 0 AND {safe_status_field} = 0 AND (device = '' OR device IS NULL)
                ORDER BY id ASC
                LIMIT 1;
                """,
            # 读取候选账号。
            ).fetchone()
            # 没有可用账号时返回空，让 worker 进入等待。
            if candidate_row is None:
                # 提交事务，释放写锁。
                conn.commit()
                return None

            # 读取候选账号主键，后续用于条件更新。
            candidate_id = int(candidate_row["id"])
            # 尝试把候选账号原子更新为“本设备占用中”。
            update_cursor = conn.execute(
                f"""
                UPDATE {TABLE_NAME}
                SET status = 1, device = ?, update_at = ?
                WHERE id = ? AND status = 0 AND {safe_status_field} = 0 AND (device = '' OR device IS NULL);
                """,
                # 传入设备 serial、更新时间和候选 id。
                (safe_device, int(ts_now), candidate_id),
            # SQL 执行结束。
            )
            # 理论上持锁后不会失败，这里做防御性保护。
            if int(update_cursor.rowcount) <= 0:
                # 更新失败时回滚事务，避免半状态。
                conn.rollback()
                # 返回空让上层等待下一轮重试。
                return None

            # 查询更新后的完整账号记录返回给调用方。
            assigned_row = conn.execute(
                # 按 id 查询刚刚分配的账号。
                f"SELECT * FROM {TABLE_NAME} WHERE id = ? LIMIT 1;",
                # 传入候选账号 id。
                (candidate_id,),
            # 读取分配结果首行。
            ).fetchone()
            # 提交事务，正式完成本次分配并释放写锁。
            conn.commit()
            # 极端防御：如果查不到记录则返回空。
            if assigned_row is None:
                return None
            # 返回分配成功的账号信息。
            return dict(assigned_row)
        # 任意异常都回滚事务，确保数据库状态一致。
        except Exception:
            try:
                # 回滚未提交事务。
                conn.rollback()
            except Exception:
                pass
            # 把原异常继续抛出给上层处理。
            raise

    # 定义“按设备释放账号占用”方法（status=1 -> 0，status=2/3/4 保持不变）。
    def release_user_for_device(self, device: str) -> int:
        # 获取可用连接。
        conn = self.connect()
        # 标准化设备 serial 文本。
        safe_device = self._normalize_optional_text(device)
        # 设备 serial 为空时无可释放数据。
        if safe_device == "":
            return 0
        # 生成本次释放更新时间戳。
        update_time = now_ts()
        # 使用事务上下文执行释放更新，保证原子性。
        with conn:
            # 执行按设备释放 SQL。
            cursor = conn.execute(
                f"""
                UPDATE {TABLE_NAME}
                SET
                    status = CASE WHEN status = 1 THEN 0 ELSE status END,
                    device = '',
                    update_at = ?
                WHERE device = ?;
                """,
                # 传入更新时间和设备 serial。
                (int(update_time), safe_device),
            # SQL 执行结束。
            )
        # 返回释放影响行数。
        return int(cursor.rowcount)

    # 定义“全局重置运行中账号”方法（status=1 -> 0，并清空 device）。
    def reset_all_running_users(self) -> int:
        # 获取可用连接。
        conn = self.connect()
        # 生成本次批量重置更新时间戳。
        update_time = now_ts()
        # 使用事务上下文执行批量更新，保证原子性。
        with conn:
            # 执行全局释放 SQL，仅回退仍处于“使用中”的账号。
            cursor = conn.execute(
                f"""
                UPDATE {TABLE_NAME}
                SET
                    status = 0,
                    device = '',
                    update_at = ?
                WHERE status = 1;
                """,
                # 传入更新时间参数。
                (int(update_time),),
            # SQL 执行结束。
            )
        # 返回批量重置影响行数。
        return int(cursor.rowcount)

    # 定义“按用户 id 清空 device 绑定（不改 status）”方法。
    def clear_device_by_user_id(self, user_id: int) -> int:
        # 把 user_id 转成整数，统一 SQL 入参类型。
        safe_user_id = int(user_id)
        # 非法 id 时直接返回 0。
        if safe_user_id <= 0:
            return 0
        # 获取可用连接。
        conn = self.connect()
        # 生成更新时间戳。
        update_time = now_ts()
        # 使用事务上下文执行更新。
        with conn:
            # 执行仅清空 device 的 SQL。
            cursor = conn.execute(
                # 不改 status，仅释放设备绑定。
                f"UPDATE {TABLE_NAME} SET device = '', update_at = ? WHERE id = ?;",
                # 传入更新时间和目标用户 id。
                (int(update_time), safe_user_id),
            # SQL 执行结束。
            )
        # 返回影响行数。
        return int(cursor.rowcount)

    # 定义账号总数查询方法，供分页统计使用。
    def count_users(self) -> int:
        # 获取可用连接。
        conn = self.connect()
        # 执行总数统计 SQL。
        cursor = conn.execute(f"SELECT COUNT(1) AS total FROM {TABLE_NAME};")
        # 读取统计结果首行。
        row = cursor.fetchone()
        # 理论上不会为空，这里做防御性判断。
        if row is None:
            # 空结果时返回 0。
            return 0
        # 返回账号总数整数值。
        return int(row["total"])

    # 定义分页查询方法（按 id 倒序）。
    def list_users_page(self, page: int, page_size: int = 20) -> list[dict[str, Any]]:
        # 对页码做下限保护，至少为第 1 页。
        safe_page = max(int(page), 1)
        # 对每页条数做下限保护，至少 1 条。
        safe_page_size = max(int(page_size), 1)
        # 根据页码和页大小计算偏移量。
        offset = (safe_page - 1) * safe_page_size
        # 复用 list_users 返回当前页数据。
        return self.list_users(limit=safe_page_size, offset=offset)

    # 定义账号筛选 SQL 片段构建方法（供列表与计数复用）。
    def _build_user_filters_sql(
        # 当前实例自身。
        self,
        # 邮箱关键字筛选（模糊匹配）。
        email_keyword: str = "",
        # 账号状态筛选（None 表示不过滤）。
        status: int | None = None,
        # fb 状态筛选（None 表示不过滤）。
        fb_status: int | None = None,
        # vt 状态筛选（None 表示不过滤）。
        vinted_status: int | None = None,
        # tt 状态筛选（None 表示不过滤）。
        titok_status: int | None = None,
    # 返回 where SQL 片段和参数列表。
    ) -> tuple[str, list[Any]]:
        # 初始化 where 子句片段列表。
        where_parts: list[str] = []
        # 初始化 SQL 参数列表。
        args: list[Any] = []

        # 清理邮箱关键字输入。
        email_kw = str(email_keyword).strip()
        # 关键字非空时启用邮箱模糊匹配。
        if email_kw != "":
            # 追加邮箱 LIKE 条件。
            where_parts.append("email_account LIKE ?")
            # 追加邮箱模糊匹配参数。
            args.append(f"%{email_kw}%")
        # 传入账号状态时追加过滤条件。
        if status is not None:
            # 追加 status 精确匹配条件。
            where_parts.append("status = ?")
            # 追加 status 参数。
            args.append(int(status))
        # 传入 fb 状态时追加过滤条件。
        if fb_status is not None:
            # 追加 fb_status 精确匹配条件。
            where_parts.append("fb_status = ?")
            # 追加 fb_status 参数。
            args.append(int(fb_status))
        # 传入 vt 状态时追加过滤条件。
        if vinted_status is not None:
            # 追加 vinted_status 精确匹配条件。
            where_parts.append("vinted_status = ?")
            # 追加 vinted_status 参数。
            args.append(int(vinted_status))
        # 传入 tt 状态时追加过滤条件。
        if titok_status is not None:
            # 追加 titok_status 精确匹配条件。
            where_parts.append("titok_status = ?")
            # 追加 titok_status 参数。
            args.append(int(titok_status))

        # 没有任何过滤条件时直接返回空 where。
        if not where_parts:
            return "", args
        # 拼接并返回 where 子句和参数列表。
        return f" WHERE {' AND '.join(where_parts)}", args

    # 定义带筛选条件的账号总数查询方法。
    def count_users_filtered(
        # 当前实例自身。
        self,
        # 邮箱关键字筛选。
        email_keyword: str = "",
        # 账号状态筛选。
        status: int | None = None,
        # fb 状态筛选。
        fb_status: int | None = None,
        # vt 状态筛选。
        vinted_status: int | None = None,
        # tt 状态筛选。
        titok_status: int | None = None,
    # 返回筛选后的总条数。
    ) -> int:
        # 获取可用连接。
        conn = self.connect()
        # 构建 where 子句和参数。
        where_sql, args = self._build_user_filters_sql(
            # 传入邮箱关键字筛选参数。
            email_keyword=email_keyword,
            # 传入账号状态筛选参数。
            status=status,
            # 传入 fb 状态筛选参数。
            fb_status=fb_status,
            # 传入 vt 状态筛选参数。
            vinted_status=vinted_status,
            # 传入 tt 状态筛选参数。
            titok_status=titok_status,
        )
        # 执行筛选计数 SQL。
        cursor = conn.execute(
            # 查询筛选后的账号总数。
            f"SELECT COUNT(1) AS total FROM {TABLE_NAME}{where_sql};",
            # 传入 where 参数列表。
            tuple(args),
        # SQL 执行结束。
        )
        # 读取统计结果第一行。
        row = cursor.fetchone()
        # 理论上不会为空，这里做防御性判断。
        if row is None:
            return 0
        # 返回筛选后账号总数。
        return int(row["total"])

    # 定义带筛选条件的账号列表查询方法（按 id 倒序）。
    def list_users_filtered(
        # 当前实例自身。
        self,
        # 查询条数上限。
        limit: int = 20,
        # 查询偏移量。
        offset: int = 0,
        # 邮箱关键字筛选。
        email_keyword: str = "",
        # 账号状态筛选。
        status: int | None = None,
        # fb 状态筛选。
        fb_status: int | None = None,
        # vt 状态筛选。
        vinted_status: int | None = None,
        # tt 状态筛选。
        titok_status: int | None = None,
    # 返回筛选后的账号列表。
    ) -> list[dict[str, Any]]:
        # 获取可用连接。
        conn = self.connect()
        # 对 limit 做下限保护，避免传入无效值。
        safe_limit = max(int(limit), 1)
        # 对 offset 做下限保护，避免负数偏移。
        safe_offset = max(int(offset), 0)
        # 构建 where 子句和参数。
        where_sql, args = self._build_user_filters_sql(
            # 传入邮箱关键字筛选参数。
            email_keyword=email_keyword,
            # 传入账号状态筛选参数。
            status=status,
            # 传入 fb 状态筛选参数。
            fb_status=fb_status,
            # 传入 vt 状态筛选参数。
            vinted_status=vinted_status,
            # 传入 tt 状态筛选参数。
            titok_status=titok_status,
        )
        # 执行带筛选条件的列表查询 SQL。
        cursor = conn.execute(
            # 按 id 倒序分页查询筛选结果。
            f"SELECT * FROM {TABLE_NAME}{where_sql} ORDER BY id DESC LIMIT ? OFFSET ?;",
            # 传入 where 参数和分页参数。
            tuple(args + [safe_limit, safe_offset]),
        # SQL 执行结束。
        )
        # 把结果集逐行转字典后返回列表。
        return [dict(row) for row in cursor.fetchall()]

    # 定义带筛选条件的分页查询方法（按 id 倒序）。
    def list_users_page_filtered(
        # 当前实例自身。
        self,
        # 页码（从 1 开始）。
        page: int,
        # 每页条数。
        page_size: int = 20,
        # 邮箱关键字筛选。
        email_keyword: str = "",
        # 账号状态筛选。
        status: int | None = None,
        # fb 状态筛选。
        fb_status: int | None = None,
        # vt 状态筛选。
        vinted_status: int | None = None,
        # tt 状态筛选。
        titok_status: int | None = None,
    # 返回筛选后的分页结果。
    ) -> list[dict[str, Any]]:
        # 对页码做下限保护，至少为第 1 页。
        safe_page = max(int(page), 1)
        # 对每页条数做下限保护，至少 1 条。
        safe_page_size = max(int(page_size), 1)
        # 根据页码和页大小计算偏移量。
        offset = (safe_page - 1) * safe_page_size
        # 复用带筛选列表查询方法返回当前页数据。
        return self.list_users_filtered(
            # 传入分页条数。
            limit=safe_page_size,
            # 传入分页偏移量。
            offset=offset,
            # 传入邮箱关键字筛选参数。
            email_keyword=email_keyword,
            # 传入账号状态筛选参数。
            status=status,
            # 传入 fb 状态筛选参数。
            fb_status=fb_status,
            # 传入 vt 状态筛选参数。
            vinted_status=vinted_status,
            # 传入 tt 状态筛选参数。
            titok_status=titok_status,
        )

    # 定义按 id 查询单条账号记录方法。
    def get_user_by_id(self, user_id: int) -> dict[str, Any] | None:
        # 把 user_id 转成整数，统一后续 SQL 入参类型。
        safe_user_id = int(user_id)
        # 非法 id 直接返回 None，避免无意义查询。
        if safe_user_id <= 0:
            return None
        # 获取可用连接。
        conn = self.connect()
        # 执行按 id 查询 SQL。
        cursor = conn.execute(
            # 按主键 id 查询单条记录。
            f"SELECT * FROM {TABLE_NAME} WHERE id = ? LIMIT 1;",
            # 传入 id 参数。
            (safe_user_id,),
        # SQL 执行结束。
        )
        # 读取查询结果第一行。
        row = cursor.fetchone()
        # 查询不到记录时返回 None。
        if row is None:
            return None
        # 把 sqlite3.Row 转字典后返回。
        return dict(row)

    # 定义新增账号方法，成功返回新记录 id。
    def create_user(self, record: UserRecord) -> int:
        # 先执行新增必填和状态范围校验。
        normalized_record = self.validate_user_record(record)
        # 获取可用连接。
        conn = self.connect()
        # 获取当前时间戳，供 create_at/update_at 默认值使用。
        ts_now = now_ts()
        # 计算创建时间戳。
        create_at_value = normalized_record.create_at if normalized_record.create_at > 0 else ts_now
        # 计算更新时间戳。
        update_at_value = normalized_record.update_at if normalized_record.update_at > 0 else ts_now
        sql = f"""
        INSERT INTO {TABLE_NAME} (
            email_account,
            email_pwd,
            email_access_key,
            client_id,
            status,
            first_name,
            last_name,
            vinted_status,
            fb_status,
            fb_fail_num,
            titok_status,
            pwd,
            device,
            msg,
            create_at,
            update_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        # 组装 SQL 参数元组。
        params = (
            # 邮箱账号。
            normalized_record.email_account,
            # 邮箱密码。
            normalized_record.email_pwd,
            # 邮箱授权码。
            normalized_record.email_access_key,
            # 微软 OAuth 应用 client_id。
            normalized_record.client_id,
            # 账号状态。
            int(normalized_record.status),
            # 姓字段。
            normalized_record.first_name,
            # 名字段。
            normalized_record.last_name,
            # vinted 状态。
            int(normalized_record.vinted_status),
            # fb 状态。
            int(normalized_record.fb_status),
            # Facebook 失败累计次数。
            int(normalized_record.fb_fail_num),
            # titok 状态。
            int(normalized_record.titok_status),
            # vinted 密码字段。
            normalized_record.pwd,
            # 设备 ID（仅展示字段）。
            normalized_record.device,
            # 备注字段。
            normalized_record.msg,
            # 创建时间戳。
            int(create_at_value),
            # 更新时间戳。
            int(update_at_value),
        # 参数元组构造完成。
        )
        # 捕获数据库唯一约束异常并转成可读错误。
        try:
            # 使用事务上下文执行写入。
            with conn:
                # 执行新增 SQL。
                cursor = conn.execute(sql, params)
        # 捕获 SQLite 约束异常。
        except sqlite3.IntegrityError as exc:
            # 邮箱唯一键冲突时返回友好提示。
            if self._is_unique_email_error(exc):
                # 抛出业务可读异常。
                raise ValueError("email_account 已存在，请使用不同邮箱账号") from exc
            # 其他约束异常直接继续抛出，避免吞错。
            raise
        # 返回新增记录主键 id。
        return int(cursor.lastrowid)

    # 定义按 id 更新账号方法，返回受影响行数。
    def update_user_by_id(self, user_id: int, record: UserRecord) -> int:
        # 把 user_id 转成整数。
        safe_user_id = int(user_id)
        # 非法 id 直接抛错，避免误更新。
        if safe_user_id <= 0:
            # 抛出明确错误提示。
            raise ValueError("user_id 必须是大于 0 的整数")
        # 先执行修改必填和状态范围校验。
        normalized_record = self.validate_user_record(record)
        # 获取可用连接。
        conn = self.connect()
        # 计算本次更新时间戳。
        update_at_value = normalized_record.update_at if normalized_record.update_at > 0 else now_ts()
        sql = f"""
        UPDATE {TABLE_NAME}
        SET
            email_account = ?,
            email_pwd = ?,
            email_access_key = ?,
            client_id = ?,
            status = ?,
            first_name = ?,
            last_name = ?,
            vinted_status = ?,
            fb_status = ?,
            fb_fail_num = ?,
            titok_status = ?,
            pwd = ?,
            device = ?,
            msg = ?,
            update_at = ?
        WHERE id = ?;
        """
        # 组装 SQL 参数元组。
        params = (
            # 邮箱账号。
            normalized_record.email_account,
            # 邮箱密码。
            normalized_record.email_pwd,
            # 邮箱授权码。
            normalized_record.email_access_key,
            # 微软 OAuth 应用 client_id。
            normalized_record.client_id,
            # 账号状态。
            int(normalized_record.status),
            # 姓字段。
            normalized_record.first_name,
            # 名字段。
            normalized_record.last_name,
            # vinted 状态。
            int(normalized_record.vinted_status),
            # fb 状态。
            int(normalized_record.fb_status),
            # Facebook 失败累计次数。
            int(normalized_record.fb_fail_num),
            # titok 状态。
            int(normalized_record.titok_status),
            # vinted 密码字段。
            normalized_record.pwd,
            # 设备 ID（仅展示字段）。
            normalized_record.device,
            # 备注字段。
            normalized_record.msg,
            # 更新时间戳。
            int(update_at_value),
            # 目标账号 id。
            safe_user_id,
        # 参数元组构造完成。
        )
        # 捕获数据库唯一约束异常并转成可读错误。
        try:
            # 使用事务上下文执行更新。
            with conn:
                # 执行更新 SQL。
                cursor = conn.execute(sql, params)
        # 捕获 SQLite 约束异常。
        except sqlite3.IntegrityError as exc:
            # 邮箱唯一键冲突时返回友好提示。
            if self._is_unique_email_error(exc):
                # 抛出业务可读异常。
                raise ValueError("email_account 已存在，请使用不同邮箱账号") from exc
            # 其他约束异常继续抛出，避免吞错。
            raise
        # 返回更新受影响行数。
        return int(cursor.rowcount)

    # 定义按 id 删除账号方法，返回受影响行数。
    def delete_user_by_id(self, user_id: int) -> int:
        # 把 user_id 转成整数。
        safe_user_id = int(user_id)
        # 非法 id 直接抛错，避免误删。
        if safe_user_id <= 0:
            # 抛出明确错误提示。
            raise ValueError("user_id 必须是大于 0 的整数")
        # 获取可用连接。
        conn = self.connect()
        # 使用事务上下文执行删除。
        with conn:
            # 执行按 id 删除 SQL。
            cursor = conn.execute(
                # 删除指定 id 的账号记录。
                f"DELETE FROM {TABLE_NAME} WHERE id = ?;",
                # 传入要删除的 id 参数。
                (safe_user_id,),
            # SQL 执行结束。
            )
        # 返回删除受影响行数。
        return int(cursor.rowcount)

    # 定义按 id 列表批量删除账号方法，返回受影响行数。
    def delete_users_by_ids(self, user_ids: list[int]) -> int:
        # 初始化去重后的安全 id 列表。
        safe_user_ids: list[int] = []
        # 初始化已见 id 集合，避免重复删除同一条记录。
        seen_user_ids: set[int] = set()
        # 遍历外部传入的 id 列表。
        for user_id in user_ids:
            # 把当前 id 转成整数。
            safe_user_id = int(user_id)
            # 非法 id 直接抛错，避免误删。
            if safe_user_id <= 0:
                # 抛出明确错误提示。
                raise ValueError("user_ids 中存在小于等于 0 的非法账号 ID")
            # 已经收录过的 id 直接跳过，避免重复拼接 SQL 参数。
            if safe_user_id in seen_user_ids:
                # 继续处理下一个 id。
                continue
            # 把当前 id 加入已见集合。
            seen_user_ids.add(safe_user_id)
            # 把当前 id 追加到最终删除列表。
            safe_user_ids.append(safe_user_id)
        # 没有任何合法 id 时直接返回 0。
        if not safe_user_ids:
            # 返回 0 表示本次没有删除任何记录。
            return 0
        # 按实际数量生成 SQL 占位符字符串。
        placeholders = ",".join(["?"] * len(safe_user_ids))
        # 获取可用连接。
        conn = self.connect()
        # 使用事务上下文执行批量删除。
        with conn:
            # 执行按 id 集合批量删除 SQL。
            cursor = conn.execute(
                # 删除命中 id 列表的账号记录。
                f"DELETE FROM {TABLE_NAME} WHERE id IN ({placeholders});",
                # 传入全部安全 id 参数。
                tuple(safe_user_ids),
            # SQL 执行结束。
            )
        # 返回删除受影响行数。
        return int(cursor.rowcount)

    # 定义按 key 查询单个配置项方法。
    def get_config(self, key: str) -> dict[str, Any] | None:
        # 获取可用连接。
        conn = self.connect()
        # 执行配置查询 SQL。
        cursor = conn.execute(
            # 按 key 查询单条配置。
            f'SELECT "key", "val", "desc", update_at FROM {CONFIG_TABLE_NAME} WHERE "key" = ? LIMIT 1;',
            # 传入 key 参数。
            (str(key),),
        # SQL 执行结束。
        )
        # 读取查询结果第一行。
        row = cursor.fetchone()
        # 查询不到配置时返回 None。
        if row is None:
            return None
        # 把 sqlite3.Row 转字典后返回。
        return dict(row)

    # 定义配置列表查询方法。
    def list_configs(self, limit: int = 200, offset: int = 0) -> list[dict[str, Any]]:
        # 获取可用连接。
        conn = self.connect()
        # 对 limit 做下限保护，避免传入无效值。
        safe_limit = max(int(limit), 1)
        # 对 offset 做下限保护，避免负数偏移。
        safe_offset = max(int(offset), 0)
        # 执行配置列表查询 SQL。
        cursor = conn.execute(
            # 按 key 升序查询配置列表。
            f'SELECT "key", "val", "desc", update_at FROM {CONFIG_TABLE_NAME} ORDER BY "key" ASC LIMIT ? OFFSET ?;',
            # 传入限制数量和偏移参数。
            (safe_limit, safe_offset),
        # SQL 执行结束。
        )
        # 把结果集逐行转字典后返回列表。
        return [dict(row) for row in cursor.fetchall()]

    # 定义配置映射查询方法（返回 key->val）。
    def get_config_map(self) -> dict[str, str]:
        # 获取可用连接。
        conn = self.connect()
        # 用事务上下文确保默认配置存在（缺失时自动补齐）。
        with conn:
            # 写入默认配置（仅首次缺失时生效）。
            self._ensure_default_configs(conn)
        # 查询全部配置键值对。
        cursor = conn.execute(
            # 按 key 升序读取配置。
            f'SELECT "key", "val" FROM {CONFIG_TABLE_NAME} ORDER BY "key" ASC;'
        # SQL 执行结束。
        )
        # 读取配置结果集。
        rows = cursor.fetchall()
        # 初始化配置映射字典。
        config_map: dict[str, str] = {}
        # 逐条写入 key->val 映射。
        for row in rows:
            # 强制转成字符串，便于任务层直接消费。
            config_map[str(row["key"])] = str(row["val"])
        # 返回配置映射。
        return config_map

    # 定义配置写入方法（不存在时插入，存在时更新）。
    def set_config(self, key: str, val: str, desc: str | None = None) -> None:
        # 获取可用连接。
        conn = self.connect()
        # 清理 key 文本，避免空白字符干扰。
        key_value = str(key).strip()
        # 空 key 直接判定非法。
        if key_value == "":
            # 抛出明确错误提示。
            raise ValueError("配置 key 不能为空")

        # 标准化并校验配置值。
        normalized_val = self._normalize_config_value(key_value, val)
        # 读取当前配置，便于保留已有描述文案。
        current_row = self.get_config(key_value)
        # 解析入参描述文本。
        desc_value = str(desc).strip() if desc is not None else ""
        # 入参描述为空时，按“当前值 -> 默认值 -> 空字符串”顺序回退。
        if desc_value == "":
            # 当前记录有描述时优先沿用。
            if current_row is not None and str(current_row.get("desc", "")).strip() != "":
                # 使用当前记录描述。
                desc_value = str(current_row.get("desc", ""))
            # 抹机王配置使用固定默认描述。
            elif key_value == MOJIWANG_RUN_NUM_KEY:
                # 采用默认描述文案。
                desc_value = MOJIWANG_RUN_NUM_DESC
            # status=2/3 重试配置使用固定默认描述。
            elif key_value == STATUS_23_RETRY_MAX_KEY:
                # 采用默认描述文案。
                desc_value = STATUS_23_RETRY_MAX_DESC
            # 全局 vinted 密码配置使用固定默认描述。
            elif key_value == VT_PWD_KEY:
                # 采用默认描述文案。
                desc_value = VT_PWD_DESC
            # Vinted 删除控制配置使用固定默认描述。
            elif key_value == VT_DELETE_NUM_KEY:
                # 采用默认描述文案。
                desc_value = VT_DELETE_NUM_DESC
            # Facebook 删除控制配置使用固定默认描述。
            elif key_value == FB_DELETE_NUM_KEY:
                # 采用默认描述文案。
                desc_value = FB_DELETE_NUM_DESC
            # 设置页 Facebook 账号清理控制配置使用固定默认描述。
            elif key_value == SETTING_FB_DEL_NUM_KEY:
                # 采用默认描述文案。
                desc_value = SETTING_FB_DEL_NUM_DESC
            # 代理开始位置配置使用固定默认描述。
            elif key_value == PROXYIP_START_NUM_KEY:
                # 采用默认描述文案。
                desc_value = PROXYIP_START_NUM_DESC
            # 代理结束位置配置使用固定默认描述。
            elif key_value == PROXYIP_END_NUM_KEY:
                # 采用默认描述文案。
                desc_value = PROXYIP_END_NUM_DESC

        # 生成本次写入更新时间戳。
        update_time = now_ts()
        # 使用事务上下文执行写入，保证原子性。
        with conn:
            # 执行 UPSERT 写入配置 SQL。
            conn.execute(
                f"""
                INSERT INTO {CONFIG_TABLE_NAME} ("key", "val", "desc", update_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT("key") DO UPDATE SET
                    "val" = excluded."val",
                    "desc" = excluded."desc",
                    update_at = excluded.update_at;
                """,
                # UPSERT 参数。
                (key_value, normalized_val, desc_value, int(update_time)),
            # SQL 执行结束。
            )

    # 定义按邮箱更新状态字段（可选更新 fb_status、vinted_status、备注和失败累计次数）方法。
    def update_status(
        self,
        email_account: str,
        status: int,
        msg: str | None = None,
        fb_status: int | None = None,
        vinted_status: int | None = None,
        increment_fb_fail_num: bool = False,
    ) -> int:
        # 获取可用连接。
        conn = self.connect()
        # 标准化邮箱参数，避免空白字符导致命中失败。
        safe_email_account = str(email_account).strip()
        # 邮箱为空时直接抛错，避免误更新整表。
        if safe_email_account == "":
            # 抛出可读错误提示。
            raise ValueError("email_account 不能为空")
        # 生成本次更新时间戳。
        update_time = now_ts()
        # 预处理备注文本参数（None 表示不更新 msg 字段）。
        safe_msg = None if msg is None else str(msg)
        # 标准化“是否累加 Facebook 失败次数”参数。
        should_increment_fb_fail_num = bool(increment_fb_fail_num)
        # 初始化更新子句列表。
        set_parts: list[str] = []
        # 初始化 SQL 参数列表。
        params: list[Any] = []
        # 追加账号状态更新子句。
        set_parts.append("status = ?")
        # 追加账号状态参数。
        params.append(int(status))
        # 需要更新 fb_status 时追加对应 SQL 子句。
        if fb_status is not None:
            # 追加 Facebook 状态字段更新子句。
            set_parts.append("fb_status = ?")
            # 追加 Facebook 状态参数。
            params.append(int(fb_status))
        # 需要更新 vinted_status 时追加对应 SQL 子句。
        if vinted_status is not None:
            # 追加 Vinted 状态字段更新子句。
            set_parts.append("vinted_status = ?")
            # 追加 Vinted 状态参数。
            params.append(int(vinted_status))
        # 需要更新备注时追加对应 SQL 子句。
        if safe_msg is not None:
            # 追加备注字段更新子句。
            set_parts.append("msg = ?")
            # 追加备注字段参数。
            params.append(safe_msg)
        # 需要累加失败次数时追加原子自增子句。
        if should_increment_fb_fail_num:
            # 使用数据库原子自增，避免并发下先查后改导致覆盖。
            set_parts.append("fb_fail_num = fb_fail_num + 1")
        # 无论何种分支都追加更新时间字段。
        set_parts.append("update_at = ?")
        # 追加更新时间参数。
        params.append(int(update_time))
        # 最后追加 where 条件参数。
        params.append(safe_email_account)
        # 按当前子句动态拼接 UPDATE SQL。
        sql = f"UPDATE {TABLE_NAME} SET {', '.join(set_parts)} WHERE email_account = ?;"
        # 使用事务上下文执行更新。
        with conn:
            # 执行动态拼接后的更新 SQL。
            cursor = conn.execute(
                # 使用动态 SQL 支持备注、fb_status、vinted_status、失败次数累加的任意组合。
                sql,
                # 传入与动态 SQL 对应的参数列表。
                tuple(params),
            # SQL 执行结束。
            )
        # 返回受影响行数，便于上层判断是否更新成功。
        return int(cursor.rowcount)

    # 定义“统计可恢复账号总数”方法。
    def count_retryable_problem_users(self, max_fb_fail_num: int = 3) -> int:
        # 获取可用连接。
        conn = self.connect()
        # 对失败次数阈值做下限保护，避免传入负数导致条件失真。
        safe_max_fb_fail_num = max(int(max_fb_fail_num), 0)
        # 执行“可恢复账号数”统计 SQL。
        cursor = conn.execute(
            f"""
            SELECT COUNT(1) AS total
            FROM {TABLE_NAME}
            WHERE
                status = 3
                AND fb_fail_num < ?
                AND fb_status != 1;
            """,
            # 传入失败次数阈值参数。
            (int(safe_max_fb_fail_num),),
        # SQL 执行结束。
        )
        # 读取统计结果首行。
        row = cursor.fetchone()
        # 理论上不会为空，这里做防御性回退。
        if row is None:
            return 0
        # 返回可恢复账号总数。
        return int(row["total"])

    # 定义“一键恢复可重试账号问题记录”方法。
    def reset_retryable_problem_users(self, max_fb_fail_num: int = 3) -> int:
        # 获取可用连接。
        conn = self.connect()
        # 对失败次数阈值做下限保护，避免传入负数导致全表命中。
        safe_max_fb_fail_num = max(int(max_fb_fail_num), 0)
        # 生成本次批量更新时间戳。
        update_time = now_ts()
        # 使用事务上下文执行批量更新，保证状态和 device 同步切换。
        with conn:
            # 执行批量恢复 SQL。
            cursor = conn.execute(
                f"""
                UPDATE {TABLE_NAME}
                SET
                    status = 0,
                    device = '',
                    update_at = ?
                WHERE
                    status = 3
                    AND fb_fail_num < ?
                    AND fb_status != 1;
                """,
                # 传入更新时间和失败次数阈值。
                (int(update_time), int(safe_max_fb_fail_num)),
            # SQL 执行结束。
            )
        # 返回本次批量恢复影响行数。
        return int(cursor.rowcount)
