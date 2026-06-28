"""Tests for the external-plugin scope catalog (Phase 5b)."""
from app.plugins.scope_catalog import SCOPE_CATALOG, CATALOG_KEYS, ScopeInfo
from app.plugins.sandbox.capabilities import CAPABILITY_SCOPE


def test_catalog_has_six_entries():
    assert len(SCOPE_CATALOG) == 6


def test_frontend_tier_keys_are_the_three_sdk_scopes():
    fe = {s.key for s in SCOPE_CATALOG if s.tier == "frontend"}
    assert fe == {"read:system-info", "read:storage", "read:power"}


def test_backend_tier_keys_derived_from_capability_scope_no_drift():
    be = {s.key for s in SCOPE_CATALOG if s.tier == "backend"}
    assert be == set(CAPABILITY_SCOPE.values())


def test_every_entry_is_structural_and_not_dangerous():
    for s in SCOPE_CATALOG:
        assert isinstance(s, ScopeInfo)
        assert s.tier in ("frontend", "backend")
        assert s.dangerous is False


def test_catalog_keys_matches_entry_keys():
    assert CATALOG_KEYS == frozenset(s.key for s in SCOPE_CATALOG)
