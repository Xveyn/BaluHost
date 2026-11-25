from app.core.rate_limiter import RATE_LIMITS


def test_file_upload_limit_is_realistic():
    """50000/min was effectively unlimited (DoS path). 300/min is plenty for the
    web file manager while bounding abuse."""
    assert RATE_LIMITS["file_upload"] == "300/minute"


def test_file_chunked_stays_high_for_per_chunk_puts():
    """file_chunked gates every chunk PUT, so it must stay high — do not slash it."""
    count = int(RATE_LIMITS["file_chunked"].split("/")[0])
    assert count >= 10000


def test_system_restart_is_strict():
    """/api/system/restart-all nimmt ein Passwort entgegen.

    admin_operations (30/minute) wäre dafür zu locker. Was dieser Wert NICHT
    ist: derselbe Schutz wie auth_password_change — jene Route liegt zusätzlich
    hinter nginx' auth_limit (5 r/m), diese nicht. Und der Limiter lebt im
    Prozessspeicher, den der Endpunkt selbst neu startet. Siehe security-agent.md.
    """
    assert RATE_LIMITS["system_restart"] == "5/minute"


def test_session_handoff_limits_are_registered():
    """Ohne Eintrag faellt get_limit() fuer die Handoff-Routen auf einen
    Standard zurueck, der nicht fuer sie gedacht ist (#847)."""
    assert RATE_LIMITS["auth_handoff"] == "10/minute"
    assert RATE_LIMITS["auth_handoff_redeem"] == "10/minute"


def test_session_handoff_limits_are_seeded(db_session):
    """Die Admin-UI zeigt nur, was seed_defaults anlegt."""
    from app.models.rate_limit_config import RateLimitConfig
    from app.services.rate_limit_config import RateLimitConfigService

    RateLimitConfigService.seed_defaults(db_session)

    seeded = {
        c.endpoint_type: c.limit_string
        for c in db_session.query(RateLimitConfig).all()
    }
    assert seeded.get("auth_handoff") == RATE_LIMITS["auth_handoff"]
    assert seeded.get("auth_handoff_redeem") == RATE_LIMITS["auth_handoff_redeem"]
