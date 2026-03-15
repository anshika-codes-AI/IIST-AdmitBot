"""Tests for the multi-provider AI client: parsing and rule-based fallback."""

import pytest

from backend.chatbot.ai_client import (
    AIResponse,
    GeminiResponse,
    _parse_structured_output,
    _rule_based_response,
)


class TestAIResponse:
    def test_backward_compat_alias(self):
        """GeminiResponse must be an alias for AIResponse."""
        assert GeminiResponse is AIResponse

    def test_default_values(self):
        r = AIResponse(reply_text="Hello")
        assert r.reply_text == "Hello"
        assert r.intent_score is None
        assert r.extracted_data == {}
        assert r.needs_escalation is False
        assert r.raw_text == ""


class TestParseStructuredOutput:
    def test_parses_reply_and_json_block(self):
        raw = (
            "Great news! CSE at IIST has 120 seats. 🎓\n\n"
            "```json\n"
            '{"intent_score": "Hot", "extracted_data": {"name": "Rahul", "city": "Indore"}, "needs_escalation": false}\n'
            "```"
        )
        result = _parse_structured_output(raw)
        assert "Great news" in result.reply_text
        assert result.intent_score == "Hot"
        assert result.extracted_data["name"] == "Rahul"
        assert result.extracted_data["city"] == "Indore"
        assert result.needs_escalation is False

    def test_raw_text_without_json_block(self):
        raw = "Hi! I'm AdmitBot and I can help you."
        result = _parse_structured_output(raw)
        assert result.reply_text == "Hi! I'm AdmitBot and I can help you."
        assert result.intent_score is None
        assert result.extracted_data == {}

    def test_malformed_json_block_does_not_crash(self):
        raw = "Some reply\n```json\n{not valid json}\n```"
        result = _parse_structured_output(raw)
        # Reply text is extracted even if JSON is invalid
        assert "Some reply" in result.reply_text
        assert result.intent_score is None

    def test_needs_escalation_true(self):
        raw = (
            "Please speak to a counsellor.\n"
            '```json\n{"intent_score": "Hot", "extracted_data": {}, "needs_escalation": true}\n```'
        )
        result = _parse_structured_output(raw)
        assert result.needs_escalation is True

    def test_json_block_stripped_from_reply(self):
        raw = (
            "CSE fees are ₹85,000/year.\n"
            '```json\n{"intent_score": "Warm", "extracted_data": {}, "needs_escalation": false}\n```'
        )
        result = _parse_structured_output(raw)
        assert "```json" not in result.reply_text
        assert "₹85,000" in result.reply_text


class TestRuleBasedResponse:
    def test_cse_query(self):
        r = _rule_based_response("tell me about cse admission")
        assert "CSE" in r.reply_text or "Computer Science" in r.reply_text
        assert r.intent_score == "Warm"
        assert r.needs_escalation is False

    def test_hostel_query(self):
        r = _rule_based_response("is there a hostel on campus?")
        assert "Hostel" in r.reply_text or "hostel" in r.reply_text

    def test_fees_query(self):
        r = _rule_based_response("what are the fees?")
        assert "₹" in r.reply_text

    def test_placement_query(self):
        r = _rule_based_response("What is the placement package?")
        assert "LPA" in r.reply_text or "placement" in r.reply_text.lower()

    def test_deadline_query(self):
        r = _rule_based_response("what is the last date to apply?")
        assert "2026" in r.reply_text

    def test_scholarship_query(self):
        r = _rule_based_response("Is there any scholarship available?")
        assert "scholarship" in r.reply_text.lower() or "%" in r.reply_text

    def test_generic_fallback(self):
        r = _rule_based_response("good morning sir")
        assert "AdmitBot" in r.reply_text
        assert r.intent_score == "Cold"

    def test_hinglish_fee_query(self):
        r = _rule_based_response("fees kitni hai bhai?")
        assert "₹" in r.reply_text
