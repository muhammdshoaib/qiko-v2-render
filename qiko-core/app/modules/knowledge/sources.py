"""Structured agent knowledge sources: behaviors, FAQs, policies, websites, and the agent persona.

Each source is rendered to text and ingested into the vector store under a DETERMINISTIC doc_id
({agent}-{kind}-{id}), so updating re-ingests the same doc_id and deleting removes exactly that
source's chunks. This is a typed layer over KnowledgeService (chunk/embed/store)."""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Awaitable, Callable

from app.modules.knowledge.parsing import UnsupportedDocumentError, extract_text
from app.modules.knowledge.service import KnowledgeService
from app.modules.sales_intelligence.ssrf import SsrfError, assert_public_url

_MD = re.compile(r"!?\[[^\]]*\]\([^)]*\)")


def _strip_markdown_links(text: str) -> str:
    return _MD.sub("", text or "")


def _doc_id(agent: str, kind: str, source_id: str) -> str:
    return f"{agent}-{kind}-{source_id}"


FetchUrl = Callable[[str], Awaitable[str]]


class WebsiteFetchError(ValueError):
    """Fetching or extracting a website for knowledge ingestion failed."""


@dataclass
class KnowledgeSources:
    knowledge: KnowledgeService
    fetch_url: FetchUrl | None = None

    async def _default_fetch_url(self, url: str) -> str:
        import httpx

        try:
            assert_public_url(url)
        except SsrfError as e:
            raise WebsiteFetchError(str(e)) from e
        try:
            resp = await asyncio.to_thread(httpx.get, url, timeout=20.0, follow_redirects=False,
                                            headers={"User-Agent": "Mozilla/5.0 (compatible; QikoBot/1.0)"})
            resp.raise_for_status()
        except httpx.HTTPError as e:
            raise WebsiteFetchError(f"could not fetch that URL: {e}") from e
        content_type = resp.headers.get("content-type", "")
        filename = ("page.pdf" if "pdf" in content_type else "page.docx" if "officedocument" in content_type
                    else "page.html" if "html" in content_type or not content_type else (url.rsplit("/", 1)[-1] or "page.html"))
        try:
            return extract_text(filename, resp.content)
        except UnsupportedDocumentError as e:
            raise WebsiteFetchError(str(e)) from e

    async def _fetch_url(self, url: str) -> str:
        if self.fetch_url is not None:
            return await self.fetch_url(url)
        return await self._default_fetch_url(url)

    async def _upsert(self, tenant: str, agent: str, kind: str, source_id: str, text: str) -> str:
        doc_id = _doc_id(agent, kind, source_id)
        # Scope the source to its owning worker (QIK-315) so it is retrieved only in that worker's chat.
        await self.knowledge.delete_document(tenant, doc_id, agent_id=agent)  # idempotent re-ingest
        await self.knowledge.ingest(tenant, doc_id, text, agent_id=agent)
        return doc_id

    async def add_behavior(self, tenant: str, agent: str, source_id: str, behavior: str) -> str:
        return await self._upsert(tenant, agent, "behavior", source_id, behavior)

    async def add_faq(self, tenant: str, agent: str, source_id: str, question: str, answer: str) -> str:
        return await self._upsert(tenant, agent, "faq", source_id, f"Q: {question}\nA: {answer}")

    async def add_policy(self, tenant: str, agent: str, source_id: str, title: str, body: str) -> str:
        return await self._upsert(tenant, agent, "policy", source_id, f"{title}\n{body}")

    async def add_website(self, tenant: str, agent: str, source_id: str, name: str, url: str, details: str) -> str:
        content = await self._fetch_url(url)
        text = f"{name}\n{url}\n\n{content.strip()}"
        stripped = _strip_markdown_links(details).strip()
        if stripped:
            text += f"\n\nAdditional details:\n{stripped}"
        return await self._upsert(tenant, agent, "website", source_id, text)

    async def set_persona(self, tenant: str, agent: str, fields: dict) -> str:
        text = "\n".join(f"{k}: {v}" for k, v in fields.items() if v)
        return await self._upsert(tenant, agent, "persona", "core", text)

    async def delete_source(self, tenant: str, agent: str, kind: str, source_id: str) -> int:
        return await self.knowledge.delete_document(tenant, _doc_id(agent, kind, source_id), agent_id=agent)
