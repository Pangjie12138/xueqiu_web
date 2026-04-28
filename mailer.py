"""
邮件发送模块
SMTP 配置从环境变量读取
"""
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header

SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.qq.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "465"))
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "")
SMTP_AUTH_CODE = os.environ.get("SMTP_AUTH_CODE", "")


def send_email(to: str, subject: str, body: str, is_html: bool = True) -> bool:
    """发送邮件给单个收件人"""
    if not SENDER_EMAIL or not SMTP_AUTH_CODE:
        print("[WARN] 邮件配置不完整，跳过发送")
        return False

    msg = MIMEMultipart()
    msg["From"] = f"雪球调仓监控 <{SENDER_EMAIL}>"
    msg["To"] = to
    msg["Subject"] = Header(subject, "utf-8")

    content_type = "html" if is_html else "plain"
    msg.attach(MIMEText(body, content_type, "utf-8"))

    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30) as server:
            server.login(SENDER_EMAIL, SMTP_AUTH_CODE)
            server.sendmail(SENDER_EMAIL, [to], msg.as_string())
        return True
    except Exception as e:
        print(f"[ERROR] 发送邮件到 {to} 失败: {e}")
        return False
