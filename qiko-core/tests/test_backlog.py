"""Backlog proposal decomposition tests."""
import socket
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from app.modules.intelligence.backlog import BacklogService, ProposedTicket
from app.modules.intelligence.orchestration.models import Finding
from app.modules.intelligence.research import Brief


def _fake_resolver(_host: str, port: int, **kwargs):
    return [(socket.AddressFamily.AF_INET, socket.SOCK_STREAM, 0, "", ("8.8.8.8", port))]


def _brief(findings: list[str] | None = None, summary: str = "summary") -> Brief:
    finding_texts = findings if findings is not None else ["Fix the preview bug"]
    return Brief(
        run_id="r-1",
        tenant="t-1",
        agent_id="a-1",
        subject="Onboard Acme Corp",
        status="accepted",
        summary=summary,
        findings=[
            Finding(text=text, evidence_refs=["doc"], gaps="gap")
            for text in finding_texts
        ],
        gaps="",
        citations=["c1"],
        accepted_at=datetime.now(timezone.utc),
    )


def test_propose_epic_and_children_from_brief():
    brief = _brief([
        "SSO via SAML is required by security.",
        "Customer reports a bug in the import preview.",
        "Refactor onboarding checklist into reusable templates.",
    ])
    service = BacklogService(base_url="https://track.qiko.ai", token="x", resolver=_fake_resolver)
    proposal = service.propose(brief, "ACM")

    assert proposal.project_key == "ACM"
    assert len(proposal.items) == 4
    assert proposal.items[0].type == "EPIC"
    assert proposal.items[0].title == "Onboard Acme Corp"

    types = [item.type for item in proposal.items[1:]]
    assert types == ["FEATURE", "BUG", "CHORE"]
    assert all(item.parent_index == 0 for item in proposal.items[1:])
    assert proposal.items[1].finding_index == 0


def test_propose_empty_brief_returns_placeholder():
    brief = _brief(findings=[], summary="")
    service = BacklogService(base_url="https://track.qiko.ai", token="x", resolver=_fake_resolver)
    proposal = service.propose(brief, "ACM")

    assert len(proposal.items) == 1
    assert proposal.items[0].type == "EPIC"
    assert "Onboard Acme Corp" in proposal.items[0].title


def test_proposed_ticket_to_dict_is_json_safe():
    ticket = ProposedTicket(
        title="Fix it",
        description_md="desc",
        type="BUG",
        priority="HIGH",
        estimate_points=3,
        parent_index=0,
        finding_index=1,
        evidence_refs=["doc1"],
    )
    d = ticket.to_dict()
    assert d["type"] == "BUG"
    assert d["priority"] == "HIGH"
    assert d["estimate_points"] == 3
    assert d["parent_index"] == 0
    assert d["finding_index"] == 1


@pytest.mark.asyncio
async def test_create_approved_creates_in_parent_first_order():
    service = BacklogService(base_url="https://track.qiko.ai", token="x", resolver=_fake_resolver)
    service.client.create_ticket = AsyncMock(return_value={"key": "ACM-1", "id": "id1"})

    proposal = service.propose(
        _brief([
            "SSO via SAML is required by security.",
            "Fix the preview bug.",
        ]),
        "ACM",
    )
    created = await service.create_approved(proposal, {0, 1, 2})
    assert len(created) == 3
    assert created[0]["key"] == "ACM-1"
    assert service.client.create_ticket.call_count == 3
    first_call = service.client.create_ticket.call_args_list[0]
    payload = first_call.args[0]
    assert payload["type"] == "EPIC"
