"""Bluetooth — bundled Plugin.

Verbindet, trennt, entfernt und koppelt Bluetooth-Geraete ueber BlueZ auf
dem System-Bus. Laeuft im Host-Prozess als Dienst-User, der in der Gruppe
``bluetooth`` ist; ein Sandbox-Plugin kaeme nicht an ``org.bluez``.
"""
# NB: kein ``from __future__ import annotations`` hier (vgl. audio_control).
# Zusammen mit Pydantic v2 + FastAPIs Body-Erkennung durch slowapis
# ``@user_limiter.limit``-Wrapper werden aufgeschobene Annotationen zu
# ForwardRefs, die FastAPI nicht mehr als Pydantic-Modell aufloest — jedes
# POST liefert dann 422.
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Request, Response, status

from app.api.deps import require_power_manage_bluetooth
from app.core.exceptions import ForbiddenError
from app.core.rate_limiter import get_limit, user_limiter
from app.plugins.base import PluginBase, PluginMetadata, PluginUIManifest
from app.plugins.installed.bluetooth import service as service_module
from app.plugins.installed.bluetooth.bluez import DeviceInfo, kind_for_icon
from app.plugins.installed.bluetooth.models import (
    BluetoothState,
    ConfirmRequest,
    PairingSession,
    PairStartResponse,
    PowerRequest,
    ScanResponse,
)
from app.schemas.user import UserPublic
from app.services.audit.logger_db import get_audit_logger_db

logger = logging.getLogger(__name__)

router = APIRouter()

_LIMIT = get_limit("bluetooth")


def _client_host(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


def _audit(action: str, user: UserPublic, success: bool, details: dict) -> None:
    """Audit fuer Koppeln, Entfernen und Adapter an/aus — nie mit Code oder PIN."""
    audit_logger = get_audit_logger_db()
    audit_logger.log_event(
        event_type="POWER",
        action=action,
        user=user.username,
        resource="bluetooth",
        success=success,
        details=details,
    )
    if getattr(user, "role", None) != "admin":
        audit_logger.log_security_event(
            action="delegated_power_action",
            user=user.username,
            resource="manage_bluetooth",
            details={"action": action},
            success=True,
        )


@router.get("/state", response_model=BluetoothState)
@user_limiter.limit(_LIMIT)
async def get_bluetooth_state(
    request: Request,
    response: Response,
    current_user=Depends(require_power_manage_bluetooth),
) -> BluetoothState:
    """Adapter, Geraete und ob hier gekoppelt werden darf.

    Hinter derselben Berechtigung wie die Schreibrouten: die Liste verraet
    Hardware und MAC-Adressen.
    """
    return await service_module.get_bluetooth_service().get_state(_client_host(request))


@router.post("/adapter/power")
@user_limiter.limit(_LIMIT)
async def set_adapter_power(
    body: PowerRequest,
    request: Request,
    response: Response,
    current_user=Depends(require_power_manage_bluetooth),
) -> dict:
    await service_module.get_bluetooth_service().set_powered(body.powered)
    _audit("bluetooth_adapter_power", current_user, True, {"powered": body.powered})
    return {"success": True}


@router.post("/scan", response_model=ScanResponse)
@user_limiter.limit(_LIMIT)
async def start_scan(
    request: Request,
    response: Response,
    current_user=Depends(require_power_manage_bluetooth),
) -> ScanResponse:
    until = await service_module.get_bluetooth_service().start_scan()
    return ScanResponse(until=until)


@router.post("/devices/{address}/connect")
@user_limiter.limit(_LIMIT)
async def connect_device(
    address: str,
    request: Request,
    response: Response,
    current_user=Depends(require_power_manage_bluetooth),
) -> dict:
    await service_module.get_bluetooth_service().connect(address)
    return {"success": True}


@router.post("/devices/{address}/disconnect")
@user_limiter.limit(_LIMIT)
async def disconnect_device(
    address: str,
    request: Request,
    response: Response,
    current_user=Depends(require_power_manage_bluetooth),
) -> dict:
    await service_module.get_bluetooth_service().disconnect(address)
    return {"success": True}


@router.delete("/devices/{address}")
@user_limiter.limit(_LIMIT)
async def remove_device(
    address: str,
    request: Request,
    response: Response,
    current_user=Depends(require_power_manage_bluetooth),
) -> dict:
    device = await service_module.get_bluetooth_service().remove(address)
    _audit("bluetooth_remove", current_user, True,
           {"address": device.address, "kind": kind_for_icon(device.icon)})
    return {"success": True}


@router.post("/devices/{address}/pair", status_code=status.HTTP_202_ACCEPTED,
             response_model=PairStartResponse)
@user_limiter.limit(_LIMIT)
async def pair_device(
    address: str,
    request: Request,
    response: Response,
    current_user=Depends(require_power_manage_bluetooth),
) -> PairStartResponse:
    """Startet eine Kopplung; der Ablauf laeuft im Hintergrund dieses Workers.

    Nur aus privaten Netzen — fuer ALLE Rollen. Ein abgelehnter Versuch von
    aussen wird auditiert: er ist genau das Muster, gegen das diese Pruefung
    steht (gestohlenes Konto plus Funkreichweite).
    """
    def on_finished(device: DeviceInfo, stage: str, error: Optional[str]) -> None:
        _audit("bluetooth_pair", current_user, stage == "succeeded", {
            "address": device.address, "kind": kind_for_icon(device.icon),
            "stage": stage, "error": error,
        })

    try:
        session_id = await service_module.get_bluetooth_service().start_pairing(
            address, current_user.id, _client_host(request), on_finished,
        )
    except ForbiddenError:
        _audit("bluetooth_pair_denied", current_user, False, {"reason": "not_local"})
        raise
    return PairStartResponse(session_id=session_id)


@router.get("/pairing", response_model=Optional[PairingSession])
@user_limiter.limit(_LIMIT)
async def get_pairing(
    request: Request,
    response: Response,
    current_user=Depends(require_power_manage_bluetooth),
) -> Optional[PairingSession]:
    """Die Sitzung des Aufrufers oder ``null`` — fremde Codes sieht niemand."""
    return service_module.get_bluetooth_service().pairing_status(current_user.id)


@router.post("/pairing/{session_id}/confirm")
@user_limiter.limit(_LIMIT)
async def confirm_pairing(
    session_id: str,
    body: ConfirmRequest,
    request: Request,
    response: Response,
    current_user=Depends(require_power_manage_bluetooth),
) -> dict:
    service_module.get_bluetooth_service().answer(
        session_id, current_user.id, "accept" if body.accept else "reject", _client_host(request),
    )
    return {"success": True}


@router.post("/pairing/{session_id}/cancel")
@user_limiter.limit(_LIMIT)
async def cancel_pairing(
    session_id: str,
    request: Request,
    response: Response,
    current_user=Depends(require_power_manage_bluetooth),
) -> dict:
    service_module.get_bluetooth_service().answer(
        session_id, current_user.id, "cancel", _client_host(request),
    )
    return {"success": True}


class BluetoothPlugin(PluginBase):
    """Bundled Plugin fuer Bluetooth."""

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="bluetooth",
            version="1.0.0",
            display_name="Bluetooth",
            description=(
                "Bluetooth-Geraete verbinden, trennen und koppeln — "
                "Controller, Kopfhoerer, Maus und Tastatur."
            ),
            author="Xveyn",
            category="system",
        )

    def get_router(self) -> APIRouter:
        return router

    def get_ui_manifest(self) -> PluginUIManifest:
        """Meldet das Plugin ans Frontend, ohne Nav-Eintrag.

        **Ohne diese Ueberschreibung ist das Feature unsichtbar**:
        ``usePluginEnabled('bluetooth')`` liest genau die Liste der Plugins
        mit aktivem Manifest. Die Bedienung sitzt in der Topbar.
        """
        return PluginUIManifest(enabled=True)
