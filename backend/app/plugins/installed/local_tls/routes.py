"""Admin-Routen des Plugins local_tls (Status, Token, manuelle Laeufe).

Nur fuer Admins. Der Anbieter-Token ist schreibend-only: er erscheint in keiner
Antwort, keinem Log und keinem Audit-Eintrag.
"""
# NB: kein ``from __future__ import annotations`` (vgl. bluetooth): Pydantic-Bodies
# hinter slowapis Limiter-Wrapper wuerden sonst zu ForwardRefs und 422.
import asyncio
import logging
import re
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api import deps
from app.core.database import get_db
from app.core.rate_limiter import get_limit, user_limiter
from app.plugins.installed.local_tls import paths, providers, service, state
from app.plugins.installed.local_tls.config import LocalTlsConfig
from app.plugins.installed.local_tls.models import CredentialsRequest, StatusResponse
from app.schemas.user import UserPublic
from app.services.audit.logger_db import get_audit_logger_db

logger = logging.getLogger(__name__)

router = APIRouter()

_LIMIT = get_limit("local_tls")
_TOKEN_MAX = 200


def _load_config(db: Session) -> LocalTlsConfig:
    from app.plugins.installed.local_tls import LocalTlsPlugin  # noqa: PLC0415

    return LocalTlsPlugin().load_config(db)


def _error(code: int, name: str) -> JSONResponse:
    return JSONResponse(status_code=code, content={"error": name})


def _audit(action: str, user: UserPublic, details: Optional[dict] = None) -> None:
    get_audit_logger_db().log_event(
        event_type="SYSTEM_CONFIG",
        action=action,
        user=user.username,
        resource="local_tls",
        success=True,
        details=details or {},
    )


def _nginx_hint(domain: str) -> str:
    live = paths.DATA_DIR / "live"
    return (
        "# In beiden TLS-Bloecken der nginx-Site (listen 443 ssl ...):\n"
        f"server_name {domain};\n"
        f"ssl_certificate {live}/fullchain.pem;\n"
        f"ssl_certificate_key {live}/privkey.pem;\n"
    )


def _build_status(db: Session, config: LocalTlsConfig) -> StatusResponse:
    """Blockierend (lego, ip, TLS-Handshake): nur aus ``asyncio.to_thread`` rufen."""
    snapshot = service.get_status(db, config, datetime.now(timezone.utc))
    hint = (
        _nginx_hint(config.domain)
        if snapshot.served_matches is False and config.domain
        else None
    )
    return StatusResponse(
        **asdict(snapshot), token_set=state.has_token(db), nginx_hint=hint
    )


@router.get("/status", response_model=StatusResponse)
@user_limiter.limit(_LIMIT)
async def get_status(
    request: Request,
    response: Response,
    current_user: UserPublic = Depends(deps.get_current_admin),
    db: Session = Depends(get_db),
) -> StatusResponse:
    config = _load_config(db)
    return await asyncio.to_thread(_build_status, db, config)


@router.put("/credentials", status_code=status.HTTP_204_NO_CONTENT)
@user_limiter.limit(_LIMIT)
async def put_credentials(
    body: CredentialsRequest,
    request: Request,
    response: Response,
    current_user: UserPublic = Depends(deps.get_current_admin),
    db: Session = Depends(get_db),
):
    config = _load_config(db)
    fields = [f for f in providers.get_provider(config.provider).credential_fields if f.secret]
    token = body.token
    # Weder Token noch Teile davon in die Antwort.
    if not (1 <= len(token) <= _TOKEN_MAX) or any(
        re.fullmatch(f.pattern, token) is None for f in fields
    ):
        return _error(422, "invalid_token_format")
    try:
        state.set_token(db, token)
    except Exception:  # noqa: BLE001 - jede Verschluesselungsstoerung, nie mit Ursache
        db.rollback()
        return _error(400, "encryption_key_missing")
    _audit("local_tls_credentials_changed", current_user, {"action": "set"})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/credentials", status_code=status.HTTP_204_NO_CONTENT)
@user_limiter.limit(_LIMIT)
async def delete_credentials(
    request: Request,
    response: Response,
    current_user: UserPublic = Depends(deps.get_current_admin),
    db: Session = Depends(get_db),
):
    state.clear_token(db)
    _audit("local_tls_credentials_changed", current_user, {"action": "cleared"})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _manual_run(check, db: Session):
    """Fuehrt einen erzwungenen Lauf aus und liefert danach den Status."""
    config = _load_config(db)
    try:
        await service.run_check(
            check, _load_config, force=True, raise_if_running=True
        )
    except paths.AlreadyRunning:
        return None
    return await asyncio.to_thread(_build_status, db, config)


@router.post("/renew", response_model=StatusResponse, status_code=status.HTTP_202_ACCEPTED)
@user_limiter.limit(_LIMIT)
async def renew(
    request: Request,
    response: Response,
    current_user: UserPublic = Depends(deps.get_current_admin),
    db: Session = Depends(get_db),
):
    _audit("local_tls_renew_triggered", current_user)
    result = await _manual_run(service.run_cert_check, db)
    if result is None:
        return _error(409, "already_running")
    return result


@router.post("/update-dns", response_model=StatusResponse)
@user_limiter.limit(_LIMIT)
async def update_dns(
    request: Request,
    response: Response,
    current_user: UserPublic = Depends(deps.get_current_admin),
    db: Session = Depends(get_db),
):
    _audit("local_tls_dns_update_triggered", current_user)
    result = await _manual_run(service.run_address_check, db)
    if result is None:
        return _error(409, "already_running")
    return result
