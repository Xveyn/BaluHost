"""firebase.py must route output through logging, not print() (audit hygiene)."""
import inspect
from app.services.notifications import firebase


def test_firebase_module_has_no_print_calls():
    src = inspect.getsource(firebase)
    assert "print(" not in src, "firebase.py must not use print() (use logger)"
