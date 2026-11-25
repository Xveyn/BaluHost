"""A paired device must be able to refresh — today it cannot.

poll_device_code hands out a refresh token whose jti it throws away, and
/auth/refresh treats an unknown jti as revoked. The pairing therefore dies
with the access token.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import jwt as pyjwt

from app.models.desktop_pairing import DesktopPairingCode
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.services import desktop_pairing
from app.services.desktop_pairing import DesktopPairingService


def test_pairing_stores_the_refresh_token_jti():
    """Der jti muss in der RefreshToken-Tabelle landen, sonst ist er wertlos.

    Minimum-Regressionstest laut Brief: stubbt store_refresh_token und prueft
    die uebergebenen kwargs. Bleibt gruen, wenn der jti verworfen wird, aber
    NICHT, wenn der Produktionsaufruf Pflichtfelder (token/expires_at)
    vergisst — dafuer sind die letzten beiden Assertions da.
    """
    stored = {}

    def _capture(db, **kwargs):
        stored.update(kwargs)
        return MagicMock()

    with patch(
        "app.services.refresh_rotation.create_refresh_token",
        return_value=("rt", "jti-123"),
    ), patch(
        "app.services.desktop_pairing.create_access_token", return_value="at"
    ), patch(
        "app.services.refresh_rotation.token_service.store_refresh_token",
        side_effect=_capture,
    ):
        desktop_pairing._issue_tokens(
            db=MagicMock(),
            user=MagicMock(id=5),
            device_id="dev-1",
        )

    assert stored.get("jti") == "jti-123"
    assert stored.get("user_id") == 5
    assert stored.get("device_id") == "dev-1"
    # Pflichtfelder der echten Signatur — ohne sie wirft die Produktion einen
    # TypeError, waehrend ein kwargs-Stub gruen bleibt. Genau der Fehlertyp,
    # den ein TDD-Plan nicht durchlassen darf.
    assert stored.get("token") == "rt"
    assert stored.get("expires_at") is not None


def test_poll_device_code_persists_the_refresh_token_row(db_session, regular_user: User):
    """End-to-end gegen die echte Test-DB: kein Stub kann hier einen
    Signaturfehler (z.B. fehlendes `token`/`expires_at`) verschleiern, weil
    store_refresh_token tatsaechlich ausgefuehrt wird.
    """
    device_id = "dev-real-1"
    pairing = DesktopPairingCode(
        device_code="device-code-real-1",
        user_code="654321",
        device_name="Test Desktop",
        device_id=device_id,
        platform="linux",
        status="approved",
        user_id=regular_user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    db_session.add(pairing)
    db_session.commit()

    response = DesktopPairingService.poll_device_code(db_session, "device-code-real-1")

    assert response.status == "approved"
    assert response.refresh_token is not None

    # Decode without verifying the signature just to read the jti claim — the
    # point here is the DB row, not re-testing JWT encoding.
    claims = pyjwt.decode(response.refresh_token, options={"verify_signature": False})
    jti = claims["jti"]

    stored = (
        db_session.query(RefreshToken)
        .filter(RefreshToken.jti == jti)
        .first()
    )

    assert stored is not None, "poll_device_code must persist the refresh token it hands out"
    assert stored.user_id == regular_user.id
    assert stored.device_id == device_id
    assert stored.token_hash == RefreshToken.hash_token(response.refresh_token)
    assert stored.revoked is False


def _approved(db, user: User, device_id: str, code: str) -> None:
    db.add(
        DesktopPairingCode(
            device_code=code,
            user_code=code[-6:],
            device_name="Tray",
            device_id=device_id,
            platform="linux",
            status="approved",
            user_id=user.id,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        )
    )
    db.commit()


def test_repairing_revokes_the_previous_chain(client, db_session, regular_user: User):
    """Das Tray nimmt die machine-id als device_id; jedes --pair verwendet sie
    wieder. Mit gleitender Rotation lebte die alte Kette sonst ewig (#847, I2)."""
    from app.core.config import settings
    from app.services import refresh_rotation

    refresh_url = f"{settings.api_prefix}/auth/refresh"
    device_id = "machine-id-1"

    _approved(db_session, regular_user, device_id, "device-code-first-000001")
    old = DesktopPairingService.poll_device_code(db_session, "device-code-first-000001")
    old_token = old.refresh_token
    # alte Kette in die zweite Lebenshaelfte schieben, damit sie rotieren koennte
    old_jti = pyjwt.decode(old_token, options={"verify_signature": False})["jti"]
    row = db_session.query(RefreshToken).filter(RefreshToken.jti == old_jti).one()
    row.expires_at = datetime.now(timezone.utc) + timedelta(days=1)
    db_session.commit()
    # Tokens derselben device_id eines anderen Nutzers bleiben unberuehrt
    other = refresh_rotation.issue_device_refresh_token(
        db_session,
        db_session.query(User).filter(User.id != regular_user.id).first(),
        device_id,
    )

    _approved(db_session, regular_user, device_id, "device-code-second-00002")
    new = DesktopPairingService.poll_device_code(db_session, "device-code-second-00002")

    db_session.expire_all()
    row = db_session.query(RefreshToken).filter(RefreshToken.jti == old_jti).one()
    assert row.revoked is True
    assert row.revocation_reason == "repaired"
    r = client.post(refresh_url, json={"refresh_token": old_token, "rotate": True})
    assert r.status_code == 401
    assert client.post(refresh_url, json={"refresh_token": new.refresh_token}).status_code == 200
    assert client.post(refresh_url, json={"refresh_token": other}).status_code == 200
