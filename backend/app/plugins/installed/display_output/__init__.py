"""Displaysteuerung — bundled Plugin.

Enumeriert die KWin-Ausgaenge und setzt Auswahl und Video-Modus ueber
kscreen-doctor. Laeuft als bundled Plugin im Host-Prozess und damit unter
derselben UID wie die Desktop-Session; ein Sandbox-Plugin kaeme nicht an den
Wayland-Socket.
"""
# NB: kein ``from __future__ import annotations`` hier (vgl. audio_control).
# Zusammen mit Pydantic v2 + FastAPIs Body-Erkennung durch slowapis
# ``@user_limiter.limit``-Wrapper werden aufgeschobene Annotationen zu
# ForwardRefs, die FastAPI nicht mehr als Pydantic-Modell aufloest — der
# Request-Body wuerde als Query-Parameter fehlinterpretiert und jedes
# POST liefert 422.
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.api.deps import require_power_manage_displays
from app.core.rate_limiter import get_limit, user_limiter
from app.plugins.base import PluginBase, PluginMetadata, PluginUIManifest
from app.plugins.installed.display_output import service as service_module
from app.plugins.installed.display_output.models import DisplayApplyRequest, DisplayLayout
from app.plugins.installed.display_output.service import (
    DisplayUnavailable,
    InvalidRequest,
    ModeMismatch,
)
from app.schemas.user import UserPublic
from app.services.audit.logger_db import get_audit_logger_db

logger = logging.getLogger(__name__)

router = APIRouter()

_LIMIT = get_limit("display_output")


def _audit(user: UserPublic, success: bool, wanted: dict) -> None:
    """Schreibt einen Audit-Eintrag fuer jede Aenderung der Ausgangswahl.

    Anders als bei den Pegeln der Audiosteuerung ist hier jeder Vorgang
    interessant: ein apply schaltet Bildschirme.
    """
    audit_logger = get_audit_logger_db()
    audit_logger.log_event(
        event_type="POWER",
        action="display_apply",
        user=user.username,
        resource="displays",
        success=success,
        details={"wanted": {k: list(v) for k, v in wanted.items()}},
    )
    if getattr(user, "role", None) != "admin":
        audit_logger.log_security_event(
            action="delegated_power_action",
            user=user.username,
            resource="manage_displays",
            details={"action": "display_apply"},
            success=True,
        )


@router.get("/state", response_model=DisplayLayout)
@user_limiter.limit(_LIMIT)
async def get_display_state(
    request: Request,
    response: Response,
    current_user=Depends(require_power_manage_displays),
) -> DisplayLayout:
    """Liefert alle Ausgaenge, ihre Modi und den globalen DPMS-Zustand.

    Hinter derselben Berechtigung wie die Schreibroute: die Ausgangsliste
    verraet die angeschlossene Hardware samt EDID-Groessenangaben.

    Eine unerreichbare Session ist hier **kein** Fehler, sondern
    ``available=false`` — die UI soll das anzeigen koennen, statt nur eine
    Fehlermeldung zu bekommen.
    """
    return await service_module.get_display_service().get_layout()


@router.post("/apply")
@user_limiter.limit(_LIMIT)
async def apply_display_layout(
    body: DisplayApplyRequest,
    request: Request,
    response: Response,
    current_user=Depends(require_power_manage_displays),
) -> dict:
    """Setzt Auswahl und Modus in genau einem kscreen-doctor-Aufruf.

    Jeder Name und jede Mode-ID aus dem Rumpf wird zuvor gegen die live
    enumerierten Werte **dieses** Ausgangs geprueft (im Service). Was dort
    nicht steht, wird nie zu einem argv-Element.
    """
    service = service_module.get_display_service()
    wanted = {o.name: (o.selected, o.mode_id) for o in body.outputs}
    try:
        ok, message = await service.apply(body)
    except InvalidRequest as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except ModeMismatch as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except DisplayUnavailable:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="Displays nicht erreichbar"
        )

    _audit(current_user, ok, wanted)

    if ok:
        return {"success": True}

    # `message` stammt roh aus kscreen-doctor und kann EDID-Namen und Pfade
    # enthalten. Es wird geloggt, aber nie ausgeliefert.
    logger.warning("Display-Anwendung fehlgeschlagen: %s", message)
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY, detail="Aktion fehlgeschlagen"
    )


class DisplayOutputPlugin(PluginBase):
    """Bundled Plugin fuer die Displaysteuerung."""

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="display_output",
            version="1.0.0",
            display_name="Displaysteuerung",
            description=(
                "Angeschlossene Bildschirme erkennen, den Ausgang waehlen und "
                "Aufloesung samt Bildwiederholrate setzen."
            ),
            author="Xveyn",
            category="system",
        )

    def get_router(self) -> APIRouter:
        return router

    def get_ui_manifest(self) -> PluginUIManifest:
        """Meldet das Plugin ans Frontend, ohne einen Nav-Eintrag beizusteuern.

        **Ohne diese Ueberschreibung ist das Feature unsichtbar.**
        ``PluginBase`` liefert hier ``None``, und
        ``PluginManager.get_ui_manifest()`` nimmt nur Plugins mit einem aktiven
        Manifest in ``/api/plugins/ui/manifest`` auf — genau die Liste, aus der
        ``usePluginEnabled`` speist. Ohne Manifest gilt das Plugin dort
        dauerhaft als abgeschaltet, und die Topbar rendert das Monitor-Symbol
        nie: kein Fehler, keine Logzeile.

        ``nav_items`` bleibt leer: die Bedienung sitzt in der Topbar. Ein
        leeres ``nav_items`` erzeugt keine Route, also wird auch kein
        ``bundle.js`` nachgeladen.
        """
        return PluginUIManifest(enabled=True)
