"""BaluPi handshake service — notifies the companion Raspberry Pi of NAS lifecycle events.

Uses HMAC-SHA256 signed requests for authentication (shared secret, timestamp-nonce).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# Reusable client (created lazily)
_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    """Get or create a reusable async HTTP client."""
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(10.0, connect=5.0),
            limits=httpx.Limits(
                max_connections=3,
                max_keepalive_connections=1,
                keepalive_expiry=30.0,
            ),
        )
    return _client


async def close_client() -> None:
    """Close the HTTP client (call during shutdown)."""
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
        _client = None


def _sign_request(method: str, path: str, body: dict | None) -> dict[str, str]:
    """Generate HMAC-SHA256 signature headers.

    Signature = HMAC-SHA256(secret, "{method}:{path}:{timestamp}:{body_sha256}")

    Args:
        method: HTTP method (POST, GET, etc.)
        path: Request path (e.g. /api/handshake/nas-going-offline)
        body: Request body dict (or None)

    Returns:
        Dict with X-Balupi-Timestamp and X-Balupi-Signature headers.
    """
    secret = settings.balupi_handshake_secret
    if not secret:
        raise ValueError("balupi_handshake_secret is not configured")

    timestamp = str(int(time.time()))

    if body is not None:
        body_bytes = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
        body_hash = hashlib.sha256(body_bytes).hexdigest()
    else:
        body_hash = hashlib.sha256(b"").hexdigest()

    message = f"{method.upper()}:{path}:{timestamp}:{body_hash}"
    signature = hmac.new(
        secret.encode(),
        message.encode(),
        hashlib.sha256,
    ).hexdigest()

    return {
        "X-Balupi-Timestamp": timestamp,
        "X-Balupi-Signature": signature,
    }


async def _send_to_pi(
    method: str,
    path: str,
    body: dict | None = None,
    timeout: float = 10.0,
) -> dict[str, Any] | None:
    """Send a signed request to the BaluPi backend.

    Args:
        method: HTTP method.
        path: API path (e.g. /api/handshake/nas-going-offline).
        body: JSON body (optional).
        timeout: Request timeout in seconds.

    Returns:
        Response JSON dict, or None on failure.
    """
    if not settings.balupi_url:
        logger.warning("balupi_url not configured, skipping Pi notification")
        return None

    url = f"{settings.balupi_url.rstrip('/')}{path}"
    headers = _sign_request(method, path, body)
    headers["Content-Type"] = "application/json"

    client = _get_client()
    try:
        resp = await client.request(
            method,
            url,
            json=body,
            headers=headers,
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json()
    except httpx.TimeoutException:
        logger.warning("BaluPi request timed out: %s %s", method, path)
        return None
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "BaluPi returned %d for %s %s: %s",
            exc.response.status_code, method, path, exc.response.text[:200],
        )
        return None
    except httpx.HTTPError as exc:
        logger.warning("BaluPi request failed: %s %s — %s", method, path, exc)
        return None


async def notify_balupi_shutdown(snapshot: dict) -> bool:
    """Notify BaluPi that the NAS is going offline, sending a metadata snapshot.

    Args:
        snapshot: Snapshot dict from snapshot_export.create_shutdown_snapshot().

    Returns:
        True if Pi acknowledged, False otherwise.
    """
    logger.info("Notifying BaluPi of NAS shutdown...")
    result = await _send_to_pi(
        "POST",
        "/api/handshake/nas-going-offline",
        body=snapshot,
        timeout=10.0,
    )
    if result and result.get("acknowledged"):
        logger.info(
            "BaluPi acknowledged shutdown (dns_switched=%s)",
            result.get("dns_switched"),
        )
        return True
    logger.warning("BaluPi did not acknowledge shutdown notification")
    return False


async def notify_balupi_startup() -> bool:
    """Notify BaluPi that the NAS is coming online.

    Returns:
        True if Pi acknowledged, False otherwise.
    """
    logger.info("Notifying BaluPi of NAS startup...")
    result = await _send_to_pi(
        "POST",
        "/api/handshake/nas-coming-online",
        timeout=5.0,
    )
    if result and result.get("acknowledged"):
        logger.info(
            "BaluPi acknowledged startup (inbox_flushed=%s, files_transferred=%s)",
            result.get("inbox_flushed"),
            result.get("files_transferred"),
        )
        return True
    logger.warning("BaluPi did not acknowledge startup notification")
    return False
