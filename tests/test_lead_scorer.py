"""Tests for lead scoring: Hot / Warm / Cold classification."""

import pytest

from backend.chatbot.lead_scorer import LeadScore, score_lead


class TestAIScoreOverride:
    def test_ai_hot_score_trusted(self):
        assert score_lead("hello", ai_score="Hot") == LeadScore.HOT

    def test_ai_warm_score_trusted(self):
        assert score_lead("hello", ai_score="Warm") == LeadScore.WARM

    def test_ai_cold_score_trusted(self):
        assert score_lead("hello", ai_score="Cold") == LeadScore.COLD

    def test_ai_score_case_insensitive(self):
        assert score_lead("hello", ai_score="hot") == LeadScore.HOT

    def test_invalid_ai_score_falls_back_to_rules(self):
        # "Maybe" is not a valid score — should fall through to rule-based
        result = score_lead("CSE mein admission chahiye confirm", ai_score="Maybe")
        assert result == LeadScore.HOT


class TestHotSignals:
    def test_admission_lena_is_hot(self):
        assert score_lead("mujhe admission lena hai") == LeadScore.HOT

    def test_confirm_keyword_is_hot(self):
        assert score_lead("I want to confirm my seat") == LeadScore.HOT

    def test_deadline_keyword_is_hot(self):
        assert score_lead("What is the last date? I need to apply today") == LeadScore.HOT

    def test_call_me_is_hot(self):
        assert score_lead("please call me back") == LeadScore.HOT

    def test_how_to_apply_is_hot(self):
        assert score_lead("How to apply for CSE admission?") == LeadScore.HOT

    def test_phone_and_name_together_is_hot(self):
        # Two data points + phone → Hot even without keywords
        assert score_lead("my name is Rahul", has_phone=True, has_name=True) == LeadScore.HOT


class TestWarmSignals:
    def test_percentile_query_is_warm(self):
        assert score_lead("I have 80 percentile in JEE") == LeadScore.WARM

    def test_hostel_query_is_warm(self):
        assert score_lead("Do you have hostel facilities?") == LeadScore.WARM

    def test_placement_query_is_warm(self):
        assert score_lead("What are the placement packages?") == LeadScore.WARM

    def test_fees_query_is_warm(self):
        assert score_lead("What are the fees for B.Tech?") == LeadScore.WARM

    def test_has_phone_alone_is_warm(self):
        assert score_lead("hi there", has_phone=True) == LeadScore.WARM


class TestColdSignals:
    def test_generic_greeting_is_cold(self):
        assert score_lead("hi") == LeadScore.COLD

    def test_no_signals_cold(self):
        assert score_lead("good morning") == LeadScore.COLD

    def test_no_data_points_cold(self):
        assert score_lead("hello world", has_phone=False, has_name=False, has_score=False) == LeadScore.COLD
