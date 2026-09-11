"""QIW: IDG's own Scout (reads one Opportunity's notice data, no LLM call) and facet construction
(targets exactly what QualificationService.qualify() could not resolve confidently)."""
from datetime import datetime, timezone

from app.modules.sales_intelligence.models import Opportunity
from app.modules.sales_intelligence.orchestration import IdgScout, build_facets


def _opportunity(**overrides) -> Opportunity:
    defaults = dict(
        id="o1", tenant="acme", agent_id="a1", external_id="e1", source_key="ted",
        source_name="TED - EU Tenders", title="Security guarding services for federal buildings",
        buyer="Ministry of Interior", country="France", category="Security services",
        estimated_value=None, deadline_at=datetime(2027, 1, 1, tzinfo=timezone.utc),
        raw_payload={"description": "Ongoing physical security and access control."},
    )
    defaults.update(overrides)
    return Opportunity(**defaults)


async def test_idg_scout_gathers_the_opportunity_fields_as_evidence_text():
    scout = IdgScout()
    bundle = await scout.gather(_opportunity())
    joined = " ".join(bundle.text_chunks)
    assert "Security guarding services for federal buildings" in joined
    assert "Ministry of Interior" in joined
    assert "France" in joined
    assert "Ongoing physical security and access control." in joined


def test_build_facets_targets_missing_fields_and_risks_only():
    qualification = {
        "missing_fields": ["estimated_value"],
        "risks": ["Tender has partial service alignment but needs human confirmation."],
    }
    facets = build_facets(qualification)
    assert len(facets) == 2
    assert any("estimated" in f.lower() or "value" in f.lower() for f in facets)
    assert any("service" in f.lower() or "alignment" in f.lower() for f in facets)


def test_build_facets_is_empty_for_a_confident_result():
    assert build_facets({"missing_fields": [], "risks": []}) == []
