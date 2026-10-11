"""SCIM 2.0 provisioning (S10.6)."""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum
import secrets


@dataclass
class SCIMUser:
    """SCIM 2.0 User resource."""

    id: str
    tenant_id: str
    user_name: str  # Unique identifier
    given_name: str
    family_name: str
    email: str
    active: bool = True
    mfa_enabled: bool = False
    mfa_secret: Optional[str] = None
    created_at: datetime = None
    updated_at: datetime = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()
        if self.updated_at is None:
            self.updated_at = datetime.utcnow()

    def to_scim_dict(self) -> Dict[str, Any]:
        """Convert to SCIM JSON representation."""
        return {
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
            "id": self.id,
            "userName": self.user_name,
            "name": {
                "givenName": self.given_name,
                "familyName": self.family_name,
            },
            "emails": [{"value": self.email}],
            "active": self.active,
            "meta": {
                "resourceType": "User",
                "created": self.created_at.isoformat(),
                "lastModified": self.updated_at.isoformat(),
            },
        }


@dataclass
class SCIMPatchOp:
    """SCIM PATCH operation."""

    op: str  # "add", "replace", "remove"
    path: str
    value: Optional[Any] = None


class SCIMProvisioner:
    """SCIM 2.0 provisioning engine."""

    def __init__(self, test_mode: bool = False):
        self.test_mode = test_mode
        self.users: Dict[str, SCIMUser] = {}
        self.api_keys_by_user: Dict[str, List[str]] = {}
        self.sessions_by_user: Dict[str, List[str]] = {}
        self.sync_log: List[Dict[str, Any]] = []

    def create_user(
        self,
        tenant_id: str,
        user_name: str,
        given_name: str,
        family_name: str,
        email: str,
        mfa_required: bool = False,
    ) -> SCIMUser:
        """Create user via SCIM (POST /Users).

        Args:
            tenant_id: Tenant ID
            user_name: Username
            given_name: First name
            family_name: Last name
            email: Email address
            mfa_required: Whether to enable MFA

        Returns:
            SCIMUser
        """
        user_id = secrets.token_hex(16)

        user = SCIMUser(
            id=user_id,
            tenant_id=tenant_id,
            user_name=user_name,
            given_name=given_name,
            family_name=family_name,
            email=email,
            active=True,
        )

        # Enable MFA if required
        if mfa_required:
            user.mfa_enabled = True
            user.mfa_secret = secrets.token_hex(20)

        self.users[user_id] = user
        self.api_keys_by_user[user_id] = []
        self.sessions_by_user[user_id] = []

        return user

    def get_user(self, user_id: str) -> Optional[SCIMUser]:
        """Get user (GET /Users/{id})."""
        return self.users.get(user_id)

    def update_user(self, user_id: str, operations: List[SCIMPatchOp]) -> Optional[SCIMUser]:
        """Update user (PATCH /Users/{id}).

        Args:
            user_id: User ID
            operations: List of SCIM PATCH operations

        Returns:
            Updated user or None if not found
        """
        if user_id not in self.users:
            return None

        user = self.users[user_id]
        for op in operations:
            if op.op == "replace":
                if op.path == "/active":
                    user.active = op.value
            elif op.op == "add":
                if op.path == "/mfa":
                    user.mfa_enabled = True
                    user.mfa_secret = op.value or secrets.token_hex(20)
            elif op.op == "remove":
                if op.path == "/mfa":
                    user.mfa_enabled = False
                    user.mfa_secret = None

        user.updated_at = datetime.utcnow()
        return user

    async def deprovision_user(self, user_id: str, timeout_seconds: int = 60) -> bool:
        """Deprovision user (DELETE /Users/{id}, set active=false).

        Args:
            user_id: User ID
            timeout_seconds: Max time for deprovisioning

        Returns:
            True if successful

        Deprovisioning steps:
        1. Set active=false
        2. Revoke API keys
        3. Revoke sessions
        All within timeout_seconds
        """
        if user_id not in self.users:
            return False

        user = self.users[user_id]
        start_time = datetime.utcnow()

        # Step 1: Set active=false
        user.active = False

        # Step 2: Revoke API keys
        if user_id in self.api_keys_by_user:
            self.api_keys_by_user[user_id] = []

        # Step 3: Revoke sessions
        if user_id in self.sessions_by_user:
            self.sessions_by_user[user_id] = []

        # Check timeout
        elapsed = (datetime.utcnow() - start_time).total_seconds()
        return elapsed < timeout_seconds

    async def sync_with_idp(
        self,
        tenant_id: str,
        idp_users: List[Dict[str, str]],
    ) -> Dict[str, Any]:
        """Sync users from external IDP (Okta, Azure).

        Args:
            tenant_id: Tenant ID
            idp_users: Users from IDP

        Returns:
            Sync result {created, updated, deleted, errors}
        """
        result = {
            "created": [],
            "updated": [],
            "deleted": [],
            "errors": [],
        }

        for idp_user in idp_users:
            try:
                # Check if user exists locally
                existing = self._find_user_by_username(tenant_id, idp_user["username"])

                if existing:
                    # Update
                    ops = []
                    if existing.email != idp_user.get("email"):
                        ops.append(SCIMPatchOp("replace", "/email", idp_user.get("email")))
                    if existing.active != idp_user.get("active", True):
                        ops.append(SCIMPatchOp("replace", "/active", idp_user.get("active", True)))

                    if ops:
                        self.update_user(existing.id, ops)
                        result["updated"].append(existing.id)
                else:
                    # Create
                    user = self.create_user(
                        tenant_id,
                        idp_user["username"],
                        idp_user.get("given_name", ""),
                        idp_user.get("family_name", ""),
                        idp_user.get("email", ""),
                    )
                    result["created"].append(user.id)
            except Exception as e:
                result["errors"].append(f"Error syncing {idp_user.get('username')}: {e}")

        self.sync_log.append({
            "tenant_id": tenant_id,
            "timestamp": datetime.utcnow().isoformat(),
            "result": result,
        })

        return result

    def _find_user_by_username(self, tenant_id: str, username: str) -> Optional[SCIMUser]:
        """Find user by username."""
        for user in self.users.values():
            if user.tenant_id == tenant_id and user.user_name == username:
                return user
        return None

    def get_sync_log(self, tenant_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Get sync log entries."""
        return [
            entry for entry in self.sync_log
            if entry["tenant_id"] == tenant_id
        ][-limit:]


class TOTPGenerator:
    """Generate TOTP secrets for MFA."""

    @staticmethod
    def generate_secret() -> str:
        """Generate base32-encoded TOTP secret."""
        return secrets.token_urlsafe(32)

    @staticmethod
    def get_provisioning_uri(username: str, issuer: str, secret: str) -> str:
        """Get provisioning URI for QR code.

        Args:
            username: User email or username
            issuer: Issuer name (e.g., "Triage")
            secret: TOTP secret

        Returns:
            otpauth:// URI
        """
        return f"otpauth://totp/{issuer}:{username}?secret={secret}&issuer={issuer}"
