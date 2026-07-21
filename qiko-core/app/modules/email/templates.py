"""Branded transactional email templates.

Link-based templates return (subject, body). The OTP password-reset template returns
(subject, text_body, html_body): a plaintext fallback plus a table-based, inline-styled HTML
email that renders across Gmail, Outlook, Apple Mail and iOS (no external CSS, no flexbox/grid).
"""
from __future__ import annotations

import html as _html

BRAND = "Qiko"
BRAND_COLOUR = "#4f46e5"  # indigo/violet wordmark + button
INK = "#1f2937"  # dark-on-light body text
MUTED = "#6b7280"  # secondary/footer text


def verification_email(link: str) -> tuple[str, str]:
    return (f"Verify your {BRAND} account",
            f"Welcome to {BRAND}. Confirm your email by visiting:\n\n{link}\n\n"
            f"If you did not sign up, ignore this message.")


def password_reset_email(link: str) -> tuple[str, str]:
    return (f"Reset your {BRAND} password",
            f"We received a request to reset your {BRAND} password. Reset it here:\n\n{link}\n\n"
            f"If you did not request this, ignore this message; your password stays the same.")


def password_reset_code_email(code: str, *, reset_url: str, minutes: int = 10) -> tuple[str, str, str]:
    """Branded, responsive OTP password-reset email.

    Returns (subject, text_body, html_body). The HTML uses a centred, table-based layout with
    inline styles only so it renders consistently across email clients; the plaintext body is the
    fallback for clients that do not render HTML.
    """
    subject = f"Your {BRAND} password reset code"

    text_body = (
        "Hello,\n\n"
        f"We received a request to reset your {BRAND} password. "
        "Use this code to continue:\n\n"
        f"    {code}\n\n"
        f"This code expires in {minutes} minutes.\n\n"
        f"You can also reset your password here:\n{reset_url}\n\n"
        "If you did not request this, you can ignore this email; your password will not change.\n\n"
        f"Thanks,\nThe {BRAND} team"
    )

    code_e = _html.escape(code)
    url_e = _html.escape(reset_url, quote=True)
    html_body = f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="color-scheme" content="light">
<title>{subject}</title>
</head>
<body style="margin:0; padding:0; background-color:#f3f4f6; \
-webkit-text-size-adjust:100%; -ms-text-size-adjust:100%;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" \
style="background-color:#f3f4f6;">
<tr>
<td align="center" style="padding:24px 12px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" \
style="max-width:480px; width:100%; background-color:#ffffff; border-radius:12px; \
border:1px solid #e5e7eb; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,\
Helvetica,Arial,sans-serif;">
<tr>
<td style="padding:32px 32px 8px 32px;">
<span style="font-size:24px; font-weight:700; letter-spacing:-0.5px; \
color:{BRAND_COLOUR};">{BRAND}</span>
</td>
</tr>
<tr>
<td style="padding:8px 32px 0 32px;">
<h1 style="margin:0; font-size:20px; line-height:28px; color:{INK}; \
font-weight:700;">Reset your password</h1>
<p style="margin:12px 0 0 0; font-size:15px; line-height:22px; color:{INK};">
We received a request to reset your {BRAND} password. Enter the code below to continue.
</p>
</td>
</tr>
<tr>
<td style="padding:24px 32px 0 32px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
<tr>
<td align="center" style="border:1px solid #e5e7eb; border-radius:10px; \
background-color:#f9fafb; padding:18px 12px;">
<span style="font-family:'Courier New',Courier,monospace; font-size:32px; \
font-weight:700; letter-spacing:8px; color:{INK};">{code_e}</span>
</td>
</tr>
</table>
<p style="margin:12px 0 0 0; font-size:13px; line-height:20px; color:{MUTED}; \
text-align:center;">This code expires in {minutes} minutes.</p>
</td>
</tr>
<tr>
<td align="center" style="padding:24px 32px 0 32px;">
<table role="presentation" cellpadding="0" cellspacing="0" border="0">
<tr>
<td align="center" style="border-radius:8px; background-color:{BRAND_COLOUR};">
<a href="{url_e}" target="_blank" style="display:inline-block; padding:12px 28px; \
font-size:15px; font-weight:600; color:#ffffff; text-decoration:none; border-radius:8px;">\
Reset password</a>
</td>
</tr>
</table>
</td>
</tr>
<tr>
<td style="padding:24px 32px 0 32px;">
<hr style="border:none; border-top:1px solid #e5e7eb; margin:0;">
<p style="margin:16px 0 0 0; font-size:13px; line-height:20px; color:{MUTED};">
If you did not request this, you can ignore this email; your password will not change.
</p>
</td>
</tr>
<tr>
<td style="padding:16px 32px 32px 32px;">
<p style="margin:0; font-size:12px; line-height:18px; color:{MUTED};">
&copy; {BRAND}. This is an automated message, please do not reply.
</p>
</td>
</tr>
</table>
</td>
</tr>
</table>
</body>
</html>"""

    return subject, text_body, html_body
