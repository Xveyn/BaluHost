from app.services.update.changelog_fallback import parse_changelog, notes_since_last_stable_from_changelog

SAMPLE = """# Changelog

---

## [1.36.0] - 2026-06-06

### Added
- thing A

## [1.35.0] - 2026-05-01

### Fixed
- thing B
"""


def test_parse_changelog(tmp_path):
    p = tmp_path / "CHANGELOG.md"
    p.write_text(SAMPLE, encoding="utf-8")
    sections = parse_changelog(str(p))
    assert sections[0].version == "1.36.0"
    assert "thing A" in sections[0].body_markdown
    assert sections[1].version == "1.35.0"


def test_notes_for_current(tmp_path):
    p = tmp_path / "CHANGELOG.md"
    p.write_text(SAMPLE, encoding="utf-8")
    items, since = notes_since_last_stable_from_changelog(str(p), "1.36.0")
    assert items[0].version == "1.36.0"
    assert "thing A" in items[0].body_markdown
    assert since == "1.35.0"


def test_notes_missing_file(tmp_path):
    items, since = notes_since_last_stable_from_changelog(str(tmp_path / "nope.md"), "1.36.0")
    assert items == [] and since is None


def test_ignores_bare_unreleased_header(tmp_path):
    sample = """# Changelog

---

## [Unreleased]

### Added
- in progress thing

## [1.36.0] - 2026-06-06

### Added
- thing A

## [1.35.0] - 2026-05-01

### Fixed
- thing B
"""
    p = tmp_path / "CHANGELOG.md"
    p.write_text(sample, encoding="utf-8")
    sections = parse_changelog(str(p))
    # The bare '## [Unreleased]' header (no ' - date') must not be parsed as
    # a release section -- only the real, dated sections show up.
    assert [s.version for s in sections] == ["1.36.0", "1.35.0"]
    assert all("in progress thing" not in s.body_markdown for s in sections)
