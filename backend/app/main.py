from __future__ import annotations

from typing import Any
from pathlib import Path

from app.compat import apply_asyncio_patches

apply_asyncio_patches()

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.formparsers import MultiPartParser
from starlette.requests import Request as StarletteRequest
from slowapi.errors import RateLimitExceeded

from app import __version__
from app.core.config import settings
from app.core.rate_limiter import limiter, rate_limit_exceeded_handler
from app.core.lifespan import lifespan
from app.middleware.device_tracking import DeviceTrackingMiddleware
from app.middleware.local_only import LocalOnlyMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.middleware.error_counter import ErrorCounterMiddleware
from app.middleware.plugin_gate import PluginGateMiddleware
from app.middleware.sleep_auto_wake import SleepAutoWakeMiddleware
from app.middleware.api_version import ApiVersionMiddleware

# Individual file size limit — class attribute, works correctly
MultiPartParser.max_file_size = 10 * 1024 * 1024 * 1024  # 10 GB (matches nginx client_max_body_size)

# Batch upload limits — must patch Request.form() because FastAPI calls it
# without arguments, and the defaults (1000) are hardcoded in the method signature.
# Class attributes on MultiPartParser do NOT work (constructor overrides them).
_orig_form = StarletteRequest.form


def _form_with_limits(self, *, max_files: int | float = float('inf'), max_fields: int | float = float('inf')):
    return _orig_form(self, max_files=max_files, max_fields=max_fields)


StarletteRequest.form = _form_with_limits  # type: ignore[assignment]


def create_app() -> FastAPI:
    # Configure structured logging before any other setup
    from app.core.logging_config import setup_logging
    setup_logging()

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        debug=settings.debug,
        lifespan=lifespan,
        docs_url=None,  # Disable default docs
        redoc_url=None,  # Disable default redoc
    )

    # Add rate limiting state and exception handler
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)  # type: ignore[arg-type]

    # Map specific validation errors (e.g. SSH private key format) to 400
    def _validation_exception_handler(request, exc: RequestValidationError):
        try:
            errors = exc.errors()
            # If any validation message mentions PRIVATE KEY, return 400
            for e in errors:
                msg = e.get("msg", "")
                if "PRIVATE KEY" in str(msg).upper():
                    return JSONResponse(status_code=400, content={"detail": msg})
        except Exception:
            pass

        # Convert errors to JSON-serializable format (fixes Python 3.13 compatibility)
        serializable_errors = []
        try:
            errors = exc.errors()
            for error in errors:
                serializable_error = {}
                for key, value in error.items():
                    # Convert non-serializable objects (like ValueError) to strings
                    if isinstance(value, (str, int, float, bool, type(None))):
                        serializable_error[key] = value
                    elif isinstance(value, (list, tuple)):
                        serializable_error[key] = [str(v) if not isinstance(v, (str, int, float, bool, type(None))) else v for v in value]
                    else:
                        serializable_error[key] = str(value)
                serializable_errors.append(serializable_error)
        except Exception:
            # Fallback: convert entire error to string
            serializable_errors = [{"msg": str(exc)}]

        # Default behavior: return standard 422 response body
        return JSONResponse(status_code=422, content={"detail": serializable_errors})

    app.add_exception_handler(RequestValidationError, _validation_exception_handler)  # type: ignore[arg-type]

    # Security headers: CSP, X-Frame-Options, X-Content-Type-Options, HSTS
    app.add_middleware(SecurityHeadersMiddleware)

    # Add API version headers (X-API-Version, X-API-Min-Version) to /api/ responses
    app.add_middleware(ApiVersionMiddleware)

    # Add error counter middleware for admin metrics
    app.add_middleware(ErrorCounterMiddleware)

    # Gate plugin routes: block requests to disabled plugins (checks DB with TTL cache)
    app.add_middleware(PluginGateMiddleware)

    # Add sleep auto-wake middleware (counts requests + auto-wakes from soft sleep)
    app.add_middleware(SleepAutoWakeMiddleware)

    # Add local-only enforcement middleware (Option B security)
    if settings.enforce_local_only:
        app.add_middleware(
            LocalOnlyMiddleware,
            enforce=True,
            protected_prefixes=[
                "/api/server-profiles",
                "/api/auth/login",
                "/api/auth/register",
            ]
        )

    # Add device tracking middleware (updates last_seen for mobile devices)
    app.add_middleware(DeviceTrackingMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin) for origin in settings.cors_origins],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Device-ID", "X-Requested-With", "Accept", "Origin", "X-Chunk-Index"],
    )

    from app.api.versioned import create_versioned_router
    app.include_router(create_versioned_router(), prefix=settings.api_prefix)

    # Mount static files for avatars
    avatars_path = Path(settings.nas_storage_path) / ".system" / "avatars"
    avatars_path.mkdir(parents=True, exist_ok=True)
    app.mount("/avatars", StaticFiles(directory=str(avatars_path)), name="avatars")

    # Include custom styled docs
    from app.api.docs import router as docs_router
    app.include_router(docs_router)

    return app


app = create_app()


def run(**kwargs: Any) -> None:  # pragma: no cover - convenience launcher
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level="info",
        **kwargs,
    )


if __name__ == "__main__":  # pragma: no cover
    run()
