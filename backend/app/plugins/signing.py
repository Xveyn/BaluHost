"""Detached ed25519 signature verification for the marketplace index.

Given the raw signed bytes, a base64 detached signature, and a list of
trusted base64 ed25519 public keys, verify that *some* trusted key signed
the bytes. Used by the marketplace service (fail-closed index gate) and the
deploy smoke-check. Pure — no I/O.
"""
from __future__ import annotations

import base64
import binascii
from typing import Sequence

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


class SignatureError(Exception):
    """Raised when a detached ed25519 signature cannot be verified."""


def verify_detached_ed25519(
    message: bytes,
    signature_b64: str,
    public_keys_b64: Sequence[str],
) -> None:
    """Verify ``signature_b64`` over ``message`` against any trusted key.

    Returns None on the first trusted key that validates. Raises
    ``SignatureError`` if the key list is empty, the signature is not valid
    base64 / not 64 bytes, or no trusted key validates the signature. A
    malformed key in the list is skipped, not fatal, unless it is the only
    reason nothing validated.
    """
    keys = list(public_keys_b64)
    if not keys:
        raise SignatureError("no trusted public keys configured")

    try:
        signature = base64.b64decode(signature_b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise SignatureError(f"signature is not valid base64: {exc}") from exc
    if len(signature) != 64:
        raise SignatureError(f"signature must be 64 bytes, got {len(signature)}")

    last_err = "no trusted key validated the signature"
    for key_b64 in keys:
        try:
            raw = base64.b64decode(key_b64, validate=True)
        except (binascii.Error, ValueError) as exc:
            last_err = f"public key is not valid base64: {exc}"
            continue
        if len(raw) != 32:
            last_err = f"public key must be 32 bytes, got {len(raw)}"
            continue
        try:
            Ed25519PublicKey.from_public_bytes(raw).verify(signature, message)
            return
        except InvalidSignature:
            last_err = "no trusted key validated the signature"
            continue

    raise SignatureError(last_err)
