"""Public /contact endpoint (WEB-1030): the website's contact form, forwarded to a human inbox.

Public like the labs-contact form in router.py: no auth dependency, no tenant exists for a
prospect. Unlike labs-contact the caller only sees success after the sender has accepted the
message, so this returns 502 rather than claiming success on a refused send.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.modules.email.sender import EmailSender, get_email_sender
from app.modules.marketing.router import _EMAIL_RE

router = APIRouter(tags=["marketing"])

logger = logging.getLogger(__name__)

TOPICS = ("general", "labs", "signal")


class ContactBody(BaseModel):
    # All optional so every failure is a deliberate 400 from the handler below; FastAPI/Pydantic
    # would otherwise answer 422, which the published contract for this endpoint does not use.
    topic: str | None = None
    name: str | None = None
    email: str | None = None
    message: str | None = None


def _invalid(field: str) -> HTTPException:
    return HTTPException(status_code=400, detail=f"invalid or missing field: {field}")


@router.post("/contact")
async def contact(body: ContactBody, email_sender: EmailSender = Depends(get_email_sender)) -> dict:
    """Forward a /contact submission to the configured inbox. Transactional only: no list, no
    subscription, no lead record."""
    if body.topic not in TOPICS:
        raise _invalid("topic")
    if body.name is None or not (1 <= len(body.name.strip()) <= 120):
        raise _invalid("name")
    if body.email is None or len(body.email) > 254 or not _EMAIL_RE.match(body.email.strip()):
        raise _invalid("email")
    if body.message is None or not (1 <= len(body.message) <= 4000):
        raise _invalid("message")

    settings = get_settings()
    body_text = (
        f"New contact form submission\n\n"
        f"Topic: {body.topic}\n"
        f"Name: {body.name.strip()}\n"
        f"Reply to: {body.email.strip()}\n\n"
        f"{body.message}\n"
    )
    # The house pattern sends mail from a worker job (tasks.jobs.send_email), but a queued job
    # cannot tell this caller whether the delivery service accepted the message, and the ticket
    # requires reporting success only after acceptance -- so the send runs here, in a threadpool
    # because SmtpEmailSender.send is synchronous and must not block the event loop
    # (smtp_timeout_seconds bounds it).
    try:
        sent = await run_in_threadpool(
            email_sender.send,
            to=settings.contact_inbox,
            subject=f"Qiko contact form ({body.topic})",
            body=body_text,
        )
    except Exception as exc:
        logger.warning("contact_email_failed", extra={"topic": body.topic})
        raise HTTPException(status_code=502, detail="message could not be delivered") from exc
    if not sent:
        logger.warning("contact_email_failed", extra={"topic": body.topic})
        raise HTTPException(status_code=502, detail="message could not be delivered")
    logger.info("contact_email_sent", extra={"topic": body.topic})
    return {"status": "sent"}
