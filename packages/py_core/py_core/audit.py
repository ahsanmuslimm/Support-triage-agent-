"""Audit logging with hash-chain integrity verification."""

from dataclasses import dataclass
from uuid import UUID


@dataclass
class AuditBreak:
    """Represents a broken link in the audit hash chain."""

    broken_at: int
    """Row ID where the chain break occurred."""

    expected_hash: str
    """Expected hash value based on previous row."""

    found_hash: str
    """Actual hash value found in the database."""


async def verify_audit_chain(session, tenant_id: UUID) -> list[AuditBreak]:
    """Verify integrity of audit log hash chain.

    Args:
        session: SQLAlchemy async session.
        tenant_id: Tenant ID to verify.

    Returns:
        list[AuditBreak]: List of chain breaks; empty if chain is intact.
    """
    from sqlalchemy import text

    result = await session.execute(
        text("SELECT * FROM triage.verify_audit_chain(:tenant_id)"),
        {"tenant_id": str(tenant_id)},
    )

    breaks = []
    for row in result:
        breaks.append(
            AuditBreak(
                broken_at=row[0],
                expected_hash=row[1],
                found_hash=row[2],
            )
        )

    return breaks
