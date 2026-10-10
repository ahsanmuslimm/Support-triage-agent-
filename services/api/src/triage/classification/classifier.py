"""Intent classifier using embeddings + k-NN + temperature scaling."""

import asyncio
import numpy as np
from typing import Optional, List, Dict, Any
import structlog
from sentence_transformers import SentenceTransformer  # type: ignore
from sklearn.neighbors import NearestNeighbors  # type: ignore
from packages.py_core.py_core.errors import TriageBaseError
from services.api.src.triage.models.intent import IntentPrediction, IntentClassifierResult

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

        # Load embedding model
        self.embedding_model = SentenceTransformer(model_name)
        self.embedding_dim = self.embedding_model.get_sentence_embedding_dimension()

        # k-NN will be initialized when intent examples are provided
        self.knn_model: Optional[NearestNeighbors] = None
        self.intent_embeddings: Dict[str, np.ndarray] = {}
        self.intent_examples_per_intent: Dict[str, List[str]] = {}

    def set_intent_examples(self, examples: Dict[str, List[str]]) -> None:
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
            similarities = 1.0 - distances

            # Temperature scale: apply softmax with temperature
            similarities_normalized = np.exp(similarities / self.temperature)
            confidences = similarities_normalized / np.sum(similarities_normalized)

            # Build predictions
            all_intents = []
            for idx, intent_idx in enumerate(indices):
                intent_name = self.intent_names_list[intent_idx]
                confidence = float(confidences[idx])

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
            raise IntentClassifierError(f"Classification failed: {str(e)}")

    def get_intents(self) -> List[str]:
        """Get list of known intents."""
        return list(self.intent_embeddings.keys())
