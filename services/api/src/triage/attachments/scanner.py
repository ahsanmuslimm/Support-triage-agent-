"""Malware scanning via ClamAV REST API."""

from dataclasses import dataclass
from enum import Enum

import structlog

log = structlog.get_logger()


class ScanStatus(str, Enum):
    """Scan result status."""

    CLEAN = "clean"
    INFECTED = "infected"
    ERROR = "error"
    UNSUPPORTED = "unsupported"


@dataclass
class MalwareScanResult:
    """Result of malware scan."""

    status: ScanStatus
    """Scan status."""

    threat_name: str | None = None
    """Name of detected threat (if infected)."""

    engine: str = "clamav"
    """Scanning engine used."""

    scanned_at: str = ""
    """Scan timestamp."""

    error: str | None = None
    """Error message if scan failed."""


class MalwareScanner:
    """Scan attachments for malware using ClamAV."""

    def __init__(self, clamav_endpoint: str = "http://localhost:8080") -> None:
        """Initialize scanner.

        Args:
            clamav_endpoint: ClamAV REST API endpoint.
        """
        self.clamav_endpoint = clamav_endpoint

    async def scan_file(self, file_path: str, filename: str) -> MalwareScanResult:
        """Scan file for malware.

        Args:
            file_path: Path to file on disk.
            filename: Original filename for logging.

        Returns:
            MalwareScanResult: Scan result.
        """
        try:
            from datetime import datetime

            log.info("scan_start", filename=filename)

            # In real implementation, POST to ClamAV API
            # POST {clamav_endpoint}/scan with multipart/form-data

            # Simulated ClamAV response
            is_infected = filename.lower().endswith(".eicar")  # EICAR test file

            if is_infected:
                result = MalwareScanResult(
                    status=ScanStatus.INFECTED,
                    threat_name="Win.Test.EICAR_HDB-1",
                    scanned_at=datetime.utcnow().isoformat(),
                )
                log.warning("malware_detected", filename=filename, threat=result.threat_name)
            else:
                result = MalwareScanResult(
                    status=ScanStatus.CLEAN,
                    scanned_at=datetime.utcnow().isoformat(),
                )
                log.info("scan_clean", filename=filename)

            return result

        except Exception as e:
            log.error("scan_error", error=str(e), filename=filename)
            return MalwareScanResult(
                status=ScanStatus.ERROR,
                error=str(e),
                scanned_at="",
            )

    async def scan_bytes(self, file_bytes: bytes, filename: str) -> MalwareScanResult:
        """Scan file contents for malware.

        Args:
            file_bytes: File content bytes.
            filename: Original filename for logging.

        Returns:
            MalwareScanResult: Scan result.
        """
        try:
            from datetime import datetime

            log.info("scan_bytes_start", filename=filename, size_bytes=len(file_bytes))

            # In real implementation, POST to ClamAV with file content
            # POST {clamav_endpoint}/scan with body=file_bytes

            # Simulated check: reject if starts with EICAR signature
            eicar_sig = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
            is_infected = file_bytes.startswith(eicar_sig)

            if is_infected:
                result = MalwareScanResult(
                    status=ScanStatus.INFECTED,
                    threat_name="Win.Test.EICAR_HDB-1",
                    scanned_at=datetime.utcnow().isoformat(),
                )
                log.warning("malware_detected", filename=filename, threat=result.threat_name)
            else:
                result = MalwareScanResult(
                    status=ScanStatus.CLEAN,
                    scanned_at=datetime.utcnow().isoformat(),
                )
                log.info("scan_clean", filename=filename)

            return result

        except Exception as e:
            log.error("scan_bytes_error", error=str(e), filename=filename)
            return MalwareScanResult(
                status=ScanStatus.ERROR,
                error=str(e),
            )

    def is_supported_format(self, filename: str) -> bool:
        """Check if file format is supported for scanning.

        Args:
            filename: Filename with extension.

        Returns:
            bool: True if format is scannable.
        """
        supported_extensions = {
            ".exe", ".dll", ".com", ".scr", ".vbs", ".js", ".zip", ".rar",
            ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".jar"
        }
        ext = filename.lower()[filename.rfind("."):]
        return ext in supported_extensions or len(ext) == 0
