"""Intent classification module."""

from typing import Any

from .fallback import FallbackIntentClassifier

__all__ = [
    "FallbackIntentClassifier",
    "IntentClassifier",
    "IntentClassifierError",
    "TemperatureScaler",
]


def __getattr__(name: str) -> Any:
    # Lazy: .classifier pulls numpy/sklearn and .temperature_scaler pulls
    # numpy at import time; workers and lightweight images must not pay for
    # them unless they actually use these classes.
    if name in ("IntentClassifier", "IntentClassifierError"):
        from . import classifier

        return getattr(classifier, name)
    if name == "TemperatureScaler":
        from .temperature_scaler import TemperatureScaler

        return TemperatureScaler
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
