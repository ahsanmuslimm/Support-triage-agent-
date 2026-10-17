"""Attachment handling with scanning, extraction, and pseudonymization."""

from triage.attachments.extractor import ExtractionResult, TextExtractor
from triage.attachments.pii_pseudonymizer import PIIPseudonymizer
from triage.attachments.scanner import MalwareScanner, MalwareScanResult

__all__ = [
    "ExtractionResult",
    "MalwareScanResult",
    "MalwareScanner",
    "PIIPseudonymizer",
    "TextExtractor",
]
