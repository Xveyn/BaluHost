"""Deploy smoke-check: verify the live marketplace index signature.

Run as ``python -m app.plugins.verify_index_signature``. ALWAYS exits 0 — a
signing hiccup must never fail a deploy. Prints ``PASS: <msg>`` or
``WARN: <reason>`` for the deploy log. Reuses ``verify_detached_ed25519``.
"""
from __future__ import annotations

import sys
from typing import Callable, Optional, Sequence

from app.plugins.signing import SignatureError, verify_detached_ed25519


def check_index_signature(
    index_url: str,
    signature_url: str,
    public_keys: Sequence[str],
    fetcher: Callable[[str], bytes],
) -> tuple[bool, str]:
    """Return ``(ok, message)``. Never raises."""
    if not list(public_keys):
        return False, "marketplace signing not configured"
    try:
        raw = fetcher(index_url)
        sig = fetcher(signature_url)
        sig_b64 = sig.decode("ascii").strip()
    except Exception as exc:  # noqa: BLE001 - smoke-check must not crash
        return False, f"could not fetch index or signature: {exc}"
    try:
        verify_detached_ed25519(raw, sig_b64, public_keys)
    except (SignatureError, UnicodeDecodeError) as exc:
        return False, f"signature verification failed: {exc}"
    except Exception as exc:  # noqa: BLE001 - defensive: never crash the deploy
        return False, f"unexpected verification error: {exc}"
    return True, "signature OK"


def _default_fetcher(url: str) -> bytes:
    import httpx

    with httpx.Client(timeout=15.0, follow_redirects=True) as client:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.content


def main(argv: Optional[Sequence[str]] = None) -> int:
    from app.core.config import settings

    index_url = settings.plugins_marketplace_index_url
    sig_url = settings.plugins_marketplace_signature_url or (index_url + ".sig")
    ok, message = check_index_signature(
        index_url, sig_url, settings.plugins_marketplace_public_keys, _default_fetcher
    )
    print(f"PASS: {message}" if ok else f"WARN: {message}")
    return 0  # always non-fatal


if __name__ == "__main__":
    sys.exit(main())
