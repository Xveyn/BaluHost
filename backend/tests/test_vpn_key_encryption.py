"""Tests for VPN key encryption at rest.

Verifies that:
- server_private_key is encrypted before being stored in VPNConfig
- preshared_key is encrypted before being stored in VPNClient
- Config generation still produces correct WireGuard configs (decrypt works)
- Encryption is conditional on VPN_ENCRYPTION_KEY availability
"""

import base64
import os
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from sqlalchemy.orm import Session

from app.models.vpn import VPNConfig, VPNClient
from app.services.vpn.service import VPNService
from app.services.vpn.encryption import VPNEncryption


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_fernet_token(value: str) -> bool:
    """Return True if *value* looks like a Fernet-encrypted token."""
    # Fernet tokens are URL-safe base64 strings starting with 'gAAAAA'
    return value.startswith("gAAAAA")


def _is_base64_key(value: str) -> bool:
    """Return True if *value* looks like a raw WireGuard base64 key (44 chars)."""
    try:
        decoded = base64.b64decode(value)
        return len(decoded) == 32
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Tests — encryption active (VPN_ENCRYPTION_KEY set)
# ---------------------------------------------------------------------------

class TestVPNKeyEncryptionActive:
    """Tests when VPN_ENCRYPTION_KEY is set (should encrypt)."""

    def test_server_private_key_encrypted_in_db(self, db_session: Session):
        """After creating a VPN config, the stored server_private_key should be encrypted."""
        config_response = VPNService.create_client_config(
            db=db_session,
            user_id=1,
            device_name="TestDevice",
            server_public_endpoint="vpn.example.com",
        )

        # Fetch the VPNConfig directly from DB
        server_config = db_session.query(VPNConfig).first()
        assert server_config is not None

        stored_key = server_config.server_private_key
        # The stored value must be a Fernet token, not a raw base64 key
        assert _is_fernet_token(stored_key), (
            f"server_private_key should be Fernet-encrypted, got: {stored_key[:40]}..."
        )
        assert not _is_base64_key(stored_key), (
            "server_private_key should NOT look like a raw WireGuard key"
        )

    def test_preshared_key_encrypted_in_db(self, db_session: Session):
        """After creating a VPN client, the stored preshared_key should be encrypted."""
        config_response = VPNService.create_client_config(
            db=db_session,
            user_id=1,
            device_name="TestDevice",
            server_public_endpoint="vpn.example.com",
        )

        client = db_session.query(VPNClient).first()
        assert client is not None

        stored_psk = client.preshared_key
        assert _is_fernet_token(stored_psk), (
            f"preshared_key should be Fernet-encrypted, got: {stored_psk[:40]}..."
        )
        assert not _is_base64_key(stored_psk), (
            "preshared_key should NOT look like a raw WireGuard key"
        )

    def test_config_content_contains_plaintext_keys(self, db_session: Session):
        """The generated WireGuard config content should contain plaintext keys, not encrypted."""
        config_response = VPNService.create_client_config(
            db=db_session,
            user_id=1,
            device_name="TestDevice",
            server_public_endpoint="vpn.example.com",
        )

        config_text = config_response.config_content

        # Config should contain [Interface] and [Peer] sections
        assert "[Interface]" in config_text
        assert "[Peer]" in config_text

        # Extract PrivateKey and PresharedKey from config
        private_key_line = [
            l for l in config_text.splitlines() if l.strip().startswith("PrivateKey")
        ]
        psk_line = [
            l for l in config_text.splitlines() if l.strip().startswith("PresharedKey")
        ]
        assert len(private_key_line) == 1, "Should have exactly one PrivateKey line"
        assert len(psk_line) == 1, "Should have exactly one PresharedKey line"

        private_key_value = private_key_line[0].split("=", 1)[1].strip()
        psk_value = psk_line[0].split("=", 1)[1].strip()

        # These should be raw base64 keys, NOT Fernet tokens
        assert _is_base64_key(private_key_value), (
            f"Config PrivateKey should be a raw base64 key, got: {private_key_value[:40]}"
        )
        assert _is_base64_key(psk_value), (
            f"Config PresharedKey should be a raw base64 key, got: {psk_value[:40]}"
        )
        assert not _is_fernet_token(private_key_value), (
            "Config PrivateKey should NOT be Fernet-encrypted"
        )
        assert not _is_fernet_token(psk_value), (
            "Config PresharedKey should NOT be Fernet-encrypted"
        )

    def test_encrypted_key_can_be_decrypted(self, db_session: Session):
        """Encrypted keys stored in DB can be decrypted back to valid WireGuard keys."""
        VPNService.create_client_config(
            db=db_session,
            user_id=1,
            device_name="DecryptTest",
            server_public_endpoint="vpn.example.com",
        )

        server_config = db_session.query(VPNConfig).first()
        client = db_session.query(VPNClient).first()

        # Decrypt and verify they're valid base64 keys
        decrypted_server_key = VPNService._decrypt_key(server_config.server_private_key)
        decrypted_psk = VPNService._decrypt_key(client.preshared_key)

        assert _is_base64_key(decrypted_server_key), (
            "Decrypted server_private_key should be a valid base64 key"
        )
        assert _is_base64_key(decrypted_psk), (
            "Decrypted preshared_key should be a valid base64 key"
        )

    def test_multiple_clients_have_different_encrypted_keys(self, db_session: Session):
        """Each client should have a uniquely encrypted preshared key."""
        VPNService.create_client_config(
            db=db_session,
            user_id=1,
            device_name="Device1",
            server_public_endpoint="vpn.example.com",
        )
        VPNService.create_client_config(
            db=db_session,
            user_id=1,
            device_name="Device2",
            server_public_endpoint="vpn.example.com",
        )

        clients = db_session.query(VPNClient).all()
        assert len(clients) == 2

        # Different plaintext keys => different encrypted values
        # (Fernet also uses random IV, so even same plaintext would differ)
        assert clients[0].preshared_key != clients[1].preshared_key

    def test_server_config_reused_not_recreated(self, db_session: Session):
        """Creating a second client should reuse the existing server config."""
        VPNService.create_client_config(
            db=db_session,
            user_id=1,
            device_name="Device1",
            server_public_endpoint="vpn.example.com",
        )
        first_config = db_session.query(VPNConfig).first()

        VPNService.create_client_config(
            db=db_session,
            user_id=1,
            device_name="Device2",
            server_public_endpoint="vpn.example.com",
        )

        configs = db_session.query(VPNConfig).all()
        assert len(configs) == 1, "Should reuse existing server config"
        assert configs[0].id == first_config.id


# ---------------------------------------------------------------------------
# Tests — encryption not available (VPN_ENCRYPTION_KEY empty)
# ---------------------------------------------------------------------------

class TestVPNKeyEncryptionDisabled:
    """Tests when VPN_ENCRYPTION_KEY is not set (fallback to plaintext)."""

    def test_keys_stored_as_plaintext_without_encryption_key(self, db_session: Session):
        """Without VPN_ENCRYPTION_KEY, keys should be stored as plaintext."""
        with patch.object(
            VPNService, '_encryption_available',
            staticmethod(lambda: False),
        ):
            config_response = VPNService.create_client_config(
                db=db_session,
                user_id=1,
                device_name="NoEncDevice",
                server_public_endpoint="vpn.example.com",
            )

            server_config = db_session.query(VPNConfig).first()
            client = db_session.query(VPNClient).first()

            # Should be raw base64 keys, not Fernet tokens
            assert _is_base64_key(server_config.server_private_key), (
                "Without encryption, server_private_key should be a raw base64 key"
            )
            assert _is_base64_key(client.preshared_key), (
                "Without encryption, preshared_key should be a raw base64 key"
            )
            assert not _is_fernet_token(server_config.server_private_key)
            assert not _is_fernet_token(client.preshared_key)

    def test_decrypt_handles_plaintext_gracefully(self, db_session: Session):
        """_decrypt_key should return plaintext values unchanged when encryption is off."""
        raw_key = base64.b64encode(os.urandom(32)).decode()

        with patch.object(
            VPNService, '_encryption_available',
            staticmethod(lambda: False),
        ):
            result = VPNService._decrypt_key(raw_key)
            assert result == raw_key

    def test_decrypt_handles_legacy_plaintext_with_encryption_on(self):
        """When encryption is on but value is legacy plaintext, _decrypt_key returns it as-is."""
        raw_key = base64.b64encode(os.urandom(32)).decode()

        # With encryption available, decrypting a non-Fernet value should
        # gracefully return the original value (legacy plaintext)
        result = VPNService._decrypt_key(raw_key)
        assert result == raw_key


# ---------------------------------------------------------------------------
# Tests — helper methods
# ---------------------------------------------------------------------------

class TestVPNEncryptionHelpers:
    """Tests for the _encrypt_key / _decrypt_key helper methods."""

    def test_encrypt_decrypt_roundtrip(self):
        """Encrypting then decrypting should return the original key."""
        original = base64.b64encode(os.urandom(32)).decode()
        encrypted = VPNService._encrypt_key(original)
        decrypted = VPNService._decrypt_key(encrypted)
        assert decrypted == original

    def test_encrypt_produces_fernet_token(self):
        """_encrypt_key should produce a Fernet token."""
        original = base64.b64encode(os.urandom(32)).decode()
        encrypted = VPNService._encrypt_key(original)
        assert _is_fernet_token(encrypted)

    def test_decrypt_empty_string_returns_empty(self):
        """_decrypt_key should handle empty string gracefully."""
        assert VPNService._decrypt_key("") == ""

    def test_encryption_available_reflects_setting(self):
        """_encryption_available should return True when key is set."""
        # conftest.py sets VPN_ENCRYPTION_KEY for tests
        assert VPNService._encryption_available() is True
