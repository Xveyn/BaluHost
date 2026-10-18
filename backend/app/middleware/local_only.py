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

from app.core.network_utils import is_private_or_local_ip

logger = logging.getLogger(__name__)


class LocalOnlyMiddleware(BaseHTTPMiddleware):
    """
    Middleware to restrict access to localhost only for specific endpoints.
    
    When enabled (via ENFORCE_LOCAL_ONLY env var), this middleware checks
    the client IP and blocks non-local requests to protected endpoints.
    """
    
    def __init__(self, app, enforce: bool = False, protected_prefixes: list[str] | None = None):
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
        
        # Eine einzige Definition von "lokal": core/network_utils.py (#324). Eine
        # eigene String-Praefix-Liste hatte 172.16.0.0/12 als "172.16." gelesen.
        is_local = is_private_or_local_ip(client_host)

        if not is_local:
            logger.warning(f"Blocking non-local request to {path} from {client_host}")
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": "Access denied: only localhost allowed"}
            )
        
        logger.debug(f"Allowing local request to {path} from {client_host}")
        return await call_next(request)
