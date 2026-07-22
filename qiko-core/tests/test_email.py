from app.modules.email.sender import ConsoleEmailSender, get_email_sender
from app.modules.email.templates import (
    password_reset_code_email,
    password_reset_email,
    team_invite_email,
    welcome_email,
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


def test_welcome_email_is_branded_responsive_and_escapes_its_link():
    login_url = 'https://app.qiko.ai/login?next="><script>alert(1)</script>'
    subject, text_body, html_body = welcome_email(login_url=login_url)

    assert subject == "Welcome to Qiko"
    assert "Welcome to Qiko" in html_body
    assert "account is ready" in text_body
    assert login_url in text_body
    assert "support@qiko.ai" in text_body and "support@qiko.ai" in html_body
    assert "security" in text_body.lower() and "security" in html_body.lower()
    assert "<script>" not in html_body
    assert "&quot;&gt;&lt;script&gt;" in html_body
    assert '<table role="presentation"' in html_body
    assert "@media" not in html_body and "<script" not in html_body
    assert "password" not in (text_body + html_body).lower()
    assert "\u2014" not in text_body and "\u2014" not in html_body


def test_team_invite_email_has_real_signup_guidance_and_escaped_context():
    signup_url = "https://preprod.qiko.ai/signup"
    subject, text_body, html_body = team_invite_email(
        signup_url=signup_url,
        invited_email="new.person@example.test",
        role_label="Admin<script>",
        workspace="IDG & Partners",
        inviter_email='owner"><img src=x onerror=alert(1)>@qiko.ai',
    )

    assert subject == "You have been invited to Qiko"
    assert signup_url in text_body and signup_url in html_body
    assert "new.person@example.test" in text_body and "new.person@example.test" in html_body
    assert "same email address" in text_body and "same email address" in html_body
    assert "IDG & Partners" in text_body and "IDG &amp; Partners" in html_body
    assert "Admin<script>" in text_body and "Admin&lt;script&gt;" in html_body
    assert "<img" not in html_body and "&lt;img" in html_body
    assert '<table role="presentation"' in html_body
    assert "accept" not in signup_url
    assert "\u2014" not in text_body and "\u2014" not in html_body


def test_default_sender_is_console():
    assert isinstance(get_email_sender(), ConsoleEmailSender)
