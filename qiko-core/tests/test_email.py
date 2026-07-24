import struct
from pathlib import Path

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


def test_password_reset_code_email_is_branded_complete_and_escapes_dynamic_content():
    code = "12<34&56"
    reset_url = 'https://app.qiko.ai/reset-password?next="><script>alert(1)</script>'
    minutes = "10<script>"
    subject, text_body, html_body = password_reset_code_email(
        code, reset_url=reset_url, minutes=minutes
    )

    assert subject == "Your Qiko password reset code"
    assert text_body
    assert code in text_body
    assert reset_url not in text_body
    expected_instruction = (
        "We received a request to reset your Qiko password. Please enter the code below into the "
        "platform to reset your password."
    )
    assert expected_instruction in text_body
    assert f"{minutes} minutes" in text_body
    assert html_body
    assert expected_instruction in html_body
    assert "12&lt;34&amp;56" in html_body
    assert code not in html_body
    assert reset_url not in html_body
    assert "<a " not in html_body
    assert "10&lt;script&gt; minutes" in html_body
    assert "<script>" not in html_body
    assert "\u2014" not in subject + text_body + html_body


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
    assert 'owner&quot;&gt;&lt;img src=x onerror=alert(1)&gt;@qiko.ai' in html_body
    assert html_body.count("<img ") == 1
    assert '<table role="presentation"' in html_body
    assert "accept" not in signup_url
    assert "\u2014" not in subject + text_body + html_body


def test_branded_email_html_uses_the_remote_png_logo_and_keeps_plaintext_complete():
    emails = (
        welcome_email(login_url="https://app.qiko.ai/login"),
        team_invite_email(
            signup_url="https://app.qiko.ai/signup?invite=signed-token",
            invited_email="new.person@example.test",
            role_label="Admin",
            workspace="Qiko workspace",
            inviter_email="owner@qiko.ai",
        ),
        password_reset_code_email(
            "123456",
            reset_url="https://app.qiko.ai/reset-password?email=u%40qiko.ai",
            minutes=10,
        ),
    )

    for subject, text_body, html_body in emails:
        assert '<img src="https://qiko.ai/qiko-logo-email.png"' in html_body
        assert 'alt="Qiko"' in html_body
        assert 'width="140"' in html_body
        assert "display:block" in html_body
        assert "data:image" not in html_body.lower()
        assert "cid:" not in html_body.lower()
        assert "https://qiko.ai/qiko-logo-email.png?" not in html_body
        assert text_body.strip()
        assert "Qiko" in text_body
        if subject == "Your Qiko password reset code":
            assert "https://app.qiko.ai/" not in text_body
            assert "<a " not in html_body
        else:
            assert "https://app.qiko.ai/" in text_body
        assert "\u2014" not in subject + text_body + html_body


def test_email_logo_asset_is_an_optimised_transparent_png():
    asset = (
        Path(__file__).resolve().parents[2]
        / "frontend"
        / "apps"
        / "creator"
        / "public"
        / "qiko-logo-email.png"
    )
    data = asset.read_bytes()
    width, height = struct.unpack(">II", data[16:24])

    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    assert 180 <= width <= 220
    assert height > 0
    assert data[25] in (4, 6)
    assert len(data) < 80 * 1024


def test_default_sender_is_console():
    assert isinstance(get_email_sender(), ConsoleEmailSender)
