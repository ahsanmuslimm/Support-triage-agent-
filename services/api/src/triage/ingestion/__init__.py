"""Message ingestion pipeline."""

from .coalescing import MessageCoalescer
from .encryption import EnvelopeEncryption
from .idempotency import IdempotencyManager
from .identity import IdentityResolver
from .normalizers import NormalizerFactory
from .outbox import OutboxPoller, OutboxWriter
from .pii_handler import PiiHandler

__all__ = [
    "EnvelopeEncryption",
    "IdempotencyManager",
    "IdentityResolver",
    "MessageCoalescer",
    "NormalizerFactory",
    "OutboxPoller",
    "OutboxWriter",
    "PiiHandler",
]
