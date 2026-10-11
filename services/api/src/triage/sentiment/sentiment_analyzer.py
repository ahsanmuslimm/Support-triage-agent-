"""S3.6: Customer Sentiment & NPS History."""

import logging
from dataclasses import dataclass
from typing import Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)


class SentimentAnalyzer:
    """Sentiment classification with TextBlob + transformer fallback."""

    def __init__(self, use_transformer: bool = False):
        self.use_transformer = use_transformer
        self.transformer_model = None

        if use_transformer:
            try:
                from transformers import pipeline

                self.transformer_model = pipeline(
                    "sentiment-analysis", model="distilbert-base-uncased-finetuned-sst-2-english"
                )
            except Exception as e:
                logger.warning(f"Failed to load transformer model: {e}")
                self.use_transformer = False

    def analyze(self, text: str) -> dict:
        """
        Analyze sentiment of text.

        Returns:
            {sentiment: 'positive'|'neutral'|'negative', score: -1.0 to 1.0}
        """
        if not text:
            return {"sentiment": "neutral", "score": 0.0}

        if self.use_transformer and self.transformer_model:
            return self._analyze_transformer(text)
        else:
            return self._analyze_textblob(text)

    def _analyze_textblob(self, text: str) -> dict:
        """Analyze using TextBlob polarity."""
        try:
            from textblob import TextBlob

            blob = TextBlob(text)
            polarity = blob.sentiment.polarity  # -1.0 to 1.0

            if polarity > 0.1:
                sentiment = "positive"
            elif polarity < -0.1:
                sentiment = "negative"
            else:
                sentiment = "neutral"

            return {"sentiment": sentiment, "score": polarity}
        except Exception as e:
            logger.error(f"TextBlob analysis failed: {e}")
            return {"sentiment": "neutral", "score": 0.0}

    def _analyze_transformer(self, text: str) -> dict:
        """Analyze using DistilBERT transformer."""
        try:
            result = self.transformer_model(text[:512])[0]  # Truncate to 512 tokens
            label = result["label"]  # POSITIVE or NEGATIVE
            score = result["score"]

            # Map to polarity
            if label == "POSITIVE":
                polarity = score
                sentiment = "positive"
            else:
                polarity = -score
                sentiment = "negative"

            return {"sentiment": sentiment, "score": polarity}
        except Exception as e:
            logger.error(f"Transformer analysis failed: {e}")
            return {"sentiment": "neutral", "score": 0.0}

    @staticmethod
    def segment_nps(nps_score: int) -> str:
        """Map NPS score to segment."""
        if nps_score >= 9:
            return "promoter"
        elif nps_score >= 7:
            return "passive"
        else:
            return "detractor"

    @staticmethod
    def compute_trend(scores: List[float]) -> str:
        """Compute trend from score history (last 5)."""
        if len(scores) < 2:
            return "stable"

        recent = scores[-3:]  # Last 3 scores
        early = scores[:3] if len(scores) >= 3 else scores[:1]

        avg_recent = sum(recent) / len(recent)
        avg_early = sum(early) / len(early)

        delta = avg_recent - avg_early
        if delta > 0.1:
            return "improving"
        elif delta < -0.1:
            return "declining"
        else:
            return "stable"
