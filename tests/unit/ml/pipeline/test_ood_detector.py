"""Tests for S8.4: Out-of-Distribution Detector."""

import pytest
import numpy as np
from ml.pipeline.ood_detector import (
    EnergyDetector,
    CentroidDetector,
    OODEnsemble,
    ThresholdCalibrator,
    OODAnalyzer,
)


class TestEnergyDetector:
    """Energy-based OOD detection tests."""
    
    def test_energy_computation(self):
        """Test energy computation."""
        logits = np.array([[10.0, 1.0], [1.0, 10.0], [1.0, 1.0]])
        energy = EnergyDetector.compute_energy(logits)
        
        assert energy.shape == (3,)
        assert np.all(energy > 0.0)
        # High logits = low energy (confident = ID)
        # Low logits = high energy (uncertain = OOD)
        assert energy[2] > energy[0]


class TestCentroidDetector:
    """Centroid distance OOD detection tests."""
    
    def test_centroid_fitting(self):
        """Test fitting centroids."""
        embeddings = np.random.randn(30, 64)
        labels = np.array([0] * 10 + [1] * 10 + [2] * 10)
        
        detector = CentroidDetector()
        detector.fit(embeddings, labels)
        
        assert len(detector.centroids) == 3
        assert all(c.shape == (64,) for c in detector.centroids.values())
    
    def test_centroid_distances(self):
        """Test computing distances to centroids."""
        embeddings = np.random.randn(30, 64)
        labels = np.array([0] * 10 + [1] * 10 + [2] * 10)
        
        detector = CentroidDetector()
        detector.fit(embeddings, labels)
        
        distances = detector.compute_centroid_distances(embeddings)
        
        assert distances.shape == (30,)
        assert np.all(distances >= 0.0)
    
    def test_distance_normalization(self):
        """Test distance normalization."""
        distances = np.array([0.0, 1.0, 2.0, 3.0])
        normalized = CentroidDetector.normalize_distances(distances)
        
        assert np.allclose(normalized[0], 0.0)
        assert np.allclose(normalized[-1], 1.0)
        assert np.all((normalized >= 0.0) & (normalized <= 1.0))


class TestOODEnsemble:
    """Ensemble OOD detector tests."""
    
    def test_ensemble_initialization(self):
        """Test ensemble initialization."""
        ensemble = OODEnsemble()
        assert ensemble.threshold == 0.5
    
    def test_ensemble_fitting(self):
        """Test ensemble fitting."""
        embeddings = np.random.randn(50, 64)
        logits = np.random.randn(50, 10)
        labels = np.random.randint(0, 10, 50)
        
        ensemble = OODEnsemble()
        ensemble.fit(embeddings, logits, labels)
    
    def test_ensemble_predict_ood(self):
        """Test OOD prediction."""
        embeddings = np.random.randn(50, 64)
        logits = np.random.randn(50, 10)
        labels = np.random.randint(0, 10, 50)
        
        ensemble = OODEnsemble()
        ensemble.fit(embeddings, logits, labels)
        
        ood_scores, ood_preds = ensemble.predict_ood(embeddings, logits)
        
        assert ood_scores.shape == (50,)
        assert ood_preds.shape == (50,)
        assert np.all((ood_preds == 0) | (ood_preds == 1))
    
    def test_calibrate_threshold(self):
        """Test threshold calibration."""
        embeddings = np.random.randn(100, 64)
        logits = np.random.randn(100, 10)
        labels = np.arange(100) % 10  # 10 classes
        is_ood = np.arange(100) > 80  # Last 20 are OOD
        
        ensemble = OODEnsemble()
        ensemble.fit(embeddings, logits, labels)
        
        threshold = ensemble.calibrate_threshold(
            embeddings, logits, labels, is_ood, target_recall=0.80
        )
        
        assert threshold > 0.0
        assert threshold < 1.0


class TestThresholdCalibrator:
    """Threshold calibration tests."""
    
    def test_calibrate_for_recall(self):
        """Test calibrating threshold for target recall."""
        ood_scores = np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95])
        labels = np.array([0] * 10)  # All same intent
        novel_ids = {1, 2}  # Novel intents
        
        threshold = ThresholdCalibrator.calibrate(
            ood_scores, labels, novel_ids, target_recall=0.80
        )
        
        assert 0.0 < threshold < 1.0


class TestOODAnalyzer:
    """OOD analysis tests."""
    
    def test_roc_auc_computation(self):
        """Test ROC AUC computation."""
        ood_scores = np.random.rand(100)
        is_ood = np.random.rand(100) > 0.5
        
        auc = OODAnalyzer.compute_roc_auc(ood_scores, is_ood)
        
        assert 0.0 <= auc <= 1.0
    
    def test_pr_curve_computation(self):
        """Test PR curve computation."""
        ood_scores = np.random.rand(50)
        is_ood = np.random.rand(50) > 0.5
        
        pr_curve = OODAnalyzer.compute_pr_curve(ood_scores, is_ood)
        
        assert "thresholds" in pr_curve
        assert "precisions" in pr_curve
        assert "recalls" in pr_curve
        assert len(pr_curve["thresholds"]) > 0
    
    def test_full_analysis(self):
        """Test full OOD analysis."""
        embeddings = np.random.randn(100, 64)
        logits = np.random.randn(100, 20)
        labels = np.arange(100) % 20
        novel_ids = {15, 16, 17}  # Novel intents
        
        metrics = OODAnalyzer.analyze(embeddings, logits, labels, novel_ids)
        
        assert 0.0 <= metrics.auc_roc <= 1.0
        assert 0.0 <= metrics.threshold <= 1.0
        assert 0.0 <= metrics.recall_at_80 <= 1.0
        assert 0.0 <= metrics.precision_at_80 <= 1.0


class TestEnergyVsCentroid:
    """Compare energy vs centroid methods."""
    
    def test_ensemble_combines_both(self):
        """Test that ensemble uses both energy and centroid."""
        embeddings = np.random.randn(50, 64)
        logits = np.random.randn(50, 10)
        labels = np.random.randint(0, 10, 50)
        
        ensemble = OODEnsemble()
        ensemble.fit(embeddings, logits, labels)
        
        scores_energy = ensemble.energy_detector.compute_energy(logits)
        distances_centroid = ensemble.centroid_detector.compute_centroid_distances(embeddings)
        
        # Both should contribute
        assert scores_energy.shape == (50,)
        assert distances_centroid.shape == (50,)
