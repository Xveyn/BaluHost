import base64

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.plugins.signing import SignatureError, verify_detached_ed25519


def _keypair() -> tuple[Ed25519PrivateKey, str]:
    sk = Ed25519PrivateKey.generate()
    pub_b64 = base64.b64encode(
        sk.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
    ).decode()
    return sk, pub_b64


def _sign(sk: Ed25519PrivateKey, message: bytes) -> str:
    return base64.b64encode(sk.sign(message)).decode()


def test_valid_signature_passes():
    sk, pub = _keypair()
    msg = b'{"index_version": 1}'
    verify_detached_ed25519(msg, _sign(sk, msg), [pub])  # no raise


def test_tampered_message_fails():
    sk, pub = _keypair()
    msg = b'{"index_version": 1}'
    sig = _sign(sk, msg)
    with pytest.raises(SignatureError):
        verify_detached_ed25519(msg + b" ", sig, [pub])


def test_wrong_key_fails():
    sk, _ = _keypair()
    _, other_pub = _keypair()
    msg = b"hello"
    with pytest.raises(SignatureError):
        verify_detached_ed25519(msg, _sign(sk, msg), [other_pub])


def test_rotation_second_key_validates():
    sk, pub = _keypair()
    _, old_pub = _keypair()
    msg = b"payload"
    verify_detached_ed25519(msg, _sign(sk, msg), [old_pub, pub])  # no raise


def test_empty_key_list_fails():
    sk, _ = _keypair()
    with pytest.raises(SignatureError):
        verify_detached_ed25519(b"x", _sign(sk, b"x"), [])


def test_malformed_signature_base64_fails():
    _, pub = _keypair()
    with pytest.raises(SignatureError):
        verify_detached_ed25519(b"x", "not!base64!!", [pub])


def test_malformed_key_fails():
    sk, _ = _keypair()
    with pytest.raises(SignatureError):
        verify_detached_ed25519(b"x", _sign(sk, b"x"), ["not!base64!!"])
