"""Structured logging configuration with PII masking."""

import re
from typing import Any

import structlog
from structlog.types import EventDict


# PII field patterns to mask
_PII_FIELDS = {"email", "phone", "name", "address", "ip", "token", "card", "ssn", "dob"}

# Regex patterns for detecting PII values
_EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_PHONE_PATTERN = re.compile(r"\+?1?\s*\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}")
_IP_PATTERN = re.compile(r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b")


class PiiFilter(structlog.processors.BaseProcessor):
    """Structlog processor that masks PII fields before logging."""

    def __call__(
        self, logger: structlog.PrintLogger, method_name: str, event_dict: EventDict
    ) -> EventDict:
        """Process event dict and mask PII fields.

        Args:
            logger: Structlog logger instance.
            method_name: Name of the method being called.
            event_dict: Dictionary of event data.

        Returns:
            EventDict: Event dict with PII masked.
        """
        for key, value in event_dict.items():
            if isinstance(value, str):
                # Mask based on field name
                if any(pii_field in key.lower() for pii_field in _PII_FIELDS):
                    event_dict[key] = "[REDACTED]"
                # Mask based on value patterns
                elif _EMAIL_PATTERN.search(value):
                    event_dict[key] = "[REDACTED_EMAIL]"
                elif _PHONE_PATTERN.search(value):
                    event_dict[key] = "[REDACTED_PHONE]"
                elif _IP_PATTERN.search(value):
                    event_dict[key] = "[REDACTED_IP]"

        return event_dict


def configure_logging(environment: str = "production") -> None:
    """Configure structlog for the application.

    Args:
        environment: Environment name (production, development, etc.).
    """
    processors: list[structlog.processors.BaseProcessor] = [
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        PiiFilter(),
    ]

    if environment == "production":
        # Production: JSON output
        processors.append(structlog.processors.JSONRenderer())
    else:
        # Development: colored console output
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(logging_level="DEBUG"),
    )


def get_logger(name: str) -> structlog.BoundLogger:
    """Get a bound logger instance.

    Args:
        name: Logger name (typically __name__).

    Returns:
        structlog.BoundLogger: Configured logger.
    """
    return structlog.get_logger(name)
