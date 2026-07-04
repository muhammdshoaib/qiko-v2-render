"""Structured agent knowledge sources: behaviors, FAQs, policies, websites, and the agent persona.

Each source is rendered to text and ingested into the vector store under a DETERMINISTIC doc_id
({agent}-{kind}-{id}), so updating re-ingests the same doc_id and deleting removes exactly that
source's chunks. This is a typed layer over KnowledgeService (chunk/embed/store)."""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.modules.knowledge.service import KnowledgeService

_MD = re.compile(r"!?\[[^\]]*\]\([^)]*\)")


def _strip_markdown_links(text: str) -> str:
    return _MD.sub("", text or "")


def _doc_id(agent: str, kind: str, source_id: str) -> str:
    return f"{agent}-{kind}-{source_id}"


@dataclass
class KnowledgeSources:
    knowledge: KnowledgeService

    async def _upsert(self, tenant: str, agent: str, kind: str, source_id: str, text: str) -> str:
        doc_id = _doc_id(agent, kind, source_id)
        await self.knowledge.delete_document(tenant, doc_id)  # re-ingest cleanly (idempotent update)
        await self.knowledge.ingest(tenant, doc_id, text)
        return doc_id

    async def add_behavior(self, tenant: str, agent: str, source_id: str, behavior: str) -> str:
        return await self._upsert(tenant, agent, "behavior", source_id, behavior)

    async def add_faq(self, tenant: str, agent: str, source_id: str, question: str, answer: str) -> str:
        return await self._upsert(tenant, agent, "faq", source_id, f"Q: {question}\nA: {answer}")

    async def add_policy(self, tenant: str, agent: str, source_id: str, title: str, body: str) -> str:
        return await self._upsert(tenant, agent, "policy", source_id, f"{title}\n{body}")

    async def add_website(self, tenant: str, agent: str, source_id: str, name: str, url: str, details: str) -> str:
        text = f"{name}\n{url}\n{_strip_markdown_links(details)}"
        return await self._upsert(tenant, agent, "website", source_id, text)

    async def set_persona(self, tenant: str, agent: str, fields: dict) -> str:
        text = "\n".join(f"{k}: {v}" for k, v in fields.items() if v)
        return await self._upsert(tenant, agent, "persona", "core", text)

    async def delete_source(self, tenant: str, agent: str, kind: str, source_id: str) -> int:
        return await self.knowledge.delete_document(tenant, _doc_id(agent, kind, source_id))
