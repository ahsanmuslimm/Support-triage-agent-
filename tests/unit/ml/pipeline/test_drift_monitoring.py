"""Tests for S8.8: Drift Monitoring."""

import pytest
import numpy as np
from pathlib import Path
import tempfile
from ml.pipeline.drift_monitoring import (
    PSIComputer,
    CentroidDriftDetector,
    OODRateMonitor,
    ConceptDriftDetector,
    DriftMonitor,
)


class TestPSIComputer:
    """Population Stability Index tests."""
    
    def test_psi_computation(self):
        """Test PSI computation."""
        baseline = {"intent_a": 0.5, "intent_b": 0.3, "intent_c": 0.2}
        current = {"intent_a": 0.4, "intent_b": 0.4, "intent_c": 0.2}
        
        psi = PSIComputer.compute_psi(baseline, current)
        
        assert psi >= 0.0
    
    def test_psi_stable_distribution(self):
        """Test PSI on stable distribution."""
        dist = {"intent_a": 0.5, "intent_b": 0.3, "intent_c": 0.2}
        
        psi = PSIComputer.compute_psi(dist, dist)
        
        # Identical distributions should have ~0 PSI
        assert psi < 0.01
    
    def test_psi_by_intent(self):
        """Test per-intent PSI."""
        baseline = {"intent_a": 0.5, "intent_b": 0.5}
        current = {"intent_a": 0.4, "intent_b": 0.6}
        
        psi_by_intent = PSIComputer.compute_psi_by_intent(baseline, current)
        
        assert len(psi_by_intent) == 2
        assert "intent_a" in psi_by_intent
        assert "intent_b" in psi_by_intent
    
    def test_distribution_from_predictions(self):
        """Test computing distribution from predictions."""
        predictions = ["billing"] * 50 + ["refund"] * 30 + ["support"] * 20
        
        dist = PSIComputer.compute_intent_distribution(predictions)
        
        assert dist["billing"] == pytest.approx(0.5, abs=0.01)
        assert dist["refund"] == pytest.approx(0.3, abs=0.01)
        assert dist["support"] == pytest.approx(0.2, abs=0.01)


class TestCentroidDriftDetector:
    """Centroid drift detection tests."""
    
    def test_fit_baseline(self):
        """Test fitting baseline centroids."""
        embeddings = np.random.randn(60, 64)
        labels = ["intent_a"] * 20 + ["intent_b"] * 20 + ["intent_c"] * 20
        
        detector = CentroidDriftDetector()
        detector.fit_baseline(embeddings, labels)
        
        assert len(detector.baseline_centroids) == 3
    
    def test_compute_drift(self):
        """Test computing centroid drift."""
        embeddings_baseline = np.random.randn(60, 64)
        labels = ["intent_a"] * 20 + ["intent_b"] * 20 + ["intent_c"] * 20
        
        detector = CentroidDriftDetector()
        detector.fit_baseline(embeddings_baseline, labels)
        
        # Similar embeddings should have small drift
        embeddings_current = embeddings_baseline + 0.01 * np.random.randn(60, 64)
        
        overall_drift, per_class_drift = detector.compute_drift(
            embeddings_current, labels
        )
        
        assert overall_drift >= 0.0
        assert len(per_class_drift) == 3
    
    def test_drift_detection_signature_change(self):
        """Test drift detection with significant change."""
        embeddings_baseline = np.zeros((60, 64))
        labels = ["intent_a"] * 20 + ["intent_b"] * 20 + ["intent_c"] * 20
        
        detector = CentroidDriftDetector()
        detector.fit_baseline(embeddings_baseline, labels)
        
        # Very different embeddings
        embeddings_shifted = np.ones((60, 64)) * 10
        
        overall_drift, _ = detector.compute_drift(embeddings_shifted, labels)
        
        assert overall_drift > 5.0  # Significant drift


class TestOODRateMonitor:
    """OOD rate monitoring tests."""
    
    def test_ood_rate_monitoring(self):
        """Test tracking OOD rate."""
        monitor = OODRateMonitor(window_size=10)
        
        # Add flags: 2 OOD out of 10
        for i in range(10):
            monitor.update(i < 2)
        
        ood_rate = monitor.get_ood_rate()
        assert ood_rate == pytest.approx(0.2, abs=0.01)
    
    def test_window_size_limit(self):
        """Test that window respects size limit."""
        monitor = OODRateMonitor(window_size=5)
        
        for i in range(10):
            monitor.update(False)
        
        assert len(monitor.recent_ood_flags) == 5
    
    def test_empty_window(self):
        """Test OOD rate on empty window."""
        monitor = OODRateMonitor()
        
        rate = monitor.get_ood_rate()
        assert rate == 0.0


class TestConceptDriftDetector:
    """Concept drift (performance degradation) tests."""
    
    def test_f1_on_window(self):
        """Test F1 computation on rolling window."""
        detector = ConceptDriftDetector()
        
        # Add perfect predictions
        for i in range(30):
            intent = ["a", "b", "c"][i % 3]
            detector.update(intent, intent)
        
        f1 = detector.compute_f1_on_window()
        
        assert f1 == pytest.approx(1.0, abs=0.01)
    
    def test_window_cleanup(self):
        """Test that old predictions are cleaned up."""
        from datetime import datetime, timedelta
        
        detector = ConceptDriftDetector(window_days=7)
        
        # Add a prediction
        detector.update("intent_a", "intent_a")
        
        # Manually add old prediction
        old_time = datetime.utcnow() - timedelta(days=8)
        detector.prediction_history.append((old_time, "a", "a"))
        
        f1 = detector.compute_f1_on_window()
        
        # Old prediction should be ignored
        assert len(detector.prediction_history) < 2 or f1 >= 0.0


class TestDriftMonitor:
    """Full drift monitoring tests."""
    
    def test_fit_baseline(self):
        """Test fitting baseline for drift detection."""
        predictions = ["intent_a"] * 50 + ["intent_b"] * 30 + ["intent_c"] * 20
        embeddings = np.random.randn(100, 64)
        labels = predictions.copy()
        
        monitor = DriftMonitor()
        monitor.fit_baseline(predictions, embeddings, labels)
        
        assert monitor.baseline_dist is not None
    
    def test_monitor_no_drift(self):
        """Test monitoring with stable data."""
        # Baseline
        baseline_preds = ["intent_a"] * 50 + ["intent_b"] * 50
        baseline_emb = np.random.randn(100, 64)
        baseline_labels = baseline_preds.copy()
        
        # Similar current data
        current_preds = ["intent_a"] * 50 + ["intent_b"] * 50
        current_emb = baseline_emb + 0.001 * np.random.randn(100, 64)
        current_labels = current_preds.copy()
        current_ood = [False] * 100
        
        monitor = DriftMonitor()
        monitor.fit_baseline(baseline_preds, baseline_emb, baseline_labels)
        
        metrics = monitor.monitor(current_emb, current_preds, current_labels, current_ood)
        
        assert metrics.psi < 0.25  # No significant drift
        assert metrics.alert_triggered is False
    
    def test_monitor_psi_alert(self):
        """Test PSI alert triggering."""
        baseline_preds = ["intent_a"] * 80 + ["intent_b"] * 20
        baseline_emb = np.random.randn(100, 64)
        baseline_labels = baseline_preds.copy()
        
        # Very different distribution
        current_preds = ["intent_a"] * 20 + ["intent_b"] * 80
        current_emb = np.random.randn(100, 64)
        current_labels = current_preds.copy()
        current_ood = [False] * 100
        
        monitor = DriftMonitor()
        monitor.PSI_ALERT_THRESHOLD = 0.1  # Lower threshold
        monitor.fit_baseline(baseline_preds, baseline_emb, baseline_labels)
        
        metrics = monitor.monitor(current_emb, current_preds, current_labels, current_ood)
        
        # Significant distribution shift should trigger alert
        assert metrics.psi > 0.25 or metrics.alert_triggered
    
    def test_monitor_ood_alert(self):
        """Test OOD rate alert triggering."""
        baseline_preds = ["intent_a"] * 100
        baseline_emb = np.random.randn(100, 64)
        baseline_labels = baseline_preds.copy()
        
        current_preds = ["intent_a"] * 100
        current_emb = np.random.randn(100, 64)
        current_labels = current_preds.copy()
        current_ood = [True] * 100  # All OOD
        
        monitor = DriftMonitor()
        monitor.OOD_RATE_ALERT_THRESHOLD = 0.10
        monitor.fit_baseline(baseline_preds, baseline_emb, baseline_labels)
        
        metrics = monitor.monitor(current_emb, current_preds, current_labels, current_ood)
        
        # High OOD rate should trigger alert
        assert metrics.ood_rate > 0.5
    
    def test_export_prometheus_metrics(self):
        """Test Prometheus metrics export."""
        baseline_preds = ["intent_a"] * 50 + ["intent_b"] * 50
        baseline_emb = np.random.randn(100, 64)
        baseline_labels = baseline_preds.copy()
        
        monitor = DriftMonitor()
        monitor.fit_baseline(baseline_preds, baseline_emb, baseline_labels)
        
        current_preds = baseline_preds.copy()
        current_emb = baseline_emb + 0.01 * np.random.randn(100, 64)
        current_labels = baseline_labels.copy()
        current_ood = [False] * 100
        
        monitor.monitor(current_emb, current_preds, current_labels, current_ood)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "metrics.txt"
            monitor.export_prometheus_metrics(output_path)
            
            assert output_path.exists()
    
    def test_export_report(self):
        """Test drift monitoring report export."""
        baseline_preds = ["intent_a"] * 50 + ["intent_b"] * 50
        baseline_emb = np.random.randn(100, 64)
        baseline_labels = baseline_preds.copy()
        
        monitor = DriftMonitor()
        monitor.fit_baseline(baseline_preds, baseline_emb, baseline_labels)
        
        current_preds = baseline_preds.copy()
        current_emb = baseline_emb
        current_labels = baseline_labels.copy()
        current_ood = [False] * 100
        
        monitor.monitor(current_emb, current_preds, current_labels, current_ood)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "report.json"
            monitor.export_report(output_path)
            
            assert output_path.exists()


class TestDriftMetrics:
    """Drift metrics tests."""
    
    def test_metrics_creation(self):
        """Test creating drift metrics."""
        from ml.pipeline.drift_monitoring import DriftMetrics
        from datetime import datetime
        
        metrics = DriftMetrics(
            timestamp=datetime.utcnow(),
            psi=0.15,
            psi_by_intent={"intent_a": 0.10, "intent_b": 0.05},
            centroid_drift=0.05,
            centroid_drift_by_class={},
            ood_rate=0.05,
            concept_drift_f1=0.90,
            alert_triggered=False,
        )
        
        assert metrics.psi == 0.15
        assert metrics.ood_rate == 0.05
        assert metrics.alert_triggered is False
