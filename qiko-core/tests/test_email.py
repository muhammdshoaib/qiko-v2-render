from app.modules.email.sender import ConsoleEmailSender, get_email_sender
from app.modules.email.templates import password_reset_email, verification_email


def test_console_sender_records():
    s = ConsoleEmailSender()
    assert s.send(to="u@qiko.ai", subject="Hi", body="Body") is True
    assert s.sent == [{"to": "u@qiko.ai", "subject": "Hi", "body": "Body"}]


def test_templates_include_link_and_brand():
    subject, body = verification_email("https://qiko.ai/verify?t=abc")
    assert "Qiko" in subject and "https://qiko.ai/verify?t=abc" in body
    subject, body = password_reset_email("https://qiko.ai/reset?t=xyz")
    assert "reset" in subject.lower() and "https://qiko.ai/reset?t=xyz" in body


def test_default_sender_is_console():
    assert isinstance(get_email_sender(), ConsoleEmailSender)
