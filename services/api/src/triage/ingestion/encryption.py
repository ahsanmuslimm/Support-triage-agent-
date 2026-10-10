"""Envelope encryption for message bodies."""

import os
import json
from typing import Optional, Dict, Any
from cryptography.fernet import Fernet, InvalidToken


class EnvelopeEncryption:
    """Encrypts and decrypts message bodies using Fernet (AES-128-CBC)."""

    def __init__(self, master_key: Optional[str] = None):
        """Initialize with master key (Fernet format, base64-encoded).

        Args:
            master_key: Base64-encoded Fernet key. If None, loads from ENCRYPTION_KEY env var.
        """
        if master_key is None:
            master_key = os.environ.get("ENCRYPTION_KEY")
            if not master_key:
                raise ValueError(
                    "ENCRYPTION_KEY environment variable or master_key parameter required"
                )

        try:
            self.cipher = Fernet(master_key.encode() if isinstance(master_key, str) else master_key)
        except Exception as e:
            raise ValueError(f"Invalid encryption key: {e}")

        self.dek_version = 1  # Data Encryption Key version

    def encrypt(self, plaintext: str) -> Dict[str, Any]:
        """Encrypt plaintext and return ciphertext with metadata.

        Args:
            plaintext: Text to encrypt

        Returns:
            {
                "ciphertext": base64-encoded encrypted bytes,
                "dek_version": version of key used,
                "algorithm": "fernet"
            }
        """
        try:
            ciphertext = self.cipher.encrypt(plaintext.encode("utf-8"))
            return {
                "ciphertext": ciphertext.decode("utf-8"),
                "dek_version": self.dek_version,
                "algorithm": "fernet",
            }
        except Exception as e:
            raise RuntimeError(f"Encryption failed: {e}")

    def decrypt(self, ciphertext: str, dek_version: int = 1) -> str:
        """Decrypt ciphertext to plaintext.

        Args:
            ciphertext: Base64-encoded encrypted bytes
            dek_version: Version of DEK used (for key rotation)

        Returns:
            Decrypted plaintext

        Raises:
            InvalidToken: If decryption fails (wrong key, corrupted data)
        """
        try:
            plaintext = self.cipher.decrypt(ciphertext.encode("utf-8"))
            return plaintext.decode("utf-8")
        except InvalidToken as e:
            raise RuntimeError(f"Decryption failed (invalid key or corrupted data): {e}")
        except Exception as e:
            raise RuntimeError(f"Decryption failed: {e}")
