"""Tests for plugin sandbox asset serving: CORS, host.html bootstrap, framable headers.

All three tests patch the enabled-checks so the route reaches its serving branch
and returns 200.  Assertions are UNCONDITIONAL — no ``if status == 200`` guards
that can silently skip when the plugin has no DB record (which is always the case
for the TestClient's fresh in-memory DB).

Patching strategy
-----------------
``serve_plugin_asset`` gates on two checks (logical OR):

    db_record = plugin_service.get_enabled_plugin(db, name)  # DB path
    if not db_record and not plugin_manager.is_enabled(name): raise 404

Patching ``app.services.plugin_service.get_enabled_plugin`` to return a truthy
sentinel makes the guard pass without touching the DB or the PluginManager
singleton.

For host.html the route also calls ``load_manifest`` (imported locally inside
the handler body): ``from app.plugins.manifest import load_manifest``.  We patch
the function at its *definition* module (``app.plugins.manifest.load_manifest``)
so the local import picks up the stub.

For the static-asset (bundle.js) test, ``storage_analytics/ui/bundle.js`` is a
real bundled file that ships with the repo — no extra fixture needed.
"""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from app.main import app
    return TestClient(app)


# ---------------------------------------------------------------------------
# 1. CORS header on a static UI asset
# ---------------------------------------------------------------------------

def test_ui_asset_has_permissive_cors(client):
    """ui/ assets must carry Access-Control-Allow-Origin: * for the opaque-origin sandbox."""
    fake_record = MagicMock()  # truthy — makes the enabled-guard pass
    with patch("app.services.plugin_service.get_enabled_plugin", return_value=fake_record):
        resp = client.get("/api/plugins/storage_analytics/ui/bundle.js")

    # The bundle.js file ships in the repo, so the route resolves to 200.
    assert resp.status_code == 200, (
        f"Expected 200 from serve_plugin_asset; got {resp.status_code}. "
        "Check that backend/app/plugins/installed/storage_analytics/ui/bundle.js exists."
    )
    assert resp.headers.get("access-control-allow-origin") == "*", (
        "Static plugin assets must carry CORS: * so the opaque-origin sandbox iframe "
        "can import them via ES dynamic import."
    )


# ---------------------------------------------------------------------------
# 2. host.html bootstrap document structure
# ---------------------------------------------------------------------------

def test_host_html_bootstrap_served(client):
    """host.html must contain plugin-runtime.js src, plugin-bundle meta, and be text/html."""
    fake_record = MagicMock()

    # Build a fake manifest whose ui.bundle matches what the route uses.
    fake_ui = MagicMock()
    fake_ui.bundle = "ui/bundle.js"
    fake_manifest = MagicMock()
    fake_manifest.ui = fake_ui

    with patch("app.services.plugin_service.get_enabled_plugin", return_value=fake_record), \
         patch("app.plugins.manifest.load_manifest", return_value=fake_manifest):
        resp = client.get("/api/plugins/storage_analytics/ui/host.html")

    assert resp.status_code == 200, (
        f"Expected 200 from host.html handler; got {resp.status_code}."
    )
    body = resp.text
    assert "plugin-runtime.js" in body, "host.html must include a <script src='/plugin-runtime.js'>"
    assert 'name="plugin-bundle"' in body, "host.html must include the plugin-bundle <meta> tag"
    assert resp.headers.get("content-type", "").startswith("text/html"), (
        f"host.html must have content-type text/html, got: {resp.headers.get('content-type')}"
    )


# ---------------------------------------------------------------------------
# 3. host.html security headers — framable by same-origin, not globally DENYed
# ---------------------------------------------------------------------------

def test_host_html_is_framable_same_origin(client):
    """The sandbox bootstrap MUST be framable by our own SPA.

    The global SecurityHeadersMiddleware sets ``X-Frame-Options: DENY`` for all
    responses, but the middleware has a carve-out for ``/api/plugins/*/ui/host.html``
    that preserves the route's own framability headers instead.
    """
    fake_record = MagicMock()

    fake_ui = MagicMock()
    fake_ui.bundle = "ui/bundle.js"
    fake_manifest = MagicMock()
    fake_manifest.ui = fake_ui

    with patch("app.services.plugin_service.get_enabled_plugin", return_value=fake_record), \
         patch("app.plugins.manifest.load_manifest", return_value=fake_manifest):
        resp = client.get("/api/plugins/storage_analytics/ui/host.html")

    assert resp.status_code == 200, (
        f"Expected 200 from host.html handler; got {resp.status_code}."
    )
    xfo = resp.headers.get("x-frame-options", "DENY").upper()
    assert xfo != "DENY", (
        f"host.html must NOT carry X-Frame-Options: DENY (got {xfo!r}). "
        "The middleware carve-out in security_headers.py must skip the global DENY."
    )
    csp = resp.headers.get("content-security-policy", "")
    assert "frame-ancestors" in csp, (
        f"host.html CSP must contain 'frame-ancestors' to allow same-origin framing. "
        f"Got CSP: {csp!r}"
    )
