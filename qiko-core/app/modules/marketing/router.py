"""Public marketing-site forms (no auth -- these run before a prospect has a tenant).

Distinct from app.modules.leads, which captures leads a *tenant's own* AI worker collects
from its end-users; this module is for prospects contacting Qiko itself.
"""
from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator

from fastapi import APIRouter

from app.core.config import get_settings
from app.modules.email.sender import get_email_sender

router = APIRouter(prefix="/marketing", tags=["marketing"])

_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class LabsContactBody(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    work_email: str = Field(min_length=3, max_length=200)
    company: str = Field(min_length=1, max_length=200)
    company_size: str = Field(min_length=1, max_length=50)
    build_request: str = Field(min_length=1, max_length=4000)

    @field_validator("work_email")
    @classmethod
    def _check_email(cls, v: str) -> str:
        if not _EMAIL_RE.match(v.strip()):
            raise ValueError("must be a valid email address")
        return v.strip()


@router.post("/labs-contact")
def labs_contact(body: LabsContactBody) -> dict:
    """The /labs 'talk to Qiko Labs' form. Forwards straight to support -- no DB record, no
    tenant context exists yet for a prospect who hasn't signed up."""
    settings = get_settings()
    to = settings.labs_contact_email or settings.email_from
    body_text = (
        f"New Qiko Labs inquiry\n\n"
        f"Name: {body.name}\n"
        f"Work email: {body.work_email}\n"
        f"Company: {body.company}\n"
        f"Company size: {body.company_size}\n\n"
        f"What they want to build:\n{body.build_request}\n"
    )
    get_email_sender().send(to=to, subject=f"Qiko Labs inquiry from {body.company}", body=body_text)
    return {"success": True, "message": "Qiko Labs inquiry submitted successfully."}
