"""Runtime English-only guardrail (JM2-1030).

The client's own prompt says "Speak only english with the users. If the user speaks another
language, apologize and say that you can only speak english" (worker.py's _JOE_PROMPT), but
until this module existed that was pure prompt instruction with no runtime check: nothing caught
it if the model ignored the instruction and replied in the lead's own language.

This is deliberately a cheap, dependency-free heuristic, not a real language classifier (no
langdetect/fasttext model is installed, and pulling one in for a single guardrail on short
WhatsApp-length replies is a heavier dependency than the problem calls for). It is tuned to two
failure modes that actually matter for this worker, in order of how confidently they can be
detected:

1. The reply switches to a non-Latin script entirely (Cyrillic, Arabic, CJK, etc.) - unambiguous,
   zero false positives on English text.
2. The reply is in a Latin-script European language, detected via a small set of
   English-uses-essentially-never letters (accented vowels, cedilla, eszett, etc.) - a real but
   much rarer failure mode for this worker (see worker.py's UK/UAE-focused audience), still worth
   catching for the "international client" branch the prompt explicitly names.

Deliberately NOT implemented: a common-English-stopword-ratio check. This domain's own reply
style is short and numbers-heavy ("Manchester yields ~5.5-6.5%.") and would trigger constant
false positives on completely normal English replies under that approach - see
test_short_technical_english_reply_is_not_flagged for the exact example that ruled it out.
"""

from __future__ import annotations

import unicodedata

# Unicode blocks a genuine English reply should never contain. Ranges chosen to cover the
# scripts most plausible for this worker's actual audience (worker.py: UK, UAE, Hong Kong, South
# Africa) rather than exhaustively every script in Unicode.
_NON_LATIN_RANGES: tuple[tuple[int, int], ...] = (
    (0x0370, 0x03FF),  # Greek
    (0x0400, 0x04FF),  # Cyrillic
    (0x0590, 0x05FF),  # Hebrew
    (0x0600, 0x06FF),  # Arabic
    (0x0900, 0x097F),  # Devanagari
    (0x0E00, 0x0E7F),  # Thai
    (0x3040, 0x30FF),  # Hiragana/Katakana
    (0x4E00, 0x9FFF),  # CJK Unified Ideographs
    (0xAC00, 0xD7A3),  # Hangul
)

# Letters that appear in common words of major Latin-script European languages but essentially
# never in English (loanwords like "café" aside, which is far too rare to cause a false
# positive over a whole reply). Deliberately excludes plain ASCII letters entirely.
_NON_ENGLISH_LATIN_LETTERS = set("àâäçèéêëîïôöùûüÿñãõáíóúÁÉÍÓÚÑÃÕÀÂÄÇÈÊËÎÏÔÖÙÛÜŸ")

# A non-Latin-script reply is flagged on a single occurrence (unambiguous). A Latin-script
# reply needs more than one occurrence, so a single incidental accented character (rare, but
# possible in a proper noun transliteration) does not alone flip the result.
_MIN_NON_ENGLISH_LATIN_LETTERS = 2


def _is_non_latin_script_char(char: str) -> bool:
    if not char.isalpha():
        return False
    code_point = ord(char)
    return any(start <= code_point <= end for start, end in _NON_LATIN_RANGES)


def looks_non_english(text: str) -> bool:
    """Best-effort, not a certainty: True means "confidently not English", False means "assume
    English" (including "too short/ambiguous to tell" - never block a reply on a guess)."""
    text = (text or "").strip()
    if not text:
        return False
    if any(_is_non_latin_script_char(char) for char in text):
        return True
    non_english_latin_count = sum(
        1 for char in unicodedata.normalize("NFC", text) if char in _NON_ENGLISH_LATIN_LETTERS
    )
    return non_english_latin_count >= _MIN_NON_ENGLISH_LATIN_LETTERS
