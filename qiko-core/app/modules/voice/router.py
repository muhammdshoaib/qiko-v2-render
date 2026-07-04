"""Voice HTTP API (tenant-scoped, agentic-first): audio -> STT -> agentcore -> TTS."""
from __future__ import annotations

import base64

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.core.deps import build_tenant_worker, get_voice, authed_tenant

router = APIRouter(prefix="/voice", tags=["voice"])


class SpeakBody(BaseModel):
    conversation_id: str = Field(min_length=1)
    audio_b64: str = Field(min_length=1)
    topic: str | None = None


@router.post("/speak")
async def speak(body: SpeakBody, request: Request, tenant: str = Depends(authed_tenant), pipeline=Depends(get_voice)) -> dict:
    worker = build_tenant_worker(request, tenant)
    result = await pipeline.speak(worker, body.conversation_id, base64.b64decode(body.audio_b64), topic=body.topic)
    return {"transcript": result.transcript, "answer": result.answer,
            "audio_b64": base64.b64encode(result.audio).decode()}


@router.get("/web-call-config")
def web_call_config_route(_tenant: str = Depends(authed_tenant)) -> dict:
    from app.core.config import get_settings
    from app.modules.voice.pipeline import web_call_config

    s = get_settings()
    return web_call_config(model=s.voice_model, region=s.aws_region)
