# !/usr/bin/python
# -*- coding: utf-8 -*-
"""
# @Author  : RanKe
# @Time    : 2024/10/18 22:16
# @File      : get_mail_info.py
# @Desc   : 
"""

import imaplib
import email
import socket
import time
import requests
import webbrowser
from datetime import datetime
from pathlib import Path
from email.utils import parsedate_to_datetime
from email.header import decode_header, make_header

# 导入项目日志工厂，统一记录网络与解析异常。
from autovt.logs import get_logger

# 创建 outlook 模块日志对象，便于按组件过滤日志。
log = get_logger("emails.outlook")
# 定义 OAuth 接口超时时间（秒），避免网络异常时无限等待。
OAUTH_TIMEOUT_SEC = 20
# 定义 IMAP 连接与操作超时时间（秒），避免卡死。
IMAP_TIMEOUT_SEC = 20
# 定义 Graph 邮件读取超时时间（秒），避免接口阻塞。
GRAPH_TIMEOUT_SEC = 20
# 定义每次最多抓取最新邮件数量，默认取近 3 封用于验证码解析。
MAX_FETCH_MAIL_COUNT = 3
# 定义网络请求最大重试次数（不含首轮），避免代理偶发抖动直接失败。
NETWORK_RETRY_COUNT = 2
# 定义网络重试退避秒数，使用短等待避免连续撞失败。
NETWORK_RETRY_BACKOFF_SEC = 1.0
# 定义 Outlook IMAP 主机候选列表，优先使用微软当前文档推荐地址。
IMAP_HOST_CANDIDATES = [
    "outlook.office365.com",
    "outlook.live.com",
]
# 定义 IMAP 所需 OAuth scope 文本。
IMAP_SCOPE = "https://outlook.office.com/IMAP.AccessAsUser.All"
# 定义 Graph 邮件读取所需 scope 文本列表。
GRAPH_MAIL_READ_SCOPES = {
    "mail.read",
    "mail.readwrite",
    "https://graph.microsoft.com/mail.read",
    "https://graph.microsoft.com/mail.readwrite",
}


def get_access_token(client_id,refresh_token):
    # 记录开始刷新 token 的日志，便于定位卡在哪一步。
    log.info("开始刷新 access_token")
    url = 'https://login.microsoftonline.com/common/oauth2/v2.0/token'
    data = {
        'client_id': client_id,
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token,
    }
    # 初始化最后一次请求异常，便于重试全部失败后返回。
    last_request_exception = None
    # 按设定次数重试 OAuth 刷新，降低代理抖动导致的一次性失败概率。
    for attempt_index in range(1, NETWORK_RETRY_COUNT + 2):
        try:
            # 调用微软 OAuth 接口并显式设置超时时间，避免请求长期挂起。
            response = requests.post(url, data=data, timeout=OAUTH_TIMEOUT_SEC)
            # 请求成功拿到响应后直接跳出重试循环。
            break
        # 捕获请求异常并按是否最后一次决定重试或返回。
        except requests.RequestException as exc:
            # 记录最后一次异常对象，便于循环结束后返回具体原因。
            last_request_exception = exc
            # 非最后一次失败时记录 warning，并等待后重试。
            if attempt_index <= NETWORK_RETRY_COUNT:
                log.warning(
                    "刷新 access_token 请求失败，准备重试",
                    attempt_index=attempt_index,
                    max_attempt=NETWORK_RETRY_COUNT + 1,
                    error_text=str(exc),
                )
                time.sleep(NETWORK_RETRY_BACKOFF_SEC)
                continue
            # 最后一次仍失败时记录完整异常堆栈，便于后续排查网络连通性问题。
            log.exception("刷新 access_token 请求失败")
            return [False, f"刷新 access_token 请求失败：{exc}"]
    else:
        # 理论上不会进入该分支，这里做兜底返回，保证变量存在。
        return [False, f"刷新 access_token 请求失败：{last_request_exception}"]
    # 尝试解析 JSON 响应体，兼容接口异常返回非 JSON 的场景。
    try:
        response_json = response.json()
    # JSON 解析失败时直接返回错误，避免后续 key 读取崩溃。
    except ValueError:
        # 记录响应解析异常，包含状态码便于排查。
        log.error("刷新 access_token 响应非 JSON", status_code=response.status_code)
        return [False, f"刷新 access_token 失败：响应非 JSON（HTTP {response.status_code}）"]
    # 读取接口错误字段，非空表示刷新失败。
    result_status = response_json.get('error')
    if result_status is not None:
        # 读取错误描述，提升返回信息可读性。
        error_desc = response_json.get("error_description", "")
        # 记录刷新失败日志，便于定位具体错误原因。
        log.error("刷新 access_token 失败", error=result_status, error_description=error_desc)
        return [False, f"邮箱状态异常：{result_status}"]
    else:
        # 读取 access_token 字段，若缺失则返回失败。
        new_access_token = response_json.get('access_token', '')
        # 读取 scope 字段，便于后续判断应走 IMAP 还是 Graph。
        scope_text = str(response_json.get("scope", "")).strip()
        # 返回 token 为空时直接报错，避免进入后续 IMAP 步骤才失败。
        if not new_access_token:
            # 记录 token 缺失错误，包含状态码便于排查。
            log.error("刷新 access_token 失败：缺少 access_token", status_code=response.status_code)
            return [False, "刷新 access_token 失败：返回缺少 access_token"]
        # 记录 token 刷新成功日志（不打印 token 本文，避免泄露）。
        log.info("刷新 access_token 成功", scope_text=scope_text or "<empty>")
        # 返回 access_token 与 scope，便于上层做协议选择。
        return [True, new_access_token, scope_text]

def generate_auth_string(email_name,access_token):
    # 按 XOAUTH2 规范拼装认证字符串，供 IMAP authenticate 使用。
    auth_string = f"user={email_name}\1auth=Bearer {access_token}\1\1"
    return auth_string

def _normalize_scope_set(scope_text: str) -> set[str]:
    # 把 scope 文本按空格拆分并统一转小写，便于稳定判断权限。
    return {item.strip().lower() for item in str(scope_text).split() if item.strip()}


def _has_imap_scope(scope_text: str) -> bool:
    # 判断当前 access_token 是否具备 Outlook IMAP 所需权限。
    return IMAP_SCOPE.lower() in _normalize_scope_set(scope_text)


def _has_graph_mail_read_scope(scope_text: str) -> bool:
    # 判断当前 access_token 是否具备 Graph 读取邮件权限。
    return bool(_normalize_scope_set(scope_text) & GRAPH_MAIL_READ_SCOPES)


def _format_graph_person(person_info):
    # 兼容 Graph 的发件人/收件人对象结构，统一转成可读字符串。
    email_address = (person_info or {}).get("emailAddress") or {}
    # 读取展示名。
    name_text = str(email_address.get("name", "")).strip()
    # 读取邮箱地址。
    address_text = str(email_address.get("address", "")).strip()
    # 名称和地址同时存在时按“名称(邮箱)”格式返回。
    if name_text and address_text:
        return f"{name_text}({address_text})"
    # 有地址时优先返回地址。
    if address_text:
        return address_text
    # 否则回退到名称文本。
    return name_text


def _format_graph_datetime(dt_text: str) -> str:
    # Graph 返回 ISO 8601 时间，这里统一格式化成项目现有时间样式。
    normalized_text = str(dt_text).strip()
    # 空值直接返回空串，避免 fromisoformat 报错。
    if not normalized_text:
        return ""
    try:
        # 把 Z 结尾时间显式转成 UTC 偏移，兼容 Python 标准解析。
        dt_value = datetime.fromisoformat(normalized_text.replace("Z", "+00:00"))
        # 输出为项目统一的本地展示格式。
        return dt_value.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        # 非标准格式时原样返回，避免因为格式异常丢失时间信息。
        return normalized_text


def _get_mail_info_by_graph(email_name,access_token):
    # 初始化 Graph 返回列表，用于承接邮件解析结果。
    result_list = []
    # 定义 Graph 邮件读取接口地址，只取最新若干封并保留必要字段。
    url = (
        "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages"
        f"?$top={MAX_FETCH_MAIL_COUNT}"
        "&$orderby=receivedDateTime desc"
        "&$select=subject,from,toRecipients,receivedDateTime,body"
    )
    # 组装 Graph 请求头，要求正文返回 HTML 以兼容现有验证码解析逻辑。
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        'Prefer': 'outlook.body-content-type="html"',
    }
    # 初始化最后一次请求异常，便于重试全部失败后返回。
    last_request_exception = None
    # 对 Graph 请求做轻量重试，降低代理瞬断带来的失败概率。
    for attempt_index in range(1, NETWORK_RETRY_COUNT + 2):
        try:
            # 发起 Graph 请求并设置超时，避免接口异常导致流程卡住。
            response = requests.get(url, headers=headers, timeout=GRAPH_TIMEOUT_SEC)
            # 请求成功拿到响应后跳出重试循环。
            break
        except requests.RequestException as exc:
            # 记录最后一次异常，便于最终返回。
            last_request_exception = exc
            # 非最后一次失败时先记录 warning 再重试。
            if attempt_index <= NETWORK_RETRY_COUNT:
                log.warning(
                    "Graph 邮件拉取请求异常，准备重试",
                    email_name=email_name,
                    attempt_index=attempt_index,
                    max_attempt=NETWORK_RETRY_COUNT + 1,
                    error_text=str(exc),
                )
                time.sleep(NETWORK_RETRY_BACKOFF_SEC)
                continue
            # 最后一次仍失败时记录完整堆栈。
            log.exception("Graph 邮件拉取请求异常", email_name=email_name)
            return {"error_key": "登录失败", "error_msg": f"登录失败，Graph 邮件拉取异常：{exc}"}
    else:
        # 理论兜底：所有重试都未拿到响应时返回最后一次异常。
        return {"error_key": "登录失败", "error_msg": f"登录失败，Graph 邮件拉取异常：{last_request_exception}"}
    try:
        # 解析 Graph JSON 返回体，便于后续读取 value 或 error。
        response_json = response.json()
    except ValueError:
        # 返回非 JSON 时记录错误并返回可读提示。
        log.error("Graph 邮件拉取响应非 JSON", email_name=email_name, status_code=response.status_code)
        return {"error_key": "登录失败", "error_msg": f"登录失败，Graph 邮件拉取返回非 JSON（HTTP {response.status_code}）"}
    # Graph 非 2xx 时优先读取 error message，避免用户只看到笼统状态码。
    if not response.ok:
        # 读取 Graph 标准错误结构。
        error_info = response_json.get("error", {}) if isinstance(response_json, dict) else {}
        # 读取具体错误消息。
        error_msg = str(error_info.get("message", "")).strip() or f"HTTP {response.status_code}"
        # 记录 Graph 拉取失败日志。
        log.error("Graph 邮件拉取失败", email_name=email_name, status_code=response.status_code, error_msg=error_msg)
        return {"error_key": "登录失败", "error_msg": f"登录失败，Graph 邮件拉取失败：{error_msg}"}
    # 读取邮件数组，结构异常时回退为空列表。
    mail_items = response_json.get("value", []) if isinstance(response_json, dict) else []
    # 记录 Graph 拉取成功日志，便于区分协议路径。
    log.info("Graph 邮件拉取成功", email_name=email_name, fetch_count=len(mail_items))
    # 遍历最新邮件，转换成现有解析器兼容结构。
    for item in mail_items:
        # 读取 Graph body 结构。
        body_info = item.get("body") or {}
        # 优先读取 HTML/文本正文内容。
        body_text = str(body_info.get("content", "")).strip()
        # 读取收件人列表并组装为逗号分隔字符串。
        to_list = item.get("toRecipients") or []
        # 转换单个收件人结构。
        mail_to = ",".join(filter(None, (_format_graph_person(person) for person in to_list)))
        # 组装成与 IMAP 解析一致的结构。
        result_list.append(
            {
                "subject": str(item.get("subject", "")).strip(),
                "mail_from": _format_graph_person(item.get("from")),
                "mail_to": mail_to,
                "mail_dt": _format_graph_datetime(item.get("receivedDateTime", "")),
                "body": body_text,
            }
        )
    # 返回标准化后的邮件列表。
    return result_list


def _get_mail_info_by_imap(email_name,access_token):
    # 初始化返回列表，用于承接邮件解析结果。
    result_list = []
    # 初始化最后一次 IMAP 错误对象，便于所有主机都失败时统一返回。
    last_exception = None
    # 遍历候选主机，优先走微软当前推荐主机。
    for host_name in IMAP_HOST_CANDIDATES:
        # 初始化 IMAP 客户端对象，放在 try 外方便 finally 安全 logout。
        mail = None
        try:
            # 记录开始连接日志，便于定位卡点。
            log.info("开始连接 Outlook IMAP", email_name=email_name, timeout_sec=IMAP_TIMEOUT_SEC, host_name=host_name)
            # 建立 IMAP SSL 连接并设置超时，避免网络异常时无限阻塞。
            mail = imaplib.IMAP4_SSL(host_name, timeout=IMAP_TIMEOUT_SEC)
            # 先生成 XOAUTH2 认证字符串。
            auth_string = generate_auth_string(email_name, access_token)
            # 执行 XOAUTH2 认证登录。
            mail.authenticate('XOAUTH2', lambda _: auth_string)
            # 记录认证成功日志，便于定位问题范围。
            log.info("Outlook IMAP 认证成功", email_name=email_name, host_name=host_name)
            # 选择收件箱作为检索目标目录。
            select_result, _ = mail.select('inbox')
            # 选择收件箱失败时直接返回可读错误。
            if select_result != "OK":
                # 记录收件箱选择失败日志。
                log.error("Outlook 收件箱选择失败", email_name=email_name, select_result=select_result, host_name=host_name)
                return {"error_key": "登录失败", "error_msg": "登录失败，收件箱不可用"}
            # 在收件箱检索所有邮件 ID（由上层取最新若干封）。
            result, data = mail.search(None, 'ALL')
            # 检索失败时返回错误信息。
            if result != "OK":
                # 记录检索失败日志，便于排查 IMAP 服务状态。
                log.error("Outlook 邮件检索失败", email_name=email_name, search_result=result, host_name=host_name)
                return {"error_key": "登录失败", "error_msg": "登录失败，邮件检索失败"}
            # 把邮件 ID 按新到旧排序（倒序）以便优先解析最新邮件。
            mail_ids = sorted(data[0].split(), reverse=True)
            # 限制最多抓取最近 N 封，避免大邮箱拉取过慢。
            last_mail_id_list = mail_ids[:MAX_FETCH_MAIL_COUNT]
            # 记录检索完成日志，便于观察邮箱体量与抓取范围。
            log.info(
                "Outlook 邮件检索成功",
                email_name=email_name,
                total_count=len(mail_ids),
                fetch_count=len(last_mail_id_list),
                host_name=host_name,
            )
            # 逐封抓取并解析邮件内容。
            for last_mail_id in last_mail_id_list:
                # 使用 RFC822 拉取完整原始邮件。
                fetch_result, msg_data = mail.fetch(last_mail_id, "(RFC822)")
                # 初始化正文字符串容器。
                body = ""
                # 拉取失败时返回错误信息。
                if fetch_result != 'OK':
                    # 记录抓取失败日志，包含邮件 ID 便于复现。
                    log.error("Outlook 邮件抓取失败", email_name=email_name, mail_id=last_mail_id.decode(errors="ignore"), host_name=host_name)
                    return {"error_key": "解析失败", "error_msg": "邮件信息解析失败，请联系管理员优化处理！"}
                # 解析邮件原始字节内容。
                raw_email = msg_data[0][1]
                # 把原始字节转为 email message 对象。
                email_message = email.message_from_bytes(raw_email)
                # 提取主题文本。
                subject = str(make_header(decode_header(email_message['SUBJECT'])))
                # 提取发件人文本并做括号格式统一。
                mail_from = str(make_header(decode_header(email_message['From']))).replace('<', '(').replace('>', ')')
                # 提取收件人文本并做括号格式统一。
                mail_to = str(make_header(decode_header(email_message['To']))).replace('<', '(').replace('>', ')')
                # 解析邮件时间并格式化为标准字符串。
                mail_dt = parsedate_to_datetime(email_message['Date']).strftime("%Y-%m-%d %H:%M:%S")
                # 多段邮件时遍历所有子段，优先累积 text/html 正文。
                if email_message.is_multipart():
                    for part in email_message.walk():
                        # 读取当前子段 content-type。
                        content_type = part.get_content_type()
                        # 只拼接 HTML 正文段，避免附件噪音。
                        if content_type in ["text/html"]:
                            # 读取并解码当前 HTML 正文子段。
                            payload = part.get_payload(decode=True)
                            # payload 为空时跳过，避免解码报错。
                            if payload is None:
                                continue
                            # 以 utf-8 兜底解码并忽略异常字符。
                            body += payload.decode('utf-8', errors='ignore')
                # 单段邮件时直接读取正文。
                else:
                    # 读取正文 payload 字节。
                    payload = email_message.get_payload(decode=True)
                    # payload 存在时才执行解码。
                    if payload is not None:
                        # 以 utf-8 兜底解码并忽略异常字符。
                        body = payload.decode('utf-8', errors='ignore')
                # 组装当前邮件结构并加入结果列表。
                res_dict = {"subject": subject, "mail_from": mail_from, "mail_to": mail_to, "mail_dt": mail_dt, "body": body}
                result_list.append(res_dict)
            # 全部解析完成后返回结果列表。
            return result_list
        # 捕获 IMAP、超时、网络相关异常并尝试下一个主机。
        except (imaplib.IMAP4.error, TimeoutError, socket.timeout, OSError) as exc:
            # 记录异常堆栈，便于排查认证和网络问题。
            log.exception("Outlook 邮件拉取异常", email_name=email_name, host_name=host_name)
            # 缓存最后一次异常，供所有主机都失败时返回。
            last_exception = exc
        # 无论成功失败都尝试退出 IMAP 会话，避免连接残留。
        finally:
            # 只有 mail 对象存在时才执行 logout。
            if mail is not None:
                try:
                    # 主动退出 IMAP 会话。
                    mail.logout()
                except Exception:
                    # logout 异常不影响主流程返回。
                    pass
    # 所有主机都失败时返回最后一次可读错误。
    return {"error_key": "登录失败", "error_msg": f"登录失败，邮箱连接异常：{last_exception}"}


def get_mail_info(email_name,access_token,access_scope=""):
    # 记录当前 token scope，便于后续排查账号授权问题。
    log.info("准备拉取 Outlook 邮件", email_name=email_name, scope_text=str(access_scope).strip() or "<empty>")
    # 当前 token 没有 IMAP scope，但有 Graph 邮件读取权限时，直接切到 Graph。
    if not _has_imap_scope(access_scope) and _has_graph_mail_read_scope(access_scope):
        # 记录协议切换日志，避免用户只看到 IMAP failed 的表面现象。
        log.warning("当前 token 缺少 IMAP scope，自动切换 Graph 拉取邮件", email_name=email_name)
        # 走 Graph 拉取邮箱内容，兼容 Graph-only 授权邮箱。
        return _get_mail_info_by_graph(email_name, access_token)
    # 当前 token 具备 IMAP scope 时先走 IMAP 读取。
    imap_result = _get_mail_info_by_imap(email_name, access_token)
    # IMAP 成功返回列表时直接结束。
    if isinstance(imap_result, list):
        # 返回 IMAP 拉取结果给调用方。
        return imap_result
    # IMAP 失败且 Graph 也可用时自动切到 Graph，提升兼容性。
    if _has_graph_mail_read_scope(access_scope):
        # 记录 IMAP 失败后的兜底日志，便于定位是协议切换还是彻底失败。
        log.warning("IMAP 拉取失败，自动切换 Graph 继续尝试", email_name=email_name, imap_error=imap_result.get("error_msg", ""))
        # 返回 Graph 拉取结果。
        return _get_mail_info_by_graph(email_name, access_token)
    # Graph 不可用时直接返回 IMAP 错误结果。
    return imap_result


def write_html(mail_info_list, file_path="test.html"):
    """Render mail info into a simple HTML report and open it locally."""
    output_path = Path(file_path).resolve()
    sections = []
    if isinstance(mail_info_list, list):
        for idx, mail_info in enumerate(mail_info_list, start=1):
            sections.append(
                f"""
                <section>
                    <h2>邮件 {idx}</h2>
                    <p><strong>邮件主题：</strong>{mail_info['subject']}</p>
                    <p><strong>发件时间：</strong>{mail_info['mail_dt']}</p>
                    <p><strong>发件人：</strong>{mail_info['mail_from']}</p>
                    <p><strong>收件人：</strong>{mail_info['mail_to']}</p>
                    <div class="body"><strong>邮件正文：</strong>{mail_info['body']}</div>
                </section>
                """
            )
    else:
        sections.append(
            f"""
            <section>
                <h2>错误信息</h2>
                <p>{mail_info_list.get('error_msg', '未知错误')}</p>
            </section>
            """
        )

    html_template = f"""
    <!DOCTYPE html>
    <html lang=\"zh\">
    <head>
        <meta charset=\"UTF-8\">
        <title>Outlook 邮件预览</title>
        <style>
            body {{font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 2rem;}}
            section {{border: 1px solid #e0e0e0; padding: 1rem; margin-bottom: 1.5rem; border-radius: 8px;}}
            .body {{margin-top: 0.5rem; padding: 0.5rem; background-color: #fafafa; border-radius: 4px;}}
        </style>
    </head>
    <body>
        <h1>最新邮件列表</h1>
        {''.join(sections)}
    </body>
    </html>
    """

    output_path.write_text(html_template, encoding="utf-8")
    webbrowser.open(f"file://{output_path}")

if __name__ == '__main__':

    client_id = '9e5f94bc-e8a4-4e73-b8be-63364c29d753'
    email_name = 'DawnGraves2153@hotmail.com'
    refresh_token = 'M.C505_BL2.0.U.-ClSWIDDxhiCKLmG8vpuQRu1yaidcRXOYRMhYT5r8*wY88FSOpWKe5OuIZ6uEyb2KjcVSlx19ac2yRs7td978CciIVQ!SiCLLLuN8nMz1Xw3sCYKWkGoSM8S46FstIEl6O1dUPmVhwEtYROebXnlorGyWq5Uk2rHNSLdVjeZIaYu*4a70OePwVXD6T5GVM9RpZB18r*ct2C22alAO3H59l9ceFlhVmCKlIOK0SlJ8SfY48Khs82FmDP77XgwdhOHHe3Fh9uULFWfi!ZwdEbB*tSiDp7ZhjxqvZGduGgXrjguseCFABWg6TUfhmufWnbQPk4M4BL7qeMCWo!20sX8logNZnVkPEMyLgQ6*BAh2Kj5oAbrYuVYxa!OlSemQy21BQNrfXKciG!amoXQ*lbStUzjOy2H8F6ZC16X84SqfVgkQnc82ZiRph9kLyUUbgzdSOg$$'
    access_res = get_access_token(client_id,refresh_token)
    if access_res[0]:
        access_token = access_res[1]
        mail_info_res = get_mail_info(email_name,access_token)
        write_html(mail_info_res)
    else:
        print(access_res[1])
        
        
        
