"""Tests for S8.7: Nightly Eval Suite."""

import pytest
import numpy as np
from pathlib import Path
import tempfile
from ml.pipeline.nightly_eval_suite import (
    RagasEvaluator,
    PromptfooEvaluator,
    RegressionDetector,
    PromptVersioning,
    NightlyEvalSuite,
)


class TestRagasEvaluator:
    """Ragas evaluation tests."""
    
    def test_evaluate_sample(self):
        """Test evaluating a single RAG sample."""
        metrics = RagasEvaluator.evaluate_sample(
            context="The customer reported a billing issue.",
            question="What is the customer's problem?",
            answer="The customer has a billing issue.",
        )
        
        assert 0.0 <= metrics.context_precision <= 1.0
        assert 0.0 <= metrics.context_recall <= 1.0
        assert 0.0 <= metrics.faithfulness <= 1.0
        assert 0.0 <= metrics.answer_relevance <= 1.0
    
    def test_evaluate_golden_set(self):
        """Test evaluating golden set."""
        golden_set = [
            {
                "context": "Payment failed due to expired card.",
                "question": "Why did payment fail?",
                "answer": "Payment failed due to expired card.",
                "ground_truth": "expired card",
            },
            {
                "context": "Account locked for security.",
                "question": "Why is account locked?",
                "answer": "Account locked for security.",
            },
        ]
        
        metrics = RagasEvaluator.evaluate_golden_set(golden_set)
        
        assert 0.0 <= metrics.context_precision <= 1.0
        assert 0.0 <= metrics.context_recall <= 1.0
        assert 0.0 <= metrics.faithfulness <= 1.0
        assert 0.0 <= metrics.answer_relevance <= 1.0


class TestPromptfooEvaluator:
    """Promptfoo evaluation tests."""
    
    def test_intent_classification_accuracy(self):
        """Test intent classification accuracy."""
        texts = ["I need billing help", "I want a refund", "API not working"]
        predictions = ["billing", "refund", "technical"]
        ground_truth = ["billing", "refund", "technical"]
        
        accuracy = PromptfooEvaluator.evaluate_intent_classification(
            texts, predictions, ground_truth
        )
        
        assert accuracy == 1.0
    
    def test_entity_extraction_f1(self):
        """Test entity extraction F1."""
        predictions = [
            {"person": ["John"], "email": ["john@example.com"]},
            {"person": ["Jane"], "email": ["jane@test.com"]},
        ]
        ground_truth = [
            {"person": ["John"], "email": ["john@example.com"]},
            {"person": ["Jane"], "email": ["jane@test.com"]},
        ]
        
        f1 = PromptfooEvaluator.evaluate_entity_extraction(
            ["text1", "text2"], predictions, ground_truth
        )
        
        assert f1 == 1.0
    
    def test_composition_score(self):
        """Test multi-step composition scoring."""
        steps = [
            {"expected_output": "yes", "actual_output": "yes"},
            {"expected_output": "result_x", "actual_output": "result_x"},
            {"expected_output": "ok", "actual_output": "error"},
        ]
        
        score = PromptfooEvaluator.evaluate_composition(steps)
        
        assert score == pytest.approx(2/3, abs=0.01)


class TestRegressionDetector:
    """Regression detection tests."""
    
    def test_no_regression(self):
        """Test when no regression occurs."""
        baseline = {"f1": 0.95, "accuracy": 0.92}
        current = {"f1": 0.94, "accuracy": 0.91}
        
        report = RegressionDetector.detect_regression(baseline, current, threshold=0.10)
        
        assert report.passed is True
        assert len(report.regressions) == 0
    
    def test_detect_regression(self):
        """Test regression detection."""
        baseline = {"f1": 0.95, "accuracy": 0.92}
        current = {"f1": 0.85, "accuracy": 0.92}  # 10.5% drop in F1
        
        report = RegressionDetector.detect_regression(baseline, current, threshold=0.05)
        
        assert report.passed is False
        assert len(report.regressions) > 0
    
    def test_diff_table_computation(self):
        """Test diff table computation."""
        baseline = {"metric_a": 0.90, "metric_b": 0.80}
        current = {"metric_a": 0.85, "metric_b": 0.80}
        
        report = RegressionDetector.detect_regression(baseline, current)
        
        assert "metric_a" in report.diff_table
        assert report.diff_table["metric_a"]["baseline"] == 0.90
        assert report.diff_table["metric_a"]["current"] == 0.85


class TestPromptVersioning:
    """Prompt versioning tests."""
    
    def test_register_prompt(self):
        """Test registering prompt version."""
        versioning = PromptVersioning()
        
        prompt_text = "You are a helpful assistant..."
        hash_val = versioning.register_prompt(prompt_text, "v1.0")
        
        assert hash_val is not None
        assert "v1.0" in versioning.versions
    
    def test_link_eval_results(self):
        """Test linking eval results to prompt."""
        versioning = PromptVersioning()
        
        versioning.register_prompt("prompt text", "v1.0")
        eval_results = {"f1": 0.95, "accuracy": 0.92}
        versioning.link_eval_results("v1.0", eval_results)
        
        assert versioning.versions["v1.0"]["eval_results"] == eval_results
    
    def test_export_versions(self):
        """Test exporting prompt versions."""
        versioning = PromptVersioning()
        
        versioning.register_prompt("prompt v1", "v1.0")
        versioning.register_prompt("prompt v2", "v1.1")
        
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "versions.json"
            versioning.export_versions(output_path)
            
            assert output_path.exists()


class TestNightlyEvalSuite:
    """Full nightly eval suite tests."""
    
    def test_run_nightly_eval(self):
        """Test running full nightly evaluation."""
        suite = NightlyEvalSuite()
        
        golden_sets = {
            "rag": [
                {
                    "context": "Context text",
                    "question": "Question?",
                    "answer": "Answer",
                }
            ],
            "promptfoo": [
                {
                    "message": "I need help",
                    "predicted_intent": "support",
                    "intent": "support",
                    "predicted_entities": {},
                    "entities": {},
                }
            ],
        }
        
        baseline_metrics = {
            "context_precision": 0.85,
            "faithfulness": 0.90,
            "intent_accuracy": 0.92,
        }
        
        result = suite.run_nightly_eval(
            golden_sets,
            baseline_metrics,
            "v1.0",
        )
        
        assert "timestamp" in result
        assert "ragas_metrics" in result
        assert "promptfoo_metrics" in result
        assert "regression_report" in result
    
    def test_export_report(self):
        """Test exporting nightly eval report."""
        suite = NightlyEvalSuite()
        
        # Add some history
        suite.eval_history.append({"timestamp": "2024-01-01", "metric": 0.95})
        
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "report.json"
            suite.export_report(output_path)
            
            assert output_path.exists()


class TestRagasMetrics:
    """Ragas metrics tests."""
    
    def test_metrics_creation(self):
        """Test creating Ragas metrics."""
        from ml.pipeline.nightly_eval_suite import RagasMetrics
        
        metrics = RagasMetrics(
            context_precision=0.85,
            context_recall=0.90,
            faithfulness=0.88,
            answer_relevance=0.92,
        )
        
        assert metrics.context_precision == 0.85
        assert metrics.faithfulness == 0.88
