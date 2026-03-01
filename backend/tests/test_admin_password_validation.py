"""Tests for admin_password production validation in Settings."""
from __future__ import annotations

import os

import pytest
from pydantic import ValidationError


class TestAdminPasswordValidation:
    """Test that admin_password is validated in production mode."""

    def _build_settings(self, monkeypatch, **overrides):
        """
        Construct a fresh Settings instance with controlled env vars.

        Sets production-ready defaults that pass all existing validators,
        then applies any caller overrides.
        """
        # Clear any cached settings / module-level singleton
        from app.core import config as config_module
        config_module.get_settings.cache_clear()

        # Base production-ready env vars
        prod_env = {
            "NAS_MODE": "prod",
            "SECRET_KEY": "a" * 64,
            "TOKEN_SECRET": "b" * 64,
            "ADMIN_PASSWORD": "MyStr0ngAdm1nPass!",
            "DATABASE_URL": "postgresql://u:p@localhost/db",
            "ENVIRONMENT": "production",
        }
        prod_env.update(overrides)

        for key, value in prod_env.items():
            monkeypatch.setenv(key, value)

        # Remove SKIP_APP_INIT and PYTEST_CURRENT_TEST so production
        # validators actually fire.
        monkeypatch.delenv("SKIP_APP_INIT", raising=False)
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

        from app.core.config import Settings
        return Settings()

    def test_production_rejects_default_admin_password(self, monkeypatch):
        """Production mode must reject the default 'DevMode2024' password."""
        with pytest.raises(ValidationError, match="ADMIN_PASSWORD must be changed from default"):
            self._build_settings(monkeypatch, ADMIN_PASSWORD="DevMode2024")

    def test_production_rejects_short_admin_password(self, monkeypatch):
        """Production mode must reject admin passwords shorter than 12 characters."""
        with pytest.raises(ValidationError, match="at least 12 characters"):
            self._build_settings(monkeypatch, ADMIN_PASSWORD="Short1!")

    def test_production_accepts_strong_admin_password(self, monkeypatch):
        """Production mode should accept a strong admin password."""
        settings = self._build_settings(monkeypatch, ADMIN_PASSWORD="MyStr0ngAdm1nPass!")
        assert settings.admin_password == "MyStr0ngAdm1nPass!"

    def test_production_accepts_exactly_12_char_password(self, monkeypatch):
        """Production mode should accept a password with exactly 12 characters."""
        password = "Abcdefgh1234"
        assert len(password) == 12
        settings = self._build_settings(monkeypatch, ADMIN_PASSWORD=password)
        assert settings.admin_password == password

    def test_production_rejects_11_char_password(self, monkeypatch):
        """Production mode must reject a password with only 11 characters."""
        password = "Abcdefgh123"
        assert len(password) == 11
        with pytest.raises(ValidationError, match="at least 12 characters"):
            self._build_settings(monkeypatch, ADMIN_PASSWORD=password)

    def test_dev_mode_accepts_default_password(self, monkeypatch):
        """Dev mode should accept the default 'DevMode2024' password without error."""
        settings = self._build_settings(monkeypatch, NAS_MODE="dev", ADMIN_PASSWORD="DevMode2024")
        assert settings.admin_password == "DevMode2024"

    def test_dev_mode_accepts_short_password(self, monkeypatch):
        """Dev mode should accept any password, even short ones."""
        settings = self._build_settings(monkeypatch, NAS_MODE="dev", ADMIN_PASSWORD="abc")
        assert settings.admin_password == "abc"

    def test_validation_skipped_during_testing(self, monkeypatch):
        """When SKIP_APP_INIT=1 is set (test environment), validation should be skipped."""
        # Re-set SKIP_APP_INIT (our _build_settings removes it)
        from app.core import config as config_module
        config_module.get_settings.cache_clear()

        monkeypatch.setenv("NAS_MODE", "prod")
        monkeypatch.setenv("SECRET_KEY", "a" * 64)
        monkeypatch.setenv("TOKEN_SECRET", "b" * 64)
        monkeypatch.setenv("ADMIN_PASSWORD", "DevMode2024")
        monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost/db")
        monkeypatch.setenv("SKIP_APP_INIT", "1")

        from app.core.config import Settings
        # Should NOT raise because SKIP_APP_INIT=1 bypasses validation
        settings = Settings()
        assert settings.admin_password == "DevMode2024"
