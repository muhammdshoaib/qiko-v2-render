"""Transactional email senders. Console backend for dev/tests (records what would be sent),
SMTP backend for prod. Sending runs on a worker (see tasks.jobs.send_email)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from app.core.config import get_settings


class EmailSender(Protocol):
    def send(self, *, to: str, subject: str, body: str, html: str | None = None) -> bool: ...


@dataclass
class ConsoleEmailSender:
    sent: list[dict] = field(default_factory=list)

    def send(self, *, to: str, subject: str, body: str, html: str | None = None) -> bool:
        self.sent.append({"to": to, "subject": subject, "body": body, "html": html})
        return True


@dataclass
class SmtpEmailSender:  # pragma: no cover - requires an SMTP server
    host: str = ""
    port: int = 0
    sender: str = ""
    user: str = ""
    password: str = ""
    use_tls: bool = True

    def __post_init__(self) -> None:
        s = get_settings()
        self.host = self.host or s.smtp_host
        self.port = self.port or s.smtp_port
        self.sender = self.sender or s.email_from
        self.user = self.user or s.smtp_user
        self.password = self.password or s.smtp_password

    def send(self, *, to: str, subject: str, body: str, html: str | None = None) -> bool:
        import smtplib
        from email.message import EmailMessage

        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = self.sender, to, subject
        msg.set_content(body)  # plaintext fallback
        if html is not None:
            msg.add_alternative(html, subtype="html")  # branded HTML for capable clients
        with smtplib.SMTP(self.host, self.port) as smtp:
            if self.use_tls:
                smtp.starttls()
            if self.user:
                smtp.login(self.user, self.password)
            smtp.send_message(msg)
        return True


def get_email_sender() -> EmailSender:
    if get_settings().email_backend == "smtp":  # pragma: no cover - prod path
        return SmtpEmailSender()
    return ConsoleEmailSender()
