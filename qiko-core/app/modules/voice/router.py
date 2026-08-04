"""Voice HTTP API (tenant-scoped, agentic-first): audio -> STT -> agentcore -> TTS."""
from __future__ import annotations

import base64
import binascii

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.deps import authed_tenant, get_voice, resolve_tenant_worker

router = APIRouter(prefix="/voice", tags=["voice"])


class SpeakBody(BaseModel):
    conversation_id: str = Field(min_length=1)
    audio_b64: str = Field(min_length=1)
    topic: str | None = None
    agent_id: str = Field(min_length=1)


@router.post("/speak")
async def speak(body: SpeakBody, request: Request, tenant: str = Depends(authed_tenant), pipeline=Depends(get_voice)) -> dict:
    worker, recheck = await resolve_tenant_worker(request, tenant, body.agent_id)
    try:
        audio = base64.b64decode(body.audio_b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=422, detail="audio_b64 is not valid base64") from exc
    result = await pipeline.speak(
        worker, body.conversation_id, audio,
        topic=body.topic, recheck_worker=recheck)
    await recheck()
    return {"transcript": result.transcript, "answer": result.answer,
            "audio_b64": base64.b64encode(result.audio).decode()}


@router.get("/web-call-config")
def web_call_config_route(_tenant: str = Depends(authed_tenant)) -> dict:
    from app.core.config import get_settings
    from app.modules.voice.pipeline import web_call_config

    s = get_settings()
    return web_call_config(model=s.voice_model, region=s.aws_region)
