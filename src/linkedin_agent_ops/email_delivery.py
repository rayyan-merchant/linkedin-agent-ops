from __future__ import annotations

import smtplib
from email.message import EmailMessage

from linkedin_agent_ops.models import DailyBrief


class GmailSender:
    def __init__(
        self,
        *,
        username: str,
        app_password: str,
        recipient: str,
        sender_name: str,
        smtp_factory=smtplib.SMTP_SSL,
    ) -> None:
        self.username = username
        self.app_password = app_password
        self.recipient = recipient
        self.sender_name = sender_name
        self.smtp_factory = smtp_factory

    def send(self, brief: DailyBrief, text_body: str, html_body: str) -> None:
        message = EmailMessage()
        message["Subject"] = f"Daily AI Brief - {brief.brief_date.isoformat()}"
        message["From"] = f"{self.sender_name} <{self.username}>"
        message["To"] = self.recipient
        message.set_content(text_body)
        message.add_alternative(html_body, subtype="html")

        with self.smtp_factory("smtp.gmail.com", 465, timeout=30) as smtp:
            smtp.login(self.username, self.app_password)
            smtp.send_message(message)

