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


def test_plugin_sandbox_settings_defaults():
    s = Settings(environment="development", nas_mode="dev")
    assert s.plugin_sandbox_user == "baluhost-plugin"
    assert s.plugin_sandbox_wrapper_path == "/opt/baluhost/deploy/bin/spawn-plugin-worker.sh"


def test_plugin_sandbox_settings_overridable():
    s = Settings(
        environment="development",
        nas_mode="dev",
        plugin_sandbox_user="custom-plugin-user",
        plugin_sandbox_wrapper_path="/tmp/wrapper.sh",
    )
    assert s.plugin_sandbox_user == "custom-plugin-user"
    assert s.plugin_sandbox_wrapper_path == "/tmp/wrapper.sh"
