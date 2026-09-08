from app.modules.joseph_mews.language import looks_non_english


def test_short_technical_english_reply_is_not_flagged():
    """Real risk this guardrail must not create: the domain's own terse, numbers-heavy style
    (see test_joseph_mews_conversation.py's own example sentences) has almost no common English
    stopwords, so a naive stopword-ratio check would false-positive on completely normal replies."""
    assert looks_non_english("Manchester yields ~5.5-6.5%.") is False


def test_ordinary_english_sentence_is_not_flagged():
    assert looks_non_english(
        "Based on what you're looking for, it might be worth having a proper chat with one of "
        "our investment specialists."
    ) is False


def test_short_english_acknowledgement_is_not_flagged():
    assert looks_non_english("You're welcome!") is False


def test_empty_or_blank_text_is_not_flagged():
    assert looks_non_english("") is False
    assert looks_non_english("   ") is False


def test_cyrillic_script_is_flagged():
    assert looks_non_english("Здравствуйте! Чем могу помочь?") is True


def test_arabic_script_is_flagged():
    assert looks_non_english("مرحبا، كيف يمكنني مساعدتك اليوم؟") is True


def test_chinese_script_is_flagged():
    assert looks_non_english("你好,我能帮你什么?") is True


def test_spanish_with_diacritics_is_flagged():
    assert looks_non_english("Hola, ¿cómo puedo ayudarte con tu inversión en propiedades?") is True


def test_french_with_diacritics_is_flagged():
    assert looks_non_english(
        "Bonjour, je suis très heureux de vous aider. Préférez-vous un appartement à Londres?"
    ) is True


def test_german_with_umlauts_is_flagged():
    assert looks_non_english("Können Sie mir mehr über Ihre Investitionspräferenzen erzählen?") is True


def test_a_single_foreign_proper_noun_inside_english_is_not_flagged():
    """A place name or client name written in a different script must not itself trip the
    guardrail if the surrounding reply is otherwise plain English - this is about the OVERALL
    reply language, not about rejecting foreign-origin words entirely."""
    assert looks_non_english("Manchester and Birmingham are both strong options for you.") is False
