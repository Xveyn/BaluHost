"""The FCM push token must never be written to stdout (audit #4)."""
import inspect

from app.api.routes import mobile


def test_mobile_module_has_no_print_calls():
    """All debug output in mobile.py must go through logging, not print()."""
    src = inspect.getsource(mobile)
    # Ignore occurrences inside this assertion's own string by checking the
    # source of the module file directly.
    assert "print(" not in src, "mobile.py must not use print() (use logger)"


def test_register_push_token_source_does_not_print_token():
    src = inspect.getsource(mobile.register_push_token)
    assert "print(" not in src
    # The token value must not be interpolated into any log/print line.
    assert "push_token[:20]" not in src
