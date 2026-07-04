"""RFP / proposal document evaluation.

Evaluates a stored document against a set of criteria, agentic-first: the answer comes from
agentcore (grounded generator + independent critic + gate), never a direct model call. Section
relevance filtering (token overlap) keeps only the parts of the document that matter to the
criterion, so the grounded context stays focused.
"""
from __future__ import annotations

import re

from app.modules.agentcore.models import AgentResult, Requirement
from app.modules.agentcore.runtime import AgentCore
from app.modules.knowledge.service import KnowledgeService

_WORD = re.compile(r"[a-z0-9]+")

RFP_CRITERIA = [
    "Does the document demonstrate relevant experience and past performance?",
    "Are certifications and compliance (e.g. ISO, security) evidenced?",
    "Is pricing or commercial structure stated?",
    "Are timelines and delivery commitments defined?",
]


def _tokens(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


def relevant_sections(query: str, sections: list[str], *, top_k: int = 5) -> list[str]:
    """Rank sections by token overlap with the query, keep the top_k that actually overlap."""
    q = _tokens(query)
    scored = [(len(q & _tokens(s)), s) for s in sections]
    return [s for score, s in sorted(scored, key=lambda p: p[0], reverse=True) if score > 0][:top_k]


async def evaluate_document(agent: AgentCore, knowledge: KnowledgeService, tenant: str, doc_id: str,
                            criterion: str, *, topic: str | None = None) -> AgentResult:
    """Grounded evaluation of one criterion against a stored document."""
    sections = [p.text for p in await knowledge.store.get(tenant) if p.doc_id == doc_id]
    context = relevant_sections(criterion, sections) or sections
    req = Requirement(id=f"{doc_id}:{criterion[:24]}", text=criterion, context=context, topic=topic)
    return agent.run(req, tenant=tenant)
