"""Tests for S10.6 - SCIM Provisioning."""


import pytest
from triage.identity.scim import (
    SCIMPatchOp,
    SCIMProvisioner,
    SCIMUser,
    TOTPGenerator,
)


class TestSCIMUserModel:
    """Test SCIM User model."""

    def test_create_user_model(self):
        """Test creating SCIMUser."""
        user = SCIMUser(
            id="user_123",
            tenant_id="tenant_1",
            user_name="alice@example.com",
            given_name="Alice",
            family_name="Johnson",
            email="alice@example.com",
        )

        assert user.id == "user_123"
        assert user.active
        assert not user.mfa_enabled

    def test_user_to_scim_dict(self):
        """Test converting user to SCIM representation."""
        user = SCIMUser(
            id="user_456",
            tenant_id="tenant_1",
            user_name="bob@example.com",
            given_name="Bob",
            family_name="Smith",
            email="bob@example.com",
        )

        scim_dict = user.to_scim_dict()

        assert scim_dict["id"] == "user_456"
        assert scim_dict["userName"] == "bob@example.com"
        assert scim_dict["name"]["givenName"] == "Bob"
        assert scim_dict["active"] is True
        assert "schemas" in scim_dict


class TestSCIMProvisioner:
    """Test SCIM provisioning."""

    def test_create_user(self):
        """Test creating user via SCIM."""
        provisioner = SCIMProvisioner(test_mode=True)

        user = provisioner.create_user(
            tenant_id="tenant_1",
            user_name="carol@example.com",
            given_name="Carol",
            family_name="Davis",
            email="carol@example.com",
        )

        assert user.user_name == "carol@example.com"
        assert user.active

    def test_create_user_with_mfa(self):
        """Test creating user with MFA enabled."""
        provisioner = SCIMProvisioner(test_mode=True)

        user = provisioner.create_user(
            tenant_id="tenant_1",
            user_name="david@example.com",
            given_name="David",
            family_name="Wilson",
            email="david@example.com",
            mfa_required=True,
        )

        assert user.mfa_enabled
        assert user.mfa_secret is not None

    def test_get_user(self):
        """Test retrieving user."""
        provisioner = SCIMProvisioner(test_mode=True)

        created = provisioner.create_user(
            tenant_id="tenant_1",
            user_name="eve@example.com",
            given_name="Eve",
            family_name="Martinez",
            email="eve@example.com",
        )

        retrieved = provisioner.get_user(created.id)

        assert retrieved is not None
        assert retrieved.user_name == "eve@example.com"

    def test_update_user(self):
        """Test updating user."""
        provisioner = SCIMProvisioner(test_mode=True)

        user = provisioner.create_user(
            tenant_id="tenant_1",
            user_name="frank@example.com",
            given_name="Frank",
            family_name="Brown",
            email="frank@example.com",
        )

        ops = [SCIMPatchOp("replace", "/active", False)]
        updated = provisioner.update_user(user.id, ops)

        assert not updated.active

    @pytest.mark.asyncio
    async def test_deprovision_user(self):
        """Test deprovisioning user."""
        provisioner = SCIMProvisioner(test_mode=True)

        user = provisioner.create_user(
            tenant_id="tenant_1",
            user_name="grace@example.com",
            given_name="Grace",
            family_name="Lee",
            email="grace@example.com",
        )

        success = await provisioner.deprovision_user(user.id)

        assert success

    @pytest.mark.asyncio
    async def test_sync_with_idp(self):
        """Test syncing with external IDP."""
        provisioner = SCIMProvisioner(test_mode=True)

        idp_users = [
            {
                "username": "henry@example.com",
                "given_name": "Henry",
                "family_name": "Taylor",
                "email": "henry@example.com",
                "active": True,
            },
            {
                "username": "iris@example.com",
                "given_name": "Iris",
                "family_name": "Anderson",
                "email": "iris@example.com",
                "active": True,
            },
        ]

        result = await provisioner.sync_with_idp("tenant_1", idp_users)

        assert result["created"]
        assert len(result["created"]) == 2
        assert len(result["errors"]) == 0

    @pytest.mark.asyncio
    async def test_sync_update_existing(self):
        """Test sync updating existing users."""
        provisioner = SCIMProvisioner(test_mode=True)

        # Create user
        provisioner.create_user(
            tenant_id="tenant_1",
            user_name="jack@example.com",
            given_name="Jack",
            family_name="Moore",
            email="jack@example.com",
        )

        # Sync with updated info
        idp_users = [
            {
                "username": "jack@example.com",
                "given_name": "Jack",
                "family_name": "Moore",
                "email": "jack.new@example.com",
                "active": True,
            }
        ]

        result = await provisioner.sync_with_idp("tenant_1", idp_users)

        assert len(result["updated"]) > 0


class TestTOTPGenerator:
    """Test TOTP secret generation."""

    def test_generate_secret(self):
        """Test generating TOTP secret."""
        secret = TOTPGenerator.generate_secret()

        assert isinstance(secret, str)
        assert len(secret) > 0

    def test_get_provisioning_uri(self):
        """Test getting provisioning URI."""
        secret = TOTPGenerator.generate_secret()
        uri = TOTPGenerator.get_provisioning_uri("alice@example.com", "Triage", secret)

        assert uri.startswith("otpauth://totp/")
        assert "Triage:alice@example.com" in uri
        assert secret in uri
