"""Embeddings behind one interface. Local by default (no external dependency, private, cheap),
Titan V2 on Bedrock as the managed alternative (ADR-009). The pgvector column dimension is pinned
to `embeddings_dim`; changing model is a re-embed migration.
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Protocol

from app.core.config import get_settings
from app.modules.ai import usage


class EmbeddingsProvider(Protocol):
    dim: int

    def embed(self, text: str) -> list[float]: ...


@dataclass
class LocalEmbeddings:
    """Deterministic, dependency-free embedder used for dev/tests and as the local default's
    interface. A sentence-transformers backend slots in behind the same protocol for production
    quality without changing callers."""

    dim: int = 0

    def __post_init__(self) -> None:
        self.dim = self.dim or get_settings().embeddings_dim

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for token in text.lower().split():
            h = int.from_bytes(hashlib.sha256(token.encode()).digest()[:8], "big")
            vec[h % self.dim] += 1.0
        norm = math.sqrt(sum(v * v for v in vec))
        return [v / norm for v in vec] if norm else vec


_TITAN_MODEL_ID = "amazon.titan-embed-text-v2:0"


@dataclass
class TitanEmbeddings:  # pragma: no cover - requires AWS credentials/network
    dim: int = 1024
    region: str = ""

    def __post_init__(self) -> None:
        self.region = self.region or get_settings().aws_region

    def embed(self, text: str) -> list[float]:
        import json

        import boto3

        client = boto3.client("bedrock-runtime", region_name=self.region)
        body = json.dumps({"inputText": text, "dimensions": self.dim, "normalize": True})
        resp = client.invoke_model(modelId=_TITAN_MODEL_ID, body=body)
        payload = json.loads(resp["body"].read())
        # Titan reports inputTextTokenCount and it used to be discarded. Embeddings are billed per
        # input token and an ingest embeds every chunk of every document, so this is a real cost line
        # rather than a rounding error.
        usage.record(_TITAN_MODEL_ID, "embed",
                     input_tokens=int(payload.get("inputTextTokenCount") or 0))
        return payload["embedding"]


def get_embeddings() -> EmbeddingsProvider:
    s = get_settings()
    if s.embeddings_provider == "titan":  # pragma: no cover - prod path
        return TitanEmbeddings(dim=s.embeddings_dim)
    return LocalEmbeddings(dim=s.embeddings_dim)
