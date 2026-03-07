"""账号批量导入逻辑模块。"""

from __future__ import annotations

# 导入 dataclass，用于定义导入数据结构。
from dataclasses import dataclass
# 导入 Path，用于读取本地文件。
from pathlib import Path
# 导入 Any，便于日志参数类型标注。
from typing import Any
# 导入 UUID，用于校验 client_id 格式。
from uuid import UUID

# 导入 Faker，用于按国家生成姓名。
from faker import Faker

# 导入项目用户库对象。
from autovt.userdb import UserDB, UserRecord

# 定义导入字段分隔符常量。
IMPORT_SPLITTER = "----"
# 定义单行期望字段数量常量。
IMPORT_PART_COUNT = 4

# 定义可选姓名国家（国家中文名 -> Faker locale）。
NAME_COUNTRY_OPTIONS: list[tuple[str, str]] = [
    ("法国", "fr_FR"),
    ("英国", "en_GB"),
    ("美国", "en_US"),
    ("德国", "de_DE"),
    ("西班牙", "es_ES"),
    ("意大利", "it_IT"),
]


# 定义单行原始导入数据结构。
@dataclass(slots=True)
class ParsedAccountLine:
    # 原始行号（从 1 开始）。
    line_no: int
    # 邮箱账号。
    email_account: str
    # 邮箱密码。
    email_pwd: str
    # 微软 OAuth client_id。
    client_id: str
    # 邮箱授权码。
    email_access_key: str


# 定义导入统计结果结构。
@dataclass(slots=True)
class AccountImportResult:
    # 原始非空行数量。
    total_non_empty_lines: int
    # 通过格式校验的行数量。
    valid_line_count: int
    # 实际成功写入数量。
    inserted_count: int
    # 因邮箱已存在而跳过数量。
    skipped_existing_count: int
    # 因导入文件内重复邮箱而跳过数量。
    skipped_duplicate_in_file_count: int
    # 格式错误列表（非空时不会执行写库）。
    validation_errors: list[str]
    # 写库阶段错误列表（格式通过后可能出现）。
    insert_errors: list[str]

    # 返回是否存在格式错误。
    def has_validation_error(self) -> bool:
        # 只要存在格式错误就返回 True。
        return len(self.validation_errors) > 0


# 定义“解析国家选项为 locale”的方法。
def resolve_name_locale(country_label: str) -> str:
    # 清理输入国家文案，避免空白影响匹配。
    safe_country_label = str(country_label or "").strip()
    # 遍历国家选项做精确匹配。
    for label, locale in NAME_COUNTRY_OPTIONS:
        # 命中选项时返回对应 locale。
        if safe_country_label == label:
            return locale
    # 未命中时回退法国 locale。
    return "fr_FR"


# 定义“按 locale 生成姓名”的公共方法。
def generate_account_name(name_locale: str) -> tuple[str, str]:
    # 清理 locale 入参，避免空值导致 Faker 初始化异常。
    safe_name_locale = str(name_locale or "fr_FR").strip() or "fr_FR"
    # 初始化 Faker 实例，用于生成姓名。
    faker_obj = Faker(safe_name_locale)
    # 生成账号的姓。
    generated_first_name = str(faker_obj.first_name()).strip()
    # 生成账号的名。
    generated_last_name = str(faker_obj.last_name()).strip()
    # 兜底保障姓不为空。
    if generated_first_name == "":
        generated_first_name = "FirstName"
    # 兜底保障名不为空。
    if generated_last_name == "":
        generated_last_name = "LastName"
    # 返回生成后的姓名。
    return generated_first_name, generated_last_name


# 定义“读取文本文件内容”的方法。
def read_text_file(file_path: str) -> str:
    # 把路径转成 Path 对象，便于后续操作。
    path_obj = Path(str(file_path))
    # 文件不存在时抛出明确错误。
    if not path_obj.exists():
        raise FileNotFoundError(f"导入文件不存在: {path_obj}")
    # 非普通文件时抛错。
    if not path_obj.is_file():
        raise ValueError(f"导入路径不是文件: {path_obj}")
    # 读取原始二进制数据。
    raw_bytes = path_obj.read_bytes()
    # 空文件直接返回空文本。
    if raw_bytes == b"":
        return ""
    # 命中空字节时大概率不是纯文本文件，直接拒绝。
    if b"\x00" in raw_bytes:
        raise ValueError("文件看起来不是纯文本文件（检测到空字节）")
    # 依次尝试常见文本编码解码。
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "latin1"):
        # 尝试按当前编码解码。
        try:
            return raw_bytes.decode(encoding)
        # 解码失败时继续下一个编码尝试。
        except Exception:
            continue
    # 全部编码都失败时抛错。
    raise ValueError("无法按文本方式解析文件编码，请确认文件内容是文本")


# 定义“校验 client_id 是否为合法 UUID”的方法。
def _is_valid_uuid(raw_value: str) -> bool:
    # 清理输入文本。
    safe_value = str(raw_value or "").strip()
    # 空值直接判定非法。
    if safe_value == "":
        return False
    # 尝试按 UUID 解析。
    try:
        # 解析成功即视为合法。
        UUID(safe_value)
        return True
    # 解析失败时返回非法。
    except Exception:
        return False


# 定义“基础邮箱格式校验”的方法。
def _is_valid_email(raw_value: str) -> bool:
    # 清理输入文本。
    safe_value = str(raw_value or "").strip()
    # 空值直接非法。
    if safe_value == "":
        return False
    # 必须恰好包含一个 @。
    if safe_value.count("@") != 1:
        return False
    # 按 @ 分割本地段和域名段。
    local_part, domain_part = safe_value.split("@", 1)
    # 任一段为空都非法。
    if local_part == "" or domain_part == "":
        return False
    # 域名必须包含点号。
    if "." not in domain_part:
        return False
    # 顶级域名长度至少 2。
    if len(domain_part.rsplit(".", 1)[-1]) < 2:
        return False
    # 通过基础校验则返回合法。
    return True


# 定义“清洗授权码”的方法。
def _normalize_access_key(raw_value: str) -> str:
    # 去掉头尾空白。
    safe_value = str(raw_value or "").strip()
    # 去掉中间空白和换行，避免复制污染。
    return "".join(safe_value.split())


# 定义“解析并校验单行文本”的方法。
def _parse_one_line(raw_line: str, line_no: int) -> tuple[ParsedAccountLine | None, str | None]:
    # 清理当前行文本。
    clean_line = str(raw_line or "").strip()
    # 空行直接返回空结果（非错误）。
    if clean_line == "":
        return None, None
    # 最多分割 3 次，保证授权码里出现 ---- 也不继续拆分。
    parts = [part.strip() for part in clean_line.split(IMPORT_SPLITTER, 3)]
    # 字段数不等于 4 时返回格式错误。
    if len(parts) != IMPORT_PART_COUNT:
        return None, f"第 {line_no} 行格式错误：必须是 4 段 email----email_pwd----client_id----email_access_key"
    # 提取各字段值。
    email_account = parts[0]
    email_pwd = parts[1]
    client_id = parts[2]
    email_access_key = _normalize_access_key(parts[3])
    # 校验基础非空。
    if email_account == "" or email_pwd == "" or client_id == "" or email_access_key == "":
        return None, f"第 {line_no} 行格式错误：四段字段都不能为空"
    # 校验邮箱格式。
    if not _is_valid_email(email_account):
        return None, f"第 {line_no} 行格式错误：email_account 不是有效邮箱"
    # 校验 client_id 是合法 UUID。
    if not _is_valid_uuid(client_id):
        return None, f"第 {line_no} 行格式错误：client_id 不是有效 UUID"
    # 返回解析成功结果。
    return (
        ParsedAccountLine(
            line_no=line_no,
            email_account=email_account,
            email_pwd=email_pwd,
            client_id=client_id,
            email_access_key=email_access_key,
        ),
        None,
    )


# 定义“解析并校验整段文本”的方法。
def parse_account_text(raw_text: str) -> tuple[list[ParsedAccountLine], list[str], int]:
    # 初始化解析结果列表。
    parsed_items: list[ParsedAccountLine] = []
    # 初始化错误列表。
    errors: list[str] = []
    # 初始化非空行计数器。
    non_empty_line_count = 0
    # 按行遍历文本内容。
    for index, line_text in enumerate(str(raw_text or "").splitlines(), start=1):
        # 清理当前行文本。
        clean_line = str(line_text or "").strip()
        # 空行直接跳过。
        if clean_line == "":
            continue
        # 累加非空行计数。
        non_empty_line_count += 1
        # 解析并校验当前行。
        parsed_item, error_message = _parse_one_line(clean_line, index)
        # 命中错误时记录错误并继续下一行。
        if error_message is not None:
            errors.append(error_message)
            continue
        # 解析成功时收集结果。
        if parsed_item is not None:
            parsed_items.append(parsed_item)
    # 返回解析结果、错误列表和非空行数。
    return parsed_items, errors, non_empty_line_count


# 定义账号批量导入器类。
class AccountFileImporter:
    # 定义导入器初始化方法。
    def __init__(self, user_db: UserDB, log: Any) -> None:
        # 保存用户库对象。
        self.user_db = user_db
        # 保存日志对象。
        self.log = log

    # 定义“从文件导入账号”的方法。
    def import_from_file(self, file_path: str, vt_pwd: str, name_locale: str) -> AccountImportResult:
        # 清理全局密码入参。
        safe_vt_pwd = str(vt_pwd or "").strip()
        # 未设置全局密码时直接返回格式错误风格结果。
        if safe_vt_pwd == "":
            return AccountImportResult(
                total_non_empty_lines=0,
                valid_line_count=0,
                inserted_count=0,
                skipped_existing_count=0,
                skipped_duplicate_in_file_count=0,
                validation_errors=["未设置全局 vt_pwd，请先到“全局设置”填写 vt_pwd 后再导入"],
                insert_errors=[],
            )
        # 读取文件文本内容。
        raw_text = read_text_file(file_path)
        # 解析并校验文本内容。
        parsed_items, validation_errors, total_non_empty_lines = parse_account_text(raw_text)
        # 存在格式错误时直接返回，不执行写库。
        if len(validation_errors) > 0:
            return AccountImportResult(
                total_non_empty_lines=total_non_empty_lines,
                valid_line_count=len(parsed_items),
                inserted_count=0,
                skipped_existing_count=0,
                skipped_duplicate_in_file_count=0,
                validation_errors=validation_errors,
                insert_errors=[],
            )
        # 初始化文件内去重集合（忽略邮箱大小写）。
        seen_emails: set[str] = set()
        # 初始化写库统计计数器。
        inserted_count = 0
        skipped_existing_count = 0
        skipped_duplicate_in_file_count = 0
        # 初始化写库错误列表。
        insert_errors: list[str] = []
        # 遍历解析成功的条目并写库。
        for item in parsed_items:
            # 统一邮箱比较 key（忽略大小写）。
            email_key = str(item.email_account).strip().lower()
            # 文件内重复邮箱直接跳过。
            if email_key in seen_emails:
                skipped_duplicate_in_file_count += 1
                continue
            # 标记当前邮箱为已处理。
            seen_emails.add(email_key)
            # 检查数据库里是否已存在同邮箱账号。
            existing_row = self.user_db.get_user_by_email(item.email_account)
            # 已存在时跳过，不覆盖。
            if existing_row is not None:
                skipped_existing_count += 1
                continue
            # 生成导入账号的姓名。
            generated_first_name, generated_last_name = generate_account_name(name_locale)
            # 组装要写入数据库的账号记录。
            record = UserRecord(
                email_account=item.email_account,
                email_pwd=item.email_pwd,
                email_access_key=item.email_access_key,
                client_id=item.client_id,
                status=0,
                first_name=generated_first_name,
                last_name=generated_last_name,
                vinted_status=0,
                fb_status=0,
                titok_status=0,
                pwd=safe_vt_pwd,
                device="",
                msg="批量导入",
            )
            # 尝试写入一条账号。
            try:
                # 创建新账号记录。
                self.user_db.create_user(record)
                # 成功写入计数加一。
                inserted_count += 1
            # 写库失败时记录错误并继续后续行。
            except Exception as exc:
                # 记录写库异常日志。
                self.log.exception(
                    "批量导入写库失败",
                    line_no=item.line_no,
                    email_account=item.email_account,
                    error=str(exc),
                )
                # 收集当前行错误信息。
                insert_errors.append(f"第 {item.line_no} 行写库失败：{exc}")
        # 返回导入统计结果。
        return AccountImportResult(
            total_non_empty_lines=total_non_empty_lines,
            valid_line_count=len(parsed_items),
            inserted_count=inserted_count,
            skipped_existing_count=skipped_existing_count,
            skipped_duplicate_in_file_count=skipped_duplicate_in_file_count,
            validation_errors=[],
            insert_errors=insert_errors,
        )
