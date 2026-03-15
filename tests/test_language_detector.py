"""Tests for language detection: Hindi (Devanagari), Hinglish (Roman), English."""

import pytest

from backend.chatbot.language_detector import Language, detect_language, is_hindi_or_hinglish


class TestDevanagariDetection:
    def test_pure_devanagari_is_hindi(self):
        assert detect_language("मुझे CSE में admission लेना है") == Language.HINDI

    def test_devanagari_single_word(self):
        assert detect_language("नमस्ते") == Language.HINDI

    def test_devanagari_mixed_with_roman(self):
        # Devanagari chars take priority
        assert detect_language("Mera score 85 percentile है।") == Language.HINDI

    def test_devanagari_numbers_only_not_hindi(self):
        # Pure numbers with no Devanagari
        result = detect_language("12345")
        assert result == Language.ENGLISH


class TestHinglishDetection:
    def test_hinglish_kya_hai(self):
        assert detect_language("CSE mein admission kya chahiye?") == Language.HINGLISH

    def test_hinglish_fees_kitni(self):
        assert detect_language("fees kitni hai bhai?") == Language.HINGLISH

    def test_hinglish_batao(self):
        assert detect_language("hostel ke baare mein batao") == Language.HINGLISH

    def test_hinglish_kaise(self):
        assert detect_language("apply kaise karna hai?") == Language.HINGLISH

    def test_hinglish_mujhe(self):
        assert detect_language("mujhe CSE mein admission chahiye") == Language.HINGLISH

    def test_hinglish_haan(self):
        assert detect_language("haan, mera JEE score 78 percentile hai") == Language.HINGLISH


class TestEnglishDetection:
    def test_plain_english(self):
        assert detect_language("What are the fees for CSE?") == Language.ENGLISH

    def test_english_eligibility_query(self):
        assert detect_language("I want to know about eligibility for B.Tech.") == Language.ENGLISH

    def test_english_placement(self):
        assert detect_language("What is the average placement package?") == Language.ENGLISH

    def test_empty_string_is_english(self):
        assert detect_language("") == Language.ENGLISH

    def test_whitespace_only_is_english(self):
        assert detect_language("   ") == Language.ENGLISH


class TestIsHindiOrHinglish:
    def test_hindi_returns_true(self):
        assert is_hindi_or_hinglish("मुझे admission लेना है") is True

    def test_hinglish_returns_true(self):
        assert is_hindi_or_hinglish("kya fees hai?") is True

    def test_english_returns_false(self):
        assert is_hindi_or_hinglish("What is the hostel fee?") is False

    def test_empty_string_returns_false(self):
        assert is_hindi_or_hinglish("") is False
