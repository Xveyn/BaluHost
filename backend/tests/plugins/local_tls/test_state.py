"""Tests fuer die Zugriffsschicht der Tabelle local_tls_state."""
from datetime import datetime, timezone

import pytest
from cryptography.fernet import Fernet

from app.core.config import settings
from app.models.local_tls_state import LocalTlsState
from app.plugins.installed.local_tls import state
from app.services.audit.admin_db import REDACT_PATTERN

NOW = datetime(2026, 11, 25, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def key(monkeypatch):
    monkeypatch.setattr(settings, "vpn_encryption_key", Fernet.generate_key().decode())


def test_get_state_creates_single_row(db_session):
    a = state.get_state(db_session)
    b = state.get_state(db_session)
    assert a.id == b.id
    assert db_session.query(LocalTlsState).count() == 1


def test_token_is_stored_encrypted(db_session, key):
    state.set_token(db_session, "geheim-token")
    raw = state.get_state(db_session).provider_secret
    assert raw and raw != "geheim-token"
    assert "geheim-token" not in raw
    assert state.get_token(db_session) == "geheim-token"
    assert state.has_token(db_session) is True


def test_set_token_without_key_refuses(db_session, monkeypatch):
    monkeypatch.setattr(settings, "vpn_encryption_key", "")
    with pytest.raises(ValueError, match="encryption key missing"):
        state.set_token(db_session, "geheim-token")
    assert state.get_state(db_session).provider_secret is None
    assert state.has_token(db_session) is False


def test_clear_token(db_session, key):
    state.set_token(db_session, "t")
    state.clear_token(db_session)
    assert state.get_token(db_session) is None
    assert state.has_token(db_session) is False


def test_record_ip_and_renew_roundtrip(db_session):
    state.record_ip(db_session, "192.168.1.5", NOW)
    state.record_renew(db_session, True, None, "ab" * 32, NOW, NOW)
    s = state.get_state(db_session)
    assert s.last_ip == "192.168.1.5"
    assert s.last_ip_set_at is not None
    assert s.last_renew_ok is True
    assert s.last_renew_reason is None
    assert s.cert_fingerprint == "ab" * 32
    assert s.cert_not_after is not None
    state.record_renew(db_session, False, "x" * 600, None, None, NOW)
    s = state.get_state(db_session)
    assert s.last_renew_ok is False
    assert len(s.last_renew_reason) <= 500


def test_provider_secret_matches_redact_pattern():
    assert REDACT_PATTERN.search("provider_secret")
