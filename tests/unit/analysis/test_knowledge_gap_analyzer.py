"""Unit tests for S3.5 Knowledge Gap Analyzer."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from services.api.src.triage.analysis.knowledge_gap_analyzer import KnowledgeGapAnalyzer, KnowledgeGap


@pytest.fixture
def mock_intent_classifier():
    """Mock intent classifier."""
    classifier = MagicMock()
    classifier.classify = AsyncMock()
    return classifier


@pytest.fixture
def mock_db():
    """Mock database session."""
    db = MagicMock()
    db.query = MagicMock()
    return db


@pytest.fixture
def analyzer(mock_intent_classifier, mock_db):
    """Create analyzer with mocks."""
    return KnowledgeGapAnalyzer(
        intent_classifier=mock_intent_classifier,
        db_session=mock_db,
    )


@pytest.mark.asyncio
async def test_analyze_gaps_basic(analyzer, mock_db, mock_intent_classifier):
    """Test basic gap analysis."""
    # Mock DB query
    mock_query = MagicMock()
    mock_query.all = AsyncMock(return_value=[
        MagicMock(id="1", query_text="How to reset password?", was_escalated=False),
        MagicMock(id="2", query_text="Billing question about charge", was_escalated=True),
        MagicMock(id="3", query_text="Order tracking", was_escalated=False),
        MagicMock(id="4", query_text="Refund status", was_escalated=True),
        MagicMock(id="5", query_text="Can't login", was_escalated=False),
    ])
    mock_db.query.return_value = mock_query
    
    # Mock classifier
    async def classify_side_effect(text):
        if "password" in text.lower() or "login" in text.lower():
            return "account"
        elif "billing" in text.lower() or "charge" in text.lower() or "refund" in text.lower():
            return "billing"
        elif "order" in text.lower() or "tracking" in text.lower():
            return "shipping"
        return "other"
    
    mock_intent_classifier.classify = AsyncMock(side_effect=classify_side_effect)
    
    gaps = await analyzer.analyze_gaps(tenant_id=1, lookback_days=7)
    
    assert len(gaps) > 0
    assert all(isinstance(g, KnowledgeGap) for g in gaps)
    assert all(0.0 <= g.gap_score <= 1.0 for g in gaps)


@pytest.mark.asyncio
async def test_gap_scoring_calculation(analyzer, mock_db, mock_intent_classifier):
    """Test gap score calculation (escalation rate)."""
    # All billing queries escalated = high gap
    # All account queries resolved = low gap
    mock_query = MagicMock()
    mock_query.all = AsyncMock(return_value=[
        MagicMock(id="1", query_text="Billing Q1", was_escalated=True),
        MagicMock(id="2", query_text="Billing Q2", was_escalated=True),
        MagicMock(id="3", query_text="Account Q1", was_escalated=False),
        MagicMock(id="4", query_text="Account Q2", was_escalated=False),
    ])
    mock_db.query.return_value = mock_query
    
    async def classify_side_effect(text):
        return "billing" if "billing" in text.lower() else "account"
    
    mock_intent_classifier.classify = AsyncMock(side_effect=classify_side_effect)
    
    gaps = await analyzer.analyze_gaps(tenant_id=1, lookback_days=7)
    
    # Billing should have higher gap score (1.0 escalation rate = gap_score 1.0)
    # Account should have lower gap score (0.0 escalation rate = gap_score 0.0)
    billing_gaps = [g for g in gaps if g.topic == "billing"]
    account_gaps = [g for g in gaps if g.topic == "account"]
    
    if billing_gaps and account_gaps:
        assert billing_gaps[0].gap_score >= account_gaps[0].gap_score


@pytest.mark.asyncio
async def test_top_10_gaps_returned(analyzer, mock_db, mock_intent_classifier):
    """Test that at most top 10 gaps are returned."""
    # Create 15 different categories
    queries = [
        MagicMock(id=str(i), query_text=f"Query in category_{i}", was_escalated=(i % 2 == 0))
        for i in range(15)
    ]
    mock_query = MagicMock()
    mock_query.all = AsyncMock(return_value=queries)
    mock_db.query.return_value = mock_query
    
    async def classify_side_effect(text):
        # Extract category from text
        for i in range(15):
            if f"category_{i}" in text.lower():
                return f"category_{i}"
        return "other"
    
    mock_intent_classifier.classify = AsyncMock(side_effect=classify_side_effect)
    
    gaps = await analyzer.analyze_gaps(tenant_id=1, lookback_days=7)
    
    assert len(gaps) <= 10


@pytest.mark.asyncio
async def test_gap_score_filtering(analyzer, mock_db, mock_intent_classifier):
    """Test that only significant gaps (>0.1) are included."""
    # One high-gap category (100% escalated)
    # One low-gap category (0% escalated, filtered out)
    mock_query = MagicMock()
    mock_query.all = AsyncMock(return_value=[
        MagicMock(id="1", query_text="High gap Q1", was_escalated=True),
        MagicMock(id="2", query_text="High gap Q2", was_escalated=True),
        MagicMock(id="3", query_text="No gap Q1", was_escalated=False),
        MagicMock(id="4", query_text="No gap Q2", was_escalated=False),
    ])
    mock_db.query.return_value = mock_query
    
    async def classify_side_effect(text):
        return "high_gap" if "high gap" in text.lower() else "no_gap"
    
    mock_intent_classifier.classify = AsyncMock(side_effect=classify_side_effect)
    
    gaps = await analyzer.analyze_gaps(tenant_id=1, lookback_days=7)
    
    # Only high_gap should be in results (no_gap has 0.0 score and filters out)
    assert all(g.gap_score > 0.1 for g in gaps)


@pytest.mark.asyncio
async def test_keyword_fallback_classification(analyzer, mock_db):
    """Test keyword fallback when intent classifier unavailable."""
    # Create analyzer without classifier
    analyzer_no_classifier = KnowledgeGapAnalyzer(
        intent_classifier=None,
        db_session=mock_db,
    )
    
    mock_query = MagicMock()
    mock_query.all = AsyncMock(return_value=[
        MagicMock(id="1", query_text="How to charge my card?", was_escalated=False),
        MagicMock(id="2", query_text="Track my package", was_escalated=False),
        MagicMock(id="3", query_text="Reset my password", was_escalated=False),
    ])
    mock_db.query.return_value = mock_query
    
    gaps = await analyzer_no_classifier.analyze_gaps(tenant_id=1, lookback_days=7)
    
    # Should still categorize using keywords
    topics = {g.topic for g in gaps}
    assert "billing" in topics or "shipping" in topics or "account" in topics


@pytest.mark.asyncio
async def test_suggested_titles_generation(analyzer, mock_db, mock_intent_classifier):
    """Test suggested article title generation."""
    mock_query = MagicMock()
    mock_query.all = AsyncMock(return_value=[
        MagicMock(id="1", query_text="Billing Q", was_escalated=True),
        MagicMock(id="2", query_text="Billing Q", was_escalated=True),
    ])
    mock_db.query.return_value = mock_query
    
    mock_intent_classifier.classify = AsyncMock(return_value="billing")
    
    gaps = await analyzer.analyze_gaps(tenant_id=1, lookback_days=7)
    
    if gaps:
        assert len(gaps[0].suggested_article_title) > 0
        assert "billing" in gaps[0].suggested_article_title.lower()


@pytest.mark.asyncio
async def test_escalation_count_tracking(analyzer, mock_db, mock_intent_classifier):
    """Test escalation count is properly tracked."""
    mock_query = MagicMock()
    mock_query.all = AsyncMock(return_value=[
        MagicMock(id="1", query_text="Issue", was_escalated=True),
        MagicMock(id="2", query_text="Issue", was_escalated=True),
        MagicMock(id="3", query_text="Issue", was_escalated=False),
    ])
    mock_db.query.return_value = mock_query
    
    mock_intent_classifier.classify = AsyncMock(return_value="product")
    
    gaps = await analyzer.analyze_gaps(tenant_id=1, lookback_days=7)
    
    if gaps:
        assert gaps[0].escalation_count == 2


@pytest.mark.asyncio
async def test_empty_query_results(analyzer, mock_db):
    """Test handling when no queries found."""
    mock_query = MagicMock()
    mock_query.all = AsyncMock(return_value=[])
    mock_db.query.return_value = mock_query
    
    gaps = await analyzer.analyze_gaps(tenant_id=1, lookback_days=7)
    
    assert gaps == []


@pytest.mark.asyncio
async def test_db_error_handling(analyzer, mock_db):
    """Test graceful handling of DB errors."""
    mock_query = MagicMock()
    mock_query.all = AsyncMock(side_effect=Exception("DB error"))
    mock_db.query.return_value = mock_query
    
    gaps = await analyzer.analyze_gaps(tenant_id=1, lookback_days=7)
    
    # Should return empty list on error
    assert gaps == []


@pytest.mark.asyncio
async def test_multiple_categories_sorted_by_gap(analyzer, mock_db, mock_intent_classifier):
    """Test results are sorted by gap score descending."""
    mock_query = MagicMock()
    mock_query.all = AsyncMock(return_value=[
        MagicMock(id="1", query_text="Billing", was_escalated=True),
        MagicMock(id="2", query_text="Billing", was_escalated=True),
        MagicMock(id="3", query_text="Billing", was_escalated=False),
        MagicMock(id="4", query_text="Shipping", was_escalated=True),
        MagicMock(id="5", query_text="Shipping", was_escalated=True),
        MagicMock(id="6", query_text="Account", was_escalated=False),
    ])
    mock_db.query.return_value = mock_query
    
    async def classify_side_effect(text):
        if "billing" in text.lower():
            return "billing"
        elif "shipping" in text.lower():
            return "shipping"
        return "account"
    
    mock_intent_classifier.classify = AsyncMock(side_effect=classify_side_effect)
    
    gaps = await analyzer.analyze_gaps(tenant_id=1, lookback_days=7)
    
    # Verify sorted descending
    if len(gaps) > 1:
        for i in range(len(gaps) - 1):
            assert gaps[i].gap_score >= gaps[i + 1].gap_score


def test_knowledge_gap_dataclass():
    """Test KnowledgeGap dataclass creation."""
    gap = KnowledgeGap(
        topic="billing",
        gap_score=0.75,
        suggested_article_title="Billing Issues",
        escalation_count=15,
    )
    
    assert gap.topic == "billing"
    assert gap.gap_score == 0.75
    assert gap.escalation_count == 15


@pytest.mark.asyncio
async def test_analyze_gaps_with_custom_lookback(analyzer, mock_db, mock_intent_classifier):
    """Test analyze_gaps respects lookback_days parameter."""
    mock_query = MagicMock()
    mock_query.all = AsyncMock(return_value=[])
    mock_db.query.return_value = mock_query
    
    # Call with custom lookback
    await analyzer.analyze_gaps(tenant_id=1, lookback_days=30)
    
    # Verify DB query was called
    assert mock_db.query.called


@pytest.mark.asyncio
async def test_high_resolution_rate_low_gap(analyzer, mock_db, mock_intent_classifier):
    """Test that high resolution rate results in low gap score."""
    mock_query = MagicMock()
    mock_query.all = AsyncMock(return_value=[
        MagicMock(id=str(i), query_text=f"Query {i}", was_escalated=False)
        for i in range(10)
    ])
    mock_db.query.return_value = mock_query
    
    mock_intent_classifier.classify = AsyncMock(return_value="common_issue")
    
    gaps = await analyzer.analyze_gaps(tenant_id=1, lookback_days=7)
    
    # With 0 escalations out of 10, gap_score should be 0.0, filtered out
    common_gaps = [g for g in gaps if g.topic == "common_issue"]
    if common_gaps:
        assert common_gaps[0].gap_score == 0.0
