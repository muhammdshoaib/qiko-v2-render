"""CRM / Sales Pipeline: real contacts derived from a worker's own conversation history, plus
manual follow-up actions -- what the "CRM" tab in the creator UI shows.

This replaces a client-side mock in the earlier qiko-frontend build (`getCrmData` returned
reshaped chat history with a hardcoded status and a canned summary, or literally hardcoded
sample contacts when no agent id was passed). Every worker gets this for free -- there is
nothing IDG- or "Sales"-worker-specific here; the pipeline stages, AI summary and follow-up
actions apply the same way to any worker a prospect has talked to.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol

from app.modules.ai.gateway import LLMProvider
from app.modules.chat.service import ChatService

PIPELINE_STAGES = ("new", "contacted", "interested", "quoted", "converted", "lost")
_VALID_ACTION_STATUSES = ("pending", "done", "dismissed")

_SUMMARY_SYSTEM = (
    "You are a sales assistant. Read this chat transcript between a prospect and an AI worker "
    "and return ONLY a JSON object (no prose, no markdown fences) with keys: "
    '"summary" (2-3 sentences on the prospect\'s intent and where the conversation left off), '
    '"sentiment" (one of "positive", "neutral", "negative", "mixed"), and '
    '"key_topics" (a short array of up to 5 topics/keywords the prospect asked about).'
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class CrmError(Exception):
    pass


@dataclass
class Contact:
    id: str
    tenant: str
    agent_id: str
    conversation_id: str | None = None
    name: str = "Anonymous"
    email: str | None = None
    phone: str | None = None
    status: str = "new"
    estimated_value: int = 0
    currency: str = "USD"
    ai_summary: str | None = None
    sentiment: str | None = None
    key_topics: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)


@dataclass
class CrmAction:
    id: str
    tenant: str
    contact_id: str
    title: str
    action_type: str = "custom"
    description: str = ""
    priority: str = "normal"
    status: str = "pending"
    created_at: datetime = field(default_factory=_now)


class ContactStore(Protocol):
    async def get(self, tenant: str, contact_id: str) -> Contact | None: ...
    async def get_by_conversation(self, tenant: str, agent_id: str, conversation_id: str) -> Contact | None: ...
    async def add(self, contact: Contact) -> Contact: ...
    async def update(self, contact: Contact) -> Contact: ...
    async def list_for_agent(self, tenant: str, agent_id: str) -> list[Contact]: ...


class ActionStore(Protocol):
    async def get(self, tenant: str, action_id: str) -> CrmAction | None: ...
    async def add(self, action: CrmAction) -> CrmAction: ...
    async def list_for_contact(self, tenant: str, contact_id: str) -> list[CrmAction]: ...
    async def update_status(self, tenant: str, action_id: str, status: str) -> CrmAction | None: ...


@dataclass
class InMemoryContactStore:
    _by_id: dict[str, Contact] = field(default_factory=dict)

    async def get(self, tenant: str, contact_id: str) -> Contact | None:
        c = self._by_id.get(contact_id)
        return c if c and c.tenant == tenant else None

    async def get_by_conversation(self, tenant: str, agent_id: str, conversation_id: str) -> Contact | None:
        for c in self._by_id.values():
            if c.tenant == tenant and c.agent_id == agent_id and c.conversation_id == conversation_id:
                return c
        return None

    async def add(self, contact: Contact) -> Contact:
        self._by_id[contact.id] = contact
        return contact

    async def update(self, contact: Contact) -> Contact:
        self._by_id[contact.id] = contact
        return contact

    async def list_for_agent(self, tenant: str, agent_id: str) -> list[Contact]:
        return [c for c in self._by_id.values() if c.tenant == tenant and c.agent_id == agent_id]


@dataclass
class InMemoryActionStore:
    _by_id: dict[str, CrmAction] = field(default_factory=dict)

    async def get(self, tenant: str, action_id: str) -> CrmAction | None:
        action = self._by_id.get(action_id)
        return action if action is not None and action.tenant == tenant else None

    async def add(self, action: CrmAction) -> CrmAction:
        self._by_id[action.id] = action
        return action

    async def list_for_contact(self, tenant: str, contact_id: str) -> list[CrmAction]:
        return [a for a in self._by_id.values() if a.tenant == tenant and a.contact_id == contact_id]

    async def update_status(self, tenant: str, action_id: str, status: str) -> CrmAction | None:
        a = self._by_id.get(action_id)
        if not a or a.tenant != tenant:
            return None
        a.status = status
        return a


@dataclass
class CrmService:
    chat: ChatService
    contacts: ContactStore = None  # type: ignore[assignment]
    actions: ActionStore = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.contacts is None:
            self.contacts = InMemoryContactStore()
        if self.actions is None:
            self.actions = InMemoryActionStore()

    async def _sync_contacts_from_conversations(self, tenant: str, agent_id: str) -> None:
        """Lazily create a Contact for every conversation this agent has that doesn't have one
        yet -- so the pipeline always reflects real chat activity without a separate ingestion
        step. Never overwrites a contact a human has already edited."""
        for convo in await self.chat.list_for_agent(tenant, agent_id):
            if not convo.crm_eligible:
                continue
            existing = await self.contacts.get_by_conversation(tenant, agent_id, convo.id)
            if existing:
                continue
            await self.contacts.add(Contact(
                id=uuid.uuid4().hex[:12], tenant=tenant, agent_id=agent_id,
                conversation_id=convo.id, created_at=convo.created_at or _now(),
            ))

    async def list_pipeline(self, tenant: str, agent_id: str) -> dict:
        await self._sync_contacts_from_conversations(tenant, agent_id)
        contacts = await self.contacts.list_for_agent(tenant, agent_id)
        contacts.sort(key=lambda c: c.updated_at, reverse=True)
        breakdown: dict[str, int] = {}
        for c in contacts:
            breakdown[c.status] = breakdown.get(c.status, 0) + 1
        return {
            "contacts": contacts, "total": len(contacts),
            "dashboard": {"status_breakdown": breakdown},
        }

    async def get_detail(self, tenant: str, contact_id: str) -> dict:
        contact = await self.contacts.get(tenant, contact_id)
        if not contact:
            raise CrmError("contact not found")
        timeline: list[dict] = []
        if contact.conversation_id:
            for m in await self.chat.history(tenant, contact.conversation_id, limit=0):
                timeline.append({
                    "type": "text_chat", "role": m.role,
                    "title": "Chat with AI worker" if m.role == "user" else "Worker replied",
                    "summary": m.text, "timestamp": m.created_at,
                })
        actions = await self.actions.list_for_contact(tenant, contact_id)
        message_count = sum(1 for t in timeline if t["role"] == "user")
        return {
            "contact": contact, "timeline": timeline, "actions": actions, "bookings": [],
            "stats": {"message_count": message_count, "voice_call_count": 0, "email_count": 0},
        }

    async def update_contact(self, tenant: str, contact_id: str, *, name: str | None = None,
                             email: str | None = None, phone: str | None = None,
                             status: str | None = None, estimated_value: int | None = None) -> Contact:
        contact = await self.contacts.get(tenant, contact_id)
        if not contact:
            raise CrmError("contact not found")
        if status is not None and status not in PIPELINE_STAGES:
            raise CrmError(f"invalid pipeline stage: {status}")
        if name is not None:
            contact.name = name
        if email is not None:
            contact.email = email
        if phone is not None:
            contact.phone = phone
        if status is not None:
            contact.status = status
        if estimated_value is not None:
            contact.estimated_value = estimated_value
        contact.updated_at = _now()
        return await self.contacts.update(contact)

    async def generate_summary(self, tenant: str, contact_id: str, provider: LLMProvider,
                               recheck_worker=None) -> Contact:
        """Summarize the contact's conversation with an LLM -- intent, sentiment, key topics."""
        import asyncio
        import json
        import re

        async def recheck() -> None:
            if recheck_worker is not None:
                await recheck_worker()

        await recheck()
        contact = await self.contacts.get(tenant, contact_id)
        if not contact:
            raise CrmError("contact not found")
        if not contact.conversation_id:
            raise CrmError("this contact has no linked conversation to summarize")
        messages = await self.chat.history(tenant, contact.conversation_id, limit=0)
        if not messages:
            raise CrmError("no messages to summarize yet")
        transcript = "\n".join(f"{m.role}: {m.text}" for m in messages)
        await recheck()
        try:
            response = await asyncio.to_thread(
                provider.generate, f"TRANSCRIPT:\n{transcript}",
                system=_SUMMARY_SYSTEM, temperature=0.0)
        finally:
            await recheck()
        match = re.search(r"\{.*\}", response.text, re.DOTALL)
        try:
            parsed = json.loads(match.group(0) if match else response.text)
        except (json.JSONDecodeError, AttributeError) as e:
            raise CrmError(f"model did not return valid JSON: {e}") from e
        contact.ai_summary = str(parsed.get("summary", "")).strip() or contact.ai_summary
        contact.sentiment = parsed.get("sentiment") or contact.sentiment
        contact.key_topics = list(parsed.get("key_topics") or contact.key_topics)
        contact.updated_at = _now()
        await recheck()
        return await self.contacts.update(contact)

    async def add_action(self, tenant: str, contact_id: str, *, title: str, action_type: str = "custom",
                         description: str = "", priority: str = "normal") -> CrmAction:
        contact = await self.contacts.get(tenant, contact_id)
        if not contact:
            raise CrmError("contact not found")
        action = CrmAction(id=uuid.uuid4().hex[:12], tenant=tenant, contact_id=contact_id,
                           title=title, action_type=action_type, description=description, priority=priority)
        return await self.actions.add(action)

    async def get_action(self, tenant: str, action_id: str) -> CrmAction | None:
        return await self.actions.get(tenant, action_id)

    async def update_action_status(self, tenant: str, action_id: str, status: str) -> CrmAction:
        if status not in _VALID_ACTION_STATUSES:
            raise CrmError(f"invalid action status: {status}")
        action = await self.actions.update_status(tenant, action_id, status)
        if not action:
            raise CrmError("action not found")
        return action
