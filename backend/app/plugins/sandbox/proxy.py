"""FastAPI catch-all proxy for external (sandboxed) plugins.

Forwards a token-free, header-allowlisted request to the plugin's worker over
RPC and turns the worker's response back into a FastAPI Response. Every plugin
failure is scrubbed: crash -> 502, timeout -> 504, unreachable/disabled -> 503.
The Authorization and Cookie headers are never forwarded.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

from app.plugins.sandbox.supervisor import SupervisorError, SupervisorTimeout

logger = logging.getLogger(__name__)

REQUEST_BODY_MAX = 10 * 1024 * 1024  # 10 MiB
REQUEST_TIMEOUT = 30.0
# Request headers forwarded to the plugin. NEVER includes authorization/cookie.
ALLOWED_REQUEST_HEADERS = frozenset({"content-type", "accept"})
# Response headers passed back to the client.
ALLOWED_RESPONSE_HEADERS = frozenset({"content-type"})


def _filter_request_headers(request: Request) -> dict:
    return {
        k.lower(): v
        for k, v in request.headers.items()
        if k.lower() in ALLOWED_REQUEST_HEADERS
    }


def _build_response(payload: dict) -> Response:
    status_code = int(payload.get("status", 200))
    body = payload.get("body")
    headers = {
        k.lower(): v
        for k, v in (payload.get("headers") or {}).items()
        if k.lower() in ALLOWED_RESPONSE_HEADERS
    }
    if isinstance(body, (bytes, bytearray)):
        return Response(content=bytes(body), status_code=status_code, headers=headers)
    return JSONResponse(content=body, status_code=status_code, headers=headers)


async def proxy_request(
    name: str, path: str, request: Request, current_user: Any, manager: Any
) -> Response:
    """Proxy one request to an external plugin's sandbox worker."""
    supervisor = manager.get_sandbox(name)
    if supervisor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plugin not found")

    # Reject oversized bodies BEFORE buffering them into memory. The
    # Content-Length header can lie, so we also guard after the read.
    declared = request.headers.get("content-length")
    if declared is not None:
        try:
            if int(declared) > REQUEST_BODY_MAX:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail="Request body too large",
                )
        except ValueError:
            pass  # malformed header — fall through to the post-read guard
    body = await request.body()
    if len(body) > REQUEST_BODY_MAX:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Request body too large",
        )

    context = {
        "user_id": current_user.id,
        "username": current_user.username,
        "role": current_user.role,
    }
    try:
        result = await supervisor.dispatch(
            request.method,
            path,
            body,
            context,
            query=dict(request.query_params),
            headers=_filter_request_headers(request),
            timeout=REQUEST_TIMEOUT,
        )
    except SupervisorTimeout:
        logger.warning("Plugin %s request timed out", name)
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="Plugin timed out")
    except SupervisorError as exc:
        logger.warning("Plugin %s unavailable: %s", name, exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Plugin error")
    except Exception:
        logger.exception("Unexpected error proxying to plugin %s", name)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Plugin error")

    return _build_response(result)
