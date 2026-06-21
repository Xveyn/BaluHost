"""Lock the nginx auth_limit rate (audit HÄRTUNG follow-up).

The deployed nginx config (module 11 renders baluhost-nginx-http.conf) had
`auth_limit ... rate=10r/s` (= 600/min) on /api/auth/ — effectively no brute-force
guard at the edge. It must be the intended 5 req/min. The reference configs under
deploy/nginx/ must not reintroduce the 10r/s value either.
"""
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_DEPLOYED = _REPO / "deploy" / "install" / "templates" / "baluhost-nginx-http.conf"
_REFERENCES = [
    _REPO / "deploy" / "nginx" / "baluhost-http.conf",
    _REPO / "deploy" / "nginx" / "baluhost-https.conf",
]


def test_deployed_template_auth_limit_is_5_per_min():
    text = _DEPLOYED.read_text(encoding="utf-8")
    assert "zone=auth_limit:10m rate=5r/m" in text, (
        "deployed nginx auth_limit must be rate=5r/m (brute-force guard)"
    )


def test_deployed_template_has_no_10rs_auth_limit():
    text = _DEPLOYED.read_text(encoding="utf-8")
    assert "zone=auth_limit:10m rate=10r/s" not in text, (
        "auth_limit must not be 10r/s (600/min — no real brute-force protection)"
    )


def test_reference_configs_do_not_reintroduce_10rs_auth_limit():
    for cfg in _REFERENCES:
        if not cfg.is_file():
            continue
        text = cfg.read_text(encoding="utf-8")
        assert "zone=auth_limit:10m rate=10r/s" not in text, (
            f"{cfg.name} reintroduced auth_limit rate=10r/s"
        )
