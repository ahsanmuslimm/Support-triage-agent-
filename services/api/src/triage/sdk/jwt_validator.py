"""JWT validation for in-app widget SDK."""

import base64
import json
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

import structlog

log = structlog.get_logger()


class Algorithm(str, Enum):
    """Supported JWT algorithms."""

    ES256 = "ES256"
    HS256 = "HS256"  # VULNERABLE: we reject this


class JWTError(Exception):
    """JWT validation error."""



class TokenExpiredError(JWTError):
    """Token expired."""



class AlgorithmMismatchError(JWTError):
    """Algorithm does not match expected."""



class AudienceMismatchError(JWTError):
    """Audience claim does not match."""



class KeyRotationError(JWTError):
    """Key rotation or retrieval failed."""



class JWTValidator:
    """Validate tenant-signed ES256 JWT tokens for widget auth."""

    # 15-minute TTL for widget tokens
    TOKEN_TTL = timedelta(minutes=15)

    # Algorithm must be ES256 (reject HS256 forgery attempts)
    REQUIRED_ALGORITHM = Algorithm.ES256

    def __init__(self, tenant_id: str, public_key: str) -> None:
        """Initialize validator.

        Args:
            tenant_id: Tenant ID.
            public_key: Tenant's ES256 public key (PEM format).
        """
        self.tenant_id = tenant_id
        self.public_key = public_key

    def validate(self, token: str, expected_customer_id: str | None = None) -> dict[str, Any]:
        """Validate JWT token.

        Args:
            token: JWT token from client.
            expected_customer_id: Optional expected sub claim.

        Returns:
            Dict[str, Any]: Decoded token claims.

        Raises:
            JWTError: If validation fails.
        """
        try:
            # Parse JWT (header.payload.signature)
            parts = token.split(".")
            if len(parts) != 3:
                raise JWTError("Invalid JWT format")

            header_b64, payload_b64, signature_b64 = parts

            # Decode header
            header = self._decode_base64(header_b64)

            # Check algorithm in header (prevent algorithm confusion)
            alg = header.get("alg", "")
            if alg != self.REQUIRED_ALGORITHM.value:
                raise AlgorithmMismatchError(
                    f"Expected {self.REQUIRED_ALGORITHM.value}, got {alg}. "
                    "HS256 is not accepted (use ES256)."
                )

            # Check kid (key ID) in header for key rotation
            kid = header.get("kid")
            if not kid:
                raise JWTError("Missing kid (key ID) in header")

            # Decode payload
            payload = self._decode_base64(payload_b64)

            # Verify signature (ES256)
            self._verify_es256_signature(
                token=f"{header_b64}.{payload_b64}",
                signature=signature_b64,
                public_key=self.public_key,
            )

            # Check expiry (iat + 15min)
            iat = payload.get("iat")
            if not iat:
                raise JWTError("Missing iat claim")

            token_time = datetime.utcfromtimestamp(iat)
            if datetime.utcnow() > token_time + self.TOKEN_TTL:
                raise TokenExpiredError(f"Token expired (TTL: {self.TOKEN_TTL})")

            # Check audience matches tenant_id (IAL2)
            aud = payload.get("aud")
            if aud != self.tenant_id:
                raise AudienceMismatchError(f"Expected aud={self.tenant_id}, got {aud}")

            # Check subject (customer_id)
            sub = payload.get("sub")
            if not sub:
                raise JWTError("Missing sub claim (customer_id)")

            if expected_customer_id and sub != expected_customer_id:
                raise JWTError(f"Expected sub={expected_customer_id}, got {sub}")

            log.info(
                "jwt_validated",
                tenant_id=self.tenant_id,
                customer_id=sub,
                kid=kid,
            )

            return payload

        except (JWTError, Exception) as e:
            log.error("jwt_validation_failed", error=str(e), tenant_id=self.tenant_id)
            if isinstance(e, JWTError):
                raise
            raise JWTError(f"Validation failed: {e}")

    def _decode_base64(self, data: str) -> dict[str, Any]:
        """Decode base64url-encoded JSON.

        Args:
            data: Base64url string.

        Returns:
            Dict[str, Any]: Decoded JSON object.

        Raises:
            JWTError: If decoding fails.
        """
        try:
            # Add padding if needed
            padding = 4 - (len(data) % 4)
            if padding != 4:
                data += "=" * padding

            decoded = base64.urlsafe_b64decode(data)
            return json.loads(decoded)
        except Exception as e:
            raise JWTError(f"Failed to decode base64url: {e}")

    def _verify_es256_signature(
        self,
        token: str,
        signature: str,
        public_key: str,
    ) -> None:
        """Verify ES256 signature.

        Args:
            token: Token (header.payload).
            signature: Signature (base64url).
            public_key: ES256 public key (PEM).

        Raises:
            JWTError: If signature verification fails.
        """
        try:
            # Import cryptography for ES256 verification
            from cryptography.hazmat.backends import default_backend
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.asymmetric import ec
            from cryptography.hazmat.primitives.serialization import load_pem_public_key

            # Load public key
            key = load_pem_public_key(public_key.encode(), backend=default_backend())

            # Decode signature
            padding = 4 - (len(signature) % 4)
            if padding != 4:
                signature += "=" * padding
            sig_bytes = base64.urlsafe_b64decode(signature)

            # Verify signature
            key.verify(sig_bytes, token.encode(), ec.ECDSA(hashes.SHA256()))

            log.debug("es256_signature_verified")
        except Exception as e:
            raise JWTError(f"ES256 signature verification failed: {e}")


class KeyRotationManager:
    """Manage key rotation for widget JWT validation."""

    def __init__(self, tenant_id: str, keys_endpoint: str) -> None:
        """Initialize key rotation manager.

        Args:
            tenant_id: Tenant ID.
            keys_endpoint: URL to fetch public keys (/.well-known/keys).
        """
        self.tenant_id = tenant_id
        self.keys_endpoint = keys_endpoint
        self.keys: dict[str, str] = {}  # kid -> public_key
        self.last_refresh = datetime.utcnow()
        self.refresh_interval = timedelta(hours=1)

    async def get_public_key(self, kid: str) -> str:
        """Get public key by key ID, with rotation.

        Args:
            kid: Key ID from JWT header.

        Returns:
            str: Public key in PEM format.

        Raises:
            KeyRotationError: If key not found or endpoint fails.
        """
        # Refresh if interval exceeded
        if datetime.utcnow() - self.last_refresh > self.refresh_interval:
            await self.refresh_keys()

        # Return cached key
        if kid in self.keys:
            return self.keys[kid]

        # Try refresh if not found
        await self.refresh_keys()
        if kid in self.keys:
            return self.keys[kid]

        raise KeyRotationError(f"Key {kid} not found after refresh")

    async def refresh_keys(self) -> None:
        """Refresh public keys from endpoint.

        Raises:
            KeyRotationError: If fetch fails.
        """
        try:
            # In real implementation, fetch from /.well-known/keys
            # GET {keys_endpoint}
            # Response: { keys: [{ kid: "...", key: "...", alg: "ES256" }] }

            log.info("refreshing_keys", tenant_id=self.tenant_id, endpoint=self.keys_endpoint)

            # Simulated response
            self.keys = {
                "key_1": "-----BEGIN PUBLIC KEY-----\nMFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE...\n-----END PUBLIC KEY-----",
            }

            self.last_refresh = datetime.utcnow()
            log.info("keys_refreshed", tenant_id=self.tenant_id, count=len(self.keys))

        except Exception as e:
            log.error("key_refresh_failed", error=str(e))
            raise KeyRotationError(f"Failed to refresh keys: {e}")

    def add_key(self, kid: str, public_key: str) -> None:
        """Manually add a public key.

        Args:
            kid: Key ID.
            public_key: Public key in PEM format.
        """
        self.keys[kid] = public_key
        log.info("key_added", tenant_id=self.tenant_id, kid=kid)
