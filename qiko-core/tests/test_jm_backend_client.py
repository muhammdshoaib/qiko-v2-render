"""HTTP-level tests for HttpJmBackendClient, using httpx.MockTransport (no real network)."""

import json

import httpx
import pytest

from app.modules.joseph_mews.jm_backend_client import (
    ConversationTurn,
    HandoffPacket,
    HttpJmBackendClient,
    JmBackendError,
    UnavailableJmBackendClient,
)


def test_default_client_sets_the_shared_secret_header():
    client = HttpJmBackendClient("https://jm-backend.example.com", "shared-secret")
    assert client._c.headers["X-Qiko-Worker-Secret"] == "shared-secret"


def test_record_turn_posts_the_expected_shape_and_parses_the_response():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.read())
        return httpx.Response(200, json={
            "conversation_id": "wa_447700900000", "investor_id": 42,
            "history": [{"role": "customer", "text": "hi", "template_used": None, "at": "2026-09-01T10:00:00"}],
        })

    client = HttpJmBackendClient(
        "https://jm-backend.example.com", "shared-secret",
        client=httpx.Client(base_url="https://jm-backend.example.com", transport=httpx.MockTransport(handler)),
    )
    state = client.record_turn("447700900000", "customer", "hi")

    assert captured["url"] == "https://jm-backend.example.com/internal/whatsapp/conversations/turn"
    assert captured["body"] == {"phone_number": "447700900000", "role": "customer", "text": "hi"}
    assert state.conversation_id == "wa_447700900000"
    assert state.investor_id == 42
    assert state.history == (
        ConversationTurn(role="customer", text="hi", template_used=None, at="2026-09-01T10:00:00"),
    )


def test_record_turn_includes_optional_fields_only_when_given():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.read())
        return httpx.Response(200, json={"conversation_id": "wa_1", "investor_id": None, "history": []})

    client = HttpJmBackendClient(
        "https://jm-backend.example.com", "secret",
        client=httpx.Client(base_url="https://jm-backend.example.com", transport=httpx.MockTransport(handler)),
    )
    client.record_turn("447700900000", "joe", "hello", template_used="greeting", interakt_message_id="msg-1")

    assert captured["body"] == {
        "phone_number": "447700900000", "role": "joe", "text": "hello",
        "template_used": "greeting", "interakt_message_id": "msg-1",
    }


def test_record_turn_includes_the_handoff_packet_when_given():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.read())
        return httpx.Response(200, json={"conversation_id": "wa_1", "investor_id": None, "history": []})

    client = HttpJmBackendClient(
        "https://jm-backend.example.com", "secret",
        client=httpx.Client(base_url="https://jm-backend.example.com", transport=httpx.MockTransport(handler)),
    )
    client.record_turn(
        "447700900000", "joe", "handoff",
        handoff=HandoffPacket(
            reason_code="qualification_complete",
            summary="Alex wants a 2-bed in Manchester.",
            suggested_next_action="Call to discuss financing.",
            priority="high",
            extracted_traits={"city": "Manchester", "budget": 250000},
        ),
    )

    assert captured["body"]["handoff"] == {
        "reason_code": "qualification_complete",
        "summary": "Alex wants a 2-bed in Manchester.",
        "extracted_traits": {"city": "Manchester", "budget": 250000},
        "suggested_next_action": "Call to discuss financing.",
        "priority": "high",
    }


def test_record_turn_omits_handoff_when_not_given():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.read())
        return httpx.Response(200, json={"conversation_id": "wa_1", "investor_id": None, "history": []})

    client = HttpJmBackendClient(
        "https://jm-backend.example.com", "secret",
        client=httpx.Client(base_url="https://jm-backend.example.com", transport=httpx.MockTransport(handler)),
    )
    client.record_turn("447700900000", "customer", "hi")

    assert "handoff" not in captured["body"]


def test_record_turn_raises_a_jm_backend_error_on_a_non_2xx_response():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"detail": "invalid secret"})

    client = HttpJmBackendClient(
        "https://jm-backend.example.com", "wrong-secret",
        client=httpx.Client(base_url="https://jm-backend.example.com", transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(JmBackendError):
        client.record_turn("447700900000", "customer", "hi")


def test_unavailable_client_raises_a_clear_error_rather_than_faking_empty_history():
    with pytest.raises(JmBackendError):
        UnavailableJmBackendClient().record_turn("447700900000", "customer", "hi")
