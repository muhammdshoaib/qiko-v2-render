"""Bedrock Nova Sonic speech client (SpeechGateway). Uses boto3 bedrock-runtime; requires AWS
credentials, so the network path is integration-only (not unit-tested)."""
from __future__ import annotations

from app.core.config import get_settings


class NovaSonicSpeech:  # pragma: no cover - requires AWS Bedrock credentials
    def __init__(self, model: str | None = None, region: str | None = None):
        s = get_settings()
        self.model = model or s.voice_model
        self.region = region or s.aws_region

    def _client(self):
        import boto3

        return boto3.client("bedrock-runtime", region_name=self.region)

    def transcribe(self, audio: bytes) -> str:
        resp = self._client().invoke_model(
            modelId=self.model,
            body=audio,
            contentType="audio/wav",
            accept="application/json",
        )
        import json

        return json.loads(resp["body"].read())["transcript"]

    def synthesize(self, text: str) -> bytes:
        import json

        resp = self._client().invoke_model(
            modelId=self.model,
            body=json.dumps({"text": text}),
            contentType="application/json",
            accept="audio/wav",
        )
        return resp["body"].read()
