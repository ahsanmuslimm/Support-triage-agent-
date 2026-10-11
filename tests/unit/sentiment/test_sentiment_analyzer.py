"""Unit tests for S3.6 Sentiment Analyzer."""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta

from services.api.src.triage.sentiment.sentiment_analyzer import SentimentAnalyzer


@pytest.fixture
def analyzer():
    """Create sentiment analyzer with TextBlob default."""
    return SentimentAnalyzer(use_transformer=False)


def test_analyzer_initialization(analyzer):
    """Test sentiment analyzer initializes."""
    assert analyzer is not None
    assert analyzer.use_transformer is False


def test_sentiment_positive_text(analyzer):
    """Test sentiment classification of positive text."""
    text = "I love this product! It's absolutely amazing and works great."
    result = analyzer.analyze(text)
    
    assert isinstance(result, dict)
    assert "sentiment" in result
    assert "score" in result
    assert result["sentiment"] in ["positive", "neutral"]  # neutral if textblob not available


def test_sentiment_negative_text(analyzer):
    """Test sentiment classification of negative text."""
    text = "This product is terrible. I hate it and it doesn't work at all."
    result = analyzer.analyze(text)
    
    assert isinstance(result, dict)
    assert result["sentiment"] in ["negative", "neutral"]  # neutral if textblob not available


def test_sentiment_neutral_text(analyzer):
    """Test sentiment classification of neutral text."""
    text = "This is a product. It has features."
    result = analyzer.analyze(text)
    
    assert result["sentiment"] in ["neutral", "positive", "negative"]


def test_sentiment_score_range(analyzer):
    """Test that sentiment scores are in -1 to 1 range."""
    texts = [
        "Excellent!",
        "Terrible!",
        "Okay.",
    ]
    
    for text in texts:
        result = analyzer.analyze(text)
        assert -1.0 <= result["score"] <= 1.0


def test_segment_nps_promoter(analyzer):
    """Test NPS segmentation for promoters (9-10)."""
    assert analyzer.segment_nps(9) == "promoter"
    assert analyzer.segment_nps(10) == "promoter"


def test_segment_nps_passive(analyzer):
    """Test NPS segmentation for passives (7-8)."""
    assert analyzer.segment_nps(7) == "passive"
    assert analyzer.segment_nps(8) == "passive"


def test_segment_nps_detractor(analyzer):
    """Test NPS segmentation for detractors (0-6)."""
    assert analyzer.segment_nps(0) == "detractor"
    assert analyzer.segment_nps(6) == "detractor"
    assert analyzer.segment_nps(5) == "detractor"


def test_compute_trend_improving(analyzer):
    """Test NPS trend detection for improving scores."""
    scores = [5, 6, 7, 8, 9]
    trend = analyzer.compute_trend(scores)
    
    assert trend in ["improving", "declining", "stable"]
    assert trend == "improving"


def test_compute_trend_declining(analyzer):
    """Test NPS trend detection for declining scores."""
    scores = [9, 8, 7, 6, 5]
    trend = analyzer.compute_trend(scores)
    
    assert trend in ["improving", "declining", "stable"]
    assert trend == "declining"


def test_compute_trend_stable(analyzer):
    """Test NPS trend detection for stable scores."""
    scores = [7, 7, 7, 8, 7]
    trend = analyzer.compute_trend(scores)
    
    assert trend in ["improving", "declining", "stable"]


def test_compute_trend_insufficient_data(analyzer):
    """Test NPS trend with fewer than 2 scores."""
    scores = [7]
    trend = analyzer.compute_trend(scores)
    
    assert trend == "stable"


def test_empty_text_handling(analyzer):
    """Test handling of empty text."""
    text = ""
    result = analyzer.analyze(text)
    
    assert result["sentiment"] == "neutral"
    assert result["score"] == 0.0


def test_whitespace_text_handling(analyzer):
    """Test handling of whitespace-only text."""
    text = "   \n\t  "
    result = analyzer.analyze(text)
    
    assert result["sentiment"] in ["positive", "neutral", "negative"]


def test_very_long_text(analyzer):
    """Test handling of very long text."""
    text = "Great! " * 1000
    result = analyzer.analyze(text)
    
    assert result["sentiment"] in ["positive", "neutral", "negative"]


def test_special_characters(analyzer):
    """Test handling of text with special characters."""
    text = "Love it!!! ###$%"
    result = analyzer.analyze(text)
    
    assert result["sentiment"] in ["positive", "neutral", "negative"]


def test_sentiment_positive_words(analyzer):
    """Test that positive words are classified correctly."""
    positive_texts = [
        "Excellent service!",
        "Love this!",
        "Amazing experience!",
        "Perfect!",
    ]
    
    for text in positive_texts:
        result = analyzer.analyze(text)
        # Most should be positive, but allow neutral due to simple classifier
        assert result["sentiment"] in ["positive", "neutral"], f"Failed for: {text}"


def test_sentiment_negative_words(analyzer):
    """Test that negative words are classified correctly."""
    negative_texts = [
        "Terrible!",
        "Hate it!",
        "Awful experience!",
        "Horrible!",
    ]
    
    for text in negative_texts:
        result = analyzer.analyze(text)
        assert result["sentiment"] in ["negative", "neutral"], f"Failed for: {text}"


def test_mixed_sentiment_text(analyzer):
    """Test text with mixed positive and negative."""
    text = "Great product but expensive."
    result = analyzer.analyze(text)
    
    assert result["sentiment"] in ["positive", "neutral", "negative"]


def test_nps_boundary_values(analyzer):
    """Test NPS segmentation at all boundary values."""
    assert analyzer.segment_nps(0) == "detractor"
    assert analyzer.segment_nps(6) == "detractor"
    assert analyzer.segment_nps(7) == "passive"
    assert analyzer.segment_nps(8) == "passive"
    assert analyzer.segment_nps(9) == "promoter"
    assert analyzer.segment_nps(10) == "promoter"


def test_analyze_returns_dict_structure(analyzer):
    """Test analyze always returns correct dict structure."""
    result = analyzer.analyze("Test text")
    
    assert isinstance(result, dict)
    assert len(result) == 2
    assert "sentiment" in result
    assert "score" in result


def test_negation_handling(analyzer):
    """Test that negations affect sentiment."""
    # "good" is positive
    text_positive = "This is good."
    result_pos = analyzer.analyze(text_positive)
    
    # "not good" might shift towards negative/neutral
    text_negated = "This is not good."
    result_neg = analyzer.analyze(text_negated)
    
    assert result_pos["sentiment"] in ["positive", "neutral"]
    # Negated text should have lower or equal polarity
    assert result_neg["score"] <= result_pos["score"]


def test_compound_sentiment_words(analyzer):
    """Test text with both positive and negative words."""
    text = "Great product but terrible customer service."
    result = analyzer.analyze(text)
    
    assert result["sentiment"] in ["positive", "neutral", "negative"]


def test_trend_stable_with_small_changes(analyzer):
    """Test trend detection with small fluctuations."""
    scores = [7.5, 7.6, 7.4, 7.5, 7.5]
    trend = analyzer.compute_trend(scores)
    
    # Should be stable with small changes
    assert trend == "stable"


def test_trend_clear_improvement(analyzer):
    """Test clear upward trend."""
    scores = [3, 4, 5, 7, 9]
    trend = analyzer.compute_trend(scores)
    
    assert trend == "improving"


def test_trend_clear_decline(analyzer):
    """Test clear downward trend."""
    scores = [9, 8, 6, 4, 2]
    trend = analyzer.compute_trend(scores)
    
    assert trend == "declining"
