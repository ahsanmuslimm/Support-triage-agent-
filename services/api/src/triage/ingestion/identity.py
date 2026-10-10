"""Customer identity resolution and deduplication."""

import hashlib
from typing import Optional, Dict, Any
from enum import Enum


class IdentityAssuranceLevel(str, Enum):
    """Identity assurance levels (NIST SP 800-63-3)."""

    IAL1 = "ial1"  # Channel-asserted (email, phone, external ID)
    IAL2 = "ial2"  # Verified by support team
    IAL3 = "ial3"  # Verified with strong evidence


class CustomerIdentity:
    """Customer identity record with deduplication support."""

    def __init__(
        self,
        tenant_id: str,
        customer_id: str,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        zendesk_id: Optional[str] = None,
        external_id: Optional[str] = None,
        display_name: Optional[str] = None,
    ):
        """Initialize customer identity."""
        self.tenant_id = tenant_id
        self.customer_id = customer_id
        self.email = email
        self.phone = phone
        self.zendesk_id = zendesk_id
        self.external_id = external_id
        self.display_name = display_name
        self.ial = IdentityAssuranceLevel.IAL1
        self.aliases: Dict[str, str] = {}  # {type: id}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for storage."""
        return {
            "tenant_id": self.tenant_id,
            "customer_id": self.customer_id,
            "email": self.email,
            "phone": self.phone,
            "zendesk_id": self.zendesk_id,
            "external_id": self.external_id,
            "display_name": self.display_name,
            "ial": self.ial.value,
            "aliases": self.aliases,
        }


class IdentityResolver:
    """Resolves and deduplicates customer identities across channels."""

    def __init__(self):
        """Initialize resolver."""
        # In-memory storage for demo (replace with DB query in real impl)
        self._customers: Dict[str, CustomerIdentity] = {}
        # Tenant-scoped indexes
        self._email_index: Dict[str, Dict[str, str]] = {}  # tenant_id -> {email_hash -> customer_id}
        self._phone_index: Dict[str, Dict[str, str]] = {}  # tenant_id -> {phone_hash -> customer_id}
        self._zendesk_index: Dict[str, Dict[str, str]] = {}  # tenant_id -> {zendesk_id -> customer_id}

    def resolve_or_create(
        self,
        tenant_id: str,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        zendesk_id: Optional[str] = None,
        external_id: Optional[str] = None,
        display_name: Optional[str] = None,
    ) -> CustomerIdentity:
        """Resolve or create customer identity.

        Searches by email, phone, zendesk_id in priority order.
        If multiple identities found, merges them.
        If none found, creates new.

        Args:
            tenant_id: Tenant ID
            email: Customer email
            phone: Customer phone number
            zendesk_id: Zendesk user ID
            external_id: External system ID
            display_name: Customer display name

        Returns:
            CustomerIdentity (existing or newly created)
        """
        candidates = []

        # Ensure tenant-scoped indexes exist
        if tenant_id not in self._email_index:
            self._email_index[tenant_id] = {}
        if tenant_id not in self._phone_index:
            self._phone_index[tenant_id] = {}
        if tenant_id not in self._zendesk_index:
            self._zendesk_index[tenant_id] = {}

        # Search by email (tenant-scoped)
        if email:
            email_hash = self._hash_identifier(email)
            if email_hash in self._email_index[tenant_id]:
                customer_id = self._email_index[tenant_id][email_hash]
                candidates.append(self._customers[customer_id])

        # Search by phone (tenant-scoped)
        if phone:
            phone_hash = self._hash_identifier(phone)
            if phone_hash in self._phone_index[tenant_id]:
                customer_id = self._phone_index[tenant_id][phone_hash]
                candidates.append(self._customers[customer_id])

        # Search by Zendesk ID (tenant-scoped)
        if zendesk_id:
            if zendesk_id in self._zendesk_index[tenant_id]:
                customer_id = self._zendesk_index[tenant_id][zendesk_id]
                candidates.append(self._customers[customer_id])

        # Deduplicate candidates
        candidates = list({c.customer_id: c for c in candidates}.values())

        if candidates:
            # Use first match, merge others if multiple
            primary = candidates[0]
            if len(candidates) > 1:
                for secondary in candidates[1:]:
                    self._merge_identities(primary, secondary)
            customer = primary
        else:
            # Create new customer
            import uuid
            customer_id = str(uuid.uuid4())
            customer = CustomerIdentity(
                tenant_id=tenant_id,
                customer_id=customer_id,
                email=email,
                phone=phone,
                zendesk_id=zendesk_id,
                external_id=external_id,
                display_name=display_name,
            )
            self._customers[customer_id] = customer

        # Update indexes (tenant-scoped)
        if email:
            self._email_index[tenant_id][self._hash_identifier(email)] = customer.customer_id
        if phone:
            self._phone_index[tenant_id][self._hash_identifier(phone)] = customer.customer_id
        if zendesk_id:
            self._zendesk_index[tenant_id][zendesk_id] = customer.customer_id

        # Update or add identifiers
        customer.email = customer.email or email
        customer.phone = customer.phone or phone
        customer.zendesk_id = customer.zendesk_id or zendesk_id
        customer.external_id = customer.external_id or external_id
        customer.display_name = customer.display_name or display_name

        return customer

    def _merge_identities(
        self,
        primary: CustomerIdentity,
        secondary: CustomerIdentity,
    ) -> None:
        """Merge secondary identity into primary.

        Args:
            primary: Primary identity (kept)
            secondary: Secondary identity (merged into primary)
        """
        # Consolidate identifiers
        if not primary.email and secondary.email:
            primary.email = secondary.email
        if not primary.phone and secondary.phone:
            primary.phone = secondary.phone
        if not primary.zendesk_id and secondary.zendesk_id:
            primary.zendesk_id = secondary.zendesk_id
        if not primary.external_id and secondary.external_id:
            primary.external_id = secondary.external_id
        if not primary.display_name and secondary.display_name:
            primary.display_name = secondary.display_name

        # Mark secondary as alias
        primary.aliases[secondary.customer_id] = "merged"

        # Remove secondary from main store
        if secondary.customer_id in self._customers:
            del self._customers[secondary.customer_id]

    @staticmethod
    def _hash_identifier(identifier: str) -> str:
        """Hash identifier for index lookups (privacy-preserving)."""
        return hashlib.sha256(identifier.lower().encode()).hexdigest()[:16]
