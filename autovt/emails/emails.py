from __future__ import annotations

# 导入 Path，用于拼接调试 HTML 输出路径。
from pathlib import Path
# 导入 html 转义函数，避免调试 HTML 被正文内容破坏结构。
from html import escape
# 导入计时模块，用于输出每步耗时，便于定位卡点。
import time
# 导入 Any，便于处理 outlook 返回的动态结构。
from typing import Any

# 导入邮件验证码解析函数，用于提取最新 Facebook 验证码。
from autovt.emails.fackbook_code import extract_latest_fackbook_code
# 导入 Outlook 访问令牌获取函数，用于 OAuth 刷新。
from autovt.emails.outlook import get_access_token
# 导入 Outlook 邮件读取函数，用于拉取最新邮件列表。
from autovt.emails.outlook import get_mail_info
# 导入项目统一日志工厂，保证错误可追踪。
from autovt.logs import get_logger

# 创建当前模块日志对象，方便按组件过滤日志。
log = get_logger("emails")


# 定义结果规范化方法，把返回统一成 (success, payload/message) 结构。
def _normalize_bool_payload(result: Any, fail_hint: str) -> tuple[bool, str]:
    # 返回值应是长度 >= 2 的 list/tuple，否则视为格式异常。
    if not isinstance(result, (list, tuple)) or len(result) < 2:
        # 返回失败，并附带调用提示。
        return False, f"{fail_hint}返回格式异常"
    # 第一位按布尔值解释是否成功。
    success = bool(result[0])
    # 第二位按字符串解释有效载荷或错误信息。
    payload = str(result[1]).strip()
    # 返回标准化后的结果。
    return success, payload


# 定义调试 HTML 输出方法：仅在 is_debug=True 时调用，便于离线排查。
def _write_debug_html(mail_info: Any) -> None:
    # 计算调试 HTML 输出文件路径（固定写入当前包目录下 test.html）。
    html_file = Path(__file__).resolve().parent / "test.html"
    # 初始化 section 片段列表，用于拼装多封邮件报告。
    sections: list[str] = []
    # 拉取结果是列表时，按“每封邮件一个 section”输出。
    if isinstance(mail_info, list):
        # 按顺序遍历邮件列表，生成调试展示块。
        for index, item in enumerate(mail_info, start=1):
            # 确保当前项是字典结构，不是字典时按空对象兜底。
            row = item if isinstance(item, dict) else {}
            # 读取并转义主题字段，避免 HTML 注入。
            subject = escape(str(row.get("subject", "")))
            # 读取并转义时间字段，避免 HTML 注入。
            mail_dt = escape(str(row.get("mail_dt", "")))
            # 读取并转义发件人字段，避免 HTML 注入。
            mail_from = escape(str(row.get("mail_from", "")))
            # 读取正文原文并做最小转义后写入 pre 标签，保留内容原貌便于排查。
            body = escape(str(row.get("body", "")))
            # 追加当前邮件展示片段到 sections 列表。
            sections.append(
                f"""
                <section>
                    <h2>邮件 {index}</h2>
                    <p><strong>邮件主题：</strong>{subject}</p>
                    <p><strong>发件时间：</strong>{mail_dt}</p>
                    <p><strong>发件人：</strong>{mail_from}</p>
                    <div><strong>邮件正文：</strong></div>
                    <pre>{body}</pre>
                </section>
                """
            )
    # 拉取结果不是列表时按错误结构展示，便于快速定位返回异常。
    else:
        # 读取错误文本并做转义，避免 HTML 注入。
        error_text = escape(str(mail_info))
        # 追加错误 section。
        sections.append(
            f"""
            <section>
                <h2>错误信息</h2>
                <pre>{error_text}</pre>
            </section>
            """
        )
    # 组装完整 HTML 文本，统一写入调试文件。
    html_text = f"""
    <!DOCTYPE html>
    <html lang="zh">
    <head>
        <meta charset="UTF-8">
        <title>AutoVT 邮件调试</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 16px; }}
            section {{ border: 1px solid #ddd; border-radius: 8px; padding: 12px; margin-bottom: 12px; }}
            pre {{ white-space: pre-wrap; word-break: break-word; background: #fafafa; padding: 8px; border-radius: 6px; }}
        </style>
    </head>
    <body>
        <h1>邮件调试快照</h1>
        {''.join(sections)}
    </body>
    </html>
    """
    # 把调试 HTML 写入固定文件，便于离线查看。
    html_file.write_text(html_text, encoding="utf-8")
    # 记录调试文件写入成功日志。
    log.info("调试邮件 HTML 写入成功", html_file=str(html_file))


# 定义主方法：获取最新 Facebook 验证码。
def getfackbook_code(
    client_id: str,
    email_name: str,
    refresh_token: str,
    is_debug: bool = False,
) -> tuple[bool, str]:
    # 记录整体流程起点时间，用于统计总耗时。
    overall_start_ts = time.monotonic()
    # 记录主流程开始日志，便于确认方法已进入执行。
    log.info("开始获取 Facebook 验证码", email_name=str(email_name).strip(), is_debug=bool(is_debug))
    # 先规范化 client_id 文本，避免前后空白导致 OAuth 失败。
    normalized_client_id = str(client_id).strip()
    # 先规范化邮箱账号文本，避免前后空白导致 IMAP 认证失败。
    normalized_email_name = str(email_name).strip()
    # 先规范化 refresh_token 文本，避免前后空白导致刷新失败。
    normalized_refresh_token = str(refresh_token).strip()
    # 入参缺失时立即返回，避免发起无意义网络请求。
    if not normalized_client_id or not normalized_email_name or not normalized_refresh_token:
        # 记录参数错误日志，便于快速定位调用方问题。
        log.error(
            "获取 Facebook 验证码失败：参数缺失",
            client_id=normalized_client_id,
            email_name=normalized_email_name,
            has_refresh_token=bool(normalized_refresh_token),
        )
        # 返回失败信息给调用方。
        return False, "参数缺失：client_id/email_name/refresh_token 不能为空"
    # 第一步：先用 refresh_token 换取 access_token。
    # 记录步骤开始日志，便于区分卡在 token 还是 IMAP。
    log.info("步骤 1/3：开始刷新 access_token", email_name=normalized_email_name)
    # 记录 token 刷新步骤起点时间。
    token_start_ts = time.monotonic()
    try:
        # 调用 outlook 的 access_token 刷新函数。
        token_result = get_access_token(normalized_client_id, normalized_refresh_token)
    # 捕获异常并记日志，确保错误可追踪。
    except Exception as exc:
        # 记录完整堆栈，便于排查网络或接口异常。
        log.exception("刷新 access_token 异常", email_name=normalized_email_name)
        # 返回失败信息给调用方。
        return False, f"刷新 access_token 异常: {exc}"
    # 统一解析刷新结果结构。
    token_ok, token_payload = _normalize_bool_payload(token_result, "刷新 access_token")
    # 刷新失败时直接返回。
    if not token_ok:
        # 记录失败原因日志。
        log.error("刷新 access_token 失败", email_name=normalized_email_name, reason=token_payload)
        # 返回失败原因给调用方。
        return False, token_payload or "刷新 access_token 失败"
    # 记录 token 刷新步骤完成日志和耗时。
    log.info("步骤 1/3：刷新 access_token 完成", email_name=normalized_email_name, elapsed_ms=int((time.monotonic() - token_start_ts) * 1000))
    # 读取 access_token 字符串。
    access_token = token_payload
    # access_token 为空时视为失败。
    if not access_token:
        # 记录 access_token 空值错误。
        log.error("刷新 access_token 失败：返回空 token", email_name=normalized_email_name)
        # 返回失败提示。
        return False, "刷新 access_token 失败：返回空 token"
    # 第二步：用 access_token 读取最新邮件列表。
    # 记录步骤开始日志，便于观察是否卡在 IMAP 阶段。
    log.info("步骤 2/3：开始拉取邮件", email_name=normalized_email_name)
    # 记录拉取邮件步骤起点时间。
    fetch_start_ts = time.monotonic()
    try:
        # 调用 outlook 的邮件拉取函数。
        mail_info = get_mail_info(normalized_email_name, access_token)
    # 捕获拉取异常并记录日志。
    except Exception as exc:
        # 记录完整堆栈，便于排查 IMAP 认证或网络问题。
        log.exception("拉取邮件异常", email_name=normalized_email_name)
        # 返回失败信息给调用方。
        return False, f"拉取邮件异常: {exc}"
    # 拉取结果是 dict 时通常表示错误结构，优先返回其 error_msg。
    if isinstance(mail_info, dict):
        # 读取错误信息字段，兜底为通用描述。
        error_msg = str(mail_info.get("error_msg", "拉取邮件失败")).strip()
        # 可选调试：失败时也写 HTML，方便排查具体返回。
        if bool(is_debug):
            # 写调试 HTML 时要单独兜底，防止覆盖主错误返回。
            try:
                # 写入 HTML 快照到固定调试文件。
                _write_debug_html(mail_info)
            # 记录调试写文件异常，但不影响主错误返回。
            except Exception:
                # 输出完整异常堆栈，便于排查磁盘/编码问题。
                log.exception("写入调试 HTML 失败（错误结果）", email_name=normalized_email_name)
        # 记录邮件拉取失败日志。
        log.error("拉取邮件失败", email_name=normalized_email_name, reason=error_msg)
        # 返回失败信息给调用方。
        return False, error_msg
    # 记录拉取邮件步骤完成日志与邮件数量。
    log.info(
        "步骤 2/3：拉取邮件完成",
        email_name=normalized_email_name,
        elapsed_ms=int((time.monotonic() - fetch_start_ts) * 1000),
        mail_count=len(mail_info) if isinstance(mail_info, list) else -1,
    )
    # 可选调试：成功拉取时写 HTML 报告，便于人工核对邮件内容。
    if bool(is_debug):
        # 调试写文件需要独立兜底，避免影响主流程。
        try:
            # 写入 HTML 快照到固定调试文件。
            _write_debug_html(mail_info)
        # 写入异常时只记录日志，不中断验证码流程。
        except Exception:
            # 记录写入调试文件失败异常堆栈。
            log.exception("写入调试 HTML 失败（成功结果）", email_name=normalized_email_name)
    # 第三步：从邮件列表中提取最新 Facebook 验证码。
    # 记录解析步骤开始日志，便于定位卡在解析或网络。
    log.info("步骤 3/3：开始解析验证码", email_name=normalized_email_name)
    # 记录解析步骤起点时间。
    parse_start_ts = time.monotonic()
    try:
        # 调用解析模块提取“最新验证码”。
        parse_ok, parse_payload = extract_latest_fackbook_code(mail_info)
    # 捕获解析异常并记录日志。
    except Exception as exc:
        # 输出完整异常堆栈，便于修正规则。
        log.exception("解析 Facebook 验证码异常", email_name=normalized_email_name)
        # 返回失败信息给调用方。
        return False, f"解析 Facebook 验证码异常: {exc}"
    # 解析失败时返回具体失败原因。
    if not parse_ok:
        # 记录解析失败日志。
        log.error("解析 Facebook 验证码失败", email_name=normalized_email_name, reason=parse_payload)
        # 返回失败原因给调用方。
        return False, parse_payload or "解析 Facebook 验证码失败"
    # 记录解析成功日志。
    log.info(
        "获取 Facebook 验证码成功",
        email_name=normalized_email_name,
        code_length=len(parse_payload),
        parse_elapsed_ms=int((time.monotonic() - parse_start_ts) * 1000),
        total_elapsed_ms=int((time.monotonic() - overall_start_ts) * 1000),
    )
    # 返回成功与验证码。
    return True, parse_payload
