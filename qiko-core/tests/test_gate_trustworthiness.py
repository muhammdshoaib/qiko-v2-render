"""QIKO-1086 / QIKO-1087: the gate must not be defeated by giving it more evidence, and the
writer must not make claims about the source document.

Both were found by running a real IDG tender through the pipeline on preprod. Raising
`retrieval_k` from 5 to 30 turned nine of fourteen escalations into auto-accepts without any
change to the model, the prompts or the document.
"""
from app.modules.agentcore.critic import grounding_score
from app.modules.agentcore.gate import MIN_CONFIDENCE, decide
from app.modules.agentcore.generator import _OUTPUT_CONTRACT, Generator
from app.modules.agentcore.models import Critique, Decision
from app.modules.ai.gateway import StubProvider

ISO = "IDG holds a current ISO 9001 certification for security operations management services."


# --- QIKO-1086: grounding must not rise with the number of passages ---------------------------
def test_grounding_does_not_rise_when_unrelated_passages_are_added():
    """The defect in one assertion. Same answer, same supporting passage; only the size of the
    retrieved set changes. The score must not move."""
    answer = "IDG holds a current ISO 9001 certification."
    supporting = [ISO]
    noise = [
        "The mobilisation plan covers vehicle movements and armoury handover at demobilisation.",
        "Environmental incidents are recorded in the spill log register and reviewed quarterly.",
        "Lost time incident rates are audited by the assurance division each year.",
        "Personnel receive induction training before deployment to any client site.",
    ]
    assert grounding_score(answer, supporting).grounding == \
        grounding_score(answer, supporting + noise).grounding


def test_a_sentence_assembled_from_several_passages_is_not_grounded():
    """This is the mechanism. Each word exists SOMEWHERE in the evidence, so scoring against the
    union of every passage's words passed it. No single source supports the claim, which is what
    grounded is supposed to mean."""
    evidence = [
        "The contract value is US$1,281,497 per annum.",
        "Operations are delivered across Mogadishu, Bossaso and Galkayo.",
        "Armed guarding personnel numbered sixty four at the last review.",
    ]
    invented = "The Mogadishu contract value is sixty four per annum."
    assert grounding_score(invented, evidence).grounding < 1.0


def test_a_sentence_fully_inside_one_passage_is_still_grounded():
    """The fix must not make the critic useless: real support still scores."""
    assert grounding_score("IDG holds a current ISO 9001 certification.", [ISO]).grounding == 1.0


def test_grounding_is_unchanged_for_a_single_passage():
    """With one passage there is no union to differ from, so the score is identical to before and
    every existing threshold keeps its meaning."""
    answer = "IDG holds a current ISO 9001 certification for security operations."
    assert grounding_score(answer, [ISO]).grounding == 1.0
    assert grounding_score("Cats are excellent companions for long voyages.", [ISO]).grounding == 0.0


# --- QIKO-1086: the writer's own confidence is a veto -----------------------------------------
def test_a_perfectly_grounded_answer_is_escalated_when_the_writer_disowns_it():
    """The observed worst case, from preprod pack 0ed7f36d17f0. Asked for company incorporation
    documents, the answer was "The supplied evidence does not contain company incorporation
    documents...". Every word of that appears in the evidence, so grounding was 1.00 and the gate
    auto-accepted an answer that states it is not an answer. Confidence was 0.15."""
    assert decide(Critique(grounding=1.0), confidence=0.15) == Decision.human_review


def test_a_grounded_answer_with_real_confidence_still_auto_accepts():
    assert decide(Critique(grounding=1.0), confidence=0.9) == Decision.auto_accept


def test_the_confidence_veto_sits_just_above_the_value_the_prompt_asks_for():
    """The output contract tells the writer to report 0.2 or lower when the evidence does not
    cover the question, so the veto has to fire at that value and leave normal answers alone."""
    assert MIN_CONFIDENCE > 0.2
    assert decide(Critique(grounding=1.0), confidence=0.2) == Decision.human_review
    assert decide(Critique(grounding=1.0), confidence=MIN_CONFIDENCE) == Decision.auto_accept


def test_omitting_confidence_keeps_the_previous_behaviour():
    """Callers that do not pass confidence must be unaffected, so this is additive for every
    non-RFP caller of the gate."""
    assert decide(Critique(grounding=1.0)) == Decision.auto_accept
    assert decide(Critique(grounding=0.1)) == Decision.human_review


def test_hard_fail_still_wins():
    assert decide(Critique(grounding=1.0), confidence=1.0, hard_fail=True) == Decision.human_review


# --- QIKO-1087: no claims about the source document -------------------------------------------
def test_the_contract_forbids_claims_about_the_source_document():
    """Two false claims reached a client-facing document: a figure reported as "cut off in
    evidence" whose full table row was in context, and a form reported as "not part of the source
    document" that is in the document. The model only ever sees retrieved passages."""
    assert "never the whole source document" in _OUTPUT_CONTRACT
    assert "Never state that the source lacks something" in _OUTPUT_CONTRACT
    assert "could not find it in the evidence you were given" in _OUTPUT_CONTRACT


def test_persona_workers_get_the_rule_too():
    """It lives in the output contract because a synthesized persona (QIK-315) replaces the
    identity wholesale, and the IDG pre-sales worker has one."""
    persona = Generator(provider=StubProvider(), system_prompt="You are IDG's bid writer.").system
    assert "Never state that the source lacks something" in persona
    assert "You are IDG's bid writer." in persona
