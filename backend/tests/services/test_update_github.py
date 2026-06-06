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
