from __future__ import annotations

# 导入 html 模块，用于反转义 HTML 实体字符。
import html
# 导入正则模块，用于匹配验证码与邮件字段。
import re
# 导入数据类装饰器，用于定义候选结果结构。
from dataclasses import dataclass
# 导入时间类型，用于比较“最新邮件”。
from datetime import datetime
# 导入 Any 类型，便于兼容外部不严格输入。
from typing import Any

# 导入项目统一日志工厂，保证异常可追踪。
from autovt.logs import get_logger

# 创建当前模块日志对象，方便按组件过滤日志。
log = get_logger("emails.fackbook_code")

# 预编译数字验证码正则：只接收 4~8 位纯数字，避免误提取年份等超长数字。
_CODE_PATTERN = re.compile(r"(?<!\d)(\d{4,8})(?!\d)")
# 预编译 section 分段正则：用于解析调试 HTML 报告中的单封邮件区块。
_SECTION_PATTERN = re.compile(r"<section>(.*?)</section>", re.IGNORECASE | re.DOTALL)
# 预编译“主题”字段提取正则：匹配调试 HTML 里“邮件主题”值。
_SUBJECT_PATTERN = re.compile(r"邮件主题：</strong>(.*?)</p>", re.IGNORECASE | re.DOTALL)
# 预编译“时间”字段提取正则：匹配调试 HTML 里“发件时间”值。
_MAIL_DT_PATTERN = re.compile(r"发件时间：</strong>(.*?)</p>", re.IGNORECASE | re.DOTALL)
# 预编译“发件人”字段提取正则：匹配调试 HTML 里“发件人”值。
_MAIL_FROM_PATTERN = re.compile(r"发件人：</strong>(.*?)</p>", re.IGNORECASE | re.DOTALL)
# 预编译“正文”字段提取正则：匹配调试 HTML 里“邮件正文”值。
_BODY_PATTERN = re.compile(r"邮件正文：</strong>(.*?)</div>", re.IGNORECASE | re.DOTALL)

# 定义 Facebook 判定关键词：用于识别是否为 Facebook 相关邮件。
_FACEBOOK_HINTS = (
    "facebook",
    "facebookmail.com",
    "registration@facebookmail.com",
    "sécurité facebook",
)
# 定义正文中“验证码语义”关键词：用于在正文里定位验证码附近区域。
_CODE_HINTS = (
    "code de confirmation",
    "confirmation code",
    "verification code",
    "votre code",
    "your code",
    "验证码",
    "驗證碼",
    "确认码",
)


# 定义验证码候选结构，便于后续按时间比较“最新一封”。
@dataclass(slots=True)
class FackbookCodeCandidate:
    # 保存提取出的验证码字符串。
    code: str
    # 保存邮件时间，用于比较“最新”。
    mail_dt: datetime
    # 保存邮件主题，便于日志排查。
    subject: str
    # 保存发件人，便于日志排查。
    mail_from: str
    # 保存验证码来源（subject 或 body），便于定位解析路径。
    source: str


# 定义安全转字符串方法，避免 None 或复杂对象导致解析报错。
def _safe_text(value: Any) -> str:
    # 空值直接返回空字符串，减少后续判空复杂度。
    if value is None:
        # 返回空字符串作为统一兜底值。
        return ""
    # 把输入转成字符串，兼容调用方传入非字符串类型。
    return str(value)


# 定义“去标签 + 反转义”方法，把 HTML 正文转换为纯文本，便于关键词匹配。
def _to_plain_text(raw_text: str) -> str:
    # 先确保输入是字符串，避免正则替换时报类型错误。
    text = _safe_text(raw_text)
    # 先把 HTML 实体字符还原成普通文本（例如 &nbsp;）。
    text = html.unescape(text)
    # 去掉 style/script，降低 CSS/JS 噪音对解析的干扰。
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    # 去掉所有 HTML 标签，仅保留可读文本。
    text = re.sub(r"<[^>]+>", " ", text)
    # 把连续空白折叠为单空格，提升关键词检索稳定性。
    text = re.sub(r"\s+", " ", text).strip()
    # 返回清洗后的纯文本。
    return text


# 定义邮件时间解析方法，把字符串时间转为 datetime，便于比较新旧。
def _parse_mail_datetime(mail_dt_text: str) -> datetime:
    # 先清理输入文本首尾空白。
    cleaned = _safe_text(mail_dt_text).strip()
    # 依次尝试常见时间格式，兼容不同来源返回。
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        # 尝试按当前格式解析时间。
        try:
            # 解析成功直接返回。
            return datetime.strptime(cleaned, fmt)
        # 当前格式不匹配时继续尝试下一个格式。
        except ValueError:
            # 跳到下一轮格式解析。
            continue
    # 全部格式都失败时返回最小时间，保证排序逻辑不崩溃。
    return datetime.min


# 定义“是否 Facebook 邮件”判定逻辑，避免把非目标邮件误当验证码邮件。
def _is_fackbook_mail(subject: str, mail_from: str, body: str) -> bool:
    # 把关键信息拼成一段文本后统一做小写匹配。
    merged = f"{subject} {mail_from} {body}".lower()
    # 只要命中任一 Facebook 关键词，就认为是目标邮件。
    return any(hint in merged for hint in _FACEBOOK_HINTS)


# 定义主题验证码提取逻辑：优先从主题抓取（Facebook 常见格式就在主题首部）。
def _extract_code_from_subject(subject: str) -> str | None:
    # 先把主题文本清洗成普通字符串。
    cleaned_subject = _safe_text(subject).strip()
    # 在主题中搜索第一个 4~8 位数字。
    match = _CODE_PATTERN.search(cleaned_subject)
    # 没有数字时返回 None，让上层继续走正文解析。
    if not match:
        # 返回空结果表示本路径未提取到验证码。
        return None
    # 返回匹配到的数字验证码。
    return match.group(1)


# 定义正文验证码提取逻辑：先找“验证码语义关键词”，再在邻近窗口内提数字。
def _extract_code_from_body(body: str) -> str | None:
    # 先把 HTML 正文清洗成纯文本，便于窗口扫描。
    plain_text = _to_plain_text(body)
    # 把文本转小写，统一做不区分大小写检索。
    plain_lower = plain_text.lower()
    # 遍历所有验证码语义关键词，尽量只在“相关语境”里提数字，降低误判。
    for hint in _CODE_HINTS:
        # 从文本起点开始逐次查找关键词，兼容一封邮件出现多次关键词的情况。
        start_index = 0
        # 使用循环持续查找同一关键词的所有出现位置。
        while True:
            # 查找当前关键词下一个命中位置。
            hit_index = plain_lower.find(hint, start_index)
            # 没找到时跳出当前关键词循环。
            if hit_index < 0:
                # 结束当前关键词扫描。
                break
            # 以关键词为锚点截取后续窗口，通常验证码会在后面不远处出现。
            window_text = plain_text[hit_index : hit_index + 320]
            # 在窗口中搜索验证码数字。
            window_match = _CODE_PATTERN.search(window_text)
            # 命中时直接返回验证码，优先保证“语义邻近”正确率。
            if window_match:
                # 返回窗口内提取到的验证码。
                return window_match.group(1)
            # 更新起点，继续查找同一关键词的下一次出现。
            start_index = hit_index + len(hint)
    # 没有在正文中找到可信验证码时返回 None。
    return None


# 定义从单封邮件构建“验证码候选”的方法。
def _build_candidate_from_mail(mail_info: dict[str, Any]) -> FackbookCodeCandidate | None:
    # 读取主题文本并统一转字符串。
    subject = _safe_text(mail_info.get("subject", "")).strip()
    # 读取发件人文本并统一转字符串。
    mail_from = _safe_text(mail_info.get("mail_from", "")).strip()
    # 读取正文文本并统一转字符串。
    body = _safe_text(mail_info.get("body", ""))
    # 读取邮件时间文本并统一转字符串。
    mail_dt_text = _safe_text(mail_info.get("mail_dt", "")).strip()
    # 非 Facebook 邮件直接跳过，减少误提取。
    if not _is_fackbook_mail(subject=subject, mail_from=mail_from, body=body):
        # 返回 None 表示当前邮件不参与候选。
        return None
    # 先尝试从主题提取验证码（优先级最高）。
    subject_code = _extract_code_from_subject(subject)
    # 主题提取到验证码时直接构建候选。
    if subject_code:
        # 返回来自主题的验证码候选。
        return FackbookCodeCandidate(
            code=subject_code,
            mail_dt=_parse_mail_datetime(mail_dt_text),
            subject=subject,
            mail_from=mail_from,
            source="subject",
        )
    # 主题没有验证码时再尝试正文提取。
    body_code = _extract_code_from_body(body)
    # 正文也提取失败时返回 None。
    if not body_code:
        # 返回空结果，交由上层继续检查其他邮件。
        return None
    # 返回来自正文的验证码候选。
    return FackbookCodeCandidate(
        code=body_code,
        mail_dt=_parse_mail_datetime(mail_dt_text),
        subject=subject,
        mail_from=mail_from,
        source="body",
    )


# 定义主解析函数：从邮件列表中提取“最新一封 Facebook 验证码”。
def extract_latest_fackbook_code(mail_info_list: Any) -> tuple[bool, str]:
    # 邮件列表必须是 list，否则直接返回失败信息。
    if not isinstance(mail_info_list, list):
        # 返回失败：调用方传入的数据格式异常。
        return False, "邮件列表格式异常（期望 list）"
    # 初始化最佳候选为空，后续用时间比较更新。
    best_candidate: FackbookCodeCandidate | None = None
    # 初始化最佳候选索引，用于同时间时按先后顺序稳定决策。
    best_index = 10**9
    # 遍历邮件列表逐封提取验证码候选。
    for index, raw_mail in enumerate(mail_info_list):
        # 当前项不是 dict 时直接跳过，避免结构异常导致崩溃。
        if not isinstance(raw_mail, dict):
            # 继续处理下一封邮件。
            continue
        # 从当前邮件构建验证码候选。
        candidate = _build_candidate_from_mail(raw_mail)
        # 当前邮件没提取到候选时跳过。
        if candidate is None:
            # 继续处理下一封邮件。
            continue
        # 首个候选直接作为当前最佳。
        if best_candidate is None:
            # 更新最佳候选为当前候选。
            best_candidate = candidate
            # 记录当前候选索引。
            best_index = index
            # 进入下一轮邮件处理。
            continue
        # 当前候选时间更新时覆盖最佳候选。
        if candidate.mail_dt > best_candidate.mail_dt:
            # 替换为更新时间的候选。
            best_candidate = candidate
            # 同步更新索引记录。
            best_index = index
            # 进入下一轮邮件处理。
            continue
        # 时间完全相同且索引更小（更靠前）时，优先保留更靠前项。
        if candidate.mail_dt == best_candidate.mail_dt and index < best_index:
            # 替换为更靠前的候选，保证结果稳定。
            best_candidate = candidate
            # 更新索引记录。
            best_index = index
    # 最终没有任何候选时返回失败信息。
    if best_candidate is None:
        # 返回失败：未命中 Facebook 验证码邮件。
        return False, "未找到 Facebook 验证码邮件"
    # 记录提取成功日志，便于线上排查规则命中情况。
    log.info(
        "Facebook 验证码解析成功",
        source=best_candidate.source,
        code_length=len(best_candidate.code),
        subject=best_candidate.subject,
        mail_from=best_candidate.mail_from,
        mail_dt=str(best_candidate.mail_dt),
    )
    # 返回成功与验证码文本。
    return True, best_candidate.code


# 定义从调试 HTML 文本中提取“最新 Facebook 验证码”的方法，便于离线排查。
def extract_latest_fackbook_code_from_html_text(html_text: str) -> tuple[bool, str]:
    # 把输入统一转为字符串，避免 None 引发异常。
    raw_html = _safe_text(html_text)
    # 逐个 section 区块解析，保持与 write_html 输出结构一致。
    sections = _SECTION_PATTERN.findall(raw_html)
    # section 为空时直接返回失败，提示输入内容不符合预期。
    if not sections:
        # 返回失败：HTML 中未找到邮件区块。
        return False, "HTML 中未找到 section 邮件区块"
    # 初始化伪造的邮件列表，用于复用主解析逻辑。
    fake_mail_list: list[dict[str, Any]] = []
    # 遍历每个 section 并提取主题/时间/发件人/正文字段。
    for section in sections:
        # 提取邮件主题文本。
        subject_match = _SUBJECT_PATTERN.search(section)
        # 提取发件时间文本。
        mail_dt_match = _MAIL_DT_PATTERN.search(section)
        # 提取发件人文本。
        mail_from_match = _MAIL_FROM_PATTERN.search(section)
        # 提取正文文本。
        body_match = _BODY_PATTERN.search(section)
        # 组装成与 IMAP 拉取一致的结构，便于复用统一规则。
        fake_mail_list.append(
            {
                "subject": html.unescape(subject_match.group(1).strip()) if subject_match else "",
                "mail_dt": html.unescape(mail_dt_match.group(1).strip()) if mail_dt_match else "",
                "mail_from": html.unescape(mail_from_match.group(1).strip()) if mail_from_match else "",
                "body": html.unescape(body_match.group(1).strip()) if body_match else html.unescape(section),
            }
        )
    # 复用主解析逻辑，避免两套规则不一致。
    return extract_latest_fackbook_code(fake_mail_list)


# 定义从调试 HTML 文件路径读取并解析验证码的方法，便于直接对 test.html 做验证。
def extract_latest_fackbook_code_from_html_file(html_file_path: str) -> tuple[bool, str]:
    # 导入 Path 仅在函数内部使用，减少模块级依赖。
    from pathlib import Path

    # 先把文件路径转成 Path 对象，便于文件操作。
    file_path = Path(html_file_path).expanduser().resolve()
    # 文件不存在时返回失败信息并记录日志。
    if not file_path.exists():
        # 记录文件不存在错误，方便调用方快速定位路径问题。
        log.error("调试 HTML 文件不存在", html_file=str(file_path))
        # 返回失败说明。
        return False, f"HTML 文件不存在: {file_path}"
    # 尝试读取文件内容并执行解析。
    try:
        # 按 UTF-8 读取 HTML 文件文本。
        html_text = file_path.read_text(encoding="utf-8")
        # 调用 HTML 文本解析方法提取验证码。
        return extract_latest_fackbook_code_from_html_text(html_text)
    # 捕获所有异常并记录日志，保证错误可追踪。
    except Exception as exc:
        # 记录完整异常堆栈，便于定位编码或解析问题。
        log.exception("解析调试 HTML 文件失败", html_file=str(file_path))
        # 返回失败信息给调用方。
        return False, f"解析 HTML 失败: {exc}"
