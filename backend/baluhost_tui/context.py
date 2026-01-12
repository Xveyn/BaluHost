"""Context manager for hybrid local/remote access."""
import os
import sys
from pathlib import Path
from typing import Optional, Any
from contextlib import contextmanager

import httpx
from sqlalchemy.orm import Session
import logging
import os

# Add parent directory to path for local imports
sys.path.insert(0, str(Path(__file__).parent.parent))


class BaluHostContext:
    """Context manager for accessing BaluHost services."""
    
    def __init__(self, mode: str = 'auto', server: str = 'http://localhost:8000', token: Optional[str] = None):
        """Initialize context.
        
        Args:
            mode: 'auto', 'local', or 'remote'
            server: Server URL for remote mode
            token: Authentication token
        """
        self.mode = self._detect_mode(mode)
        self.server = server
        self.token = token
        self._db_session: Optional[Session] = None
        self._api_client: Optional[httpx.Client] = None
    
    def _detect_mode(self, mode: str) -> str:
        """Auto-detect if running locally or remotely."""
        if mode != 'auto':
            return mode
        
        # Check if we can import app modules (local mode)
        try:
            from app.core.database import SessionLocal
            return 'local'
        except ImportError:
            return 'remote'
    
    @property
    def is_local(self) -> bool:
        """Check if running in local mode."""
        return self.mode == 'local'
    
    @property
    def is_remote(self) -> bool:
        """Check if running in remote mode."""
        return self.mode == 'remote'
    
    def get_db(self) -> Session:
        """Get database session (local mode only)."""
        if not self.is_local:
            raise RuntimeError("Database access not available in remote mode")
        
        if self._db_session is None:
            from app.core.database import SessionLocal
            self._db_session = SessionLocal()
        
        return self._db_session
    
    def get_api_client(self) -> httpx.Client:
        """Get API client (remote mode or fallback)."""
        if self._api_client is None:
            headers = {}
            if self.token:
                headers['Authorization'] = f'Bearer {self.token}'

            # Setup optional HTTP logging when BALUHOST_TUI_DEBUG=1 or debug token present
            enable_debug = os.environ.get('BALUHOST_TUI_DEBUG') == '1'
            logger = logging.getLogger('baluhost_tui.http')
            if enable_debug:
                logger.setLevel(logging.DEBUG)
                if not logger.handlers:
                    handler = logging.StreamHandler()
                    handler.setFormatter(logging.Formatter('[%(levelname)s] %(message)s'))
                    logger.addHandler(handler)

            event_hooks = {}
            if enable_debug or self.token:
                def _log_request(request: httpx.Request) -> None:
                    logger.debug(f"HTTP REQUEST -> {request.method} {request.url} headers={dict(request.headers)}")

                def _log_response(response: httpx.Response) -> None:
                    try:
                        req = response.request
                        logger.debug(f"HTTP RESPONSE <- {response.status_code} for {req.method} {req.url}")
                    except Exception:
                        logger.debug(f"HTTP RESPONSE <- {response.status_code}")

                event_hooks = {"request": [_log_request], "response": [_log_response]}

            self._api_client = httpx.Client(
                base_url=self.server,
                headers=headers,
                timeout=30.0,
                event_hooks=event_hooks if event_hooks else None,
            )
        
        return self._api_client
    
    def close(self):
        """Close all connections."""
        if self._db_session:
            self._db_session.close()
            self._db_session = None
        
        if self._api_client:
            self._api_client.close()
            self._api_client = None
    
    def __enter__(self):
        """Enter context manager."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context manager."""
        self.close()


@contextmanager
def get_context(mode: str = 'auto', server: str = 'http://localhost:8000', token: Optional[str] = None):
    """Context manager for BaluHost access.
    
    Usage:
        with get_context() as ctx:
            if ctx.is_local:
                db = ctx.get_db()
                users = db.query(User).all()
            else:
                client = ctx.get_api_client()
                response = client.get('/api/users')
    """
    ctx = BaluHostContext(mode=mode, server=server, token=token)
    try:
        yield ctx
    finally:
        ctx.close()
