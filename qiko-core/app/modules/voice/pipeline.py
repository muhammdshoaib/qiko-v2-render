"""Bedrock-native voice pipeline (Amazon Nova Sonic) replacing Vapi/Whisper/ElevenLabs.

Flow: audio -> STT -> agentcore grounded answer (terse voice profile) -> TTS -> audio. Agentic-first:
the reply comes from the worker's agentcore (generator/critic/gate), NOT a direct model call, so a
voice answer is grounded and gated exactly like a text answer.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.modules.workers.worker import Worker


class SpeechGateway(Protocol):
    def transcribe(self, audio: bytes) -> str: ...
    def synthesize(self, text: str) -> bytes: ...


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

    async def speak(self, worker: Worker, conversation_id: str, audio: bytes, *, topic: str | None = None) -> VoiceResult:
        transcript = self.speech.transcribe(audio)
        result = await worker.answer(conversation_id, transcript, topic=topic)  # agentcore, grounded + gated
        answer = _terse(result.answer)
        return VoiceResult(transcript=transcript, answer=answer, audio=self.speech.synthesize(answer))


def web_call_config(*, model: str, region: str) -> dict:
    """Config the browser voice widget needs (no secrets): Bedrock Nova Sonic model + region."""
    return {"provider": "bedrock-nova-sonic", "model": model, "region": region}
