from app.schemas.update import ReleaseNoteItem, ReleaseNotesResponse, ReleaseInfo, ChangelogEntry


def test_release_notes_response_shape():
    item = ReleaseNoteItem(version="1.36.0", is_prerelease=False, url="u", body_markdown="### Added\n- x")
    resp = ReleaseNotesResponse(current_version="1.36.0", since_version="1.35.0", source="github", releases=[item])
    assert resp.source == "github"
    assert resp.releases[0].body_markdown.startswith("### Added")


def test_changelog_entry_has_body_markdown():
    e = ChangelogEntry(version="1.36.0", body_markdown="- y")
    assert e.body_markdown == "- y"


def test_release_info_extended_optional_commit():
    r = ReleaseInfo(tag="v1.36.0", version="1.36.0", is_prerelease=False)
    assert r.commit_short is None and r.html_url is None


import pytest
from app.services.update.github_releases import GitHubRelease, GitHubUnavailable
from app.services.update.prod_backend import ProdUpdateBackend


def _gh(tag, pre, body="notes"):
    return GitHubRelease(tag=tag, name=tag, body_markdown=body, prerelease=pre, published_at=None, url=f"https://x/{tag}")


_REL = [_gh("v1.36.0", False), _gh("v1.35.1-pre.25", True), _gh("v1.35.0", False)]


class _FakeVersion:
    def __init__(self, v): self.version = v; self.commit = "c"; self.commit_short = "c"; self.tag = "v"+v; self.date = None


@pytest.mark.asyncio
async def test_get_release_notes_github(monkeypatch):
    b = ProdUpdateBackend()
    async def _ver(): return _FakeVersion("1.35.1-pre.25")
    monkeypatch.setattr(b, "get_current_version", _ver)
    async def fake_list(*a, **k): return _REL
    monkeypatch.setattr(b._gh, "list_releases", fake_list)
    notes = await b.get_release_notes()
    assert notes.source == "github"
    assert [r.version for r in notes.releases] == ["1.35.1-pre.25"]  # since v1.35.0


@pytest.mark.asyncio
async def test_get_release_notes_falls_back_to_changelog(monkeypatch, tmp_path):
    cl = tmp_path / "CHANGELOG.md"
    cl.write_text("# Changelog\n\n## [1.36.0] - 2026-06-06\n\n### Added\n- a\n", encoding="utf-8")
    from app.core.config import settings
    monkeypatch.setattr(settings, "update_changelog_path", str(cl))
    b = ProdUpdateBackend()
    async def _ver(): return _FakeVersion("1.36.0")
    monkeypatch.setattr(b, "get_current_version", _ver)
    async def boom(*a, **k): raise GitHubUnavailable("down")
    monkeypatch.setattr(b._gh, "list_releases", boom)
    notes = await b.get_release_notes()
    assert notes.source == "changelog"
    assert notes.releases[0].version == "1.36.0"


@pytest.mark.asyncio
async def test_check_for_updates_github(monkeypatch):
    b = ProdUpdateBackend()
    async def _ver(): return _FakeVersion("1.35.1-pre.25")
    monkeypatch.setattr(b, "get_current_version", _ver)
    async def fake_list(*a, **k): return _REL
    monkeypatch.setattr(b._gh, "list_releases", fake_list)
    available, latest, changelog = await b.check_for_updates("stable")
    assert available is True and latest.version == "1.36.0"
    assert changelog and changelog[0].body_markdown == "notes"


def test_dev_endpoints_and_fields_removed():
    import app.schemas.update as u
    assert not hasattr(u, "DevUpdateStartRequest")
    from app.api.routes import updates as r
    # No start-dev route registered
    paths = [getattr(rt, "path", "") for rt in r.router.routes]
    assert not any(p.endswith("/start-dev") for p in paths)
