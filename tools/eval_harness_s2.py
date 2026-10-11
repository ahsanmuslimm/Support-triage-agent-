#!/usr/bin/env python3
"""Sprint 2 Evaluation Harness

Evaluates intent classification, entity extraction, and routing accuracy
against a golden set of 50+ evaluation records.

Usage:
    python tools/eval_harness_s2.py
    python tools/eval_harness_s2.py --golden tests/golden_sets/sprint2_evaluation.jsonl

Exit codes:
    0: All metrics pass (intent>=0.92, entity_f1>=0.85, route_accuracy>=0.90)
    1: Any metric fails threshold
"""

import json
import sys
import argparse
from pathlib import Path
from collections import defaultdict
from typing import List, Dict, Any, Tuple

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "services" / "api" / "src"))

try:
    from triage.classification.intent_classifier import IntentClassifier
    from triage.entity.extractor import RuleBasedEntityExtractor
    from triage.routing.engine import RoutingEngine
    from triage.decision.matrix import DecisionMatrix
except ImportError as e:
    print(f"Error: Failed to import triage modules: {e}")
    sys.exit(1)


class EvaluationHarness:
    """Evaluation harness for Sprint 2 metrics."""

    def __init__(self):
        """Initialize harness with classifiers and extractors."""
        self.classifier = IntentClassifier()
        self.extractor = RuleBasedEntityExtractor()
        self.routing_engine = RoutingEngine()
        self.decision_matrix = DecisionMatrix()

    def load_golden_set(self, jsonl_path: str) -> List[Dict[str, Any]]:
        """Load golden evaluation set from JSONL file.

        Args:
            jsonl_path: Path to .jsonl file with evaluation records

        Returns:
            List of evaluation records
        """
        records = []
        try:
            with open(jsonl_path, "r") as f:
                for line in f:
                    if line.strip():
                        records.append(json.loads(line))
            print(f"Loaded {len(records)} evaluation records from {jsonl_path}")
            return records
        except Exception as e:
            print(f"Error loading golden set: {e}")
            return []

    def evaluate_intent(self, message: str, expected_intent: str) -> Tuple[bool, float]:
        """Evaluate intent classification.

        Args:
            message: User message
            expected_intent: Expected intent label

        Returns:
            (correct, confidence) tuple
        """
        try:
            intents = self.classifier.classify(message)
            primary_intent = intents[0][0] if intents else "unknown"
            confidence = intents[0][1] if intents else 0.0

            # Normalize intent names for comparison
            primary_intent_norm = primary_intent.lower().replace(" ", "_")
            expected_norm = expected_intent.lower().replace(" ", "_")

            is_correct = primary_intent_norm == expected_norm
            return is_correct, confidence
        except Exception as e:
            print(f"Intent evaluation error: {e}")
            return False, 0.0

    def evaluate_entities(
        self, message: str, expected_entities: List[Dict[str, str]]
    ) -> Tuple[float, float, float]:
        """Evaluate entity extraction (precision, recall, F1).

        Args:
            message: User message
            expected_entities: List of expected entities

        Returns:
            (precision, recall, f1) tuple
        """
        try:
            extraction_result = self.extractor.extract(message, "eval_msg")
            extracted_entities = extraction_result.entities

            # Convert to comparable format
            extracted_set = set()
            for e in extracted_entities:
                extracted_set.add((e.entity_type.name, e.value.lower()))

            expected_set = set()
            for e in expected_entities:
                if e.get("value"):
                    expected_set.add((e["type"], e["value"].lower()))

            # Calculate precision, recall, F1
            if len(extracted_set) == 0 and len(expected_set) == 0:
                return 1.0, 1.0, 1.0

            true_positives = len(extracted_set & expected_set)
            false_positives = len(extracted_set - expected_set)
            false_negatives = len(expected_set - extracted_set)

            precision = (
                true_positives / (true_positives + false_positives)
                if (true_positives + false_positives) > 0
                else 0.0
            )
            recall = (
                true_positives / (true_positives + false_negatives)
                if (true_positives + false_negatives) > 0
                else 0.0
            )
            f1 = (
                2 * (precision * recall) / (precision + recall)
                if (precision + recall) > 0
                else 0.0
            )

            return precision, recall, f1
        except Exception as e:
            print(f"Entity evaluation error: {e}")
            return 0.0, 0.0, 0.0

    def evaluate_route(self, message: str, expected_route: str) -> bool:
        """Evaluate routing decision.

        Args:
            message: User message
            expected_route: Expected route

        Returns:
            True if routing matches expected
        """
        try:
            # Classify intent first
            intents = self.classifier.classify(message)
            primary_intent = intents[0][0] if intents else "unknown"

            # Get autonomy level
            autonomy_level = self.decision_matrix.decide(
                intent=primary_intent, confidence=intents[0][1] if intents else 0.0
            )

            # Route based on intent and autonomy
            if expected_route == "escalate":
                # Low autonomy or confidence should escalate
                return autonomy_level == 0
            elif expected_route == "autonomous_agent":
                return autonomy_level >= 1
            elif expected_route == "general_agent":
                return autonomy_level >= 0
            elif expected_route == "technical_specialist":
                return "technical" in primary_intent.lower()
            elif expected_route == "billing_specialist":
                return "billing" in primary_intent.lower() or "payment" in primary_intent.lower()
            else:
                return False
        except Exception as e:
            print(f"Route evaluation error: {e}")
            return False

    def run_evaluation(self, golden_set: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Run full evaluation on golden set.

        Args:
            golden_set: List of evaluation records

        Returns:
            Metrics dictionary with accuracy, F1, etc.
        """
        intent_correct = 0
        intent_total = 0
        entity_precisions = []
        entity_recalls = []
        entity_f1s = []
        route_correct = 0
        route_total = 0

        by_scenario = defaultdict(lambda: {"correct": 0, "total": 0})

        for record in golden_set:
            message = record.get("message", "")
            expected_intent = record.get("expected_intent", "unknown")
            expected_entities = record.get("expected_entities", [])
            expected_route = record.get("expected_route", "escalate")
            scenario = record.get("scenario", "unknown")

            # Evaluate intent
            intent_correct_pred, _ = self.evaluate_intent(message, expected_intent)
            if intent_correct_pred:
                intent_correct += 1
            intent_total += 1
            by_scenario[scenario]["total"] += 1

            # Evaluate entities
            precision, recall, f1 = self.evaluate_entities(message, expected_entities)
            entity_precisions.append(precision)
            entity_recalls.append(recall)
            entity_f1s.append(f1)

            # Evaluate route
            route_correct_pred = self.evaluate_route(message, expected_route)
            if route_correct_pred:
                route_correct += 1
            route_total += 1
            if intent_correct_pred and route_correct_pred:
                by_scenario[scenario]["correct"] += 1

        # Compute aggregate metrics
        intent_accuracy = intent_correct / intent_total if intent_total > 0 else 0.0
        entity_f1_avg = (
            sum(entity_f1s) / len(entity_f1s) if entity_f1s else 0.0
        )
        route_accuracy = route_correct / route_total if route_total > 0 else 0.0

        return {
            "total_records": len(golden_set),
            "intent_accuracy": intent_accuracy,
            "entity_precision_avg": sum(entity_precisions) / len(entity_precisions) if entity_precisions else 0.0,
            "entity_recall_avg": sum(entity_recalls) / len(entity_recalls) if entity_recalls else 0.0,
            "entity_f1_avg": entity_f1_avg,
            "route_accuracy": route_accuracy,
            "by_scenario": dict(by_scenario),
        }

    def print_metrics(self, metrics: Dict[str, Any]) -> None:
        """Print evaluation metrics.

        Args:
            metrics: Metrics dictionary
        """
        print("\n" + "=" * 60)
        print("SPRINT 2 EVALUATION RESULTS")
        print("=" * 60)
        print(f"Total Records: {metrics['total_records']}")
        print()
        print("AGGREGATE METRICS:")
        print(f"  Intent Accuracy:      {metrics['intent_accuracy']:.2%} (target: >=92%)")
        print(f"  Entity F1 Average:    {metrics['entity_f1_avg']:.2%} (target: >=85%)")
        print(f"  Routing Accuracy:     {metrics['route_accuracy']:.2%} (target: >=90%)")
        print()
        print("BY SCENARIO:")
        for scenario, stats in metrics["by_scenario"].items():
            accuracy = stats["correct"] / stats["total"] if stats["total"] > 0 else 0.0
            print(f"  {scenario}: {stats['correct']}/{stats['total']} ({accuracy:.1%})")
        print("=" * 60)

    def check_thresholds(self, metrics: Dict[str, Any]) -> bool:
        """Check if all metrics meet thresholds.

        Args:
            metrics: Metrics dictionary

        Returns:
            True if all thresholds passed
        """
        thresholds = {
            "intent_accuracy": 0.92,
            "entity_f1_avg": 0.85,
            "route_accuracy": 0.90,
        }

        all_pass = True
        for key, threshold in thresholds.items():
            actual = metrics.get(key, 0.0)
            passed = actual >= threshold
            status = "✓ PASS" if passed else "✗ FAIL"
            print(
                f"{key}: {actual:.2%} >= {threshold:.2%} {status}"
            )
            if not passed:
                all_pass = False

        return all_pass


def main():
    """Run evaluation harness."""
    parser = argparse.ArgumentParser(description="Sprint 2 Evaluation Harness")
    parser.add_argument(
        "--golden",
        type=str,
        default="tests/golden_sets/sprint2_evaluation.jsonl",
        help="Path to golden evaluation set (default: tests/golden_sets/sprint2_evaluation.jsonl)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print detailed results per record",
    )

    args = parser.parse_args()

    # Initialize harness
    harness = EvaluationHarness()

    # Load golden set
    golden_set = harness.load_golden_set(args.golden)
    if not golden_set:
        print("Error: No evaluation records loaded")
        sys.exit(1)

    # Run evaluation
    print(f"Running evaluation on {len(golden_set)} records...")
    metrics = harness.run_evaluation(golden_set)

    # Print results
    harness.print_metrics(metrics)

    # Check thresholds
    print("\nTHRESHOLD CHECK:")
    all_pass = harness.check_thresholds(metrics)

    # Exit with appropriate code
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
