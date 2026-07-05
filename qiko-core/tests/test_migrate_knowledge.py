from scripts.migrate_knowledge import behavior_text, faq_text, policy_text, website_text


def test_behavior_text_formats_type_title_description():
    row = {"type": "tone", "title": "Friendly", "description": "Always upbeat."}
    assert behavior_text(row) == "tone: Friendly\nAlways upbeat."


def test_behavior_text_handles_missing_description():
    assert behavior_text({"type": "tone", "title": "Friendly", "description": None}) == "tone: Friendly"


def test_faq_text_formats_question_answer():
    row = {"question": "Do you offer refunds?", "answer": "Yes, within 30 days."}
    assert faq_text(row) == "Q: Do you offer refunds?\nA: Yes, within 30 days."


def test_policy_text_formats_name_details():
    row = {"name": "Cancellation", "details": "48h notice required."}
    assert policy_text(row) == "Policy — Cancellation:\n48h notice required."


def test_website_text_formats_name_url():
    row = {"name": "Docs", "url": "https://example.com/docs"}
    assert website_text(row) == "Website reference — Docs: https://example.com/docs"
