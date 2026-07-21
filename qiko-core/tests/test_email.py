from app.modules.email.sender import ConsoleEmailSender, get_email_sender
from app.modules.email.templates import (
    password_reset_code_email,
    password_reset_email,
    verification_email,
)


def test_console_sender_records():
    s = ConsoleEmailSender()
    assert s.send(to="u@qiko.ai", subject="Hi", body="Body") is True
    assert s.sent == [{"to": "u@qiko.ai", "subject": "Hi", "body": "Body", "html": None}]


def test_console_sender_records_html():
    s = ConsoleEmailSender()
    assert s.send(to="u@qiko.ai", subject="Hi", body="Body", html="<p>Body</p>") is True
    assert s.sent[0]["html"] == "<p>Body</p>"


def test_templates_include_link_and_brand():
    subject, body = verification_email("https://qiko.ai/verify?t=abc")
    assert "Qiko" in subject and "https://qiko.ai/verify?t=abc" in body
    subject, body = password_reset_email("https://qiko.ai/reset?t=xyz")
    assert "reset" in subject.lower() and "https://qiko.ai/reset?t=xyz" in body


def test_password_reset_code_email_is_branded_and_complete():
    reset_url = "https://app.qiko.ai/reset-password?email=u%40qiko.ai"
    subject, text_body, html_body = password_reset_code_email(
        "123456", reset_url=reset_url, minutes=10)
    assert subject == "Your Qiko password reset code"
    # plaintext fallback carries the code, expiry and the reset URL
    assert text_body
    assert "123456" in text_body
    assert reset_url in text_body
    assert "10 minutes" in text_body
    # branded HTML carries the code, the reset URL and the brand wordmark
    assert html_body
    assert "123456" in html_body
    assert reset_url in html_body
    assert "Qiko" in html_body
    assert "10 minutes" in html_body
    # no em-dashes anywhere in the rendered copy
    assert "\u2014" not in text_body and "\u2014" not in html_body


def test_default_sender_is_console():
    assert isinstance(get_email_sender(), ConsoleEmailSender)
