"""Tests for knowledge base prompt language policy wiring."""

from backend.chatbot.knowledge_base import get_system_prompt


def test_prompt_includes_preferred_language_english():
    prompt = get_system_prompt(
        student_message="What are the CSE fees?",
        conversation_context="Student: नमस्ते",
        preferred_language="english",
    )

    assert "Preferred language for this turn: english" in prompt
    assert "reply only in English" in prompt


def test_prompt_includes_preferred_language_hinglish():
    prompt = get_system_prompt(
        student_message="fees kitni hai",
        preferred_language="hinglish",
    )

    assert "Preferred language for this turn: hinglish" in prompt
    assert "Roman script Hindi/English mix" in prompt
