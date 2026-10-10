"""Evaluation harness tests with golden datasets."""

from pathlib import Path

import pytest

from ml.evals.runner import EvalRunner


@pytest.mark.eval
def test_golden_intents_v0_loads() -> None:
    """Test that golden intents dataset loads without error."""
    dataset_path = Path(__file__).parent.parent / "golden" / "intents_v0.jsonl"
    rows = EvalRunner.load_golden_set(dataset_path)
    assert len(rows) > 0
    assert "message" in rows[0]
    assert "intents" in rows[0]


@pytest.mark.eval
def test_golden_conversations_v0_loads() -> None:
    """Test that golden conversations dataset loads without error."""
    dataset_path = Path(__file__).parent.parent / "golden" / "conversations_v0.jsonl"
    rows = EvalRunner.load_golden_set(dataset_path)
    assert len(rows) == 20
    for row in rows:
        assert "scenario_id" in row
        assert "expected_decision" in row
        assert "turns" in row


@pytest.mark.eval
def test_runner_reports_metrics() -> None:
    """Test that EvalRunner generates reports with metrics."""
    def stub_evaluator(row: dict) -> float:
        """Stub evaluator that returns 0.5 for all rows."""
        return 0.5

    dataset_path = Path(__file__).parent.parent / "golden" / "conversations_v0.jsonl"
    report = EvalRunner.run(
        dataset_path,
        stub_evaluator,
        thresholds={"accuracy": 0.3},
        metric_name="accuracy",
    )

    assert "accuracy" in report.metrics
    assert report.metrics["accuracy"] == 0.5
    assert report.passed is True


@pytest.mark.eval
def test_runner_detects_threshold_failures() -> None:
    """Test that EvalRunner detects metric failures."""
    def stub_evaluator(row: dict) -> float:
        return 0.3

    dataset_path = Path(__file__).parent.parent / "golden" / "conversations_v0.jsonl"
    report = EvalRunner.run(
        dataset_path,
        stub_evaluator,
        thresholds={"accuracy": 0.8},
        metric_name="accuracy",
    )

    assert report.passed is False
    assert len(report.failures) > 0
