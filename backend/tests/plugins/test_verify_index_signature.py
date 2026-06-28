import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.plugins.verify_index_signature import check_index_signature

_SK = Ed25519PrivateKey.generate()
_PUB = base64.b64encode(
    _SK.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
).decode()

_INDEX = b'{"index_version": 1, "plugins": []}'
_SIG = base64.b64encode(_SK.sign(_INDEX))
_IDX_URL = "https://m.example/index.json"
_SIG_URL = _IDX_URL + ".sig"


def _fetcher(mapping):
    def _f(url):
        return mapping[url]
    return _f


def test_valid_index_passes():
    ok, msg = check_index_signature(
        _IDX_URL, _SIG_URL, [_PUB], _fetcher({_IDX_URL: _INDEX, _SIG_URL: _SIG})
    )
    assert ok is True


def test_empty_key_warns_not_configured():
    ok, msg = check_index_signature(
        _IDX_URL, _SIG_URL, [], _fetcher({_IDX_URL: _INDEX, _SIG_URL: _SIG})
    )
    assert ok is False
    assert msg == "marketplace signing not configured"


def test_fetch_failure_warns():
    def boom(url):
        raise RuntimeError("network down")

    ok, msg = check_index_signature(_IDX_URL, _SIG_URL, [_PUB], boom)
    assert ok is False
    assert "could not fetch" in msg


def test_invalid_signature_warns():
    bad = base64.b64encode(b"\x00" * 64)
    ok, msg = check_index_signature(
        _IDX_URL, _SIG_URL, [_PUB], _fetcher({_IDX_URL: _INDEX, _SIG_URL: bad})
    )
    assert ok is False
    assert "verification failed" in msg


def test_never_raises_on_garbage():
    # A fetcher returning non-bytes / nonsense must not crash the check.
    ok, msg = check_index_signature(_IDX_URL, _SIG_URL, [_PUB], lambda url: 12345)
    assert ok is False
