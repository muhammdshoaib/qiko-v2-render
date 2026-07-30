import ssl

from app.modules.email.sender import SmtpEmailSender


def test_smtp_starttls_uses_verified_default_context(monkeypatch):
    calls = {}

    class Smtp:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def starttls(self, *, context):
            calls["context"] = context

        def login(self, user, password):
            pass

        def send_message(self, message):
            pass

        def noop(self):
            calls["noop"] = True
            return 250, b"ok"

    monkeypatch.setattr("smtplib.SMTP", Smtp)
    sender = SmtpEmailSender(host="smtp.example.test", port=587,
                             sender="sender" + "@" + "example.test")
    assert sender.check_connection() is True and calls["noop"] is True
    assert sender.send(to="recipient" + "@" + "example.test", subject="Subject", body="Body")
    assert isinstance(calls["context"], ssl.SSLContext)
    assert calls["context"].verify_mode == ssl.CERT_REQUIRED
    assert calls["context"].check_hostname is True
