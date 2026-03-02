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
import requests
import webbrowser
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
# 定义每次最多抓取最新邮件数量，默认取近 3 封用于验证码解析。
MAX_FETCH_MAIL_COUNT = 3


def get_access_token(client_id,refresh_token):
    # 记录开始刷新 token 的日志，便于定位卡在哪一步。
    log.info("开始刷新 access_token")
    url = 'https://login.microsoftonline.com/common/oauth2/v2.0/token'
    data = {
        'client_id': client_id,
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token,
    }
    # 调用微软 OAuth 接口并显式设置超时时间，避免请求长期挂起。
    try:
        response = requests.post(url, data=data, timeout=OAUTH_TIMEOUT_SEC)
    # 捕获请求异常并返回可读错误，避免抛出长堆栈影响调用体验。
    except requests.RequestException as exc:
        # 记录异常日志，便于后续排查网络连通性问题。
        log.exception("刷新 access_token 请求失败")
        return [False, f"刷新 access_token 请求失败：{exc}"]
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
        # 返回 token 为空时直接报错，避免进入后续 IMAP 步骤才失败。
        if not new_access_token:
            # 记录 token 缺失错误，包含状态码便于排查。
            log.error("刷新 access_token 失败：缺少 access_token", status_code=response.status_code)
            return [False, "刷新 access_token 失败：返回缺少 access_token"]
        # 记录 token 刷新成功日志（不打印 token 本文，避免泄露）。
        log.info("刷新 access_token 成功")
        return [True, new_access_token]

def generate_auth_string(email_name,access_token):
    # 按 XOAUTH2 规范拼装认证字符串，供 IMAP authenticate 使用。
    auth_string = f"user={email_name}\1auth=Bearer {access_token}\1\1"
    return auth_string

def get_mail_info(email_name,access_token):
    # 初始化返回列表，用于承接邮件解析结果。
    result_list = []
    # 初始化 IMAP 客户端对象，放在 try 外方便 finally 安全 logout。
    mail = None
    # 进入网络操作流程：连接、认证、检索、抓取、解析。
    try:
        # 记录开始连接日志，便于定位卡点。
        log.info("开始连接 Outlook IMAP", email_name=email_name, timeout_sec=IMAP_TIMEOUT_SEC)
        # 建立 IMAP SSL 连接并设置超时，避免网络异常时无限阻塞。
        mail = imaplib.IMAP4_SSL('outlook.live.com', timeout=IMAP_TIMEOUT_SEC)
        # 先生成 XOAUTH2 认证字符串。
        auth_string = generate_auth_string(email_name, access_token)
        # 执行 XOAUTH2 认证登录。
        mail.authenticate('XOAUTH2', lambda _: auth_string)
        # 记录认证成功日志，便于定位问题范围。
        log.info("Outlook IMAP 认证成功", email_name=email_name)
        # 选择收件箱作为检索目标目录。
        select_result, _ = mail.select('inbox')
        # 选择收件箱失败时直接返回可读错误。
        if select_result != "OK":
            # 记录收件箱选择失败日志。
            log.error("Outlook 收件箱选择失败", email_name=email_name, select_result=select_result)
            return {"error_key": "登录失败", "error_msg": "登录失败，收件箱不可用"}
        # 在收件箱检索所有邮件 ID（由上层取最新若干封）。
        result, data = mail.search(None, 'ALL')
        # 检索失败时返回错误信息。
        if result != "OK":
            # 记录检索失败日志，便于排查 IMAP 服务状态。
            log.error("Outlook 邮件检索失败", email_name=email_name, search_result=result)
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
                log.error("Outlook 邮件抓取失败", email_name=email_name, mail_id=last_mail_id.decode(errors="ignore"))
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
    # 捕获 IMAP、超时、网络相关异常并返回可读错误。
    except (imaplib.IMAP4.error, TimeoutError, socket.timeout, OSError) as exc:
        # 记录异常堆栈，便于排查认证和网络问题。
        log.exception("Outlook 邮件拉取异常", email_name=email_name)
        return {"error_key": "登录失败", "error_msg": f"登录失败，邮箱连接异常：{exc}"}
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
        
        
        
