"""Anonymous and authenticated consent audit endpoints."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from app.modules.consent.models import (
    COOKIES_RELEASE_ID,
    PRIVACY_RELEASE_ID,
    TERMS_RELEASE_ID,
    ConsentChoices,
    ConsentRecord,
)
from app.modules.consent.service import ConsentService
from app.modules.identity import csrf
from app.modules.identity.router import current_user
from app.modules.identity.store import User

router = APIRouter(prefix="/consent", tags=["consent"])


class ConsentChoicesBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision_id: str = Field(min_length=8, max_length=128)
    client_revision: int = Field(gt=0)
    terms_release_id: Literal[TERMS_RELEASE_ID]
    privacy_release_id: Literal[PRIVACY_RELEASE_ID]
    cookies_release_id: Literal[COOKIES_RELEASE_ID]
    preferences: bool
    analytics: bool
    marketing: bool


class AnonymousConsentBody(ConsentChoicesBody):
    anonymous_id: str = Field(min_length=16, max_length=256)


def get_consent(request: Request) -> ConsentService:
    return request.app.state.consent


def _response(record: ConsentRecord) -> dict:
    return {
        "id": record.id,
        "decision_id": record.decision_id,
        "revision": record.revision,
        "client_revision": record.client_revision,
        "preferences": record.preferences,
        "analytics": record.analytics,
        "marketing": record.marketing,
        "source": record.source,
        "action": record.action,
        "terms_release_id": record.terms_release_id,
        "privacy_release_id": record.privacy_release_id,
        "cookies_release_id": record.cookies_release_id,
        "created_at": record.created_at,
    }


@router.post("/anonymous", status_code=201)
async def record_anonymous(
    body: AnonymousConsentBody,
    service: ConsentService = Depends(get_consent),
) -> dict:
    try:
        record = await service.record(
            namespace="anonymous",
            identifier=body.anonymous_id,
            choices=ConsentChoices(body.preferences, body.analytics, body.marketing),
            source="anonymous",
            decision_id=body.decision_id,
            client_revision=body.client_revision,
            terms_release_id=body.terms_release_id,
            privacy_release_id=body.privacy_release_id,
            cookies_release_id=body.cookies_release_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _response(record)


@router.get("/anonymous")
async def get_anonymous(
    anonymous_id: str = Query(min_length=16, max_length=256),
    service: ConsentService = Depends(get_consent),
) -> dict:
    record = await service.latest(namespace="anonymous", identifier=anonymous_id)
    if record is None:
        raise HTTPException(status_code=404, detail="consent record not found")
    return _response(record)


@router.post("", status_code=201)
async def record_authenticated(
    request: Request,
    body: ConsentChoicesBody,
    user: User = Depends(current_user),
    service: ConsentService = Depends(get_consent),
) -> dict:
    csrf.require_csrf(request)
    try:
        record = await service.record(
            namespace="user",
            identifier=user.id,
            choices=ConsentChoices(body.preferences, body.analytics, body.marketing),
            source="authenticated",
            decision_id=body.decision_id,
            client_revision=body.client_revision,
            terms_release_id=body.terms_release_id,
            privacy_release_id=body.privacy_release_id,
            cookies_release_id=body.cookies_release_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _response(record)


@router.get("")
async def get_authenticated(
    user: User = Depends(current_user),
    service: ConsentService = Depends(get_consent),
) -> dict:
    record = await service.latest(namespace="user", identifier=user.id)
    if record is None:
        raise HTTPException(status_code=404, detail="consent record not found")
    return _response(record)


@router.get("/policy-releases")
async def policy_releases(service: ConsentService = Depends(get_consent)) -> list[dict]:
    releases = await service.store.list_policy_releases()
    return [
        {
            "id": release.id,
            "policy_type": release.policy_type,
            "content_sha256": release.content_sha256,
            "effective_at": release.effective_at,
        }
        for release in releases
    ]
