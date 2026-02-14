from __future__ import annotations  # 启用延迟注解，避免类型注解在运行时的前向引用问题。

import os  # 导入 os 模块，用于读取系统环境变量和系统类型。
import sqlite3  # 导入 sqlite3 模块，用于操作本地 SQLite 数据库文件。
import sys  # 导入 sys 模块，用于识别当前运行平台（darwin/windows/linux 等）。
import time  # 导入 time 模块，用于生成秒级时间戳。
from dataclasses import dataclass, replace  # 导入 dataclass/replace，方便定义并复制用户记录结构。
from pathlib import Path  # 导入 Path，用于跨平台路径拼接和目录创建。
from typing import Any  # 导入 Any 类型，便于声明通用字典值类型。

DEFAULT_APP_DIR_NAME = "vinted_android"  # 定义默认应用配置目录名称，保持与你的 Go 逻辑一致。
DEFAULT_DB_FILENAME = "user.db"  # 定义默认数据库文件名为 user.db。
TABLE_NAME = "t_user"  # 定义用户表名常量，统一后续 SQL 语句的表名引用。
CONFIG_TABLE_NAME = "t_config"  # 定义全局配置表名常量，统一后续 SQL 语句引用。
MOJIWANG_RUN_NUM_KEY = "mojiwang_run_num"  # 定义抹机王配置 key 常量。
MOJIWANG_RUN_NUM_DESC = "抹机玩抹机次数: 1 到 100 填写值"  # 定义抹机王配置描述文案常量。
MOJIWANG_RUN_NUM_DEFAULT = "3"  # 定义抹机王默认轮次为 3（若配置不存在则自动写入）。
STATUS_23_RETRY_MAX_KEY = "status_23_retry_max_num"  # 定义账号 status=2/3 场景的最大重试次数配置 key 常量。
STATUS_23_RETRY_MAX_DESC = "账号 status=2/3 时同账号最大重试次数: 0 到 5 填写值"  # 定义状态重试次数配置描述文案常量。
STATUS_23_RETRY_MAX_DEFAULT = "0"  # 定义状态重试默认次数为 0（表示不重试）。
STATUS_23_RETRY_MIN = 0  # 定义状态重试次数最小值（0=不重试）。
STATUS_23_RETRY_MAX = 5  # 定义状态重试次数最大值（5=最多重试 5 次）。
REGISTER_STATUS_MIN = 0  # 定义注册状态最小值（0=未注册）。
REGISTER_STATUS_MAX = 2  # 定义注册状态最大值（2=失败）。
ACCOUNT_STATUS_MIN = 0  # 定义账号状态最小值（0=未使用）。
ACCOUNT_STATUS_MAX = 3  # 定义账号状态最大值（3=账号问题）。


def now_ts() -> int:  # 定义当前时间戳方法，返回秒级 int 时间戳。
    return int(time.time())  # 取当前 Unix 秒级时间戳并转成 int 返回。


def get_user_config_dir() -> Path:  # 定义跨平台用户配置目录解析方法，严格对齐 Go 的 os.UserConfigDir 语义。
    platform_name = sys.platform.lower()  # 读取当前平台标识并转小写，便于统一判断分支。
    if os.name == "nt":  # 如果当前是 Windows 系统（对应 Go 的 windows 分支）。
        app_data = (os.environ.get("APPDATA") or "").strip()  # 读取 Windows 的 APPDATA 环境变量。
        if app_data == "":  # 如果 APPDATA 没定义或为空。
            raise EnvironmentError("%AppData% is not defined")  # 按 Go 语义抛错，不做静默回退。
        return Path(app_data)  # 返回 APPDATA 目录作为用户配置目录。
    if platform_name in {"darwin", "ios"}:  # 如果当前是 macOS 或 iOS（对应 Go 的 darwin/ios 分支）。
        home_dir = (os.environ.get("HOME") or "").strip()  # 读取 HOME 环境变量。
        if home_dir == "":  # 如果 HOME 没定义或为空。
            raise EnvironmentError("$HOME is not defined")  # 按 Go 语义抛错。
        return Path(home_dir) / "Library" / "Application Support"  # 返回 macOS/iOS 配置目录路径。
    if platform_name == "plan9":  # 如果当前是 plan9 系统（对应 Go 的 plan9 分支）。
        home_dir = (os.environ.get("home") or "").strip()  # 按 Go 行为读取小写 home 环境变量。
        if home_dir == "":  # 如果 home 没定义或为空。
            raise EnvironmentError("$home is not defined")  # 按 Go 语义抛错。
        return Path(home_dir) / "lib"  # 返回 plan9 的配置目录路径。
    xdg_config_home = (os.environ.get("XDG_CONFIG_HOME") or "").strip()  # Unix 分支优先读取 XDG_CONFIG_HOME。
    if xdg_config_home == "":  # 如果 XDG_CONFIG_HOME 没定义或为空。
        home_dir = (os.environ.get("HOME") or "").strip()  # 回退读取 HOME 环境变量。
        if home_dir == "":  # 如果 HOME 也没定义或为空。
            raise EnvironmentError("neither $XDG_CONFIG_HOME nor $HOME are defined")  # 按 Go 语义抛错。
        return Path(home_dir) / ".config"  # 返回 HOME/.config 作为配置目录。
    xdg_path = Path(xdg_config_home)  # 把 XDG_CONFIG_HOME 转成 Path 对象，便于做绝对路径校验。
    if not xdg_path.is_absolute():  # 如果 XDG_CONFIG_HOME 是相对路径。
        raise EnvironmentError("path in $XDG_CONFIG_HOME is relative")  # 按 Go 语义抛错。
    return xdg_path  # 返回合法的绝对配置目录路径。


def resolve_user_db_path(  # 定义数据库路径解析方法，返回最终 user.db 文件路径。
    app_name: str = DEFAULT_APP_DIR_NAME,  # 声明应用目录名参数，默认 vinted_android。
    db_filename: str = DEFAULT_DB_FILENAME,  # 声明数据库文件名参数，默认 user.db。
) -> Path:  # 返回值是 Path 对象。
    config_dir = get_user_config_dir()  # 先获取跨平台用户配置目录。
    app_dir = config_dir / app_name  # 在配置目录下拼出业务应用目录。
    app_dir.mkdir(parents=True, exist_ok=True)  # 自动创建目录（不存在时创建，存在时忽略）。
    return app_dir / db_filename  # 返回最终数据库文件完整路径。


@dataclass(slots=True)  # 使用 dataclass+slots 定义轻量用户记录结构，减少样板代码和内存开销。
class UserRecord:  # 定义 t_user 表对应的业务数据结构。
    email_account: str  # 邮箱账号，业务上要求唯一。
    email_pwd: str = ""  # 邮箱密码字段，默认空字符串。
    email_access_key: str = ""  # 邮箱 access_key 字段，默认空字符串。
    client_id: str = ""  # 微软 OAuth 应用 client_id 字段，新增必填。
    status: int = 0  # 任务状态字段，默认 0（1=正在使用，2=已使用过）。
    first_name: str = ""  # 名字段，默认空字符串。
    last_name: str = ""  # 姓字段，默认空字符串。
    vinted_status: int = 0  # vinted 状态字段，默认 0（1=成功，2=失败，3=成功但封号）。
    fb_status: int = 0  # Facebook 状态字段，默认 0（0=未注册，1=成功，2=失败）。
    titok_status: int = 0  # titok 状态字段，默认 0（1=成功）。
    pwd: str = ""  # 业务密码字段，默认空字符串。
    device: str = ""  # 设备 ID 字段，仅用于列表展示，默认空字符串。
    msg: str = ""  # 备注说明字段，默认空字符串。
    create_at: int = 0  # 创建时间戳字段，默认 0（入库时会自动补当前时间）。
    update_at: int = 0  # 更新时间戳字段，默认 0（入库/更新时会自动补当前时间）。


class UserDB:  # 定义数据库封装类，统一管理连接、建表和常用读写方法。
    def __init__(  # 定义初始化方法，支持自定义数据库路径或默认路径。
        self,  # 当前实例自身。
        db_path: str | os.PathLike[str] | None = None,  # 可选数据库路径，未传时自动走默认路径。
        app_name: str = DEFAULT_APP_DIR_NAME,  # 可选应用目录名，默认 vinted_android。
        db_filename: str = DEFAULT_DB_FILENAME,  # 可选数据库文件名，默认 user.db。
    ) -> None:  # 初始化方法不返回值。
        if db_path is None:  # 如果调用方没有传入数据库路径。
            self.db_path = resolve_user_db_path(app_name=app_name, db_filename=db_filename)  # 按默认规则解析路径。
        else:  # 如果调用方显式传入数据库路径。
            self.db_path = Path(db_path)  # 把传入路径统一转为 Path 对象。
        self._conn: sqlite3.Connection | None = None  # 初始化连接对象缓存，首次使用时再创建连接。

    @property  # 把 path 暴露成只读属性，调用更直观。
    def path(self) -> Path:  # 定义数据库文件路径属性方法。
        return self.db_path  # 返回数据库文件路径。

    def connect(self) -> sqlite3.Connection:  # 定义连接方法，按需创建并复用 SQLite 连接。
        if self._conn is not None:  # 如果连接已创建。
            return self._conn  # 直接返回已有连接，避免重复打开文件。
        self.db_path.parent.mkdir(parents=True, exist_ok=True)  # 再次确保父目录存在，防止路径目录缺失。
        self._conn = sqlite3.connect(str(self.db_path))  # 创建 SQLite 连接并绑定到当前数据库文件。
        self._conn.row_factory = sqlite3.Row  # 设置行工厂为 Row，便于按列名读取数据。
        self._conn.execute("PRAGMA busy_timeout=5000;")  # 设置锁等待超时 5 秒，降低多进程并发写时的锁冲突报错概率。
        self._conn.execute("PRAGMA journal_mode=WAL;")  # 开启 WAL 模式，提升并发读写稳定性。
        self._conn.execute("PRAGMA synchronous=NORMAL;")  # 同步级别用 NORMAL，兼顾性能与可靠性。
        self._conn.execute("PRAGMA foreign_keys=ON;")  # 打开外键开关，保持行为一致性（即使当前表未用外键）。
        self.ensure_schema()  # 连接创建后立即确保表结构已存在。
        return self._conn  # 返回可用连接对象。

    def close(self) -> None:  # 定义关闭连接方法，便于脚本退出前主动释放资源。
        if self._conn is None:  # 如果当前没有连接。
            return  # 直接返回，不做任何操作。
        self._conn.close()  # 关闭 SQLite 连接。
        self._conn = None  # 重置连接缓存状态，避免误用已关闭连接。

    def ensure_schema(self) -> None:  # 定义建表方法，若表不存在则自动创建。
        conn = self.connect()  # 获取可用连接（首次会自动创建）。
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
            titok_status INTEGER NOT NULL DEFAULT 0 CHECK (titok_status >= 0),
            pwd TEXT NOT NULL DEFAULT '',
            device TEXT NOT NULL DEFAULT '',
            msg TEXT NOT NULL DEFAULT '',
            create_at INTEGER NOT NULL DEFAULT 0,
            update_at INTEGER NOT NULL DEFAULT 0
        );
        """  # 组装建表 SQL（SQL 字符串内部不放 Python 注释，避免 SQLite 解析错误）。
        create_config_table_sql = f"""
        CREATE TABLE IF NOT EXISTS {CONFIG_TABLE_NAME} (
            "key" TEXT PRIMARY KEY,
            "val" TEXT NOT NULL DEFAULT '',
            "desc" TEXT NOT NULL DEFAULT '',
            update_at INTEGER NOT NULL DEFAULT 0
        );
        """  # 组装配置表 SQL（key/val/desc 结构）。
        with conn:  # 使用事务上下文执行建表和索引创建，保证原子性。
            conn.execute(create_table_sql)  # 执行建表 SQL。
            self._ensure_optional_columns(conn)  # 兼容旧表结构：缺字段时自动补齐（例如 fb_status）。
            conn.execute(create_config_table_sql)  # 执行配置表建表 SQL。
            self._ensure_default_configs(conn)  # 确保默认配置项存在（例如 mojiwang_run_num）。
            conn.execute(  # 创建状态索引，便于按 status 批量筛选任务数据。
                f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_status ON {TABLE_NAME}(status);"
            )  # 索引 SQL 执行结束。
            conn.execute(  # 创建 Facebook 状态索引，便于按 fb_status 查询。
                f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_fb_status ON {TABLE_NAME}(fb_status);"
            )  # 索引 SQL 执行结束。
            conn.execute(  # 创建设备字段索引，便于按 device 查询“当前占用账号”。
                f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_device ON {TABLE_NAME}(device);"
            )  # 索引 SQL 执行结束。
            conn.execute(  # 创建更新时间索引，便于按更新时间排序或查询。
                f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_update_at ON {TABLE_NAME}(update_at);"
            )  # 索引 SQL 执行结束。
            conn.execute(  # 创建配置更新时间索引，便于按更新时间查询配置变更。
                f"CREATE INDEX IF NOT EXISTS idx_{CONFIG_TABLE_NAME}_update_at ON {CONFIG_TABLE_NAME}(update_at);"
            )  # 索引 SQL 执行结束。

    def _ensure_optional_columns(self, conn: sqlite3.Connection) -> None:  # 定义“可选列补齐”方法，兼容旧版本表结构。
        cursor = conn.execute(f"PRAGMA table_info({TABLE_NAME});")  # 读取当前表结构字段信息。
        exists_columns = {str(row["name"]) for row in cursor.fetchall()}  # 把字段名整理为集合，便于判断缺失列。
        if "fb_status" not in exists_columns:  # 旧表缺少 fb_status 列时执行补齐。
            conn.execute(  # 执行 ALTER TABLE 增加 fb_status 字段，并设置默认值和非空约束。
                f"ALTER TABLE {TABLE_NAME} ADD COLUMN fb_status INTEGER NOT NULL DEFAULT 0;"
            )  # SQL 执行结束。
        if "client_id" not in exists_columns:  # 旧表缺少 client_id 列时执行补齐。
            conn.execute(  # 执行 ALTER TABLE 增加 client_id 字段，并设置默认值和非空约束。
                f"ALTER TABLE {TABLE_NAME} ADD COLUMN client_id TEXT NOT NULL DEFAULT '';"
            )  # SQL 执行结束。
        if "device" not in exists_columns:  # 旧表缺少 device 列时执行补齐。
            conn.execute(  # 执行 ALTER TABLE 增加 device 字段，并设置默认值和非空约束。
                f"ALTER TABLE {TABLE_NAME} ADD COLUMN device TEXT NOT NULL DEFAULT '';"
            )  # SQL 执行结束。

    def _ensure_default_configs(self, conn: sqlite3.Connection) -> None:  # 定义默认配置补齐方法，确保新库可直接使用。
        default_val = self._normalize_config_value(MOJIWANG_RUN_NUM_KEY, MOJIWANG_RUN_NUM_DEFAULT)  # 计算并校验默认配置值。
        conn.execute(  # 插入默认配置（若 key 已存在则忽略）。
            f"""
            INSERT OR IGNORE INTO {CONFIG_TABLE_NAME} ("key", "val", "desc", update_at)
            VALUES (?, ?, ?, ?);
            """,  # 默认配置 SQL。
            (MOJIWANG_RUN_NUM_KEY, default_val, MOJIWANG_RUN_NUM_DESC, now_ts()),  # 默认配置参数。
        )  # SQL 执行结束。
        retry_default_val = self._normalize_config_value(STATUS_23_RETRY_MAX_KEY, STATUS_23_RETRY_MAX_DEFAULT)  # 计算并校验 status=2/3 重试默认值。
        conn.execute(  # 插入 status=2/3 最大重试次数默认配置（若 key 已存在则忽略）。
            f"""
            INSERT OR IGNORE INTO {CONFIG_TABLE_NAME} ("key", "val", "desc", update_at)
            VALUES (?, ?, ?, ?);
            """,  # 默认配置 SQL。
            (STATUS_23_RETRY_MAX_KEY, retry_default_val, STATUS_23_RETRY_MAX_DESC, now_ts()),  # 默认配置参数。
        )  # SQL 执行结束。

    def _normalize_config_value(self, key: str, val: str) -> str:  # 定义配置值标准化方法，并做 key 级别校验。
        raw_value = str(val).strip()  # 把配置值转字符串并清理空白字符。
        if key == MOJIWANG_RUN_NUM_KEY:  # 针对抹机王次数配置执行范围校验。
            if raw_value == "":  # 空值直接判定为非法。
                raise ValueError("mojiwang_run_num 不能为空，需填写 1 到 100 的整数")  # 抛出明确错误提示。
            try:  # 尝试把输入值解析为整数。
                num_value = int(raw_value)  # 转成整数做范围检查。
            except ValueError as exc:  # 非整数输入直接报错。
                raise ValueError("mojiwang_run_num 必须是整数，范围 1 到 100") from exc  # 抛出明确错误提示。
            if not 1 <= num_value <= 100:  # 范围不在 1~100 时判定为非法。
                raise ValueError("mojiwang_run_num 超出范围，必须在 1 到 100 之间")  # 抛出明确错误提示。
            return str(num_value)  # 返回标准化后的整数文本。
        if key == STATUS_23_RETRY_MAX_KEY:  # 针对 status=2/3 重试次数配置执行范围校验。
            if raw_value == "":  # 空值直接判定为非法。
                raise ValueError("status_23_retry_max_num 不能为空，需填写 0 到 5 的整数")  # 抛出明确错误提示。
            try:  # 尝试把输入值解析为整数。
                retry_value = int(raw_value)  # 转成整数做范围检查。
            except ValueError as exc:  # 非整数输入直接报错。
                raise ValueError("status_23_retry_max_num 必须是整数，范围 0 到 5") from exc  # 抛出明确错误提示。
            if not STATUS_23_RETRY_MIN <= retry_value <= STATUS_23_RETRY_MAX:  # 范围不在 0~5 时判定为非法。
                raise ValueError("status_23_retry_max_num 超出范围，必须在 0 到 5 之间")  # 抛出范围错误提示。
            return str(retry_value)  # 返回标准化后的整数文本。
        return raw_value  # 其他 key 当前不做额外规则，直接返回清理后文本。

    def _normalize_required_text(self, field_name: str, raw_value: str) -> str:  # 定义必填文本字段标准化方法。
        normalized_value = str(raw_value).strip()  # 把输入值转字符串并清理前后空白。
        if normalized_value == "":  # 空字符串直接判定为非法。
            raise ValueError(f"{field_name} 不能为空")  # 抛出带字段名的明确错误提示。
        return normalized_value  # 返回标准化后的非空文本。

    def _normalize_optional_text(self, raw_value: str) -> str:  # 定义可选文本字段标准化方法（允许空字符串）。
        return str(raw_value or "").strip()  # 把输入值转字符串并清理前后空白后返回。

    def _normalize_int_range(self, field_name: str, raw_value: int | str, min_value: int, max_value: int) -> int:  # 定义整数范围校验方法。
        try:  # 尝试把输入值转成整数。
            int_value = int(raw_value)  # 把原始值转成 int。
        except Exception as exc:  # 转换失败时判定为非法整数。
            raise ValueError(f"{field_name} 必须是整数") from exc  # 抛出明确错误提示并保留原始异常链。
        if int_value < int(min_value) or int_value > int(max_value):  # 值超出范围时判定为非法输入。
            raise ValueError(f"{field_name} 超出范围，必须在 {int(min_value)} 到 {int(max_value)} 之间")  # 抛出范围错误提示。
        return int_value  # 返回通过校验的整数值。

    def _is_unique_email_error(self, exc: sqlite3.IntegrityError) -> bool:  # 定义唯一键冲突识别方法（email_account）。
        message = str(exc).lower()  # 读取数据库异常文本并转小写，便于统一匹配。
        return "unique constraint failed" in message and f"{TABLE_NAME}.email_account" in message  # 判断是否为邮箱唯一约束冲突。

    def validate_user_record(self, record: UserRecord) -> UserRecord:  # 定义账号记录校验方法（新增/修改共用）。
        if not isinstance(record, UserRecord):  # 非 UserRecord 输入直接判定为非法参数。
            raise TypeError("record 必须是 UserRecord 类型")  # 抛出类型错误，避免后续字段访问异常。

        normalized_email_account = self._normalize_required_text("email_account", record.email_account)  # 校验并标准化邮箱账号（必填）。
        normalized_email_pwd = self._normalize_required_text("email_pwd", record.email_pwd)  # 校验并标准化邮箱密码（必填）。
        normalized_email_access_key = self._normalize_required_text("email_access_key", record.email_access_key)  # 校验并标准化邮箱授权码（必填）。
        normalized_client_id = self._normalize_required_text("client_id", record.client_id)  # 校验并标准化 client_id（必填）。
        normalized_first_name = self._normalize_required_text("first_name", record.first_name)  # 校验并标准化姓（必填）。
        normalized_last_name = self._normalize_required_text("last_name", record.last_name)  # 校验并标准化名（必填）。
        normalized_pwd = self._normalize_required_text("pwd", record.pwd)  # 校验并标准化业务密码（必填）。
        normalized_status = self._normalize_int_range("status", record.status, ACCOUNT_STATUS_MIN, ACCOUNT_STATUS_MAX)  # 校验并标准化账号状态（0~3）。
        normalized_vinted_status = self._normalize_int_range("vinted_status", record.vinted_status, REGISTER_STATUS_MIN, REGISTER_STATUS_MAX)  # 校验并标准化 vt 状态（0~2）。
        normalized_fb_status = self._normalize_int_range("fb_status", record.fb_status, REGISTER_STATUS_MIN, REGISTER_STATUS_MAX)  # 校验并标准化 fb 状态（0~2）。
        normalized_titok_status = self._normalize_int_range("titok_status", record.titok_status, REGISTER_STATUS_MIN, REGISTER_STATUS_MAX)  # 校验并标准化 tt 状态（0~2）。
        normalized_device = str(record.device or "").strip()  # 标准化设备字段（非必填，允许为空）。
        normalized_msg = str(record.msg or "").strip()  # 标准化备注字段（非必填，允许为空）。

        return replace(  # 返回标准化后的新记录对象，避免直接修改原始入参对象。
            record,  # 基于原始记录复制新对象。
            email_account=normalized_email_account,  # 写回标准化邮箱账号。
            email_pwd=normalized_email_pwd,  # 写回标准化邮箱密码。
            email_access_key=normalized_email_access_key,  # 写回标准化邮箱授权码。
            client_id=normalized_client_id,  # 写回标准化 client_id。
            first_name=normalized_first_name,  # 写回标准化姓。
            last_name=normalized_last_name,  # 写回标准化名。
            pwd=normalized_pwd,  # 写回标准化业务密码。
            status=normalized_status,  # 写回标准化账号状态。
            vinted_status=normalized_vinted_status,  # 写回标准化 vt 状态。
            fb_status=normalized_fb_status,  # 写回标准化 fb 状态。
            titok_status=normalized_titok_status,  # 写回标准化 tt 状态。
            device=normalized_device,  # 写回标准化设备字段。
            msg=normalized_msg,  # 写回标准化备注文本。
        )  # 返回值构造完成。

    def upsert_user(self, record: UserRecord) -> None:  # 定义插入或更新方法（以 email_account 唯一键冲突处理）。
        conn = self.connect()  # 获取可用连接。
        ts_now = now_ts()  # 取当前时间戳用于默认 create_at/update_at。
        create_at_value = record.create_at if record.create_at > 0 else ts_now  # 如果外部没传 create_at，则自动用当前时间戳。
        update_at_value = record.update_at if record.update_at > 0 else ts_now  # 如果外部没传 update_at，则自动用当前时间戳。
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
            titok_status,
            pwd,
            device,
            msg,
            create_at,
            update_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(email_account) DO UPDATE SET
            email_pwd = excluded.email_pwd,
            email_access_key = excluded.email_access_key,
            client_id = excluded.client_id,
            status = excluded.status,
            first_name = excluded.first_name,
            last_name = excluded.last_name,
            vinted_status = excluded.vinted_status,
            fb_status = excluded.fb_status,
            titok_status = excluded.titok_status,
            pwd = excluded.pwd,
            device = excluded.device,
            msg = excluded.msg,
            update_at = excluded.update_at;
        """  # 组装 UPSERT SQL（SQL 字符串内部不放 Python 注释，避免 SQLite 解析错误）。
        params = (  # 组装 SQL 参数元组，按占位符顺序传入。
            record.email_account,  # 传入邮箱账号。
            record.email_pwd,  # 传入邮箱密码。
            record.email_access_key,  # 传入邮箱 access_key。
            record.client_id,  # 传入微软 OAuth 应用 client_id。
            int(record.status),  # 传入状态并强转为 int。
            record.first_name,  # 传入名字段。
            record.last_name,  # 传入姓字段。
            int(record.vinted_status),  # 传入 vinted 状态并强转为 int。
            int(record.fb_status),  # 传入 Facebook 状态并强转为 int。
            int(record.titok_status),  # 传入 titok 状态并强转为 int。
            record.pwd,  # 传入业务密码。
            record.device,  # 传入设备 ID（仅展示字段）。
            record.msg,  # 传入备注说明。
            int(create_at_value),  # 传入创建时间戳。
            int(update_at_value),  # 传入更新时间戳。
        )  # 参数元组定义结束。
        with conn:  # 使用事务上下文执行写入，自动提交。
            conn.execute(sql, params)  # 执行 UPSERT 写入操作。

    def get_user_by_email(self, email_account: str) -> dict[str, Any] | None:  # 定义按邮箱查询单条记录方法。
        conn = self.connect()  # 获取可用连接。
        cursor = conn.execute(  # 执行查询语句并返回游标。
            f"SELECT * FROM {TABLE_NAME} WHERE email_account = ? LIMIT 1;",  # 按唯一邮箱查询一条记录。
            (email_account,),  # 传入邮箱参数。
        )  # 查询执行结束。
        row = cursor.fetchone()  # 读取查询结果第一行。
        if row is None:  # 如果查询不到记录。
            return None  # 返回 None 表示不存在。
        return dict(row)  # 把 sqlite3.Row 转为普通字典返回。

    def list_users_by_status(self, status: int, limit: int = 100) -> list[dict[str, Any]]:  # 定义按状态批量查询方法。
        conn = self.connect()  # 获取可用连接。
        safe_limit = max(int(limit), 1)  # 对 limit 做下限保护，避免传入 0 或负数。
        cursor = conn.execute(  # 执行按状态查询 SQL。
            f"SELECT * FROM {TABLE_NAME} WHERE status = ? ORDER BY id ASC LIMIT ?;",  # 按 status 查询并按 id 升序返回。
            (int(status), safe_limit),  # 传入状态值和限制数量。
        )  # 查询执行结束。
        return [dict(row) for row in cursor.fetchall()]  # 把结果集逐行转字典后返回列表。

    def list_users(self, limit: int = 300, offset: int = 0) -> list[dict[str, Any]]:  # 定义账号列表查询方法（账号列表 Tab 使用）。
        conn = self.connect()  # 获取可用连接。
        safe_limit = max(int(limit), 1)  # 对 limit 做下限保护，避免传入无效值。
        safe_offset = max(int(offset), 0)  # 对 offset 做下限保护，避免负数偏移。
        cursor = conn.execute(  # 执行列表查询 SQL。
            f"SELECT * FROM {TABLE_NAME} ORDER BY id DESC LIMIT ? OFFSET ?;",  # 按 id 倒序查询，优先展示最新账号。
            (safe_limit, safe_offset),  # 传入限制数量和偏移量参数。
        )  # SQL 执行结束。
        return [dict(row) for row in cursor.fetchall()]  # 把结果集逐行转字典后返回列表。

    def get_user_by_device(self, device: str) -> dict[str, Any] | None:  # 定义按设备 serial 查询当前绑定账号方法。
        conn = self.connect()  # 获取可用连接。
        safe_device = self._normalize_optional_text(device)  # 标准化设备 serial 文本。
        if safe_device == "":  # 设备 serial 为空时直接返回空。
            return None
        cursor = conn.execute(  # 执行按 device 查询 SQL。
            f"SELECT * FROM {TABLE_NAME} WHERE device = ? ORDER BY id ASC LIMIT 1;",  # 按设备 serial 取一条绑定账号。
            (safe_device,),  # 传入设备 serial 参数。
        )  # SQL 执行结束。
        row = cursor.fetchone()  # 读取查询结果第一行。
        if row is None:  # 查询不到绑定账号时返回 None。
            return None
        return dict(row)  # 把 sqlite3.Row 转字典后返回。

    def claim_user_for_device(self, device: str) -> dict[str, Any] | None:  # 定义“按设备领取一条可用账号（status=0）”方法（事务加锁防并发冲突）。
        conn = self.connect()  # 获取可用连接。
        safe_device = self._normalize_required_text("device", device)  # 校验并标准化设备 serial。
        ts_now = now_ts()  # 获取当前时间戳，供 update_at 写入。
        try:  # 使用显式事务，确保“查询+更新”原子化。
            conn.execute("BEGIN IMMEDIATE;")  # 申请写锁，避免多个设备并发抢到同一条账号。

            current_row = conn.execute(  # 先检查当前设备是否已占用一条 status=1 的账号。
                f"SELECT * FROM {TABLE_NAME} WHERE device = ? AND status = 1 ORDER BY id ASC LIMIT 1;",  # 查询本设备已占用账号。
                (safe_device,),  # 传入设备 serial 参数。
            ).fetchone()  # 读取查询结果首行。
            if current_row is not None:  # 已有占用账号时直接复用，避免重复分配。
                conn.commit()  # 提交事务，释放写锁。
                return dict(current_row)  # 返回当前占用账号。

            conn.execute(  # 清理本设备遗留的非运行态绑定（例如 status=2/3 停机后遗留 device）。
                f"UPDATE {TABLE_NAME} SET device = '', update_at = ? WHERE device = ? AND status != 1;",  # 仅清理非 status=1 绑定。
                (int(ts_now), safe_device),  # 传入更新时间和设备 serial。
            )  # SQL 执行结束。

            candidate_row = conn.execute(  # 从可用池里找一条“未使用且未绑定设备”的账号。
                f"""
                SELECT * FROM {TABLE_NAME}
                WHERE status = 0 AND (device = '' OR device IS NULL)
                ORDER BY id ASC
                LIMIT 1;
                """,  # 取最早可用账号，确保分配顺序稳定。
            ).fetchone()  # 读取候选账号。
            if candidate_row is None:  # 没有可用账号时返回空，让 worker 进入等待。
                conn.commit()  # 提交事务，释放写锁。
                return None

            candidate_id = int(candidate_row["id"])  # 读取候选账号主键，后续用于条件更新。
            update_cursor = conn.execute(  # 尝试把候选账号原子更新为“本设备占用中”。
                f"""
                UPDATE {TABLE_NAME}
                SET status = 1, device = ?, update_at = ?
                WHERE id = ? AND status = 0 AND (device = '' OR device IS NULL);
                """,  # 条件更新再次校验，防止异常场景下脏写。
                (safe_device, int(ts_now), candidate_id),  # 传入设备 serial、更新时间和候选 id。
            )  # SQL 执行结束。
            if int(update_cursor.rowcount) <= 0:  # 理论上持锁后不会失败，这里做防御性保护。
                conn.rollback()  # 更新失败时回滚事务，避免半状态。
                return None  # 返回空让上层等待下一轮重试。

            assigned_row = conn.execute(  # 查询更新后的完整账号记录返回给调用方。
                f"SELECT * FROM {TABLE_NAME} WHERE id = ? LIMIT 1;",  # 按 id 查询刚刚分配的账号。
                (candidate_id,),  # 传入候选账号 id。
            ).fetchone()  # 读取分配结果首行。
            conn.commit()  # 提交事务，正式完成本次分配并释放写锁。
            if assigned_row is None:  # 极端防御：如果查不到记录则返回空。
                return None
            return dict(assigned_row)  # 返回分配成功的账号信息。
        except Exception:  # 任意异常都回滚事务，确保数据库状态一致。
            try:
                conn.rollback()  # 回滚未提交事务。
            except Exception:
                pass
            raise  # 把原异常继续抛出给上层处理。

    def release_user_for_device(self, device: str) -> int:  # 定义“按设备释放账号占用”方法（status=1 -> 0，status=2/3 保持不变）。
        conn = self.connect()  # 获取可用连接。
        safe_device = self._normalize_optional_text(device)  # 标准化设备 serial 文本。
        if safe_device == "":  # 设备 serial 为空时无可释放数据。
            return 0
        update_time = now_ts()  # 生成本次释放更新时间戳。
        with conn:  # 使用事务上下文执行释放更新，保证原子性。
            cursor = conn.execute(  # 执行按设备释放 SQL。
                f"""
                UPDATE {TABLE_NAME}
                SET
                    status = CASE WHEN status = 1 THEN 0 ELSE status END,
                    device = '',
                    update_at = ?
                WHERE device = ?;
                """,  # status=1 回收为 0；status=2/3 只清空 device 不改状态。
                (int(update_time), safe_device),  # 传入更新时间和设备 serial。
            )  # SQL 执行结束。
        return int(cursor.rowcount)  # 返回释放影响行数。

    def clear_device_by_user_id(self, user_id: int) -> int:  # 定义“按用户 id 清空 device 绑定（不改 status）”方法。
        safe_user_id = int(user_id)  # 把 user_id 转成整数，统一 SQL 入参类型。
        if safe_user_id <= 0:  # 非法 id 时直接返回 0。
            return 0
        conn = self.connect()  # 获取可用连接。
        update_time = now_ts()  # 生成更新时间戳。
        with conn:  # 使用事务上下文执行更新。
            cursor = conn.execute(  # 执行仅清空 device 的 SQL。
                f"UPDATE {TABLE_NAME} SET device = '', update_at = ? WHERE id = ?;",  # 不改 status，仅释放设备绑定。
                (int(update_time), safe_user_id),  # 传入更新时间和目标用户 id。
            )  # SQL 执行结束。
        return int(cursor.rowcount)  # 返回影响行数。

    def count_users(self) -> int:  # 定义账号总数查询方法，供分页统计使用。
        conn = self.connect()  # 获取可用连接。
        cursor = conn.execute(f"SELECT COUNT(1) AS total FROM {TABLE_NAME};")  # 执行总数统计 SQL。
        row = cursor.fetchone()  # 读取统计结果首行。
        if row is None:  # 理论上不会为空，这里做防御性判断。
            return 0  # 空结果时返回 0。
        return int(row["total"])  # 返回账号总数整数值。

    def list_users_page(self, page: int, page_size: int = 20) -> list[dict[str, Any]]:  # 定义分页查询方法（按 id 倒序）。
        safe_page = max(int(page), 1)  # 对页码做下限保护，至少为第 1 页。
        safe_page_size = max(int(page_size), 1)  # 对每页条数做下限保护，至少 1 条。
        offset = (safe_page - 1) * safe_page_size  # 根据页码和页大小计算偏移量。
        return self.list_users(limit=safe_page_size, offset=offset)  # 复用 list_users 返回当前页数据。

    def _build_user_filters_sql(  # 定义账号筛选 SQL 片段构建方法（供列表与计数复用）。
        self,  # 当前实例自身。
        email_keyword: str = "",  # 邮箱关键字筛选（模糊匹配）。
        status: int | None = None,  # 账号状态筛选（None 表示不过滤）。
        fb_status: int | None = None,  # fb 状态筛选（None 表示不过滤）。
        vinted_status: int | None = None,  # vt 状态筛选（None 表示不过滤）。
        titok_status: int | None = None,  # tt 状态筛选（None 表示不过滤）。
    ) -> tuple[str, list[Any]]:  # 返回 where SQL 片段和参数列表。
        where_parts: list[str] = []  # 初始化 where 子句片段列表。
        args: list[Any] = []  # 初始化 SQL 参数列表。

        email_kw = str(email_keyword).strip()  # 清理邮箱关键字输入。
        if email_kw != "":  # 关键字非空时启用邮箱模糊匹配。
            where_parts.append("email_account LIKE ?")  # 追加邮箱 LIKE 条件。
            args.append(f"%{email_kw}%")  # 追加邮箱模糊匹配参数。
        if status is not None:  # 传入账号状态时追加过滤条件。
            where_parts.append("status = ?")  # 追加 status 精确匹配条件。
            args.append(int(status))  # 追加 status 参数。
        if fb_status is not None:  # 传入 fb 状态时追加过滤条件。
            where_parts.append("fb_status = ?")  # 追加 fb_status 精确匹配条件。
            args.append(int(fb_status))  # 追加 fb_status 参数。
        if vinted_status is not None:  # 传入 vt 状态时追加过滤条件。
            where_parts.append("vinted_status = ?")  # 追加 vinted_status 精确匹配条件。
            args.append(int(vinted_status))  # 追加 vinted_status 参数。
        if titok_status is not None:  # 传入 tt 状态时追加过滤条件。
            where_parts.append("titok_status = ?")  # 追加 titok_status 精确匹配条件。
            args.append(int(titok_status))  # 追加 titok_status 参数。

        if not where_parts:  # 没有任何过滤条件时直接返回空 where。
            return "", args
        return f" WHERE {' AND '.join(where_parts)}", args  # 拼接并返回 where 子句和参数列表。

    def count_users_filtered(  # 定义带筛选条件的账号总数查询方法。
        self,  # 当前实例自身。
        email_keyword: str = "",  # 邮箱关键字筛选。
        status: int | None = None,  # 账号状态筛选。
        fb_status: int | None = None,  # fb 状态筛选。
        vinted_status: int | None = None,  # vt 状态筛选。
        titok_status: int | None = None,  # tt 状态筛选。
    ) -> int:  # 返回筛选后的总条数。
        conn = self.connect()  # 获取可用连接。
        where_sql, args = self._build_user_filters_sql(  # 构建 where 子句和参数。
            email_keyword=email_keyword,  # 传入邮箱关键字筛选参数。
            status=status,  # 传入账号状态筛选参数。
            fb_status=fb_status,  # 传入 fb 状态筛选参数。
            vinted_status=vinted_status,  # 传入 vt 状态筛选参数。
            titok_status=titok_status,  # 传入 tt 状态筛选参数。
        )
        cursor = conn.execute(  # 执行筛选计数 SQL。
            f"SELECT COUNT(1) AS total FROM {TABLE_NAME}{where_sql};",  # 查询筛选后的账号总数。
            tuple(args),  # 传入 where 参数列表。
        )  # SQL 执行结束。
        row = cursor.fetchone()  # 读取统计结果第一行。
        if row is None:  # 理论上不会为空，这里做防御性判断。
            return 0
        return int(row["total"])  # 返回筛选后账号总数。

    def list_users_filtered(  # 定义带筛选条件的账号列表查询方法（按 id 倒序）。
        self,  # 当前实例自身。
        limit: int = 20,  # 查询条数上限。
        offset: int = 0,  # 查询偏移量。
        email_keyword: str = "",  # 邮箱关键字筛选。
        status: int | None = None,  # 账号状态筛选。
        fb_status: int | None = None,  # fb 状态筛选。
        vinted_status: int | None = None,  # vt 状态筛选。
        titok_status: int | None = None,  # tt 状态筛选。
    ) -> list[dict[str, Any]]:  # 返回筛选后的账号列表。
        conn = self.connect()  # 获取可用连接。
        safe_limit = max(int(limit), 1)  # 对 limit 做下限保护，避免传入无效值。
        safe_offset = max(int(offset), 0)  # 对 offset 做下限保护，避免负数偏移。
        where_sql, args = self._build_user_filters_sql(  # 构建 where 子句和参数。
            email_keyword=email_keyword,  # 传入邮箱关键字筛选参数。
            status=status,  # 传入账号状态筛选参数。
            fb_status=fb_status,  # 传入 fb 状态筛选参数。
            vinted_status=vinted_status,  # 传入 vt 状态筛选参数。
            titok_status=titok_status,  # 传入 tt 状态筛选参数。
        )
        cursor = conn.execute(  # 执行带筛选条件的列表查询 SQL。
            f"SELECT * FROM {TABLE_NAME}{where_sql} ORDER BY id DESC LIMIT ? OFFSET ?;",  # 按 id 倒序分页查询筛选结果。
            tuple(args + [safe_limit, safe_offset]),  # 传入 where 参数和分页参数。
        )  # SQL 执行结束。
        return [dict(row) for row in cursor.fetchall()]  # 把结果集逐行转字典后返回列表。

    def list_users_page_filtered(  # 定义带筛选条件的分页查询方法（按 id 倒序）。
        self,  # 当前实例自身。
        page: int,  # 页码（从 1 开始）。
        page_size: int = 20,  # 每页条数。
        email_keyword: str = "",  # 邮箱关键字筛选。
        status: int | None = None,  # 账号状态筛选。
        fb_status: int | None = None,  # fb 状态筛选。
        vinted_status: int | None = None,  # vt 状态筛选。
        titok_status: int | None = None,  # tt 状态筛选。
    ) -> list[dict[str, Any]]:  # 返回筛选后的分页结果。
        safe_page = max(int(page), 1)  # 对页码做下限保护，至少为第 1 页。
        safe_page_size = max(int(page_size), 1)  # 对每页条数做下限保护，至少 1 条。
        offset = (safe_page - 1) * safe_page_size  # 根据页码和页大小计算偏移量。
        return self.list_users_filtered(  # 复用带筛选列表查询方法返回当前页数据。
            limit=safe_page_size,  # 传入分页条数。
            offset=offset,  # 传入分页偏移量。
            email_keyword=email_keyword,  # 传入邮箱关键字筛选参数。
            status=status,  # 传入账号状态筛选参数。
            fb_status=fb_status,  # 传入 fb 状态筛选参数。
            vinted_status=vinted_status,  # 传入 vt 状态筛选参数。
            titok_status=titok_status,  # 传入 tt 状态筛选参数。
        )

    def get_user_by_id(self, user_id: int) -> dict[str, Any] | None:  # 定义按 id 查询单条账号记录方法。
        safe_user_id = int(user_id)  # 把 user_id 转成整数，统一后续 SQL 入参类型。
        if safe_user_id <= 0:  # 非法 id 直接返回 None，避免无意义查询。
            return None
        conn = self.connect()  # 获取可用连接。
        cursor = conn.execute(  # 执行按 id 查询 SQL。
            f"SELECT * FROM {TABLE_NAME} WHERE id = ? LIMIT 1;",  # 按主键 id 查询单条记录。
            (safe_user_id,),  # 传入 id 参数。
        )  # SQL 执行结束。
        row = cursor.fetchone()  # 读取查询结果第一行。
        if row is None:  # 查询不到记录时返回 None。
            return None
        return dict(row)  # 把 sqlite3.Row 转字典后返回。

    def create_user(self, record: UserRecord) -> int:  # 定义新增账号方法，成功返回新记录 id。
        normalized_record = self.validate_user_record(record)  # 先执行新增必填和状态范围校验。
        conn = self.connect()  # 获取可用连接。
        ts_now = now_ts()  # 获取当前时间戳，供 create_at/update_at 默认值使用。
        create_at_value = normalized_record.create_at if normalized_record.create_at > 0 else ts_now  # 计算创建时间戳。
        update_at_value = normalized_record.update_at if normalized_record.update_at > 0 else ts_now  # 计算更新时间戳。
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
            titok_status,
            pwd,
            device,
            msg,
            create_at,
            update_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """  # 组装新增 SQL（仅插入，不做冲突更新）。
        params = (  # 组装 SQL 参数元组。
            normalized_record.email_account,  # 邮箱账号。
            normalized_record.email_pwd,  # 邮箱密码。
            normalized_record.email_access_key,  # 邮箱授权码。
            normalized_record.client_id,  # 微软 OAuth 应用 client_id。
            int(normalized_record.status),  # 账号状态。
            normalized_record.first_name,  # 姓字段。
            normalized_record.last_name,  # 名字段。
            int(normalized_record.vinted_status),  # vinted 状态。
            int(normalized_record.fb_status),  # fb 状态。
            int(normalized_record.titok_status),  # titok 状态。
            normalized_record.pwd,  # vinted 密码字段。
            normalized_record.device,  # 设备 ID（仅展示字段）。
            normalized_record.msg,  # 备注字段。
            int(create_at_value),  # 创建时间戳。
            int(update_at_value),  # 更新时间戳。
        )  # 参数元组构造完成。
        try:  # 捕获数据库唯一约束异常并转成可读错误。
            with conn:  # 使用事务上下文执行写入。
                cursor = conn.execute(sql, params)  # 执行新增 SQL。
        except sqlite3.IntegrityError as exc:  # 捕获 SQLite 约束异常。
            if self._is_unique_email_error(exc):  # 邮箱唯一键冲突时返回友好提示。
                raise ValueError("email_account 已存在，请使用不同邮箱账号") from exc  # 抛出业务可读异常。
            raise  # 其他约束异常直接继续抛出，避免吞错。
        return int(cursor.lastrowid)  # 返回新增记录主键 id。

    def update_user_by_id(self, user_id: int, record: UserRecord) -> int:  # 定义按 id 更新账号方法，返回受影响行数。
        safe_user_id = int(user_id)  # 把 user_id 转成整数。
        if safe_user_id <= 0:  # 非法 id 直接抛错，避免误更新。
            raise ValueError("user_id 必须是大于 0 的整数")  # 抛出明确错误提示。
        normalized_record = self.validate_user_record(record)  # 先执行修改必填和状态范围校验。
        conn = self.connect()  # 获取可用连接。
        update_at_value = normalized_record.update_at if normalized_record.update_at > 0 else now_ts()  # 计算本次更新时间戳。
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
            titok_status = ?,
            pwd = ?,
            device = ?,
            msg = ?,
            update_at = ?
        WHERE id = ?;
        """  # 组装按 id 更新 SQL。
        params = (  # 组装 SQL 参数元组。
            normalized_record.email_account,  # 邮箱账号。
            normalized_record.email_pwd,  # 邮箱密码。
            normalized_record.email_access_key,  # 邮箱授权码。
            normalized_record.client_id,  # 微软 OAuth 应用 client_id。
            int(normalized_record.status),  # 账号状态。
            normalized_record.first_name,  # 姓字段。
            normalized_record.last_name,  # 名字段。
            int(normalized_record.vinted_status),  # vinted 状态。
            int(normalized_record.fb_status),  # fb 状态。
            int(normalized_record.titok_status),  # titok 状态。
            normalized_record.pwd,  # vinted 密码字段。
            normalized_record.device,  # 设备 ID（仅展示字段）。
            normalized_record.msg,  # 备注字段。
            int(update_at_value),  # 更新时间戳。
            safe_user_id,  # 目标账号 id。
        )  # 参数元组构造完成。
        try:  # 捕获数据库唯一约束异常并转成可读错误。
            with conn:  # 使用事务上下文执行更新。
                cursor = conn.execute(sql, params)  # 执行更新 SQL。
        except sqlite3.IntegrityError as exc:  # 捕获 SQLite 约束异常。
            if self._is_unique_email_error(exc):  # 邮箱唯一键冲突时返回友好提示。
                raise ValueError("email_account 已存在，请使用不同邮箱账号") from exc  # 抛出业务可读异常。
            raise  # 其他约束异常继续抛出，避免吞错。
        return int(cursor.rowcount)  # 返回更新受影响行数。

    def delete_user_by_id(self, user_id: int) -> int:  # 定义按 id 删除账号方法，返回受影响行数。
        safe_user_id = int(user_id)  # 把 user_id 转成整数。
        if safe_user_id <= 0:  # 非法 id 直接抛错，避免误删。
            raise ValueError("user_id 必须是大于 0 的整数")  # 抛出明确错误提示。
        conn = self.connect()  # 获取可用连接。
        with conn:  # 使用事务上下文执行删除。
            cursor = conn.execute(  # 执行按 id 删除 SQL。
                f"DELETE FROM {TABLE_NAME} WHERE id = ?;",  # 删除指定 id 的账号记录。
                (safe_user_id,),  # 传入要删除的 id 参数。
            )  # SQL 执行结束。
        return int(cursor.rowcount)  # 返回删除受影响行数。

    def get_config(self, key: str) -> dict[str, Any] | None:  # 定义按 key 查询单个配置项方法。
        conn = self.connect()  # 获取可用连接。
        cursor = conn.execute(  # 执行配置查询 SQL。
            f'SELECT "key", "val", "desc", update_at FROM {CONFIG_TABLE_NAME} WHERE "key" = ? LIMIT 1;',  # 按 key 查询单条配置。
            (str(key),),  # 传入 key 参数。
        )  # SQL 执行结束。
        row = cursor.fetchone()  # 读取查询结果第一行。
        if row is None:  # 查询不到配置时返回 None。
            return None
        return dict(row)  # 把 sqlite3.Row 转字典后返回。

    def list_configs(self, limit: int = 200, offset: int = 0) -> list[dict[str, Any]]:  # 定义配置列表查询方法。
        conn = self.connect()  # 获取可用连接。
        safe_limit = max(int(limit), 1)  # 对 limit 做下限保护，避免传入无效值。
        safe_offset = max(int(offset), 0)  # 对 offset 做下限保护，避免负数偏移。
        cursor = conn.execute(  # 执行配置列表查询 SQL。
            f'SELECT "key", "val", "desc", update_at FROM {CONFIG_TABLE_NAME} ORDER BY "key" ASC LIMIT ? OFFSET ?;',  # 按 key 升序查询配置列表。
            (safe_limit, safe_offset),  # 传入限制数量和偏移参数。
        )  # SQL 执行结束。
        return [dict(row) for row in cursor.fetchall()]  # 把结果集逐行转字典后返回列表。

    def get_config_map(self) -> dict[str, str]:  # 定义配置映射查询方法（返回 key->val）。
        conn = self.connect()  # 获取可用连接。
        with conn:  # 用事务上下文确保默认配置存在（缺失时自动补齐）。
            self._ensure_default_configs(conn)  # 写入默认配置（仅首次缺失时生效）。
        cursor = conn.execute(  # 查询全部配置键值对。
            f'SELECT "key", "val" FROM {CONFIG_TABLE_NAME} ORDER BY "key" ASC;'  # 按 key 升序读取配置。
        )  # SQL 执行结束。
        rows = cursor.fetchall()  # 读取配置结果集。
        config_map: dict[str, str] = {}  # 初始化配置映射字典。
        for row in rows:  # 逐条写入 key->val 映射。
            config_map[str(row["key"])] = str(row["val"])  # 强制转成字符串，便于任务层直接消费。
        return config_map  # 返回配置映射。

    def set_config(self, key: str, val: str, desc: str | None = None) -> None:  # 定义配置写入方法（不存在时插入，存在时更新）。
        conn = self.connect()  # 获取可用连接。
        key_value = str(key).strip()  # 清理 key 文本，避免空白字符干扰。
        if key_value == "":  # 空 key 直接判定非法。
            raise ValueError("配置 key 不能为空")  # 抛出明确错误提示。

        normalized_val = self._normalize_config_value(key_value, val)  # 标准化并校验配置值。
        current_row = self.get_config(key_value)  # 读取当前配置，便于保留已有描述文案。
        desc_value = str(desc).strip() if desc is not None else ""  # 解析入参描述文本。
        if desc_value == "":  # 入参描述为空时，按“当前值 -> 默认值 -> 空字符串”顺序回退。
            if current_row is not None and str(current_row.get("desc", "")).strip() != "":  # 当前记录有描述时优先沿用。
                desc_value = str(current_row.get("desc", ""))  # 使用当前记录描述。
            elif key_value == MOJIWANG_RUN_NUM_KEY:  # 抹机王配置使用固定默认描述。
                desc_value = MOJIWANG_RUN_NUM_DESC  # 采用默认描述文案。
            elif key_value == STATUS_23_RETRY_MAX_KEY:  # status=2/3 重试配置使用固定默认描述。
                desc_value = STATUS_23_RETRY_MAX_DESC  # 采用默认描述文案。

        update_time = now_ts()  # 生成本次写入更新时间戳。
        with conn:  # 使用事务上下文执行写入，保证原子性。
            conn.execute(  # 执行 UPSERT 写入配置 SQL。
                f"""
                INSERT INTO {CONFIG_TABLE_NAME} ("key", "val", "desc", update_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT("key") DO UPDATE SET
                    "val" = excluded."val",
                    "desc" = excluded."desc",
                    update_at = excluded.update_at;
                """,  # 配置 UPSERT SQL。
                (key_value, normalized_val, desc_value, int(update_time)),  # UPSERT 参数。
            )  # SQL 执行结束。

    def update_status(self, email_account: str, status: int, msg: str | None = None) -> int:  # 定义按邮箱更新 status（可选更新备注）方法。
        conn = self.connect()  # 获取可用连接。
        update_time = now_ts()  # 生成本次更新时间戳。
        with conn:  # 使用事务上下文执行更新。
            if msg is None:  # 如果调用方不想更新备注。
                cursor = conn.execute(  # 执行只更新 status 和 update_at 的 SQL。
                    f"UPDATE {TABLE_NAME} SET status = ?, update_at = ? WHERE email_account = ?;",  # 只改状态和更新时间。
                    (int(status), int(update_time), email_account),  # 传入 SQL 参数。
                )  # SQL 执行结束。
            else:  # 如果调用方传了备注。
                cursor = conn.execute(  # 执行同时更新 status、msg、update_at 的 SQL。
                    f"UPDATE {TABLE_NAME} SET status = ?, msg = ?, update_at = ? WHERE email_account = ?;",  # 同时改状态、备注、更新时间。
                    (int(status), msg, int(update_time), email_account),  # 传入 SQL 参数。
                )  # SQL 执行结束。
        return int(cursor.rowcount)  # 返回受影响行数，便于上层判断是否更新成功。
