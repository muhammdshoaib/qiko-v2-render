"""Uploaded documents for the Intelligence Worker: domain, in-memory store and service."""
from __future__ import annotations

import asyncio
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol

from app.modules.intelligence.models import Signal
from app.modules.knowledge.parsing import MAX_UPLOAD_BYTES, UnsupportedDocumentError, extract_text
from app.modules.knowledge.service import KnowledgeService
from app.tasks.queue import EagerTaskQueue

logger = logging.getLogger(__name__)

SUPPORTED_DOCUMENT_EXTENSIONS = {
    "txt", "md", "csv", "json", "jsonl", "pdf", "docx", "xlsx", "xls", "html", "htm"
}


def sanitize_filename(filename: str) -> str:
    import posixpath

    base = posixpath.basename((filename or "").replace("\\", "/")).lstrip(".")
    return re.sub(r"[^A-Za-z0-9._-]+", "-", base).strip("-") or "file"


@dataclass
class Document:
    doc_id: str
    tenant: str
    agent_id: str
    filename: str
    content_type: str
    size: int
    storage_key: str
    status: str = "uploading"
    error_message: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class DocumentNotFound(Exception):
    pass


class DocumentStore(Protocol):
    async def add(self, doc: Document) -> None: ...

    async def get(self, tenant: str, agent_id: str, doc_id: str) -> Document | None: ...

    async def list(self, tenant: str, agent_id: str) -> list[Document]: ...

    async def update(self, doc: Document) -> None: ...

    async def delete(self, tenant: str, agent_id: str, doc_id: str) -> bool: ...


class InMemoryDocumentStore:
    def __init__(self) -> None:
        self._docs: list[Document] = []

    async def add(self, doc: Document) -> None:
        self._docs.append(doc)

    async def get(self, tenant: str, agent_id: str, doc_id: str) -> Document | None:
        for d in self._docs:
            if d.tenant == tenant and d.agent_id == agent_id and d.doc_id == doc_id:
                return d
        return None

    async def list(self, tenant: str, agent_id: str) -> list[Document]:
        return [d for d in self._docs if d.tenant == tenant and d.agent_id == agent_id]

    async def update(self, doc: Document) -> None:
        for i, d in enumerate(self._docs):
            if d.tenant == doc.tenant and d.agent_id == doc.agent_id and d.doc_id == doc.doc_id:
                self._docs[i] = doc
                return

    async def delete(self, tenant: str, agent_id: str, doc_id: str) -> bool:
        before = len(self._docs)
        self._docs = [
            d for d in self._docs
            if not (d.tenant == tenant and d.agent_id == agent_id and d.doc_id == doc_id)
        ]
        return len(self._docs) < before


def _refs_in_text(text: str) -> list[str]:
    """Pull out plausible work-item refs (ticket keys, PR numbers) from a document.

    Correlation uses the first one found; a brief with many refs still gets cited.
    """
    ticket = re.search(r"\b[A-Z]{2,6}-\d{2,6}\b", text)
    if ticket:
        return [ticket.group(0)]
    pr = re.search(r"\b(?:PR|pull request)?#?\s*(\d{2,6})\b", text, re.IGNORECASE)
    if pr:
        return [f"#{pr.group(1)}"]
    return []


class DocumentService:
    def __init__(
        self,
        *,
        document_store: DocumentStore,
        knowledge: KnowledgeService,
        signal_store,
        storage,
        task_queue=None,
    ) -> None:
        self.document_store = document_store
        self.knowledge = knowledge
        self.signal_store = signal_store
        self.storage = storage
        self.task_queue = task_queue

    async def upload(
        self,
        *,
        tenant: str,
        agent_id: str,
        filename: str,
        content_type: str,
        data: bytes,
        actor: str,
    ) -> Document:
        if len(data) > MAX_UPLOAD_BYTES:
            raise ValueError(f"file exceeds maximum size of {MAX_UPLOAD_BYTES} bytes")
        if not any(filename.lower().endswith(f".{ext}") for ext in SUPPORTED_DOCUMENT_EXTENSIONS):
            raise UnsupportedDocumentError(f"unsupported document type for {filename}")

        doc_id = uuid.uuid4().hex
        storage_key = f"{tenant}/uploads/{doc_id}-{sanitize_filename(filename)}"
        await self._put(storage_key, data, content_type)

        doc = Document(
            doc_id=doc_id,
            tenant=tenant,
            agent_id=agent_id,
            filename=filename,
            content_type=content_type,
            size=len(data),
            storage_key=storage_key,
        )
        await self.document_store.add(doc)
        if self.task_queue is None:
            raise RuntimeError("task queue required for document upload")
        task_kwargs = {
            "tenant": tenant,
            "agent_id": agent_id,
            "doc_id": doc_id,
            "storage_key": storage_key,
            "filename": filename,
            "content_type": content_type,
            "actor": actor,
        }
        if isinstance(self.task_queue, EagerTaskQueue):
            task_kwargs["document_service"] = self
        await self.task_queue.enqueue("process_uploaded_document", **task_kwargs)
        return doc

    async def process(self, *, tenant: str, agent_id: str, doc_id: str,
                      storage_key: str, filename: str, actor: str) -> None:
        doc = await self.document_store.get(tenant, agent_id, doc_id)
        if doc is None:
            raise DocumentNotFound(doc_id)
        try:
            data = await asyncio.to_thread(self.storage.get, tenant, storage_key)
            text = await asyncio.to_thread(extract_text, filename, data)
            await self.knowledge.ingest(tenant, doc_id, text, agent_id=agent_id)

            refs = _refs_in_text(text)
            signal = Signal(
                tenant=tenant,
                agent_id=agent_id,
                source="upload",
                kind="document",
                external_id=doc_id,
                container=doc_id,
                actor=actor,
                title=filename,
                body=text[:4000],
                occurred_at=datetime.now(timezone.utc),
                ref=refs[0] if refs else None,
                tags=[],
            )
            await self.signal_store.add(signal)

            doc.status = "ready"
            doc.error_message = None
            doc.updated_at = datetime.now(timezone.utc)
        except Exception as exc:
            doc.status = "error"
            doc.error_message = str(exc)[:255]
            doc.updated_at = datetime.now(timezone.utc)
            await self.document_store.update(doc)
            logger.exception("document processing failed for %s/%s/%s", tenant, agent_id, doc_id)
            return
        await self.document_store.update(doc)

    async def list(self, tenant: str, agent_id: str) -> list[Document]:
        docs = await self.document_store.list(tenant, agent_id)
        return sorted(docs, key=lambda d: d.updated_at, reverse=True)

    async def delete(self, tenant: str, agent_id: str, doc_id: str) -> bool:
        doc = await self.document_store.get(tenant, agent_id, doc_id)
        if doc is None:
            return False
        await self._delete_object(tenant, doc.storage_key)
        await self.knowledge.delete_document(tenant, doc_id, agent_id=agent_id)
        await self.signal_store.clear(tenant, agent_id, source="upload", container=doc_id)
        return await self.document_store.delete(tenant, agent_id, doc_id)

    async def _put(self, key: str, data: bytes, content_type: str) -> str:
        from app.modules.storage.backend import assert_tenant_scoped

        tenant = key.split("/", 1)[0]
        assert_tenant_scoped(tenant, key)
        return await asyncio.to_thread(self.storage.put, tenant, key, data, content_type)

    async def _delete_object(self, tenant: str, key: str) -> None:
        try:
            await asyncio.to_thread(self.storage.delete, tenant, key)
        except Exception:
            logger.exception("failed to delete storage object %s for tenant %s", key, tenant)
