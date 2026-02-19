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
import requests
import webbrowser
from pathlib import Path
from email.utils import parsedate_to_datetime
from email.header import decode_header, make_header


def get_access_token(client_id,refresh_token):
    url = 'https://login.microsoftonline.com/common/oauth2/v2.0/token'
    data = {
        'client_id': client_id,
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token,
    }
    response = requests.post(url, data=data)
    result_status = response.json().get('error')
    if result_status is not None:
        print(result_status)
        return [False, f"邮箱状态异常：{result_status}"]
    else:
        new_access_token = response.json()['access_token']
        return [True, new_access_token]

def generate_auth_string(email_name,access_token):
    auth_string = f"user={email_name}\1auth=Bearer {access_token}\1\1"
    print(auth_string)
    return auth_string

def get_mail_info(email_name,access_token):
    result_list = []
    mail = imaplib.IMAP4_SSL('outlook.live.com')
    mail.authenticate('XOAUTH2', lambda x: generate_auth_string(email_name, access_token))
    mail.select('inbox') #选择收件箱
    # mail.select('Junk')  #选择垃圾箱
    result, data = mail.search(None, 'ALL')
    if result == "OK":
        mail_ids = sorted(data[0].split(), reverse=True)
        last_mail_id_list = mail_ids[:3]
        for last_mail_id in last_mail_id_list:
            result, msg_data = mail.fetch(last_mail_id, "(RFC822)")
            body = ""
            if result == 'OK':
                # 解析邮件内容
                raw_email = msg_data[0][1]
                email_message = email.message_from_bytes(raw_email)
                subject = str(make_header(decode_header(email_message['SUBJECT'])))  # 主题
                mail_from = str(make_header(decode_header(email_message['From']))).replace('<', '(').replace('>',
                                                                                                             ')')  # 发件人
                mail_to = str(make_header(decode_header(email_message['To']))).replace('<', '(').replace('>',
                                                                                                         ')')  # 收件人
                mail_dt = parsedate_to_datetime(email_message['Date']).strftime("%Y-%m-%d %H:%M:%S")  # 收件时间
                if email_message.is_multipart():
                    for part in email_message.walk():
                        content_type = part.get_content_type()
                        if content_type in ["text/html"]:
                            payload = part.get_payload(decode=True)
                            body += payload.decode('utf-8', errors='ignore')

                else:
                    body = email_message.get_payload(decode=True).decode('utf-8', errors='ignore')
                res_dict = {"subject": subject, "mail_from": mail_from, "mail_to": mail_to, "mail_dt": mail_dt,
                            "body": body}
                result_list.append(res_dict)
            else:
                res_dict = {"error_key": "解析失败", "error_msg": "邮件信息解析失败，请联系管理员优化处理！"}
                return res_dict
        return result_list
    else:
        res_dict = {"error_key": "登录失败", "error_msg": "登录失败，账号异常!"}
        return res_dict


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
    email_name = 'KendraMurphy9734@hotmail.com'
    refresh_token = 'M.C534_BAY.0.U.-CqacvkJwzOLWtfU8KNmlluwsg0Fxw5S09j5NTs5lhRxWoRDhr*5jl0ReH1LZaIySiNYiVR8MXGNBL1!*Mtn86scOWgDtu0s9j2XOjLFFbkzl6j!IdkzdPFRl!VXJOEeOc4HB9wmdKQELWfSfGlynouueRulwBOXNzrcn4jPxRfo7xf5zTsksDcW32XFHxa6C0dEIDFAyC11y8g*1LxW0D6h4dlLg4nINEhhWIKJq9qvXmQgpKY2!6cmHz0s!!RujAzolwwaMEDzFtv7PR6abtPadWCGGe3r1BuL4LrO7pLjm5h9gdkMgwIkRO6DJMrIgkp9v5IXwsQAplXS9rz6si8zuByp6haj!9Adm7teYaoBSq8ZxvlYqyh1a1JxYloI1w57uBkpjiDflAPyHTaCM0SJgzltwiLCesESjh1Sc6A0VpIfyu!V6B5nW3li4PJlbtw$$'
    access_res = get_access_token(client_id,refresh_token)
    if access_res[0]:
        access_token = access_res[1]
        mail_info_res = get_mail_info(email_name,access_token)
        write_html(mail_info_res)
    else:
        print(access_res[1])
        
        
        
