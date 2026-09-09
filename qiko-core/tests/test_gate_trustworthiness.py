"""QIKO-1086 / QIKO-1087: the gate must not be defeated by giving it more evidence, and the
writer must not make claims about the source document.

Both were found by running a real IDG tender through the pipeline on preprod. Raising
`retrieval_k` from 5 to 30 turned nine of fourteen escalations into auto-accepts without any
change to the model, the prompts or the document.
"""
from app.modules.agentcore.critic import grounding_score
from app.modules.agentcore.gate import claims_about_the_source, MIN_CONFIDENCE, decide
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


# --- QIKO-1087: the contract is now enforced, not only requested -------------------------------
# The prompt tells the writer never to claim the source document lacks something. A prompt only
# asks. These pin the check that makes it true, and the case Jake found is the first of them.

def test_the_current_liabilities_row_cannot_be_reported_as_cut_off():
    """The reported case. Asked for audited accounts, the answer gave 2023 and 2024 and wrote
    "[2025 figure cut off in evidence]". The value is 2,311,636 and the complete row was in a
    single 799-character passage, alongside three other rows the model read correctly. Grounding
    was high and confidence 0.85, so nothing else in the pipeline could have caught it."""
    answer = ("Current Liabilities: USD 2,706,689 (2023), USD 3,791,126 (2024) "
              "[2025 figure cut off in evidence]")
    assert claims_about_the_source(answer) == "cut off"
    assert decide(Critique(grounding=1.0), confidence=0.85,
                  source_claim=claims_about_the_source(answer)) == Decision.human_review


def test_the_same_row_read_correctly_is_left_alone():
    """The other half of the criterion: reading the value is the correct outcome and must not be
    escalated. Only the claim about the evidence is the defect."""
    answer = ("Current Liabilities: USD 2,706,689 (2023), USD 3,791,126 (2024), "
              "USD 2,311,636 (2025)")
    assert claims_about_the_source(answer) is None
    assert decide(Critique(grounding=1.0), confidence=0.85) == Decision.auto_accept


def test_saying_it_could_not_determine_the_value_is_allowed():
    """What the contract tells the writer to say instead. It must not be escalated as a source
    claim, or the guard would punish the correct behaviour."""
    answer = "The 2025 Current Liabilities value could not be determined from the evidence given."
    assert claims_about_the_source(answer) is None


def test_a_form_reported_absent_from_the_document_is_escalated():
    """The second observed case. Form B8-2 is in the ingested document, in Appendix B8, with
    thirteen projects. Retrieval only had part of that table, which explains an incomplete answer
    but not the assertion that the form is not in the document."""
    answer = "Form B8-2 was not part of the source document."
    assert claims_about_the_source(answer) == "not part of the source document"


def test_the_gaps_note_is_checked_too():
    """The claims landed in the gaps note as often as in the answer, and the reviewer reads it as
    the authoritative statement of what is missing."""
    gaps = "The 2025 Current Liabilities figure appears incomplete in the extracted data."
    assert claims_about_the_source("A clean answer.", gaps) == "appears incomplete"


def test_reporting_that_the_evidence_did_not_cover_it_is_still_allowed():
    """Explicitly permitted by the criterion: a statement about the retrieved evidence is true and
    useful, unlike a statement about the document. This is handled by the confidence veto, not by
    treating it as a source claim."""
    answer = "The supplied evidence does not contain company incorporation documents."
    assert claims_about_the_source(answer) is None
    assert decide(Critique(grounding=1.0), confidence=0.15) == Decision.human_review
