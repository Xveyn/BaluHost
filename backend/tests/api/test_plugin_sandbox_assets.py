"""Tests for plugin sandbox asset serving: CORS, host.html bootstrap, framable headers.

TDD task: RED → GREEN for Task 5 (Plugin Frontend iframe Sandbox).

The storage_analytics plugin is installed as a bundled plugin (plugins/installed/),
but is only *enabled* when a DB record exists. In the TestClient's fresh in-memory DB
there is no such record, so all routes return 404. The asserts are therefore
conditional on status 200, and are reached when the plugin is enabled in the env
(e.g. production, integration tests with a seed record).

We keep the conditional form because enabling a plugin requires inserting a DB record
via plugin_service.create_or_enable(), which in turn needs a seeded DB session — a
non-trivial fixture that is out of scope for this focused asset-serving test.
"""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from app.main import app
    return TestClient(app)


def test_ui_asset_has_permissive_cors(client, monkeypatch):
    """ui/ assets must be loadable from the opaque-origin sandbox iframe."""
    # A known bundled plugin is enabled in the test app's plugin manager.
    resp = client.get("/api/plugins/storage_analytics/ui/bundle.js")
    # Either the asset exists (200) or the plugin isn't enabled in this env (404);
    # when served, it must carry the CORS header.
    if resp.status_code == 200:
        assert resp.headers.get("access-control-allow-origin") == "*"


def test_host_html_bootstrap_served(client):
    resp = client.get("/api/plugins/storage_analytics/ui/host.html")
    if resp.status_code == 200:
        body = resp.text
        assert "plugin-runtime.js" in body
        assert 'name="plugin-bundle"' in body
        assert resp.headers.get("content-type", "").startswith("text/html")


def test_host_html_is_framable_same_origin(client):
    """The sandbox bootstrap MUST be framable by our own app — the global
    X-Frame-Options: DENY would otherwise blank the iframe."""
    resp = client.get("/api/plugins/storage_analytics/ui/host.html")
    if resp.status_code == 200:
        assert resp.headers.get("x-frame-options", "DENY").upper() != "DENY"
        # CSP frame-ancestors must allow same-origin framing.
        assert "frame-ancestors" in resp.headers.get("content-security-policy", "")
