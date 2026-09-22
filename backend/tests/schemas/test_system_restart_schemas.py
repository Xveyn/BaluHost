"""Tests für die Schemas des Sammelneustarts."""
from app.schemas.system import (
    SystemRestartAllRequest,
    SystemRestartAllResponse,
    UnitRestartResult,
)


def test_request_accepts_password_only():
    assert SystemRestartAllRequest(current_password="geheim").code is None


def test_request_accepts_code_only():
    assert SystemRestartAllRequest(code="123456").current_password is None


def test_request_accepts_neither():
    """Ein leerer Body ist kein 422, sondern ein gescheiterter Step-up (401).

    Ein Validierungsfehler wäre ein zweiter Fehlerpfad für dieselbe Sache.
    """
    payload = SystemRestartAllRequest()
    assert payload.current_password is None and payload.code is None


def test_response_carries_per_unit_results():
    response = SystemRestartAllResponse(
        units=[UnitRestartResult(name="baluhost-webdav", success=False, message="boom")],
        backend_restart_scheduled=True,
        eta_seconds=1,
        initiated_by="admin",
    )
    assert response.units[0].success is False
    assert response.backend_restart_scheduled is True
