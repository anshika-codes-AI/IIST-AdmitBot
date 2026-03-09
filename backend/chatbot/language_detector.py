"""
Language detection for Hindi, Hinglish, and English messages.
Used to ensure AdmitBot replies in the student's preferred language.
"""

import re
from enum import Enum


class Language(str, Enum):
    HINDI = "hindi"
    HINGLISH = "hinglish"
    ENGLISH = "english"


# Common Hindi/Devanagari Unicode range: U+0900 to U+097F
_DEVANAGARI_PATTERN = re.compile(r"[\u0900-\u097F]")

# Common Hindi/Hinglish words written in Roman script.
# Only include words that are distinctly Hindi/Hinglish — avoid English words
# like "fees", "admission", "college" which are borrowed into Hinglish but
# appear in plain English sentences too.
_HINGLISH_KEYWORDS = {
    "kya", "hai", "kaise", "hoga", "mera", "meri", "aap", "mujhe",
    "chahiye", "bhai", "yaar", "ek", "do", "teen", "nahi", "haan",
    "accha", "theek", "batao", "bata", "lena", "dena", "liye",
    "kaisa", "kaisi", "kab", "kahan", "kyun", "kitna", "kitni",
    "padhai", "jana", "aana", "milega", "milegi",
    "chahta", "chahti", "mein", "pe", "wala", "wali",
    "ke", "ki", "ka", "ko", "hain", "karo", "raha", "rahi",
    "chahiye", "batao", "bata", "hoga", "hogi",
}


def detect_language(text: str) -> Language:
    """
    Detect whether a message is Hindi (Devanagari script),
    Hinglish (Roman script with Hindi words), or English.

    Returns a Language enum value.
    """
    if not text:
        return Language.ENGLISH

    # Devanagari script → pure Hindi
    if _DEVANAGARI_PATTERN.search(text):
        return Language.HINDI

    # Check for Hinglish Roman keywords
    words = set(re.findall(r"\b[a-zA-Z]+\b", text.lower()))
    hinglish_matches = words & _HINGLISH_KEYWORDS
    if hinglish_matches:
        return Language.HINGLISH

    return Language.ENGLISH


def is_hindi_or_hinglish(text: str) -> bool:
    """Return True if message is Hindi or Hinglish."""
    lang = detect_language(text)
    return lang in (Language.HINDI, Language.HINGLISH)
