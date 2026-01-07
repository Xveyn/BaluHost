"""
Local-only access enforcement middleware.

Ensures that sensitive endpoints are only accessible from localhost
when ENFORCE_LOCAL_ONLY=true.
"""

import logging
from typing import Callable
from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class LocalOnlyMiddleware(BaseHTTPMiddleware):
    """
    Middleware to restrict access to localhost only for specific endpoints.
    
    When enabled (via ENFORCE_LOCAL_ONLY env var), this middleware checks
    the client IP and blocks non-local requests to protected endpoints.
    """
    
    def __init__(self, app, enforce: bool = False, protected_prefixes: list[str] = []):
        super().__init__(app)
        self.enforce = enforce
        self.protected_prefixes = protected_prefixes or [
            "/api/server-profiles",
            "/api/auth/login",
            "/api/auth/register",
        ]
        if self.enforce:
            logger.info(f"Local-only enforcement ENABLED for: {self.protected_prefixes}")
        else:
            logger.info("Local-only enforcement DISABLED")
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not self.enforce:
            return await call_next(request)
        
        # Check if path is protected
        path = request.url.path
        is_protected = any(path.startswith(prefix) for prefix in self.protected_prefixes)
        
        if not is_protected:
            return await call_next(request)
        
        # Check if request is from localhost
        client_host = request.client.host if request.client else None
        
        if not client_host:
            logger.warning(f"Request to {path} has no client host - blocking")
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": "Access denied: client host unknown"}
            )
        
        # Allow localhost, 127.0.0.1, ::1, and local network ranges
        is_local = (
            client_host == "localhost" or
            client_host.startswith("127.") or
            client_host == "::1" or
            client_host.startswith("::ffff:127.") or  # IPv6-mapped IPv4
            client_host.startswith("192.168.") or  # Local network (optional)
            client_host.startswith("10.") or  # Local network (optional)
            client_host.startswith("172.16.") or  # Local network (optional)
            client_host.startswith("fd")  # IPv6 ULA (optional)
        )
        
        if not is_local:
            logger.warning(f"Blocking non-local request to {path} from {client_host}")
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": "Access denied: only localhost allowed"}
            )
        
        logger.debug(f"Allowing local request to {path} from {client_host}")
        return await call_next(request)
