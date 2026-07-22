"""Branded transactional email templates.

Legacy link templates return ``(subject, body)``. Branded templates return
``(subject, text_body, html_body)`` with a plaintext fallback and table-based, inline-styled HTML
for broad email-client compatibility. Dynamic content is escaped inside the layout helper.
"""
from __future__ import annotations

import html as _html

BRAND = "Qiko"
BRAND_COLOUR = "#4f46e5"  # indigo/violet wordmark + button
INK = "#1f2937"  # dark-on-light body text
MUTED = "#6b7280"  # secondary/footer text


def _branded_action_html(
    *,
    subject: str,
    heading: str,
    paragraphs: tuple[str, ...],
    cta_label: str,
    cta_url: str,
    details: tuple[tuple[str, str], ...] = (),
    steps: tuple[str, ...] = (),
    security_notice: str,
) -> str:
    """Render trusted structure while escaping every supplied text and URL value."""
    escape = _html.escape
    paragraph_rows = "".join(
        f'<p style="margin:12px 0 0 0; font-size:15px; line-height:22px; color:{INK};">'
        f"{escape(paragraph)}</p>"
        for paragraph in paragraphs
    )
    detail_rows = "".join(
        '<tr><td style="padding:5px 12px 5px 0; font-size:13px; line-height:20px; '
        f'color:{MUTED}; white-space:nowrap;">{escape(label)}</td>'
        '<td style="padding:5px 0; font-size:13px; line-height:20px; '
        f'color:{INK}; word-break:break-word;">{escape(value)}</td></tr>'
        for label, value in details
    )
    details_block = (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        'style="margin-top:20px; border-top:1px solid #e5e7eb; border-bottom:1px solid #e5e7eb; '
        f'padding:10px 0;">{detail_rows}</table>'
        if details
        else ""
    )
    step_rows = "".join(
        '<tr><td valign="top" style="padding:5px 10px 5px 0; font-size:14px; line-height:21px; '
        f'font-weight:700; color:{BRAND_COLOUR};">{index}.</td>'
        '<td style="padding:5px 0; font-size:14px; line-height:21px; '
        f'color:{INK};">{escape(step)}</td></tr>'
        for index, step in enumerate(steps, start=1)
    )
    steps_block = (
        '<p style="margin:22px 0 6px 0; font-size:14px; line-height:21px; '
        f'font-weight:700; color:{INK};">Next steps</p>'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">'
        f"{step_rows}</table>"
        if steps
        else ""
    )
    return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="color-scheme" content="light">
<title>{escape(subject)}</title>
</head>
<body style="margin:0; padding:0; background-color:#f3f4f6; -webkit-text-size-adjust:100%; \
-ms-text-size-adjust:100%;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" \
style="background-color:#f3f4f6;">
<tr>
<td align="center" style="padding:24px 12px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" \
style="max-width:520px; width:100%; background-color:#ffffff; border-radius:12px; \
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
<h1 style="margin:0; font-size:22px; line-height:30px; color:{INK}; font-weight:700;">\
{escape(heading)}</h1>
{paragraph_rows}
{details_block}
{steps_block}
</td>
</tr>
<tr>
<td align="center" style="padding:26px 32px 0 32px;">
<table role="presentation" cellpadding="0" cellspacing="0" border="0">
<tr>
<td align="center" style="border-radius:8px; background-color:{BRAND_COLOUR};">
<a href="{escape(cta_url)}" target="_blank" style="display:inline-block; padding:12px 28px; \
font-size:15px; font-weight:600; color:#ffffff; text-decoration:none; border-radius:8px;">\
{escape(cta_label)}</a>
</td>
</tr>
</table>
</td>
</tr>
<tr>
<td style="padding:24px 32px 0 32px;">
<hr style="border:none; border-top:1px solid #e5e7eb; margin:0;">
<p style="margin:16px 0 0 0; font-size:13px; line-height:20px; color:{MUTED};">\
{escape(security_notice)}</p>
<p style="margin:10px 0 0 0; font-size:13px; line-height:20px; color:{MUTED};">\
Need help? Contact support@qiko.ai.</p>
</td>
</tr>
<tr>
<td style="padding:16px 32px 32px 32px;">
<p style="margin:0; font-size:12px; line-height:18px; color:{MUTED};">\
&copy; {BRAND}. This is an automated security message, please do not reply.</p>
</td>
</tr>
</table>
</td>
</tr>
</table>
</body>
</html>"""


def password_reset_email(link: str) -> tuple[str, str]:
    return (f"Reset your {BRAND} password",
            f"We received a request to reset your {BRAND} password. Reset it here:\n\n{link}\n\n"
            f"If you did not request this, ignore this message; your password stays the same.")


def welcome_email(*, login_url: str) -> tuple[str, str, str]:
    """Welcome a newly created account without including any credentials."""
    subject = f"Welcome to {BRAND}"
    security_notice = (
        "For your security, Qiko will never ask you to share sign-in credentials or security codes "
        "by email."
    )
    text_body = (
        "Hello,\n\n"
        "Welcome to Qiko. Your account is ready, and you can now sign in to your workspace.\n\n"
        f"Open Qiko:\n{login_url}\n\n"
        "Next steps:\n"
        "1. Sign in with the email address used to create your account.\n"
        "2. Complete your workspace setup.\n"
        "3. Create your first Qiko worker.\n\n"
        "Need help? Contact support@qiko.ai.\n\n"
        f"Security: {security_notice}\n\n"
        "Thanks,\nThe Qiko team"
    )
    html_body = _branded_action_html(
        subject=subject,
        heading="Welcome to Qiko",
        paragraphs=(
            "Your account is ready, and you can now sign in to your workspace.",
            "Qiko helps your team build and run secure AI workers for everyday work.",
        ),
        cta_label="Open Qiko",
        cta_url=login_url,
        steps=(
            "Sign in with the email address used to create your account.",
            "Complete your workspace setup.",
            "Create your first Qiko worker.",
        ),
        security_notice=security_notice,
    )
    return subject, text_body, html_body


def team_invite_email(
    *,
    signup_url: str,
    invited_email: str,
    role_label: str | None = None,
    workspace: str | None = None,
    inviter_email: str | None = None,
) -> tuple[str, str, str]:
    """Invite a person through the signed, single-use pending-role flow."""
    subject = f"You have been invited to {BRAND}"
    context = f" join the {workspace} workspace" if workspace else " join a workspace"
    inviter = f" by {inviter_email}" if inviter_email else ""
    explanation = f"You have been invited{inviter} to{context} on Qiko."
    guidance = (
        "Use the secure invitation link below and create your Qiko account with the same email "
        "address shown here. Your workspace and role will be applied automatically."
    )
    detail_values = [("Invited email", invited_email)]
    if role_label:
        detail_values.append(("Role", role_label))
    if workspace:
        detail_values.append(("Workspace", workspace))
    if inviter_email:
        detail_values.append(("Invited by", inviter_email))
    text_details = "\n".join(f"{label}: {value}" for label, value in detail_values)
    security_notice = (
        "For your security, only continue if you recognise the inviter or workspace. Qiko will "
        "never ask you to share sign-in credentials or security codes by email."
    )
    text_body = (
        f"Hello,\n\n{explanation}\n\n{guidance}\n\n{text_details}\n\n"
        f"Create your Qiko account:\n{signup_url}\n\n"
        "Need help? Contact support@qiko.ai.\n\n"
        f"Security: {security_notice}\n\n"
        "Thanks,\nThe Qiko team"
    )
    html_body = _branded_action_html(
        subject=subject,
        heading="You are invited to Qiko",
        paragraphs=(explanation, guidance),
        cta_label="Create Qiko account",
        cta_url=signup_url,
        details=tuple(detail_values),
        steps=(
            "Open the secure invitation link.",
            "Create an account with the same email address as this invitation.",
            "Sign in to access the workspace with the assigned role.",
        ),
        security_notice=security_notice,
    )
    return subject, text_body, html_body


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
