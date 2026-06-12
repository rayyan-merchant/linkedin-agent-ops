from datetime import UTC, date, datetime

from linkedin_agent_ops.email_delivery import GmailSender
from linkedin_agent_ops.models import ContentOpportunity, DailyBrief


class FakeSmtp:
    instance = None

    def __init__(self, host, port, timeout):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.login_args = None
        self.message = None
        FakeSmtp.instance = self

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return None

    def login(self, username, password):
        self.login_args = (username, password)

    def send_message(self, message):
        self.message = message


def test_gmail_sender_builds_multipart_message_and_logs_in():
    brief = DailyBrief(
        brief_date=date(2026, 6, 12),
        generated_at=datetime(2026, 6, 12, tzinfo=UTC),
        papers=[],
        trends=[],
        repositories=[],
        opportunity=ContentOpportunity(
            title="Opportunity",
            rationale="A rationale with enough detail.",
            post_angle="A practical production engineering angle.",
        ),
        model_used="deterministic",
    )
    sender = GmailSender(
        username="sender@example.com",
        app_password="secret",
        recipient="reader@example.com",
        sender_name="Daily AI Brief",
        smtp_factory=FakeSmtp,
    )

    sender.send(brief, "plain body", "<p>html body</p>")

    smtp = FakeSmtp.instance
    assert smtp.login_args == ("sender@example.com", "secret")
    assert smtp.message["To"] == "reader@example.com"
    assert smtp.message.is_multipart()

