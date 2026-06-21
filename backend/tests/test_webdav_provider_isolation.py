"""Isolation tests for BaluHostDAVProvider._loc_to_file_path (audit #5)."""
import os
from pathlib import Path

import pytest

from app.compat.webdav_provider import BaluHostDAVProvider

USER_ENV = {"baluhost.user_role": "user", "wsgidav.auth.user_name": "bob"}


def _provider(tmp_path) -> BaluHostDAVProvider:
    return BaluHostDAVProvider(str(tmp_path))


def test_normal_user_path_maps_into_user_root(tmp_path):
    provider = _provider(tmp_path)
    fp = Path(provider._loc_to_file_path("/docs/file.txt", USER_ENV))
    expected = (tmp_path / "bob" / "docs" / "file.txt").resolve()
    assert fp == expected


def test_dotdot_traversal_raises(tmp_path):
    provider = _provider(tmp_path)
    with pytest.raises(ValueError, match="Path traversal"):
        provider._loc_to_file_path("/../etc/passwd", USER_ENV)


def test_username_prefix_sibling_blocked(tmp_path):
    """user 'bob' must NOT reach a sibling dir 'bobby' via '..' (startswith bug)."""
    (tmp_path / "bobby").mkdir()
    provider = _provider(tmp_path)
    with pytest.raises(ValueError, match="Path traversal"):
        provider._loc_to_file_path("/../bobby/secret.txt", USER_ENV)


def test_symlink_escape_blocked(tmp_path):
    """A symlink inside the user root that points outside must be rejected."""
    bob_root = tmp_path / "bob"
    bob_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (bob_root / "evil").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not permitted on this platform")
    provider = _provider(tmp_path)
    with pytest.raises(ValueError, match="Path traversal"):
        provider._loc_to_file_path("/evil/secret.txt", USER_ENV)


def test_admin_path_delegates_to_super(tmp_path):
    """Admin role bypasses per-user isolation (delegates to base provider)."""
    provider = _provider(tmp_path)
    admin_env = {"baluhost.user_role": "admin", "wsgidav.auth.user_name": "root"}
    fp = provider._loc_to_file_path("/file.txt", admin_env)
    assert fp  # base provider returns a path under storage_root, no exception
