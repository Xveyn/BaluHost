"""Lock the prod backend's uvicorn proxy-header trust config (audit #9 follow-up).

Behind nginx (proxy_pass -> 127.0.0.1:8000), uvicorn must honor X-Forwarded-For
so request.client.host is the real client IP — otherwise the per-IP rate limiter
and audit logs all see 127.0.0.1. The trust MUST be pinned to the local nginx
upstream to prevent X-Forwarded-For spoofing.
"""
from pathlib import Path

_TEMPLATE = (
    Path(__file__).resolve().parents[2]
    / "deploy" / "install" / "templates" / "baluhost-backend.service"
)


def test_template_exists():
    assert _TEMPLATE.is_file(), f"systemd template missing: {_TEMPLATE}"


def test_proxy_headers_enabled():
    text = _TEMPLATE.read_text(encoding="utf-8")
    assert "--proxy-headers" in text, "uvicorn must run with --proxy-headers behind nginx"


def test_forwarded_allow_ips_pinned_to_localhost():
    text = _TEMPLATE.read_text(encoding="utf-8")
    # Trust pin: only the local nginx upstream may set X-Forwarded-For.
    assert "--forwarded-allow-ips=127.0.0.1" in text, (
        "X-Forwarded-For trust must be pinned to 127.0.0.1 (anti-spoofing)"
    )
