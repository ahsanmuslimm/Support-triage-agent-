"""LSTM model for next-issue prediction."""

from typing import List, Tuple, Dict, Optional
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class LSTMNextIssuePredictor:
    """LSTM model for predicting next issue types."""

    def __init__(self, sequence_length: int = 30, embedding_dim: int = 64):
        """
        Initialize LSTM predictor.

        Args:
            sequence_length: Length of input sequence
            embedding_dim: Embedding dimension
        """
        self.sequence_length = sequence_length
        self.embedding_dim = embedding_dim
        self.model = None
        self.intent_vocab = {}
        self.reverse_vocab = {}
        self.trained_at: Optional[datetime] = None

    async def train(
        self,
        training_sequences: List[Tuple[List[str], str]],
        validation_split: float = 0.2,
        epochs: int = 10,
    ) -> Dict[str, float]:
        """
        Train LSTM model (mocked for testing).

        Args:
            training_sequences: List of (issue_history, target_issue) tuples
            validation_split: Fraction for validation
            epochs: Training epochs

        Returns:
            Dict with metrics {accuracy, val_loss, ...}
        """
        if not training_sequences:
            logger.warning("No training sequences provided")
            return {"accuracy": 0.0}

        # Build vocabulary from training data
        all_intents = set()
        for seq, target in training_sequences:
            all_intents.update(seq)
            all_intents.add(target)

        self.intent_vocab = {intent: i for i, intent in enumerate(sorted(all_intents))}
        self.reverse_vocab = {i: intent for intent, i in self.intent_vocab.items()}

        # Mock training: compute simple accuracy metric
        num_train = int(len(training_sequences) * (1 - validation_split))
        train_data = training_sequences[:num_train]
        val_data = training_sequences[num_train:]

        # Simulate training accuracy
        train_accuracy = 0.85 + (len(self.intent_vocab) / 100) * 0.05  # Mock
        val_loss = 0.3 - (len(train_data) / 1000) * 0.1  # Mock

        self.trained_at = datetime.utcnow()

        metrics = {
            "accuracy": min(train_accuracy, 0.92),
            "val_loss": max(val_loss, 0.1),
            "vocab_size": len(self.intent_vocab),
            "training_samples": len(train_data),
        }

        logger.info(f"LSTM training complete: {metrics}")
        return metrics

    async def predict_next_issue(
        self,
        customer_id: int,
        issue_history: List[str],
        top_k: int = 3,
    ) -> List[Tuple[str, float]]:
        """
        Predict next issue types.

        Args:
            customer_id: Customer ID
            issue_history: List of past issue intents (ordered, most recent last)
            top_k: Return top K predictions

        Returns:
            List of (intent, probability) tuples
        """
        if not issue_history:
            # Return default intents if no history
            return [("billing", 0.4), ("technical", 0.35), ("general", 0.25)]

        if not self.intent_vocab:
            logger.warning("Model not trained; returning default predictions")
            return [("billing", 0.4), ("technical", 0.35), ("general", 0.25)]

        # Mock prediction: weight intents by frequency in history + recency
        intent_scores = {}
        for i, intent in enumerate(issue_history[-self.sequence_length :]):
            weight = 1.0 + (i / len(issue_history)) * 0.5  # Recency boost
            intent_scores[intent] = intent_scores.get(intent, 0.0) + weight

        # Normalize to probabilities
        total = sum(intent_scores.values()) + 1e-6
        predictions = [
            (intent, score / total)
            for intent, score in sorted(intent_scores.items(), key=lambda x: x[1], reverse=True)
        ]

        # Fill with rare intents if needed
        all_intents = set(self.intent_vocab.keys())
        predicted_intents = {p[0] for p in predictions}
        for intent in sorted(all_intents - predicted_intents):
            if len(predictions) < top_k:
                predictions.append((intent, 0.05))

        # Return top-k with threshold >= 0.15
        top_predictions = [
            (intent, prob)
            for intent, prob in predictions[:top_k]
            if prob >= 0.15
        ]

        return top_predictions if top_predictions else predictions[:top_k]

    def is_trained(self) -> bool:
        """Check if model is trained."""
        return self.model is not None or self.trained_at is not None
