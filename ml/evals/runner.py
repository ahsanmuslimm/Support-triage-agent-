"""Evaluation harness for golden datasets."""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


@dataclass
class EvalReport:
    """Results of an evaluation run."""

    metrics: dict[str, float] = field(default_factory=dict)
    """Aggregate metrics."""

    per_intent: dict[str, dict[str, float]] = field(default_factory=dict)
    """Per-intent breakdowns."""

    passed: bool = True
    """Whether all metrics exceeded thresholds."""

    failures: list[str] = field(default_factory=list)
    """List of metric failures."""


class EvalRunner:
    """Run evaluations against golden datasets."""

    @staticmethod
    def load_golden_set(dataset_path: Path | str) -> list[dict[str, Any]]:
        """Load JSONL dataset.

        Args:
            dataset_path: Path to JSONL file.

        Returns:
            List of rows.
        """
        path = Path(dataset_path)
        rows: list[dict[str, Any]] = []

        with open(path) as f:
            for line in f:
                if line.strip():
                    rows.append(json.loads(line))

        return rows

    @staticmethod
    def run(
        dataset_path: Path | str,
        evaluator_fn: Callable[[dict[str, Any]], float],
        thresholds: dict[str, float],
        metric_name: str = "accuracy",
    ) -> EvalReport:
        """Run evaluator on dataset and check gates.

        Args:
            dataset_path: Path to JSONL dataset.
            evaluator_fn: Function that takes a row and returns a score.
            thresholds: Dict of metric_name -> minimum threshold.
            metric_name: Name of the metric being evaluated.

        Returns:
            EvalReport with metrics and pass/fail status.
        """
        rows = EvalRunner.load_golden_set(dataset_path)
        scores: list[float] = []

        for row in rows:
            score = evaluator_fn(row)
            scores.append(score)

        # Compute aggregate metric
        aggregate_metric = sum(scores) / len(scores) if scores else 0.0

        report = EvalReport(
            metrics={metric_name: aggregate_metric},
            per_intent={},
            passed=True,
            failures=[],
        )

        # Check thresholds
        if metric_name in thresholds:
            if aggregate_metric < thresholds[metric_name]:
                report.passed = False
                report.failures.append(
                    f"{metric_name}: {aggregate_metric:.4f} < {thresholds[metric_name]:.4f}"
                )

        return report

    @staticmethod
    def report_table(report: EvalReport) -> str:
        """Format report as ASCII table.

        Args:
            report: EvalReport to format.

        Returns:
            Formatted table string.
        """
        lines: list[str] = []
        lines.append("=" * 60)
        lines.append("Evaluation Report")
        lines.append("=" * 60)

        for metric_name, value in report.metrics.items():
            lines.append(f"{metric_name:30} {value:.4f}")

        if report.failures:
            lines.append("")
            lines.append("Failures:")
            for failure in report.failures:
                lines.append(f"  ✗ {failure}")

        lines.append("=" * 60)
        return "\n".join(lines)
