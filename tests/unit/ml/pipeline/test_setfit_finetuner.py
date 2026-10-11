"""Tests for S8.2: SetFit Fine-Tuning."""

import pytest
import numpy as np
import torch
from ml.pipeline.setfit_finetuner import (
    SetFitTrainer,
    TrainingConfig,
    MultiLabelHead,
    FocalLoss,
    ContrastiveLoss,
    LoRAAdapter,
    HyperparameterTuner,
)


class TestTrainingConfig:
    """Training configuration tests."""
    
    def test_default_config(self):
        """Test default configuration."""
        config = TrainingConfig()
        assert config.learning_rate == 2e-5
        assert config.batch_size == 16
        assert config.num_epochs == 3
        assert config.num_labels == 50
        assert config.use_lora is True
    
    def test_custom_config(self):
        """Test custom configuration."""
        config = TrainingConfig(
            learning_rate=1e-4,
            batch_size=32,
            num_epochs=5,
        )
        assert config.learning_rate == 1e-4
        assert config.batch_size == 32
        assert config.num_epochs == 5


class TestMultiLabelHead:
    """Multi-label sigmoid head tests."""
    
    def test_head_output_shape(self):
        """Test output shape of multi-label head."""
        head = MultiLabelHead(input_dim=768, num_labels=50)
        
        batch_size = 16
        embeddings = torch.randn(batch_size, 768)
        output = head(embeddings)
        
        assert output.shape == (batch_size, 50)
    
    def test_output_in_sigmoid_range(self):
        """Test that outputs are in [0, 1] range (sigmoid)."""
        head = MultiLabelHead(input_dim=768, num_labels=50)
        
        embeddings = torch.randn(10, 768)
        output = head(embeddings)
        
        assert torch.all(output >= 0.0)
        assert torch.all(output <= 1.0)
    
    def test_per_label_independence(self):
        """Test that each label is independent (sigmoid, not softmax)."""
        head = MultiLabelHead(input_dim=768, num_labels=5)
        
        embeddings = torch.randn(1, 768)
        output = head(embeddings)
        
        # Sum should not necessarily be 1 (unlike softmax)
        # This is the key difference: multi-label can have sum != 1
        assert output.shape == (1, 5)
        # For multilabel, output sum is not constrained
        assert not torch.allclose(torch.sum(output, dim=1), torch.ones(1))


class TestFocalLoss:
    """Focal loss tests."""
    
    def test_focal_loss_computation(self):
        """Test focal loss computes."""
        loss_fn = FocalLoss(alpha=0.25, gamma=2.0)
        
        predictions = torch.tensor([[0.9, 0.1], [0.2, 0.8]], dtype=torch.float32)
        targets = torch.tensor([[1.0, 0.0], [0.0, 1.0]], dtype=torch.float32)
        
        loss = loss_fn(predictions, targets)
        
        assert isinstance(loss, torch.Tensor)
        assert loss.item() >= 0.0
    
    def test_focal_loss_class_weights(self):
        """Test focal loss with class weights."""
        loss_fn = FocalLoss()
        
        predictions = torch.tensor([[0.9, 0.1], [0.2, 0.8]], dtype=torch.float32)
        targets = torch.tensor([[1.0, 0.0], [0.0, 1.0]], dtype=torch.float32)
        class_weights = torch.tensor([2.0, 1.0])  # Weight first class more
        
        loss_weighted = loss_fn(predictions, targets, class_weights)
        loss_unweighted = loss_fn(predictions, targets)
        
        assert isinstance(loss_weighted, torch.Tensor)
        assert loss_weighted.item() >= 0.0


class TestContrastiveLoss:
    """Contrastive triplet loss tests."""
    
    def test_contrastive_loss_computation(self):
        """Test contrastive loss computes."""
        loss_fn = ContrastiveLoss(margin=0.5)
        
        anchor = torch.randn(8, 768)
        positive = anchor + 0.01 * torch.randn(8, 768)  # Close to anchor
        negative = torch.randn(8, 768)  # Far from anchor
        
        loss = loss_fn(anchor, positive, negative)
        
        assert isinstance(loss, torch.Tensor)
        assert loss.item() >= 0.0
    
    def test_triplet_loss_ordering(self):
        """Test that triplet loss prefers positive over negative."""
        loss_fn = ContrastiveLoss(margin=0.5)
        
        anchor = torch.randn(4, 128)
        positive = anchor + 0.001 * torch.randn(4, 128)  # Very close
        negative = anchor + 10 * torch.randn(4, 128)  # Far away
        
        loss = loss_fn(anchor, positive, negative)
        # Loss should be small because positive < negative
        assert loss.item() < 1.0


class TestLoRAAdapter:
    """LoRA adapter tests."""
    
    def test_lora_adapter_creation(self):
        """Test LoRA adapter creation."""
        adapter = LoRAAdapter(
            base_dim=768,
            output_dim=50,
            r=8,
            alpha=16,
        )
        
        assert adapter.r == 8
        assert adapter.alpha == 16
        assert adapter.scaling == 16 / 8  # alpha / r
    
    def test_lora_forward_pass(self):
        """Test LoRA forward pass."""
        adapter = LoRAAdapter(base_dim=128, output_dim=64, r=8)
        
        x = torch.randn(4, 128)
        output = adapter(x)
        
        assert output.shape == (4, 64)


class TestSetFitTrainer:
    """SetFit trainer tests."""
    
    def test_trainer_initialization(self):
        """Test trainer initialization."""
        config = TrainingConfig(num_epochs=1)
        trainer = SetFitTrainer(config, device="cpu")
        
        assert trainer.config == config
        assert trainer.device == torch.device("cpu")
        assert trainer.head is None
    
    def test_model_initialization(self):
        """Test model initialization."""
        config = TrainingConfig()
        trainer = SetFitTrainer(config, device="cpu")
        trainer.initialize_model(embedding_dim=768)
        
        assert trainer.head is not None
        assert isinstance(trainer.head, MultiLabelHead)
    
    def test_lora_adapter_addition(self):
        """Test adding LoRA adapters."""
        config = TrainingConfig(use_lora=True)
        trainer = SetFitTrainer(config, device="cpu")
        trainer.initialize_model(embedding_dim=768)
        
        trainer.add_lora_adapter("tenant_1")
        trainer.add_lora_adapter("tenant_2")
        
        assert "tenant_1" in trainer.lora_adapters
        assert "tenant_2" in trainer.lora_adapters
    
    def test_training_produces_metrics(self):
        """Test that training produces metrics."""
        config = TrainingConfig(num_epochs=1, batch_size=4)
        trainer = SetFitTrainer(config, device="cpu")
        
        # Small dummy data
        train_emb = np.random.randn(10, 128).astype(np.float32)
        train_labels = np.random.randint(0, 2, (10, 5)).astype(np.float32)
        val_emb = np.random.randn(5, 128).astype(np.float32)
        val_labels = np.random.randint(0, 2, (5, 5)).astype(np.float32)
        
        trainer.initialize_model(embedding_dim=128)
        metrics = trainer.train(train_emb, train_labels, val_emb, val_labels)
        
        assert len(metrics) > 0
        assert metrics[0].loss >= 0.0
    
    def test_validation_gate_check(self):
        """Test validation gates."""
        config = TrainingConfig(num_epochs=1)
        trainer = SetFitTrainer(config, device="cpu")
        
        train_emb = np.random.randn(20, 128).astype(np.float32)
        train_labels = np.random.randint(0, 2, (20, 5)).astype(np.float32)
        val_emb = np.random.randn(10, 128).astype(np.float32)
        val_labels = np.random.randint(0, 2, (10, 5)).astype(np.float32)
        
        trainer.initialize_model(embedding_dim=128)
        trainer.train(train_emb, train_labels, val_emb, val_labels)
        
        result = trainer.validate(val_emb, val_labels)
        
        assert "f1_macro" in result
        assert "f1_per_class" in result
        assert "f1_variance" in result
        assert "passed" in result
        assert result["f1_macro"] >= 0.0
        assert result["f1_macro"] <= 1.0


class TestHyperparameterTuner:
    """Hyperparameter grid search tests."""
    
    def test_grid_search_returns_best_params(self):
        """Test grid search finds best hyperparameters."""
        train_emb = np.random.randn(20, 128).astype(np.float32)
        train_labels = np.random.randint(0, 2, (20, 5)).astype(np.float32)
        val_emb = np.random.randn(10, 128).astype(np.float32)
        val_labels = np.random.randint(0, 2, (10, 5)).astype(np.float32)
        
        result = HyperparameterTuner.grid_search(
            train_emb, train_labels, val_emb, val_labels, device="cpu"
        )
        
        assert "best_params" in result
        assert "best_f1" in result
        assert "all_results" in result
        assert result["best_f1"] >= 0.0
    
    def test_grid_search_explores_space(self):
        """Test that grid search explores parameter space."""
        train_emb = np.random.randn(30, 128).astype(np.float32)
        train_labels = np.random.randint(0, 2, (30, 5)).astype(np.float32)
        val_emb = np.random.randn(15, 128).astype(np.float32)
        val_labels = np.random.randint(0, 2, (15, 5)).astype(np.float32)
        
        result = HyperparameterTuner.grid_search(
            train_emb, train_labels, val_emb, val_labels, device="cpu"
        )
        
        # Should have explored multiple combinations
        assert len(result["all_results"]) > 1


class TestF1Computation:
    """F1 metric computation tests."""
    
    def test_f1_per_class_computation(self):
        """Test per-class F1 computation."""
        y_true = np.array([[1, 0, 1], [0, 1, 0], [1, 1, 0]])
        y_pred = np.array([[1, 0, 1], [0, 1, 0], [1, 0, 0]])
        
        f1_scores = SetFitTrainer._compute_f1_per_class(y_true, y_pred)
        
        assert len(f1_scores) == 3
        assert all(0 <= f1 <= 1 for f1 in f1_scores.values())
    
    def test_f1_perfect_prediction(self):
        """Test F1 on perfect predictions."""
        y_true = np.array([[1, 0], [0, 1], [1, 1]])
        y_pred = y_true.copy()
        
        f1_scores = SetFitTrainer._compute_f1_per_class(y_true, y_pred)
        
        # Perfect predictions should have F1 = 1.0
        assert all(f1 == pytest.approx(1.0) for f1 in f1_scores.values())
