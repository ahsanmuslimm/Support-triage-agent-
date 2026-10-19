"""Tests for the triage worker pipeline (no DB required)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from triage_worker.config import DEFAULT_INTENT_KEYWORDS
from triage_worker.processor import load_intent_keywords, triage_text

pytestmark = pytest.mark.unit


class TestTriageText:
    def test_refund_keyword_routes_to_refund_intent(self):
        outcome = triage_text(
            "I want a refund for my order", channel="email", keywords=DEFAULT_INTENT_KEYWORDS
        )
        assert outcome.top_intent == "refund"
        assert outcome.top_confidence >= 0.9
        assert outcome.fallback_used is True

    def test_technical_keywords_detected(self):
        outcome = triage_text(
            "the app keeps crashing with an error",
            channel="web_chat",
            keywords=DEFAULT_INTENT_KEYWORDS,
        )
        assert outcome.top_intent == "technical_issue"

    def test_unknown_message_defaults_to_other_low_confidence(self):
        outcome = triage_text("xyzzy plugh", channel="email", keywords=DEFAULT_INTENT_KEYWORDS)
        assert outcome.top_intent == "other"
        assert outcome.top_confidence == pytest.approx(0.5)

    def test_decision_always_produces_autonomy_and_action(self):
        outcome = triage_text(
            "I want a refund for my order", channel="email", keywords=DEFAULT_INTENT_KEYWORDS
        )
        assert 0 <= outcome.autonomy_level <= 3
        assert outcome.action
        assert outcome.reason


class TestLoadIntentKeywords:
    def test_defaults_when_env_unset(self, monkeypatch):
        monkeypatch.delenv("TRIAGE_INTENT_KEYWORDS", raising=False)
        assert load_intent_keywords() == DEFAULT_INTENT_KEYWORDS

    def test_env_json_overrides(self, monkeypatch):
        monkeypatch.setenv("TRIAGE_INTENT_KEYWORDS", '{"billing": ["invoice"]}')
        keywords = load_intent_keywords()
        assert keywords == {"billing": ["invoice"]}
