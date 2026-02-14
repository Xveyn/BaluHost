"""WebDAV standalone server with BaluHost authentication and user isolation."""

import logging
from pathlib import Path

from passlib.context import CryptContext
from wsgidav.wsgidav_app import WsgiDAVApp
from wsgidav.default_conf import DEFAULT_CONFIG
from wsgidav.dc.base_dc import BaseDomainController

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.user import User
from app.compat.webdav_provider import BaluHostDAVProvider

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

logger = logging.getLogger(__name__)


class BaluHostDomainController(BaseDomainController):
    """WsgiDAV domain controller that authenticates against the BaluHost user database."""

    def __init__(self, wsgidav_app, config):
        super().__init__(wsgidav_app, config)

    def get_domain_realm(self, path_info, environ):
        return "BaluHost WebDAV"

    def require_authentication(self, realm, environ):
        return True

    def basic_auth_user(self, realm, user_name, password, environ):
        """Authenticate using BaluHost credentials (bcrypt)."""
        db = SessionLocal()
        try:
            user = db.query(User).filter(
                User.username == user_name,
                User.is_active == True,
            ).first()

            if not user:
                logger.warning("WebDAV auth failed: user '%s' not found or inactive", user_name)
                return False

            if not _pwd_context.verify(password, user.hashed_password):
                logger.warning("WebDAV auth failed: wrong password for user '%s'", user_name)
                return False

            environ["wsgidav.auth.user_name"] = user.username
            environ["baluhost.user_id"] = user.id
            environ["baluhost.user_role"] = user.role
            return True
        except Exception as e:
            logger.error("WebDAV auth error: %s", e)
            return False
        finally:
            db.close()

    def supports_http_digest_auth(self):
        return False


class RequestLoggingMiddleware:
    """WSGI middleware that logs incoming request method, path, and auth type.

    Only active when the WsgiDAV verbose level is >= 3.
    """

    def __init__(self, app, verbose: int = 0):
        self.app = app
        self.active = verbose >= 3

    def __call__(self, environ, start_response):
        if self.active:
            method = environ.get("REQUEST_METHOD", "?")
            path = environ.get("PATH_INFO", "/")
            auth_header = environ.get("HTTP_AUTHORIZATION", "")
            auth_type = auth_header.split(" ", 1)[0] if auth_header else "(none)"
            logger.debug("WebDAV %s %s  Auth: %s", method, path, auth_type)
        return self.app(environ, start_response)


def create_webdav_standalone_app():
    """Create a standalone WebDAV application with BaluHost auth and user isolation.

    User isolation is handled inside BaluHostDAVProvider._loc_to_file_path():
    - Admin users see the entire storage root
    - Regular users see only their home directory
    """

    verbose = 3 if settings.webdav_verbose_logging else 1
    storage_root = str(Path(settings.nas_storage_path).resolve())

    config = DEFAULT_CONFIG.copy()
    config.update({
        "host": "0.0.0.0",
        "port": settings.webdav_port,
        "provider_mapping": {
            "/": BaluHostDAVProvider(storage_root)
        },
        "http_authenticator": {
            "domain_controller": BaluHostDomainController,
            "accept_basic": True,
            "accept_digest": False,
            "default_to_digest": False,
        },
        "verbose": verbose,
        "logging": {
            "enable_logging": verbose >= 3,
            "enable_loggers": ["wsgidav"] if verbose >= 3 else [],
        },
    })

    dav_app = WsgiDAVApp(config)
    return RequestLoggingMiddleware(dav_app, verbose=verbose)
