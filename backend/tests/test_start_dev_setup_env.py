"""Regression tests for start_dev.py's SKIP_SETUP environment handling.

The dev launcher must default ``SKIP_SETUP=true`` in normal mode (so a fresh
dev database auto-seeds the admin and skips the first-run wizard) and force
``SKIP_SETUP=false`` in ``--setup`` mode. The env var name is ``SKIP_SETUP``
(no ``BALUHOST_`` prefix) — see ``Settings.skip_setup`` binding.
"""
import importlib.util
import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


def _load_start_dev():
    spec = importlib.util.spec_from_file_location("start_dev", REPO_ROOT / "start_dev.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_normal_mode_defaults_skip_setup_true():
    sd = _load_start_dev()
    env: dict = {}
    sd._configure_setup_env(False, env)
    assert env["SKIP_SETUP"] == "true"


def test_normal_mode_respects_explicit_override():
    """A caller who exported SKIP_SETUP=false still gets the wizard in normal mode."""
    sd = _load_start_dev()
    env = {"SKIP_SETUP": "false"}
    sd._configure_setup_env(False, env)
    assert env["SKIP_SETUP"] == "false"


def test_setup_mode_forces_skip_setup_false():
    sd = _load_start_dev()
    env = {"SKIP_SETUP": "true"}
    sd._configure_setup_env(True, env)
    assert env["SKIP_SETUP"] == "false"
