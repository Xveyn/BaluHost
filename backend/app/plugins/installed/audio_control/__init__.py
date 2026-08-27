"""Audiosteuerung — bundled Plugin.

Steuert Pegel, Ausgabegeraet und einzelne Wiedergabe-Streams der KDE-Session
ueber pactl. Laeuft als bundled Plugin im Host-Prozess und damit unter
derselben UID wie die Desktop-Session; ein Sandbox-Plugin kaeme nicht an den
PipeWire-Socket.
"""
# NB: kein ``from __future__ import annotations`` hier (vgl. gpu_power.py).
# Zusammen mit Pydantic v2 + FastAPIs Body-Erkennung durch slowapis
# ``@user_limiter.limit``-Wrapper werden aufgeschobene Annotationen zu
# ForwardRefs, die FastAPI nicht mehr als Pydantic-Modell aufloest — der
# Request-Body wuerde als Query-Parameter fehlinterpretiert und jedes
# PUT liefert 422.
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.api.deps import require_power_control_audio
from app.core.rate_limiter import get_limit, user_limiter
from app.plugins.base import PluginBase, PluginMetadata
from app.plugins.installed.audio_control.models import (
    AudioState,
    DefaultSinkRequest,
    MuteRequest,
    VolumeRequest,
)
from app.plugins.installed.audio_control import service as service_module
from app.schemas.user import UserPublic
from app.services.audit.logger_db import get_audit_logger_db

logger = logging.getLogger(__name__)

router = APIRouter()

_LIMIT = get_limit("audio_control")


def _audit(action: str, user: UserPublic, success: bool, detail: str) -> None:
    """Schreibt einen Audit-Eintrag fuer Zustandsspruenge.

    Bewusst nur fuer Geraetewechsel und Stummschaltung. Pegelaenderungen
    erzeugen selbst mit Entprellung Dutzende Schreibvorgaenge und wuerden das
    Log so zumuellen, dass die interessanten Eintraege darin untergehen.
    """
    audit_logger = get_audit_logger_db()
    audit_logger.log_event(
        event_type="POWER",
        action=action,
        user=user.username,
        resource="audio",
        success=success,
        details={"detail": detail},
    )
    if getattr(user, "role", None) != "admin":
        audit_logger.log_security_event(
            action="delegated_power_action",
            user=user.username,
            resource="control_audio",
            details={"action": action},
            success=True,
        )


async def _apply(ok: bool, message: str, kind: str, target_id: int) -> dict:
    """Uebersetzt ein Backend-Ergebnis in die Antwort.

    Unterscheidet zwei sehr verschiedene Fehlschlaege, die das Backend beide
    nur als ``False`` meldet:

    - **Der Index existiert nicht mehr** — ein Normalfall, weil Streams
      verschwinden, sobald die Wiedergabe endet. Das ist ein 404, damit die UI
      ihre Liste neu laedt.
    - **Der Audio-Stack ist gestoert** — pactl fehlt, laeuft in eine
      Zeitueberschreitung oder PipeWire ist weg. Das ist ein 502.

    Beides als 404 zu melden waere eine Falschaussage: die UI wuerde eine
    Stoerung als veraltete Liste behandeln, und bei der Fehlersuche fuehrt der
    Statuscode auf die falsche Spur. Der zusaetzliche Lesevorgang faellt nur
    auf dem Fehlerpfad an und ist dort billig.
    """
    if ok:
        # `message` stammt roh aus pactl (stdout/stderr) und kann Geraetenamen
        # und Pfade enthalten. Es wird geloggt, aber nie ausgeliefert.
        return {"success": True}

    state = await service_module.get_audio_service().get_state()
    if not state.available:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="Audio nicht erreichbar"
        )

    known = state.sinks if kind == "sink" else state.streams
    if not any(item.id == target_id for item in known):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nicht gefunden")

    logger.warning("Audio-Schreibvorgang fehlgeschlagen (%s %s): %s", kind, target_id, message)
    raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Aktion fehlgeschlagen")


async def _apply_default_sink(ok: bool, message: str, name: str) -> dict:
    """Wie ``_apply``, aber fuer das Standardgeraet (Name statt Index)."""
    if ok:
        return {"success": True}

    state = await service_module.get_audio_service().get_state()
    if not state.available:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="Audio nicht erreichbar"
        )
    if not any(sink.name == name for sink in state.sinks):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nicht gefunden")

    logger.warning("Standardgeraet konnte nicht gesetzt werden (%s): %s", name, message)
    raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Aktion fehlgeschlagen")


@router.get("/state", response_model=AudioState)
@user_limiter.limit(_LIMIT)
async def get_audio_state(
    request: Request,
    response: Response,
    current_user=Depends(require_power_control_audio),
) -> AudioState:
    """Liefert Geraete, Streams und das aktive Standardgeraet in einer Antwort.

    Hinter derselben Berechtigung wie die Schreibrouten: die Stream-Titel
    verraten, was auf dem Desktop gerade laeuft.
    """
    return await service_module.get_audio_service().get_state()


@router.put("/sinks/{sink_id}/volume")
@user_limiter.limit(_LIMIT)
async def set_sink_volume(
    sink_id: int,
    body: VolumeRequest,
    request: Request,
    response: Response,
    current_user=Depends(require_power_control_audio),
) -> dict:
    """Setzt den Pegel eines Ausgabegeraets."""
    ok, message = await service_module.get_audio_service().set_sink_volume(sink_id, body.percent)
    return await _apply(ok, message, "sink", sink_id)


@router.put("/sinks/{sink_id}/mute")
@user_limiter.limit(_LIMIT)
async def set_sink_mute(
    sink_id: int,
    body: MuteRequest,
    request: Request,
    response: Response,
    current_user=Depends(require_power_control_audio),
) -> dict:
    """Schaltet ein Ausgabegeraet stumm oder wieder laut."""
    ok, message = await service_module.get_audio_service().set_sink_mute(sink_id, body.muted)
    _audit("audio_sink_mute", current_user, ok, message)
    return await _apply(ok, message, "sink", sink_id)


@router.put("/default-sink")
@user_limiter.limit(_LIMIT)
async def set_default_sink(
    body: DefaultSinkRequest,
    request: Request,
    response: Response,
    current_user=Depends(require_power_control_audio),
) -> dict:
    """Macht ein Geraet zum Standardausgang.

    Der Name wird **vor** dem Aufruf gegen die gelesene Geraeteliste geprueft.
    Listen-Argumente verhindern zwar eine Shell-Injektion, aber dies ist die
    einzige Stelle, an der eine Client-Zeichenkette ueberhaupt in ein
    pactl-Argument gelangt — und eine Zusicherung, die nur in der Prosa steht
    und nirgends im Code, ist keine.
    """
    service = service_module.get_audio_service()
    state = await service.get_state()
    if not state.available:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="Audio nicht erreichbar"
        )
    if not any(sink.name == body.name for sink in state.sinks):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nicht gefunden")

    ok, message = await service.set_default_sink(body.name)
    _audit("audio_default_sink", current_user, ok, message)
    return await _apply_default_sink(ok, message, body.name)


@router.put("/streams/{stream_id}/volume")
@user_limiter.limit(_LIMIT)
async def set_stream_volume(
    stream_id: int,
    body: VolumeRequest,
    request: Request,
    response: Response,
    current_user=Depends(require_power_control_audio),
) -> dict:
    """Setzt den Pegel eines einzelnen Streams."""
    ok, message = await service_module.get_audio_service().set_stream_volume(
        stream_id, body.percent
    )
    return await _apply(ok, message, "stream", stream_id)


@router.put("/streams/{stream_id}/mute")
@user_limiter.limit(_LIMIT)
async def set_stream_mute(
    stream_id: int,
    body: MuteRequest,
    request: Request,
    response: Response,
    current_user=Depends(require_power_control_audio),
) -> dict:
    """Schaltet einen einzelnen Stream stumm oder wieder laut."""
    ok, message = await service_module.get_audio_service().set_stream_mute(stream_id, body.muted)
    _audit("audio_stream_mute", current_user, ok, message)
    return await _apply(ok, message, "stream", stream_id)


class AudioControlPlugin(PluginBase):
    """Bundled Plugin fuer die Audiosteuerung."""

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="audio_control",
            version="1.0.0",
            display_name="Audiosteuerung",
            description=(
                "Pegel, Ausgabegeraet und Lautstaerke einzelner Anwendungen "
                "der Desktop-Session fernsteuern."
            ),
            author="Xveyn",
            category="system",
        )

    def get_router(self) -> APIRouter:
        return router
