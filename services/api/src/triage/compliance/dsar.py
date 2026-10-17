"""Data Subject Access Request & Right-to-Erasure (GDPR, S10.7)."""

import asyncio
import secrets
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from typing import Any


class DSARStatus(str, Enum):
    """DSAR request status."""

    PENDING = "pending"
    VALIDATING = "validating"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"


class ErasureStatus(str, Enum):
    """Erasure request status."""

    PENDING = "pending"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class DSARRequest:
    """Data Subject Access Request."""

    request_id: str
    tenant_id: str
    customer_id: str
    request_type: str  # "export", "erasure"
    status: DSARStatus
    requested_at: datetime
    completed_at: datetime | None = None
    export_data: dict[str, Any] | None = None
    export_filename: str | None = None
    error: str | None = None

    def __post_init__(self):
        if not self.request_id:
            self.request_id = f"dsar_{secrets.token_hex(16)}"


@dataclass
class CustomerDataExport:
    """Exported customer data for DSAR."""

    customer_id: str
    tenant_id: str
    conversations: list[dict[str, Any]]
    messages: list[dict[str, Any]]
    metadata: list[dict[str, Any]]
    audit_logs: list[dict[str, Any]]
    exported_at: datetime


class DSARManager:
    """Data Subject Access Request & Erasure manager."""

    def __init__(self, test_mode: bool = False):
        self.test_mode = test_mode
        self.requests: dict[str, DSARRequest] = {}
        self.erasure_log: list[dict[str, Any]] = []
        # Simulated data stores (would be real DB tables in production)
        self.conversations_db: list[dict] = []
        self.messages_db: list[dict] = []
        self.metadata_db: list[dict] = []
        self.audit_logs_db: list[dict] = []
        self.pii_tokens_vault: dict[str, str] = {}

    async def request_export(
        self,
        tenant_id: str,
        customer_id: str,
    ) -> DSARRequest:
        """Request data export (step 1 of workflow).

        Args:
            tenant_id: Tenant ID
            customer_id: Customer ID

        Returns:
            DSARRequest
        """
        request = DSARRequest(
            request_id="",
            tenant_id=tenant_id,
            customer_id=customer_id,
            request_type="export",
            status=DSARStatus.PENDING,
            requested_at=datetime.utcnow(),
        )

        self.requests[request.request_id] = request
        return request

    async def request_erasure(
        self,
        tenant_id: str,
        customer_id: str,
    ) -> DSARRequest:
        """Request data erasure (right to be forgotten).

        Args:
            tenant_id: Tenant ID
            customer_id: Customer ID

        Returns:
            DSARRequest
        """
        request = DSARRequest(
            request_id="",
            tenant_id=tenant_id,
            customer_id=customer_id,
            request_type="erasure",
            status=DSARStatus.PENDING,
            requested_at=datetime.utcnow(),
        )

        self.requests[request.request_id] = request
        return request

    async def validate_request(self, request_id: str) -> bool:
        """Validate DSAR request (step 2 of workflow).

        Args:
            request_id: Request ID

        Returns:
            True if valid
        """
        if request_id not in self.requests:
            return False

        request = self.requests[request_id]
        request.status = DSARStatus.VALIDATING

        # Validation checks (e.g., customer exists, tenant owns customer)
        # For now, assume valid
        await asyncio.sleep(0.1)  # Simulate validation time

        return True

    async def execute_export(self, request_id: str) -> CustomerDataExport | None:
        """Execute data export (step 3a of workflow).

        Args:
            request_id: Request ID

        Returns:
            CustomerDataExport or None if failed
        """
        if request_id not in self.requests:
            return None

        request = self.requests[request_id]
        request.status = DSARStatus.EXECUTING

        try:
            # Collect all customer data
            export = CustomerDataExport(
                customer_id=request.customer_id,
                tenant_id=request.tenant_id,
                conversations=self._get_customer_conversations(request.customer_id),
                messages=self._get_customer_messages(request.customer_id),
                metadata=self._get_customer_metadata(request.customer_id),
                audit_logs=self._get_customer_audit_logs(request.customer_id),
                exported_at=datetime.utcnow(),
            )

            # Store export
            request.export_data = asdict(export)
            request.export_filename = f"export_{request.customer_id}_{datetime.utcnow().isoformat()}.json"
            request.status = DSARStatus.COMPLETED
            request.completed_at = datetime.utcnow()

            return export
        except Exception as e:
            request.status = DSARStatus.FAILED
            request.error = str(e)
            return None

    async def execute_erasure(self, request_id: str) -> bool:
        """Execute data erasure (step 3b of workflow).

        Args:
            request_id: Request ID

        Returns:
            True if successful
        """
        if request_id not in self.requests:
            return False

        request = self.requests[request_id]
        request.status = DSARStatus.EXECUTING

        try:
            start_time = datetime.utcnow()

            # Step 1: Crypto-shred encryption keys
            await self._crypto_shred_keys(request.customer_id)

            # Step 2: Cascade delete related data
            await self._cascade_delete_data(request.customer_id)

            # Step 3: Vault purge PII tokens
            await self._purge_pii_tokens(request.customer_id)

            # Step 4: Helpdesk redact message bodies
            await self._redact_message_bodies(request.customer_id)

            # Step 5: Analytics tombstone records
            await self._tombstone_analytics(request.customer_id)

            # Step 6: Verify deletion
            verified = await self._verify_erasure(request.customer_id)

            if not verified:
                raise Exception("Post-erasure verification failed")

            request.status = DSARStatus.COMPLETED
            request.completed_at = datetime.utcnow()

            self.erasure_log.append({
                "request_id": request_id,
                "customer_id": request.customer_id,
                "tenant_id": request.tenant_id,
                "duration_seconds": (datetime.utcnow() - start_time).total_seconds(),
                "completed_at": datetime.utcnow().isoformat(),
            })

            return True
        except Exception as e:
            request.status = DSARStatus.FAILED
            request.error = str(e)
            return False

    async def _crypto_shred_keys(self, customer_id: str):
        """Shred encryption keys for customer."""
        # In production: delete keys from key management service

    async def _cascade_delete_data(self, customer_id: str):
        """Delete all customer data from primary tables."""
        self.conversations_db = [c for c in self.conversations_db if c.get("customer_id") != customer_id]
        self.messages_db = [m for m in self.messages_db if m.get("customer_id") != customer_id]
        self.metadata_db = [m for m in self.metadata_db if m.get("customer_id") != customer_id]

    async def _purge_pii_tokens(self, customer_id: str):
        """Purge PII tokens from vault."""
        keys_to_delete = [
            k for k, v in self.pii_tokens_vault.items()
            if v.get("customer_id") == customer_id
        ]
        for key in keys_to_delete:
            del self.pii_tokens_vault[key]

    async def _redact_message_bodies(self, customer_id: str):
        """Redact message bodies in helpdesk records."""
        for message in self.messages_db:
            if message.get("customer_id") == customer_id:
                message["body"] = "[REDACTED]"
                message["redacted_at"] = datetime.utcnow().isoformat()

    async def _tombstone_analytics(self, customer_id: str):
        """Replace analytics records with tombstones."""
        # In production: insert tombstone rows in analytics tables

    async def _verify_erasure(self, customer_id: str) -> bool:
        """Verify no customer data remains (post-erasure verification).

        Returns:
            True if no data found
        """
        data_remains = (
            any(c.get("customer_id") == customer_id for c in self.conversations_db)
            or any(m.get("customer_id") == customer_id for m in self.messages_db)
            or any(m.get("customer_id") == customer_id for m in self.metadata_db)
        )
        return not data_remains

    def _get_customer_conversations(self, customer_id: str) -> list[dict]:
        """Get all conversations for customer."""
        return [c for c in self.conversations_db if c.get("customer_id") == customer_id]

    def _get_customer_messages(self, customer_id: str) -> list[dict]:
        """Get all messages for customer."""
        return [m for m in self.messages_db if m.get("customer_id") == customer_id]

    def _get_customer_metadata(self, customer_id: str) -> list[dict]:
        """Get all metadata for customer."""
        return [m for m in self.metadata_db if m.get("customer_id") == customer_id]

    def _get_customer_audit_logs(self, customer_id: str) -> list[dict]:
        """Get all audit logs for customer."""
        return [a for a in self.audit_logs_db if a.get("customer_id") == customer_id]

    def get_request_status(self, request_id: str) -> DSARRequest | None:
        """Get status of DSAR request."""
        return self.requests.get(request_id)

    def get_erasure_log(self, tenant_id: str) -> list[dict[str, Any]]:
        """Get erasure log entries."""
        return [e for e in self.erasure_log if e["tenant_id"] == tenant_id]
