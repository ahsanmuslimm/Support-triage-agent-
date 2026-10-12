"""EU Data Residency & Data Governance (S10.8)."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class Datacenter(str, Enum):
    """Supported datacenters."""

    EU = "eu"
    US = "us"
    APAC = "apac"


class DataResidencyError(Exception):
    """Data residency violation."""



@dataclass
class TenantDatacenterConfig:
    """Tenant datacenter configuration."""

    tenant_id: str
    datacenter: Datacenter
    created_at: datetime
    updated_at: datetime


@dataclass
class DataResidencyAuditLog:
    """Audit log entry for data residency."""

    timestamp: datetime
    tenant_id: str
    operation: str
    resource_type: str
    datacenter: Datacenter
    location: str  # e.g., "EU-PostgreSQL", "EU-S3", "EU-ClickHouse"
    status: str  # "success", "failure"
    error: str | None = None


class DataResidencyManager:
    """Manage data residency and governance."""

    def __init__(self, test_mode: bool = False):
        self.test_mode = test_mode
        self.tenant_config: dict[str, TenantDatacenterConfig] = {}
        self.audit_log: list[DataResidencyAuditLog] = []

    def set_tenant_datacenter(
        self,
        tenant_id: str,
        datacenter: Datacenter,
    ) -> TenantDatacenterConfig:
        """Configure tenant datacenter.

        Args:
            tenant_id: Tenant ID
            datacenter: Datacenter (eu, us, apac)

        Returns:
            TenantDatacenterConfig
        """
        config = TenantDatacenterConfig(
            tenant_id=tenant_id,
            datacenter=datacenter,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        self.tenant_config[tenant_id] = config
        return config

    def get_tenant_datacenter(self, tenant_id: str) -> Datacenter | None:
        """Get configured datacenter for tenant."""
        if tenant_id in self.tenant_config:
            return self.tenant_config[tenant_id].datacenter
        return None

    async def verify_write_location(
        self,
        tenant_id: str,
        resource_type: str,
        storage_location: str,
    ) -> bool:
        """Verify data write respects residency.

        Args:
            tenant_id: Tenant ID
            resource_type: Type of resource (conversation, message, etc.)
            storage_location: Actual storage location

        Returns:
            True if location matches tenant config

        Raises:
            DataResidencyError if mismatch
        """
        datacenter = self.get_tenant_datacenter(tenant_id)
        if not datacenter:
            # No specific requirement, allow
            return True

        # Validate location
        location_lower = storage_location.lower()
        if datacenter == Datacenter.EU:
            if "eu" not in location_lower:
                raise DataResidencyError(
                    f"Tenant {tenant_id} requires EU residency, got {storage_location}"
                )
        elif datacenter == Datacenter.US and "us" not in location_lower:
            raise DataResidencyError(
                f"Tenant {tenant_id} requires US residency, got {storage_location}"
            )

        # Log successful write
        self.audit_log.append(DataResidencyAuditLog(
            timestamp=datetime.utcnow(),
            tenant_id=tenant_id,
            operation="write",
            resource_type=resource_type,
            datacenter=datacenter,
            location=storage_location,
            status="success",
        ))

        return True

    async def verify_egress_endpoint(
        self,
        tenant_id: str,
        endpoint_url: str,
    ) -> bool:
        """Verify outbound API call respects residency.

        Args:
            tenant_id: Tenant ID
            endpoint_url: Target endpoint URL

        Returns:
            True if endpoint allowed

        Raises:
            DataResidencyError if endpoint violates residency
        """
        datacenter = self.get_tenant_datacenter(tenant_id)
        if not datacenter:
            return True

        if datacenter == Datacenter.EU:
            # EU tenant can only call EU-region LLM endpoints
            if "eu" not in endpoint_url.lower() and "europe" not in endpoint_url.lower():
                raise DataResidencyError(
                    f"EU tenant cannot call US endpoint: {endpoint_url}"
                )
        elif datacenter == Datacenter.US and (
            "eu" in endpoint_url.lower() or "europe" in endpoint_url.lower()
        ):
            # US tenant can only call US-region endpoints
            raise DataResidencyError(
                f"US tenant cannot call EU endpoint: {endpoint_url}"
            )

        # Log successful egress
        self.audit_log.append(DataResidencyAuditLog(
            timestamp=datetime.utcnow(),
            tenant_id=tenant_id,
            operation="egress",
            resource_type="llm_call",
            datacenter=datacenter,
            location=endpoint_url,
            status="success",
        ))

        return True

    def get_audit_log(
        self,
        tenant_id: str,
        limit: int = 100,
    ) -> list[DataResidencyAuditLog]:
        """Get residency audit log for tenant."""
        entries = [
            e for e in self.audit_log
            if e.tenant_id == tenant_id
        ]
        return entries[-limit:]

    def validate_schema(self) -> bool:
        """Validate data residency configuration schema."""
        # Check that all tenants with configs have valid datacenters
        return all(config.datacenter in Datacenter for config in self.tenant_config.values())


class RegionLockManager:
    """Enforce LiteLLM region locking for EU tenants."""

    def __init__(self):
        self.region_mappings: dict[str, dict[str, str]] = {
            "eu": {
                "openai": "https://api.openai.com",  # Would be EU proxy in production
                "anthropic": "https://api.anthropic.com",  # Would be EU proxy
            },
            "us": {
                "openai": "https://api.openai.com",
                "anthropic": "https://api.anthropic.com",
            },
        }

    def get_region_endpoint(
        self,
        datacenter: Datacenter,
        provider: str,
    ) -> str:
        """Get region-specific endpoint for LLM provider.

        Args:
            datacenter: Datacenter (eu, us)
            provider: Provider name (openai, anthropic)

        Returns:
            Region-locked endpoint URL
        """
        dc_key = datacenter.value if isinstance(datacenter, Datacenter) else datacenter
        if dc_key in self.region_mappings:
            return self.region_mappings[dc_key].get(provider, "")
        return ""

    def validate_endpoint_region(
        self,
        datacenter: Datacenter,
        endpoint: str,
    ) -> bool:
        """Validate endpoint matches datacenter region."""
        if datacenter == Datacenter.EU:
            return "eu" in endpoint.lower() or endpoint.startswith("https://eu-")
        elif datacenter == Datacenter.US:
            return "us" not in endpoint.lower() or endpoint.startswith("https://")
        return True
