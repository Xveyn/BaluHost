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
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.api.deps import require_power_manage_displays
from app.core.exceptions import BadGatewayError
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


def _audit(
    user: UserPublic,
    success: bool,
    *,
    status_code: int,
    argv: Optional[List[str]] = None,
    detail: str = "",
) -> None:
    """Schreibt einen Audit-Eintrag fuer JEDEN apply-Versuch — Erfolg wie Ablehnung.

    Fruher wurde nur der rohe, ungeprueften Request-Wunsch protokolliert
    (``{name: (selected, mode_id)}``); das verzeichnete auch eine mode_id auf
    einem ``selected: false``-Ausgang, obwohl der Service diese Kombination
    verwirft — der Eintrag behauptete damit einen Modus-Wechsel, der nie
    stattfand. Und eine Ablehnung (400/409/502) schrieb ueberhaupt keinen
    Eintrag, weil alle drei Ausnahmen vor dieser Funktion auslösten — dabei
    schaltet diese Route physische Bildschirme, ein abgelehnter Versuch
    gehoert in die Spur.

    ``argv`` ist — bei Erfolg oder einem Fehlschlag NACH der Validierung —
    genau der Vektor, den der Service tatsaechlich geprueft (und bei
    ``KWinDisplayBackend`` an kscreen-doctor geschickt) hat. Bei einer
    Ablehnung VOR dem Bau des Vektors (400/409/502 aus der Validierung) bleibt
    ``argv`` ``None`` — es gibt keinen geprueften Vektor, ueber den sich etwas
    Wahres aussagen liesse.

    ``detail`` darf hier mehr tragen als die Client-Antwort: der Audit-Trail
    ist serverseitig, die Regel "kein rohes kscreen-doctor-stdout/stderr zum
    Client" gilt fuer die HTTP-Antwort, nicht fuer das Log.
    """
    audit_logger = get_audit_logger_db()
    audit_logger.log_event(
        event_type="POWER",
        action="display_apply",
        user=user.username,
        resource="displays",
        success=success,
        details={"status_code": status_code, "argv": argv, "detail": detail},
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

    Jeder Ausgang dieser Funktion schreibt einen Audit-Eintrag — Erfolg UND
    Ablehnung. ``details.argv`` traegt den vom Service tatsaechlich
    geprueften Vektor (siehe ``ApplyResult``), nicht den rohen Request.
    """
    service = service_module.get_display_service()
    try:
        result = await service.apply(body)
    except InvalidRequest as exc:
        _audit(current_user, False, status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except ModeMismatch as exc:
        _audit(current_user, False, status_code=status.HTTP_409_CONFLICT, detail=str(exc))
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except DisplayUnavailable as exc:
        # BadGatewayError statt HTTPException(502): der globale 5xx-Scrubber in
        # ``core/exception_handlers.py`` ersetzt jedes HTTPException-detail ab
        # Status 500 durch "Internal server error". Nur ein ServiceError
        # transportiert eine kuratierte Meldung durch diesen Filter.
        _audit(
            current_user, False,
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc),
        )
        raise BadGatewayError("Displays nicht erreichbar") from exc

    if result.success:
        _audit(
            current_user, True,
            status_code=status.HTTP_200_OK, argv=result.argv, detail=result.message,
        )
        return {"success": True}

    # `result.message` stammt roh aus kscreen-doctor und kann EDID-Namen und
    # Pfade enthalten. Sie wird geloggt und in den (serverseitigen) Audit-
    # Eintrag geschrieben, aber nie an den Client ausgeliefert.
    # BadGatewayError statt HTTPException(502): siehe Kommentar oben beim
    # DisplayUnavailable-Zweig.
    _audit(
        current_user, False,
        status_code=status.HTTP_502_BAD_GATEWAY, argv=result.argv, detail=result.message,
    )
    logger.warning("Display-Anwendung fehlgeschlagen: %s", result.message)
    raise BadGatewayError("Aktion fehlgeschlagen")


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
