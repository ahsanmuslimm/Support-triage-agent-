"""Attachment handling with scanning, extraction, and pseudonymization."""

from triage.attachments.scanner import MalwareScanResult, MalwareScanner
from triage.attachments.extractor import TextExtractor, ExtractionResult
from triage.attachments.pii_pseudonymizer import PIIPseudonymizer

__all__ = [
    "MalwareScanResult",
    "MalwareScanner",
    "TextExtractor",
    "ExtractionResult",
    "PIIPseudonymizer",
]
