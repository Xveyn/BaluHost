import pytest
from app.core.config import Settings


def test_dev_mode_in_production_environment_is_rejected():
    """environment=production together with NAS_MODE=dev must fail fast.

    The new validator reads the INSTANCE fields (self.environment,
    self.is_dev_mode), so the nas_mode="dev" kwarg genuinely trips it.
    """
    with pytest.raises(ValueError, match="not allowed when ENVIRONMENT=production"):
        Settings(environment="production", nas_mode="dev")


def test_prod_mode_in_production_environment_is_allowed():
    # NOTE: the existing SECRET_KEY/token_secret/admin_password validators detect
    # prod via os.getenv("NAS_MODE") and are skipped under pytest (conftest sets
    # NAS_MODE=dev + SKIP_APP_INIT=1), so this constructs fine without strong
    # secrets. The new validator reads instance fields and does NOT fire here
    # (is_dev_mode is False for nas_mode="prod").
    s = Settings(environment="production", nas_mode="prod")
    assert s.is_dev_mode is False


def test_dev_mode_in_development_environment_is_allowed():
    s = Settings(environment="development", nas_mode="dev")
    assert s.is_dev_mode is True
