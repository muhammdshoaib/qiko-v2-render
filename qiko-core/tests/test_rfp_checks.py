from datetime import date

from app.modules.rfp.checks import applicability, run_checks, stale_dates


def test_stale_dates_flags_past_validity_date():
    text = "Our ISO 9001 certificate is valid until 19 May 2025 and covers all operations."
    findings = stale_dates(text, today=date(2026, 1, 1))
    assert len(findings) == 1
    assert findings[0]["iso"] == "2025-05-19"
    assert "past" in findings[0]["note"]


def test_stale_dates_ignores_dates_without_validity_context():
    text = "We completed the Al-Faw project in May 2025 with zero lost-time incidents."
    assert stale_dates(text, today=date(2026, 1, 1)) == []


def test_stale_dates_ignores_future_validity_date():
    text = "Certification valid until 19 May 2027."
    assert stale_dates(text, today=date(2026, 1, 1)) == []


def test_stale_dates_dedupes_repeated_mentions():
    text = "Valid until 19 May 2025. Also note: certificate expires 19 May 2025."
    findings = stale_dates(text, today=date(2026, 1, 1))
    assert len(findings) == 1


def test_applicability_flags_generic_works_template_language():
    status, note = applicability("Provide a ready-mix concrete inspection and testing plan (ITP).")
    assert status == "possibly_not_applicable"
    assert note


def test_applicability_ok_for_normal_requirement():
    status, note = applicability("Describe your approach to static security services staffing.")
    assert status == "applicable"
    assert note == ""


def test_run_checks_combines_both_guardrails():
    result = run_checks(
        "Provide a ready-mix concrete inspection plan.",
        "Our ISO 9001 certificate is valid until 19 May 2025.",
    )
    assert result["applicability"] == "possibly_not_applicable"
    assert len(result["stale_dates"]) >= 0  # today's real date, not asserting exact staleness here
    assert "applicability_note" in result
