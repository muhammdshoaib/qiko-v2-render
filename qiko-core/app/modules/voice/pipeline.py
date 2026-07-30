"""Bedrock-native voice pipeline (Amazon Nova Sonic) replacing Vapi/Whisper/ElevenLabs.

Flow: audio -> STT -> agentcore grounded answer (terse voice profile) -> TTS -> audio. Agentic-first:
the reply comes from the worker's agentcore (generator/critic/gate), NOT a direct model call, so a
voice answer is grounded and gated exactly like a text answer.
"""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

from app.modules.workers.worker import Worker

WorkerRecheck = Callable[[], Awaitable[None]]


class SpeechUnavailable(Exception):
    pass


class SpeechGateway(Protocol):
    def transcribe(self, audio: bytes) -> str: ...
    def synthesize(self, text: str) -> bytes: ...


class UnavailableSpeechGateway:
    def transcribe(self, _audio: bytes) -> str:
        raise SpeechUnavailable

    def synthesize(self, _text: str) -> bytes:
        raise SpeechUnavailable


def _terse(text: str, *, max_chars: int = 400) -> str:
    """Voice answers are short; trim to a sentence-ish window for TTS."""
    text = " ".join(text.split())
    return text if len(text) <= max_chars else text[:max_chars].rsplit(" ", 1)[0] + "..."


@dataclass
class VoiceResult:
    transcript: str
    answer: str
    audio: bytes


@dataclass
class VoicePipeline:
    speech: SpeechGateway

    async def speak(self, worker: Worker, conversation_id: str, audio: bytes, *,
                    topic: str | None = None,
                    recheck_worker: WorkerRecheck | None = None) -> VoiceResult:
        async def recheck() -> None:
            if recheck_worker is not None:
                await recheck_worker()

        await recheck()
        transcript = await asyncio.to_thread(self.speech.transcribe, audio)
        await recheck()
        result = await worker.answer(
            conversation_id, transcript, topic=topic, recheck_worker=recheck_worker)
        await recheck()
        answer = _terse(result.answer)
        await recheck()
        audio_out = await asyncio.to_thread(self.speech.synthesize, answer)
        await recheck()
        return VoiceResult(transcript=transcript, answer=answer, audio=audio_out)


def web_call_config(*, model: str, region: str) -> dict:
    """Config the browser voice widget needs (no secrets): Bedrock Nova Sonic model + region."""
    return {"provider": "bedrock-nova-sonic", "model": model, "region": region}
