import pytest

from app.services.update.github_releases import (
    GitHubRelease, GitHubReleasesClient, GitHubUnavailable,
    filter_channel, latest_for_channel, notes_since_last_stable, releases_between,
)


from app.services.update.utils import parse_version


def _r(tag, prerelease, body="b"):
    return GitHubRelease(tag=tag, name=tag, body_markdown=body, prerelease=prerelease,
                         published_at=None, url=f"https://x/{tag}")


def test_parse_version_tolerates_non_numeric_headers():
    # "[Unreleased]" sections must not crash the public fallback path.
    assert parse_version("Unreleased") == (0, 0, 0, "")
    assert parse_version("v1.2.x") == (1, 2, 0, "")


def test_releases_between_unknown_current_returns_only_target():
    rels = [_r("v1.36.0", False), _r("v1.35.0", False)]
    # current "1.9.9+dev" isn't a published release → show just the target's notes,
    # not the whole history.
    items = releases_between(rels, newer_than="1.9.9", up_to="1.36.0")
    assert [r.tag for r in items] == ["v1.36.0"]


# Newest-first, like the GitHub API returns.
RELEASES = [
    _r("v1.36.0", False),
    _r("v1.35.1-pre.25", True),
    _r("v1.35.1-pre.24", True),
    _r("v1.35.0", False),
    _r("v1.34.0", False),
]


def test_filter_channel():
    assert len(filter_channel(RELEASES, "unstable")) == 5
    assert [r.tag for r in filter_channel(RELEASES, "stable")] == ["v1.36.0", "v1.35.0", "v1.34.0"]


def test_latest_for_channel():
    assert latest_for_channel(RELEASES, "stable").tag == "v1.36.0"
    assert latest_for_channel(RELEASES, "unstable").tag == "v1.36.0"


def test_notes_since_last_stable_for_prerelease():
    items, since = notes_since_last_stable(RELEASES, "1.35.1-pre.25")
    # current is a pre-release: aggregate from it back to (excl.) the last stable v1.35.0
    assert [r.tag for r in items] == ["v1.35.1-pre.25", "v1.35.1-pre.24"]
    assert since == "v1.35.0"


def test_notes_since_last_stable_for_stable():
    items, since = notes_since_last_stable(RELEASES, "1.36.0")
    # current is stable: its own body already covers since-last-stable
    assert [r.tag for r in items] == ["v1.36.0"]
    assert since == "v1.35.0"


def test_releases_between_current_to_latest():
    # what an update from a pre-release to the latest stable brings
    items = releases_between(RELEASES, newer_than="1.35.1-pre.25", up_to="1.36.0")
    assert [r.tag for r in items] == ["v1.36.0"]


@pytest.mark.asyncio
async def test_list_releases_caches_and_falls_back(monkeypatch):
    client = GitHubReleasesClient(repo="x/y", ttl_seconds=999)
    calls = {"n": 0}

    class _Resp:
        status_code = 200
        def json(self):
            return [{"tag_name": "v1.0.0", "name": "v1.0.0", "body": "hi",
                     "prerelease": False, "published_at": "2026-01-01T00:00:00Z",
                     "html_url": "https://x/v1.0.0"}]

    class _Client:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, *a, **k):
            calls["n"] += 1
            return _Resp()

    monkeypatch.setattr("app.services.update.github_releases.httpx.AsyncClient", _Client)
    first = await client.list_releases()
    second = await client.list_releases()
    assert first[0].tag == "v1.0.0"
    assert calls["n"] == 1  # second served from cache


@pytest.mark.asyncio
async def test_list_releases_raises_unavailable_on_error(monkeypatch):
    import httpx
    client = GitHubReleasesClient(repo="x/y")

    class _Client:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, *a, **k):
            raise httpx.ConnectError("boom")

    monkeypatch.setattr("app.services.update.github_releases.httpx.AsyncClient", _Client)
    with pytest.raises(GitHubUnavailable):
        await client.list_releases()
