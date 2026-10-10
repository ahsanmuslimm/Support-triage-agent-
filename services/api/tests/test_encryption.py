"""Tests for envelope encryption."""

import pytest
from cryptography.fernet import Fernet

from triage.ingestion.encryption import EnvelopeEncryption


@pytest.fixture
def encryption_key():
    """Generate test encryption key."""
    return Fernet.generate_key().decode("utf-8")


def test_encrypt_decrypt_roundtrip(encryption_key):
    """Test encrypt and decrypt roundtrip."""
    cipher = EnvelopeEncryption(encryption_key)

    plaintext = "Hello World"
    encrypted = cipher.encrypt(plaintext)

    assert "ciphertext" in encrypted
    assert "dek_version" in encrypted
    assert encrypted["algorithm"] == "fernet"
    assert encrypted["dek_version"] == 1

    decrypted = cipher.decrypt(encrypted["ciphertext"])
    assert decrypted == plaintext


def test_encrypt_different_messages_different_ciphertexts(encryption_key):
    """Test that same plaintext produces different ciphertexts (due to IV)."""
    cipher = EnvelopeEncryption(encryption_key)

    plaintext = "Hello World"
    encrypted1 = cipher.encrypt(plaintext)
    encrypted2 = cipher.encrypt(plaintext)

    # Ciphertexts should be different (Fernet uses IV)
    assert encrypted1["ciphertext"] != encrypted2["ciphertext"]

    # But both should decrypt to same plaintext
    assert cipher.decrypt(encrypted1["ciphertext"]) == plaintext
    assert cipher.decrypt(encrypted2["ciphertext"]) == plaintext


def test_decrypt_invalid_key():
    """Test decryption with wrong key fails."""
    key1 = Fernet.generate_key().decode("utf-8")
    key2 = Fernet.generate_key().decode("utf-8")

    cipher1 = EnvelopeEncryption(key1)
    cipher2 = EnvelopeEncryption(key2)

    ciphertext = cipher1.encrypt("Secret data")["ciphertext"]

    with pytest.raises(RuntimeError):
        cipher2.decrypt(ciphertext)


def test_invalid_encryption_key():
    """Test initialization with invalid key."""
    with pytest.raises(ValueError):
        EnvelopeEncryption("invalid-key-not-base64")


def test_no_key_env_var_required():
    """Test that missing key raises error."""
    import os
    os.environ.pop("ENCRYPTION_KEY", None)

    with pytest.raises(ValueError):
        EnvelopeEncryption()


def test_encrypt_empty_string(encryption_key):
    """Test encryption of empty string."""
    cipher = EnvelopeEncryption(encryption_key)

    encrypted = cipher.encrypt("")
    decrypted = cipher.decrypt(encrypted["ciphertext"])

    assert decrypted == ""


def test_encrypt_large_text(encryption_key):
    """Test encryption of large text."""
    cipher = EnvelopeEncryption(encryption_key)

    plaintext = "x" * 100_000
    encrypted = cipher.encrypt(plaintext)
    decrypted = cipher.decrypt(encrypted["ciphertext"])

    assert decrypted == plaintext
