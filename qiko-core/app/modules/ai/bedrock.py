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
    # boto3's defaults (60s read timeout x up to 3 retries) mean one slow/unresponsive endpoint
    # can block for minutes before the gateway ever gets to try its fallback provider -- observed
    # live (a 15-requirement tender's answers taking >15 minutes). Fail fast instead: a couple of
    # short retries, then let the caller fall back. 20s is right for the hot path (one small
    # per-requirement answer at a time), but is too tight for a single one-shot call over a whole
    # tender document (extraction/compliance/brief -- see rfp/router.py), which legitimately needs
    # longer to read tens of thousands of chars and produce a complete structured response; those
    # call sites build their own BedrockProvider(read_timeout=...) instead of using this default.
    read_timeout: int = 20

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
        from botocore.config import Config

        config = Config(connect_timeout=5, read_timeout=self.read_timeout,
                        retries={"max_attempts": 2, "mode": "standard"})
        if not hasattr(self, "_cached_client"):
            self._cached_client = boto3.client("bedrock-runtime", region_name=self.region, config=config)
        return self._cached_client

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
