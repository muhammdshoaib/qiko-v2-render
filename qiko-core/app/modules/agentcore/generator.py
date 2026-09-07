"""Answer generator. Builds a grounded prompt (requirement + retrieved evidence + any verified
prior answers from the flywheel) and calls the LLM provider.

The generator now asks the model for STRUCTURED output: the prose answer PLUS a self-reported
`confidence` (how well the evidence lets it answer) and a `gaps` note (what it could not support).
This is genuinely distinct from the independent grounding critic (critic.py): confidence is the
writer's own read of the evidence, grounding is a separate check of how much of the prose the
evidence actually backs.

To make the JSON reliable (the model previously often returned markdown prose, which collapsed
confidence back onto grounding), we (1) seed the assistant turn with an opening "{" via the
provider prefill hook so a prefill-capable provider must return a JSON object, and (2) strengthen
the SYSTEM prompt to forbid markdown/prose outside the JSON. Parsing stays fault tolerant: a fenced
```json block or a bare object both work, and if the model still returns plain prose we treat the
whole text as the answer and leave confidence unset (the caller then derives it from grounding).

Whichever path is taken, the answer text is passed through _clean_answer() as a safety net to strip
any leading meta-scaffolding (a markdown title, an "## Answer" wrapper, a "Based on the evidence
provided" preamble, or a "GSS Response:" style label) so the client sees clean bid prose."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from app.modules.ai.gateway import LLMProvider, LLMResponse, get_provider
from app.modules.agentcore.models import Requirement

# The default IDENTITY (who the worker is + the grounding rule). A worker with its own persona
# (WorkerConfig.system_prompt, synthesized from the Train wizard's config) replaces ONLY this part,
# so e.g. a customer-support worker no longer answers in the generic bid-writer voice -- QIK-315.
_IDENTITY_DEFAULT = (
    "You are a helpful AI assistant. Answer using ONLY the supplied evidence. "
    "Do not invent facts, dates, names, or figures. "
    "If the context contains no relevant evidence, clearly state that the available evidence does "
    "not cover this and you cannot answer it yet."
)

# The extra constraint for a job restricted to ONE reference document (IDG-1000).
#
# Applied as its OWN layer rather than folded into the identity, because a worker with a
# synthesized persona (QIK-315) replaces the identity entirely -- and the IDG pre-sales worker has
# one. Folding the scope into the identity would silently drop it for exactly the workers this
# feature was built for. Layered like the output contract, it holds for persona and default
# workers alike.
#
# Note the wording of the no-evidence case. The default identity above used to assert "no
# knowledge base has been uploaded", a claim the model is in no position to make: it sees
# retrieved passages, not the corpus. On a scoped job it is flatly wrong -- the customer's
# knowledge base is full, the selected document simply does not cover the question -- and telling
# a customer their knowledge base is empty when it is not is worse than saying nothing.
_REFERENCE_SCOPE_CONSTRAINT = (
    "SCOPE: every piece of evidence you have been given comes from ONE reference document the "
    "user selected for this job, and it is the only permitted source. Never draw on, refer to, or "
    "speculate about anything outside it. If that evidence does not cover the question, say "
    "plainly that the selected reference document does not contain enough detail to answer it, "
    "and do not answer from general knowledge."
)

# The OUTPUT CONTRACT (JSON shape + no-scaffolding). This is ALWAYS enforced, for every worker,
# whether or not it has a custom persona -- so a per-worker persona never costs us the structured
# confidence/gaps signal the gate relies on.
_OUTPUT_CONTRACT = (
    "Return ONLY a single JSON object and nothing else: no markdown, no prose outside the JSON, "
    "no code fences, no leading or trailing text. The object must have exactly these keys: "
    '"answer" (string), "confidence" (a number 0..1), and "gaps" (string). '
    'The "answer" value is the final response text only: clean, professional prose in short '
    "paragraphs, with light structure at most. It must NOT contain any meta scaffolding: no "
    "'## Answer' heading, no '## Available Evidence' section, no 'Based on the evidence provided' "
    "preamble, no leading markdown title (no '# ...' or '## ...' first line), and no "
    "'Company Response:' or 'Client Response:' style labels. Write it as the words you would send to the recipient. "
    '"confidence" is your own read of how well the evidence lets you answer. '
    '"gaps" is a short note of what the evidence did not let you support, or "" if none.'
)

# Default prompt = identity + " " + contract. The identity is now worker-neutral rather than
# bid-specific, and the contract wording is also worker-neutral ("response"/"recipient"), so it
# reads correctly for persona workers too; the JSON keys, object-only shape, and no-scaffolding
# rules are unchanged, so structured parsing/gating for the default (bid/RFP) workers is
# functionally identical.
SYSTEM = f"{_IDENTITY_DEFAULT} {_OUTPUT_CONTRACT}"

# Seed the assistant turn with an opening brace so a prefill-capable provider is forced to return a
# JSON object (and no markdown preamble). Providers that cannot prefill ignore it; the strengthened
# SYSTEM prompt plus the tolerant parser below still recover the JSON in that case.
_JSON_PREFILL = "{"

# Matches a ```json ... ``` (or bare ``` ... ```) fenced block so we can pull the JSON out of a
# model that wrapped its object in markdown. DOTALL so the body can span newlines.
_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)

# --- answer clean-up (safety net) ---
# The SYSTEM prompt tells the model not to emit scaffolding, but as a last line of defence we strip
# it here if it still does. Each pattern is anchored at the START of the (stripped) text so we only
# ever remove a leading wrapper and never touch genuine body content.
# A leading markdown heading line, e.g. "# Detailed Security Arrangements" or "## Answer".
_LEADING_HEADING = re.compile(r"^\s*#{1,6}[ \t]+[^\n]*(?:\n+|$)")
# A leading "Company Response:" / "Client Response:" / bare "Response:" label, optionally bold-wrapped.
_RESPONSE_LABEL = re.compile(r"^\s*\*{0,2}\s*(?:[A-Za-z0-9]{1,16}\s+)?Response\s*:\s*\*{0,2}\s*", re.IGNORECASE)
# A leading "Based on the evidence provided," / "Based on the provided evidence:" preamble.
_EVIDENCE_PREAMBLE = re.compile(
    r"^\s*based on the (?:provided )?evidence(?:\s+provided)?\s*[:,]\s*", re.IGNORECASE)
_CLEAN_PATTERNS = (_LEADING_HEADING, _RESPONSE_LABEL, _EVIDENCE_PREAMBLE)


def _clean_answer(text: str) -> str:
    """Strip leading meta-scaffolding the model may still add despite the prompt: a leading markdown
    heading / title, an "## Answer" wrapper, a "Company Response:"-style label, and a "Based on the
    (provided) evidence" preamble. Applies repeatedly so stacked wrappers (e.g. a title followed by
    "## Answer" followed by the preamble) all come off, while genuine body content is preserved."""
    cleaned = (text or "").strip()
    changed = True
    while changed and cleaned:
        changed = False
        for pattern in _CLEAN_PATTERNS:
            stripped = pattern.sub("", cleaned, count=1).strip()
            if stripped != cleaned:
                cleaned = stripped
                changed = True
    return cleaned


@dataclass
class GenOutput:
    """Structured generator result. `confidence` is None when the model did not self-report one
    (plain-prose fallback), signalling the caller to derive confidence from the grounding score."""
    answer: str
    confidence: float | None
    gaps: str
    stub: bool = False


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def parse_structured(text: str) -> tuple[str, float | None, str] | None:
    """Parse the model's structured answer. Returns (answer, confidence|None, gaps) or None when
    the text is not a usable JSON object with an answer (so the caller falls back to plain prose).

    Tolerant of a ```json fenced block and of extra prose around a single JSON object."""
    raw = (text or "").strip()
    if not raw:
        return None
    fenced = _FENCE.search(raw)
    candidate = fenced.group(1).strip() if fenced else raw
    data = _loads(candidate)
    if data is None and not fenced:
        # No fence and the whole string isn't JSON: try the first {...} span in the prose.
        start, end = candidate.find("{"), candidate.rfind("}")
        if 0 <= start < end:
            data = _loads(candidate[start:end + 1])
    if not isinstance(data, dict):
        return None
    answer = str(data.get("answer") or "").strip()
    if not answer:
        return None
    conf = data.get("confidence")
    confidence = _clamp01(conf) if isinstance(conf, (int, float)) and not isinstance(conf, bool) else None
    gaps = str(data.get("gaps") or "").strip()
    return answer, confidence, gaps


def _loads(text: str):
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return None

# Ingestion is supposed to chunk documents to ~800 chars (app.modules.knowledge.chunking), but a
# passage that slipped in unchunked (bulk-loaded, or from an older pipeline) can be tens of
# thousands of chars. One such passage among the retrieved evidence blows up the prompt to a size
# that made real Bedrock calls take minutes instead of seconds (observed live). Cap defensively
# here regardless of how the passage got that large -- retrieval should return a snippet, not a
# whole document.
_MAX_EVIDENCE_CHARS = 2000


@dataclass
class Generator:
    provider: LLMProvider = None  # type: ignore[assignment]
    # Per-worker override (see WorkerConfig.system_prompt / Agent.config["system_prompt"]) -- a
    # tender-answering worker and a pre-sales-writing worker are the same engine but must not
    # sound like the same person. Falls back to the generic bid-response-writer prompt.
    system_prompt: str | None = None
    # True when this worker is answering a job restricted to one reference document (IDG-1000).
    # Retrieval already enforces the restriction; this only makes the model describe the limit
    # honestly instead of implying the knowledge base is empty.
    reference_scoped: bool = False

    def __post_init__(self) -> None:
        if self.provider is None:
            self.provider = get_provider()

    @property
    def system(self) -> str:
        """The full SYSTEM prompt: the worker's persona (or the default identity), then the
        reference-document scope constraint when the job is scoped, then the ALWAYS-enforced
        output contract. A custom persona replaces only the identity, so every worker keeps both
        the scope constraint and the structured JSON (confidence/gaps) the gate relies on."""
        identity = self.system_prompt if self.system_prompt else _IDENTITY_DEFAULT
        if not self.reference_scoped:
            # Unchanged from before this feature, including the single-space join on the default
            # path, so an unscoped job sends a byte-identical prompt to the one it always sent.
            return f"{identity}\n\n{_OUTPUT_CONTRACT}" if self.system_prompt else SYSTEM
        return f"{identity}\n\n{_REFERENCE_SCOPE_CONSTRAINT}\n\n{_OUTPUT_CONTRACT}"

    def build_prompt(self, req: Requirement, verified: list[str] | None = None) -> str:
        evidence = list(req.context) + list(verified or [])
        capped = [e[:_MAX_EVIDENCE_CHARS] + ("…" if len(e) > _MAX_EVIDENCE_CHARS else "") for e in evidence]
        context_block = "\n".join(f"- {e}" for e in capped) if capped else "(none)"
        return f"CONTEXT:\n{context_block}\n\nREQUIREMENT:\n{req.text}\n"

    def generate_response(self, req: Requirement, verified: list[str] | None = None,
                          *, prefill: str | None = None) -> LLMResponse:
        """Full provider response (carries the `stub` flag) for callers that must know whether the
        text is a real grounded draft or a StubProvider fallback -- see AgentCore.run."""
        prompt = self.build_prompt(req, verified)
        return self.provider.generate(prompt, system=self.system, prefill=prefill)

    def generate(self, req: Requirement, verified: list[str] | None = None) -> str:
        return self.generate_response(req, verified).text.strip()

    def generate_structured(self, req: Requirement, verified: list[str] | None = None) -> GenOutput:
        """Answer + self-reported confidence + gaps. Prefills the assistant turn with "{" (when the
        default JSON contract is in force) so a prefill-capable provider returns a JSON object,
        keeping `confidence` distinct from the critic's grounding. Falls back to plain prose
        (confidence unset) only when the model still did not return the contract -- see
        parse_structured. Either way the answer is run through _clean_answer to strip any leading
        meta-scaffolding the model added."""
        # The output contract (JSON) is enforced for EVERY worker -- persona or not -- so we always
        # prefill "{" to force a JSON object and keep confidence/gaps distinct from grounding.
        response = self.generate_response(req, verified, prefill=_JSON_PREFILL)
        parsed = parse_structured(response.text)
        if parsed is None:
            return GenOutput(answer=_clean_answer(response.text), confidence=None, gaps="",
                             stub=response.stub)
        answer, confidence, gaps = parsed
        return GenOutput(answer=_clean_answer(answer), confidence=confidence, gaps=gaps,
                         stub=response.stub)
