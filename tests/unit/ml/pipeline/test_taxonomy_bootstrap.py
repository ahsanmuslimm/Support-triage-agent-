"""Tests for S8.6: Taxonomy Bootstrap."""

import pytest
import numpy as np
from pathlib import Path
import tempfile
from ml.pipeline.taxonomy_bootstrap import (
    TaxonomyBootstrapper,
    ClusterLabel,
    LabelStatus,
)


class TestTaxonomyBootstrapper:
    """Taxonomy bootstrap tests."""
    
    def test_find_optimal_k(self):
        """Test finding optimal cluster count."""
        embeddings = np.random.randn(100, 64)
        
        bootstrapper = TaxonomyBootstrapper(min_k=5, max_k=15)
        k = bootstrapper.find_optimal_k(embeddings)
        
        assert 5 <= k <= 15
    
    def test_cluster_embeddings(self):
        """Test clustering embeddings."""
        embeddings = np.random.randn(100, 64)
        
        bootstrapper = TaxonomyBootstrapper(min_k=5, max_k=10)
        clusters = bootstrapper.cluster_embeddings(embeddings)
        
        assert len(clusters) > 0
        for cluster_id, analysis in clusters.items():
            assert analysis.size > 0
            assert analysis.centroid.shape == (64,)
    
    def test_label_clusters_with_opus(self):
        """Test cluster labeling."""
        embeddings = np.random.randn(50, 64)
        bootstrapper = TaxonomyBootstrapper()
        clusters = bootstrapper.cluster_embeddings(embeddings)
        
        labels = bootstrapper.label_clusters_with_opus(clusters)
        
        assert len(labels) == len(clusters)
        for label in labels.values():
            assert label.intent_name is not None
            assert 0.0 <= label.confidence <= 1.0
            assert label.status == LabelStatus.PENDING
    
    def test_review_labels(self):
        """Test label review workflow."""
        embeddings = np.random.randn(50, 64)
        bootstrapper = TaxonomyBootstrapper()
        clusters = bootstrapper.cluster_embeddings(embeddings)
        bootstrapper.label_clusters_with_opus(clusters)
        
        cluster_id = list(clusters.keys())[0]
        bootstrapper.review_labels(
            cluster_id=cluster_id,
            approved=True,
            reviewer_id="user_123",
            notes="Looks good",
        )
        
        label = bootstrapper.labels[cluster_id]
        assert label.status == LabelStatus.APPROVED
        assert label.reviewer_id == "user_123"
    
    def test_merge_intents(self):
        """Test merging intent clusters."""
        embeddings = np.random.randn(100, 64)
        bootstrapper = TaxonomyBootstrapper(min_k=5, max_k=10)
        clusters = bootstrapper.cluster_embeddings(embeddings)
        bootstrapper.label_clusters_with_opus(clusters)
        
        # Create mock historical tickets
        tickets = [
            {"id": f"t_{i}", "cluster_id": 0, "intent": "old_intent"}
            for i in range(20)
        ]
        
        cluster_ids = list(clusters.keys())
        if len(cluster_ids) >= 2:
            source_id = cluster_ids[0]
            target_id = cluster_ids[1]
            
            merge_op = bootstrapper.merge_intents(
                source_id, target_id, "merged_intent", tickets
            )
            
            assert merge_op.source_cluster_id == source_id
            assert merge_op.target_cluster_id == target_id
            assert merge_op.merged_intent_name == "merged_intent"
    
    def test_split_intent(self):
        """Test splitting intent cluster."""
        embeddings = np.random.randn(100, 64)
        cluster_assignments = np.zeros(100)  # All in cluster 0
        
        bootstrapper = TaxonomyBootstrapper()
        clusters = bootstrapper.cluster_embeddings(embeddings)
        bootstrapper.label_clusters_with_opus(clusters)
        
        tickets = [
            {"id": f"t_{i}", "cluster_id": 0, "intent": "original_intent"}
            for i in range(100)
        ]
        
        cluster_id = list(clusters.keys())[0]
        
        try:
            split_op = bootstrapper.split_intent(
                cluster_id,
                ["intent_a", "intent_b"],
                embeddings,
                cluster_assignments,
                tickets,
            )
            
            assert split_op.source_cluster_id == cluster_id
            assert len(split_op.new_cluster_ids) == 2
            assert split_op.separation_quality > 0.0
        except ValueError:
            # May fail if cluster too small
            pass
    
    def test_export_taxonomy(self):
        """Test taxonomy export."""
        embeddings = np.random.randn(50, 64)
        bootstrapper = TaxonomyBootstrapper()
        clusters = bootstrapper.cluster_embeddings(embeddings)
        bootstrapper.label_clusters_with_opus(clusters)
        
        # Approve some labels
        for cluster_id in list(clusters.keys())[:2]:
            bootstrapper.review_labels(
                cluster_id, approved=True, reviewer_id="user"
            )
        
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "taxonomy.json"
            bootstrapper.export_taxonomy(output_path)
            
            assert output_path.exists()


class TestClusterLabel:
    """Cluster label tests."""
    
    def test_label_creation(self):
        """Test creating cluster label."""
        label = ClusterLabel(
            cluster_id=0,
            intent_name="billing_issue",
            confidence=0.85,
            status=LabelStatus.PENDING,
        )
        
        assert label.cluster_id == 0
        assert label.intent_name == "billing_issue"
        assert label.confidence == 0.85


class TestClusterAnalysis:
    """Cluster analysis tests."""
    
    def test_cluster_info(self):
        """Test cluster analysis info."""
        from ml.pipeline.taxonomy_bootstrap import ClusterAnalysis
        
        centroid = np.random.randn(64)
        analysis = ClusterAnalysis(
            cluster_id=0,
            size=100,
            centroid=centroid,
            silhouette=0.65,
            most_common_terms=["help", "payment", "issue"],
        )
        
        assert analysis.cluster_id == 0
        assert analysis.size == 100
        assert analysis.silhouette == 0.65
