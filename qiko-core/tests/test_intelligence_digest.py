import pytest
from datetime import datetime, timedelta, timezone

from app.modules.ai.gateway import LLMResponse, StubProvider
from app.modules.intelligence.digest import (
    DigestUnavailable,
    HeadsUpDigest,
    generate_heads_up_digest,
    parse_heads_up_digest,
    window_start,
)
from app.modules.intelligence.discrepancies import Discrepancy


def _make_discrepancy(cls: str, label: str, ref: str | None, title: str, summary: str,
                      severity: str = "medium", project_key: str | None = None) -> Discrepancy:
    return Discrepancy(
        discrepancy_class=cls,
        class_label=label,
        severity=severity,
        ref=ref,
        project_key=project_key,
        title=title,
        summary=summary,
        claimed_at=datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc),
        evidence_at=datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc),
        sources=[],
    )


def test_parse_heads_up_digest_extracts_sections():
    raw = (
        '{"headline": "Three issues need attention", "summary": "The team has open blockers.", '
        '"sections": [{"title": "Blockers", "items": ["QIW-1 is blocked"]}], "tone": "at-risk"}'
    )
    digest = parse_heads_up_digest(raw)
    assert digest.headline == "Three issues need attention"
    assert digest.sections == [{"title": "Blockers", "items": ["QIW-1 is blocked"]}]
    assert digest.tone == "at-risk"


def test_parse_heads_up_digest_rejects_malformed_json():
    with pytest.raises(DigestUnavailable):
        parse_heads_up_digest("not json")


def test_generate_heads_up_digest_returns_empty_digest_when_no_discrepancies():
    digest = generate_heads_up_digest([])
    assert isinstance(digest, HeadsUpDigest)
    assert "No open discrepancies" in digest.headline


def test_generate_heads_up_digest_refuses_stub_provider():
    provider = StubProvider(canned="{" "}")
    d = _make_discrepancy("blocked_and_silent", "Blocked and gone quiet", "QIW-1",
                           "Blocked", "Something is blocked.")
    with pytest.raises(DigestUnavailable):
        generate_heads_up_digest([d], provider=provider)


def test_generate_heads_up_digest_with_valid_provider():
    provider = type("FakeProvider", (), {
        "generate": lambda self, prompt, **kwargs: LLMResponse(
            text='{"headline": "Heads-up", "summary": "One issue.", '
                 '"sections": [{"title": "Blocked and gone quiet", "items": ["QIW-1 is blocked"]}], '
                 '"tone": "tense"}')
    })()
    d = _make_discrepancy("blocked_and_silent", "Blocked and gone quiet", "QIW-1",
                           "Blocked", "Something is blocked.")
    digest = generate_heads_up_digest([d], provider=provider)
    assert digest.headline == "Heads-up"
    assert digest.sections[0]["items"] == ["QIW-1 is blocked"]


def test_window_start_daily_and_weekly():
    now = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)
    assert window_start("daily", now) == now - timedelta(days=1)
    assert window_start("weekly", now) == now - timedelta(days=7)


def test_window_start_rejects_invalid_window():
    with pytest.raises(ValueError):
        window_start("monthly")
