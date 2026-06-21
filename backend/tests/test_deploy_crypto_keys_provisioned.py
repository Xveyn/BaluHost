"""New installs must provision dedicated CLOUD/TOTP encryption keys (Posten 3)."""
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_TEMPLATE = _REPO / "deploy" / "install" / "templates" / "env.production"
_MODULE07 = _REPO / "deploy" / "install" / "modules" / "07-env-generate.sh"
_CONFIG_SH = _REPO / "deploy" / "install" / "lib" / "config.sh"


def test_env_template_has_cloud_and_totp_placeholders():
    text = _TEMPLATE.read_text(encoding="utf-8")
    assert "CLOUD_ENCRYPTION_KEY=@@CLOUD_ENCRYPTION_KEY@@" in text
    assert "TOTP_ENCRYPTION_KEY=@@TOTP_ENCRYPTION_KEY@@" in text


def test_module07_generates_both_keys():
    text = _MODULE07.read_text(encoding="utf-8")
    assert "CLOUD_ENCRYPTION_KEY=$(generate_fernet_key)" in text
    assert "TOTP_ENCRYPTION_KEY=$(generate_fernet_key)" in text


def test_module07_renders_both_keys_into_env():
    """Both keys must reach process_template, else the @@…@@ placeholder check aborts the install."""
    text = _MODULE07.read_text(encoding="utf-8")
    assert '"CLOUD_ENCRYPTION_KEY=$CLOUD_ENCRYPTION_KEY"' in text
    assert '"TOTP_ENCRYPTION_KEY=$TOTP_ENCRYPTION_KEY"' in text


def test_config_sh_persists_both_keys():
    """save_config uses a fixed allowlist — both keys must be in it, or a resumed install
    regenerates new keys and breaks existing ciphertext."""
    text = _CONFIG_SH.read_text(encoding="utf-8")
    assert "CLOUD_ENCRYPTION_KEY" in text
    assert "TOTP_ENCRYPTION_KEY" in text
