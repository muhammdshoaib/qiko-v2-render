"""IDG's own Scout and facet construction for the shared agentic pipeline (see
app.modules.agentcore.orchestration for Pipeline/Synthesizer/Critic/Magistrate, and
app.modules.intelligence.orchestration.roles.Specialist, reused here unchanged - it wraps a
generic Worker, which is not IDG-specific)."""
from __future__ import annotations

from app.modules.agentcore.orchestration import EvidenceBundle
from app.modules.sales_intelligence.models import Opportunity

# Human-readable prompts for exactly the two kinds of uncertainty QualificationService.qualify()
# can report - a missing structured field, or a named risk in its own reasons/risks list. Each
# maps to one facet the Specialist stage is asked to resolve by actually reading the notice text,
# not by re-deriving what the deterministic scorer already answered with confidence.
_MISSING_FIELD_FACETS = {
    "estimated_value": (
        "Does the notice text contain an estimated contract value the structured scan missed?"),
    "deadline": (
        "Does the notice text contain a submission deadline the structured scan missed?"),
    "country": (
        "Does the notice text identify a beneficiary country the structured scan missed?"),
    "buyer": (
        "Does the notice text identify the contracting authority the structured scan missed?"),
}


class IdgScout:
    """Read-only evidence gathering from one scanned notice. No LLM call, no external fetch -
    matches the existing Scout role's contract (Scout is always read-only in every vertical)."""

    async def gather(self, opportunity: Opportunity) -> EvidenceBundle:
        chunks = [
            f"Title: {opportunity.title}",
            f"Buyer: {opportunity.buyer or 'unknown'}",
            f"Country: {opportunity.country or 'unknown'}",
            f"Category: {opportunity.category or 'unknown'}",
        ]
        description = (opportunity.raw_payload or {}).get("description")
        if description:
            chunks.append(str(description))
        sources = [opportunity.source_url] if opportunity.source_url else []
        return EvidenceBundle(text_chunks=chunks, sources=sources)


def build_facets(qualification: dict) -> list[str]:
    """One facet per unresolved missing_field/risk from QualificationService.qualify()'s own
    output - never a fixed, re-derive-everything list. A confident qualify() result (no missing
    fields, no risks) produces zero facets, which is what keeps the "Bid"/"No Bid" cases out of
    the agentic pipeline entirely (see _scan_source()'s gate in Task 3 - it only calls this at all
    for a "Review" recommendation, which by qualification.py's own _recommendation() logic always
    has at least one risk or missing field, so an empty result here should not happen in practice,
    but this function makes no assumption about that and simply reflects whatever it is given)."""
    facets: list[str] = []
    for field_name in qualification.get("missing_fields", []):
        facets.append(_MISSING_FIELD_FACETS.get(
            field_name, f"Does the notice text resolve the missing field '{field_name}'?"))
    for risk in qualification.get("risks", []):
        facets.append(f"Read the notice text and judge this risk directly: {risk}")
    return facets
