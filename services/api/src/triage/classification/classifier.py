"""Intent classifier using embeddings + k-NN + temperature scaling."""


import numpy as np
import structlog
from sklearn.neighbors import NearestNeighbors  # type: ignore

try:
    from py_core.errors import TriageBaseError
except ImportError:
    from packages.py_core.py_core.errors import TriageBaseError

from triage.models.intent import IntentClassifierResult, IntentPrediction

log = structlog.get_logger()


class IntentClassifierError(TriageBaseError):
    """Intent classification error."""

    error_code = "intent_classifier_error"
    http_status = 500
    title = "Intent Classification Failed"


class IntentClassifier:
    """k-NN + temperature-scaled logistic classifier for multi-label intent prediction."""

    def __init__(
        self,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        temperature: float = 1.2,
        k: int = 5,
        confidence_threshold: float = 0.1,
    ):
        """Initialize classifier.

        Args:
            model_name: Sentence transformers model ID.
            temperature: Temperature for softmax scaling of confidences.
            k: Number of neighbors for k-NN.
            confidence_threshold: Minimum confidence to include intent.
        """
        self.model_name = model_name
        self.temperature = temperature
        self.k = k
        self.confidence_threshold = confidence_threshold

        # Loaded lazily: pulling torch/sentence-transformers at import time
        # would make every process (CI, workers) pay for the ML stack.
        from sentence_transformers import SentenceTransformer  # type: ignore

        self.embedding_model = SentenceTransformer(model_name)
        self.embedding_dim = self.embedding_model.get_sentence_embedding_dimension()

        # k-NN will be initialized when intent examples are provided
        self.knn_model: NearestNeighbors | None = None
        self.intent_embeddings: dict[str, np.ndarray] = {}
        self.intent_examples_per_intent: dict[str, list[str]] = {}

    def set_intent_examples(self, examples: dict[str, list[str]]) -> None:
        """Set training examples for each intent.

        Args:
            examples: Dict mapping intent_name -> list of example texts.
        """
        self.intent_examples_per_intent = examples

        # Compute embeddings for each example and average by intent
        intent_embeddings_list = []
        intent_names_list = []

        for intent_name, example_texts in examples.items():
            if not example_texts:
                continue

            embeddings = self.embedding_model.encode(example_texts, convert_to_numpy=True)
            if isinstance(embeddings, np.ndarray) and embeddings.ndim == 1:
                embeddings = embeddings.reshape(1, -1)

            # Average embeddings for this intent
            avg_embedding = np.mean(embeddings, axis=0)
            self.intent_embeddings[intent_name] = avg_embedding
            intent_embeddings_list.append(avg_embedding)
            intent_names_list.append(intent_name)

        if not intent_embeddings_list:
            raise IntentClassifierError("No valid intent examples provided")

        # Build k-NN model
        embeddings_array = np.array(intent_embeddings_list)
        self.knn_model = NearestNeighbors(n_neighbors=min(self.k, len(intent_names_list)), metric="cosine")
        self.knn_model.fit(embeddings_array)
        self.intent_names_list = intent_names_list

        log.info("intent_classifier_initialized", n_intents=len(intent_names_list), model=self.model_name)

    async def classify(self, message_text: str) -> IntentClassifierResult:
        """Classify message intents.

        Args:
            message_text: Message to classify.

        Returns:
            IntentClassifierResult with predictions.
        """
        try:
            if not self.knn_model:
                raise IntentClassifierError("Classifier not initialized: no intent examples set")

            if not message_text.strip():
                raise IntentClassifierError("Message text is empty")

            # Embed the message
            message_embedding = self.embedding_model.encode(message_text, convert_to_numpy=True)
            if message_embedding.ndim == 1:
                message_embedding = message_embedding.reshape(1, -1)

            # Find k nearest intents
            distances, indices = self.knn_model.kneighbors(message_embedding)
            distances = distances[0]  # Shape: (k,)
            indices = indices[0]  # Shape: (k,)

            # Convert distances to similarities (1 - distance for cosine)
            similarities = np.clip(1.0 - distances, 0.0, 1.0)

            # Aggregate neighbor votes per intent, weighted by similarity.
            # A per-neighbor softmax over near-identical similarities would cap
            # confidence around 1/k even for exact training matches, which is
            # useless for the 0.75-0.95 autonomy thresholds downstream.
            intent_scores: dict[str, float] = {}
            total_score = 0.0
            for idx, intent_idx in enumerate(indices):
                intent_name = self.intent_names_list[intent_idx]
                # Temperature sharpens (<1) or softens (>1) the vote weights
                weight = float(similarities[idx]) ** (1.0 / self.temperature)
                intent_scores[intent_name] = intent_scores.get(intent_name, 0.0) + weight
                total_score += weight

            # Build predictions
            all_intents = []
            for intent_name, score in intent_scores.items():
                confidence = score / total_score if total_score > 0 else 0.0

                if confidence >= self.confidence_threshold:
                    all_intents.append(
                        IntentPrediction(
                            intent_name=intent_name,
                            confidence=confidence,
                            temperature_scaled=True,
                        )
                    )

            # Sort by confidence (descending)
            all_intents = sorted(all_intents, key=lambda x: x.confidence, reverse=True)

            top_intent = all_intents[0].intent_name if all_intents else None
            top_confidence = all_intents[0].confidence if all_intents else None

            result = IntentClassifierResult(
                message_id="",  # Will be set by caller
                top_intent=top_intent,
                top_confidence=top_confidence,
                all_intents=all_intents,
                fallback_used=False,
            )

            log.info(
                "intent_classification_complete",
                top_intent=top_intent,
                top_confidence=top_confidence,
                n_intents=len(all_intents),
            )

            return result

        except Exception as e:
            log.error("intent_classification_failed", error=str(e))
            raise IntentClassifierError(f"Classification failed: {e!s}") from e

    def get_intents(self) -> list[str]:
        """Get list of known intents."""
        return list(self.intent_embeddings.keys())
