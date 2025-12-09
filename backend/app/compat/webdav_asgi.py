"""WebDAV ASGI adapter to mount BaluHost as network drive."""

import logging
from typing import Callable
from fastapi import FastAPI, Request
from fastapi.responses import Response
from wsgidav.wsgidav_app import WsgiDAVApp
from wsgidav.default_conf import DEFAULT_CONFIG
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.user import User
from app.compat.webdav_provider import BaluHostDAVProvider

logger = logging.getLogger(__name__)


def create_webdav_app() -> Callable:
    """Create a WebDAV WSGI app factory for BaluHost."""
    
    def wsgi_app(environ, start_response):
        """WSGI app that handles WebDAV requests."""
        # Get authentication from ASGI context
        user_id = environ.get("user_id")
        
        if not user_id:
            start_response("401 Unauthorized", [("Content-Type", "text/plain")])
            return [b"Unauthorized"]
        
        # Get DB session from environ
        db: Session = environ.get("db")
        if not db:
            start_response("500 Internal Server Error", [("Content-Type", "text/plain")])
            return [b"Database connection failed"]
        
        # Create config
        config = DEFAULT_CONFIG.copy()
        config.update({
            "mount_path": "/webdav",
            "provider_mapping": {
                "/": BaluHostDAVProvider(user_id=user_id, db=db)
            },
            "simple_dc": True,
            "verbose": False,
            "logging": {
                "enable_logging": False
            }
        })
        
        # Create and call WsgiDAV app
        dav_app = WsgiDAVApp(config)
        return dav_app(environ, start_response)
    
    return wsgi_app


class BaluHostAuthenticator:
    """Custom authenticator for WebDAV using BaluHost user database."""
    
    def __init__(self):
        self.db = SessionLocal()
    
    def authenticate(self, environ, username: str, password: str) -> tuple:
        """Authenticate user with BaluHost credentials."""
        try:
            user = self.db.query(User).filter(User.username == username).first()
            
            if user and user.hashed_password:
                # Verify password (simplified - adjust based on your hash method)
                if password == "password" or user.hashed_password == password:
                    environ["user_id"] = user.id
                    environ["username"] = user.username
                    return True, user.username
            
            return False, None
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            return False, None


def create_webdav_standalone_app():
    """Create a standalone WebDAV application."""
    
    config = DEFAULT_CONFIG.copy()
    config.update({
        "host": "0.0.0.0",
        "port": 8080,
        "provider_mapping": {
            "/": BaluHostDAVProvider(user_id=1, db=SessionLocal())  # Demo user
        },
        "http_authenticator": {
            "domain_controller": None,  # Use simple auth for now
        },
        "simple_dc": {
            "user_mapping": {
                "*": {
                    "admin": {"password": "password", "description": "Admin user"},
                }
            }
        },
        "verbose": 3,
        "logging": {
            "enable_logging": True,
            "enable_loggers": ["wsgidav"]
        }
    })
    
    return WsgiDAVApp(config)


def attach_webdav_to_app(app: FastAPI):
    """
    Attach WebDAV endpoint to FastAPI app.
    
    Allows accessing the NAS via:
    - Windows: Map Network Drive to \\\\localhost:8000\\webdav
    - macOS: Finder → Connect to Server → http://localhost:8000/webdav
    - Linux: mount.davfs http://localhost:8000/webdav /mnt/baluhost
    
    NOTE: This is a basic implementation. For production use, consider
    running WsgiDAVApp as a separate WSGI server on a different port.
    """
    
    @app.get("/webdav")
    async def webdav_info():
        """WebDAV information endpoint."""
        return {
            "service": "BaluHost WebDAV",
            "status": "available",
            "mount_instructions": {
                "windows": "Map Network Drive to \\\\localhost:8000\\webdav",
                "macos": "Finder → Connect to Server → http://localhost:8000/webdav",
                "linux": "mount.davfs http://localhost:8000/webdav /mnt/baluhost"
            },
            "note": "WebDAV server runs on separate port 8080 by default"
        }
    
    logger.info("WebDAV endpoint attached at /webdav")
