"""AWS Bedrock (Claude) provider.

The model id is resolved from config: an inference-profile prefix (eu/us/jp/au) routes across a
geography for data residency and throughput; "global" uses global cross-Region; "" keeps it
in-Region. This is the only place that knows about Bedrock, so agentcore stays provider-agnostic.
The network call is thin and exercised in integration, not unit tests.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.core.config import get_settings
from app.modules.ai.gateway import LLMResponse

_PROFILES = {"eu", "us", "jp", "au"}


def resolve_model_id(model: str, profile: str) -> str:
    """Prefix the base model with the inference-profile geography where applicable.

    eu.anthropic.claude-... (geo) | global.anthropic.claude-... | anthropic.claude-... (in-Region)
    """
    profile = (profile or "").strip().lower()
    if profile in _PROFILES:
        return f"{profile}.{model}"
    if profile == "global":
        return f"global.{model}"
    return model  # in-Region


@dataclass
class BedrockProvider:
    model: str = ""
    profile: str = ""
    region: str = ""

    def __post_init__(self) -> None:
        s = get_settings()
        self.model = self.model or s.bedrock_model
        self.profile = self.profile or s.bedrock_inference_profile
        self.region = self.region or s.aws_region

    @property
    def model_id(self) -> str:
        return resolve_model_id(self.model, self.profile)

    def _client(self):  # pragma: no cover - requires AWS credentials/network
        import boto3

        return boto3.client("bedrock-runtime", region_name=self.region)

    def generate(self, prompt: str, *, system: str | None = None, temperature: float = 0.2) -> LLMResponse:  # pragma: no cover - network
        messages = [{"role": "user", "content": [{"text": prompt}]}]
        kwargs = {
            "modelId": self.model_id,
            "messages": messages,
            "inferenceConfig": {"temperature": temperature},
        }
        if system:
            kwargs["system"] = [{"text": system}]
        resp = self._client().converse(**kwargs)
        text = resp["output"]["message"]["content"][0]["text"]
        return LLMResponse(text=text, model=self.model_id)
