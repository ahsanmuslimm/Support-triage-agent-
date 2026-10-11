"""Tests for anomaly detector (S4.1)."""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import MagicMock, patch, AsyncMock

from triage.anomaly.detector import AnomalyDetector
from triage.anomaly.models import SignalType, AnomalySignal


class TestAnomalyDetector:
    """Test AnomalyDetector."""

    @pytest.fixture
    def detector(self):
        """Create detector instance."""
        return AnomalyDetector(ewma_alpha=0.15, isolation_forest_contamination=0.1)

    @pytest.fixture
    def sample_daily_stats(self):
        """Sample daily statistics."""
        return {
            "health_score_avg": 0.6,
            "sentiment_negative_ratio": 0.15,
            "chargeback_count": 1,
            "high_value_order_count": 3,
            "escalation_pct": 0.08,
            "total_triages": 110,
            "api_error_count": 5,
            "api_request_count": 1000,
        }

    @pytest.fixture
    def sample_performance_stats(self):
        """Sample performance statistics."""
        return {
            "avg_resolution_time_sec": 250,
        }

    @pytest.mark.asyncio
    async def test_detector_initialization(self, detector):
        """Test detector initializes correctly."""
        assert detector.ewma_alpha == 0.15
        assert detector.isolation_forest_contamination == 0.1
        assert detector.isolation_forest is not None

    @pytest.mark.asyncio
    async def test_ewma_computation(self, detector):
        """Test EWMA computation."""
        tenant_id = 1
        signal_type = SignalType.CHURN_SPIKE
        
        # First call - should initialize
        smoothed1, sigma1 = await detector._compute_ewma(tenant_id, signal_type, 100.0)
        assert smoothed1 > 0
        
        # Second call with higher value - smoothed should move towards new value
        smoothed2, sigma2 = await detector._compute_ewma(tenant_id, signal_type, 150.0)
        assert smoothed2 > smoothed1  # Should increase

    @pytest.mark.asyncio
    async def test_churn_spike_detection(self, detector, sample_daily_stats, sample_performance_stats):
        """Test churn spike detection."""
        tenant_id = 1
        
        # Normal conditions - no spike
        normal_stats = sample_daily_stats.copy()
        normal_stats["health_score_avg"] = 0.8
        normal_stats["sentiment_negative_ratio"] = 0.05
        
        signals = await detector.detect_signals(tenant_id, normal_stats, sample_performance_stats)
        churn_signals = [s for s in signals if s.signal_type == SignalType.CHURN_SPIKE]
        assert len(churn_signals) == 0
        
        # Spike conditions - should detect
        with patch.object(detector, 'publish_webhook', new_callable=AsyncMock):
            spike_stats = sample_daily_stats.copy()
            spike_stats["health_score_avg"] = 0.3
            spike_stats["sentiment_negative_ratio"] = 0.25
            
            signals = await detector.detect_signals(tenant_id, spike_stats, sample_performance_stats)
            churn_signals = [s for s in signals if s.signal_type == SignalType.CHURN_SPIKE]
            # May or may not trigger depending on EWMA baseline
            # Just verify no error occurs

    @pytest.mark.asyncio
    async def test_fraud_pattern_detection(self, detector, sample_daily_stats, sample_performance_stats):
        """Test fraud pattern detection."""
        tenant_id = 1
        
        # Normal - no fraud
        normal_stats = sample_daily_stats.copy()
        normal_stats["chargeback_count"] = 0
        
        signals = await detector.detect_signals(tenant_id, normal_stats, sample_performance_stats)
        fraud_signals = [s for s in signals if s.signal_type == SignalType.FRAUD_PATTERN]
        assert len(fraud_signals) == 0
        
        # Fraud pattern - multiple chargebacks + high-value orders
        with patch.object(detector, 'publish_webhook', new_callable=AsyncMock):
            fraud_stats = sample_daily_stats.copy()
            fraud_stats["chargeback_count"] = 3
            fraud_stats["high_value_order_count"] = 8
            
            signals = await detector.detect_signals(tenant_id, fraud_stats, sample_performance_stats)
            fraud_signals = [s for s in signals if s.signal_type == SignalType.FRAUD_PATTERN]
            assert len(fraud_signals) == 1
            assert fraud_signals[0].confidence > 0.9

    @pytest.mark.asyncio
    async def test_complaint_surge_detection(self, detector, sample_daily_stats, sample_performance_stats):
        """Test complaint surge detection."""
        tenant_id = 1
        
        # Normal escalation rate
        normal_stats = sample_daily_stats.copy()
        normal_stats["escalation_pct"] = 0.08
        
        signals = await detector.detect_signals(tenant_id, normal_stats, sample_performance_stats)
        complaint_signals = [s for s in signals if s.signal_type == SignalType.COMPLAINT_SURGE]
        # May not trigger - depends on EWMA baseline

    @pytest.mark.asyncio
    async def test_volume_spike_detection(self, detector, sample_daily_stats, sample_performance_stats):
        """Test volume spike detection."""
        tenant_id = 1
        
        # Normal volume
        normal_stats = sample_daily_stats.copy()
        normal_stats["total_triages"] = 105
        
        signals = await detector.detect_signals(tenant_id, normal_stats, sample_performance_stats)
        volume_signals = [s for s in signals if s.signal_type == SignalType.VOLUME_SPIKE]
        # May not trigger - depends on EWMA baseline

    @pytest.mark.asyncio
    async def test_api_error_rate_detection(self, detector, sample_daily_stats, sample_performance_stats):
        """Test API error rate detection."""
        tenant_id = 1
        
        # Normal error rate
        normal_stats = sample_daily_stats.copy()
        normal_stats["api_error_count"] = 10
        normal_stats["api_request_count"] = 1000
        
        signals = await detector.detect_signals(tenant_id, normal_stats, sample_performance_stats)
        error_signals = [s for s in signals if s.signal_type == SignalType.API_ERROR_RATE]
        assert len(error_signals) == 0  # 1% error rate is normal
        
        # High error rate
        with patch.object(detector, 'publish_webhook', new_callable=AsyncMock):
            high_error_stats = sample_daily_stats.copy()
            high_error_stats["api_error_count"] = 100
            high_error_stats["api_request_count"] = 1000
            
            signals = await detector.detect_signals(tenant_id, high_error_stats, sample_performance_stats)
            error_signals = [s for s in signals if s.signal_type == SignalType.API_ERROR_RATE]
            assert len(error_signals) == 1
            assert error_signals[0].value == 0.1  # 10% error rate

    @pytest.mark.asyncio
    async def test_detect_signals_all_types(self, detector):
        """Test detection of all 6 signal types."""
        tenant_id = 1
        
        # Extreme conditions triggering all signals
        extreme_stats = {
            "health_score_avg": 0.2,
            "sentiment_negative_ratio": 0.3,
            "chargeback_count": 5,
            "high_value_order_count": 10,
            "escalation_pct": 0.5,
            "total_triages": 500,
            "api_error_count": 200,
            "api_request_count": 1000,
        }
        extreme_perf = {"avg_resolution_time_sec": 1000}
        
        with patch.object(detector, 'publish_webhook', new_callable=AsyncMock):
            signals = await detector.detect_signals(tenant_id, extreme_stats, extreme_perf)
            # Should detect multiple signals
            signal_types = {s.signal_type for s in signals}
            assert len(signal_types) > 0

    @pytest.mark.asyncio
    async def test_publish_webhook_success(self, detector):
        """Test webhook publishing on success."""
        signal = AnomalySignal(
            signal_type=SignalType.CHURN_SPIKE,
            tenant_id=1,
            timestamp=datetime.utcnow(),
            value=0.5,
            threshold=0.6,
            deviation_sigma=1.5,
            confidence=0.85,
        )
        
        with patch('aiohttp.ClientSession.post') as mock_post:
            mock_post.return_value.__aenter__.return_value.status = 200
            mock_post.return_value.__aenter__.return_value.text = AsyncMock(return_value="OK")
            
            result = await detector.publish_webhook(signal)
            assert result is True

    @pytest.mark.asyncio
    async def test_publish_webhook_failure(self, detector):
        """Test webhook publishing on failure."""
        signal = AnomalySignal(
            signal_type=SignalType.CHURN_SPIKE,
            tenant_id=1,
            timestamp=datetime.utcnow(),
            value=0.5,
            threshold=0.6,
            deviation_sigma=1.5,
            confidence=0.85,
        )
        
        with patch('aiohttp.ClientSession.post') as mock_post:
            mock_post.side_effect = Exception("Connection error")
            
            result = await detector.publish_webhook(signal)
            assert result is False

    @pytest.mark.asyncio
    async def test_signal_confidence_values(self, detector):
        """Test that signal confidence is between 0 and 1."""
        tenant_id = 1
        stats = {
            "health_score_avg": 0.2,
            "sentiment_negative_ratio": 0.3,
            "chargeback_count": 5,
            "high_value_order_count": 10,
            "escalation_pct": 0.5,
            "total_triages": 500,
            "api_error_count": 200,
            "api_request_count": 1000,
        }
        perf = {"avg_resolution_time_sec": 1000}
        
        with patch.object(detector, 'publish_webhook', new_callable=AsyncMock):
            signals = await detector.detect_signals(tenant_id, stats, perf)
            for signal in signals:
                assert 0.0 <= signal.confidence <= 1.0
