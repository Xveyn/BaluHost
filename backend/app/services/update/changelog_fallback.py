"""Offline fallback: parse the bundled CHANGELOG.md into release-note items.

Used when the GitHub Releases API is unavailable. CHANGELOG.md mainly holds
stable sections (`## [x.y.z] - date`), so this is a degraded-but-non-empty mode.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.schemas.update import ReleaseNoteItem
from app.services.update.utils import parse_version

_SECTION_RE = re.compile(r"^##\s*\[(?P<ver>[^\]]+)\]\s*-\s*(?P<date>\S+)", re.MULTILINE)


@dataclass
class ChangelogSection:
    version: str
    date: Optional[str]
    body_markdown: str


def parse_changelog(path: str) -> list[ChangelogSection]:
    """Parse `## [x.y.z] - date` sections (in file order = newest first)."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return []
    matches = list(_SECTION_RE.finditer(text))
    sections: list[ChangelogSection] = []
    for i, m in enumerate(matches):
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[body_start:body_end].strip()
        sections.append(ChangelogSection(version=m.group("ver").strip(),
                                         date=m.group("date").strip(), body_markdown=body))
    return sections


def _to_dt(date_str: Optional[str]) -> Optional[datetime]:
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def notes_since_last_stable_from_changelog(
    path: str, up_to_version: str
) -> tuple[list[ReleaseNoteItem], Optional[str]]:
    """Return CHANGELOG sections from `up_to_version` (inclusive) down to the next
    older section, as ReleaseNoteItems. Degraded fallback (stable-only)."""
    sections = parse_changelog(path)
    if not sections:
        return [], None
    target = parse_version(up_to_version)
    idx = next((i for i, s in enumerate(sections) if parse_version(s.version) == target), None)
    if idx is None:
        # Unknown current version (e.g. a pre-release not in CHANGELOG): show the newest section.
        idx = 0
    item = sections[idx]
    since = sections[idx + 1].version if idx + 1 < len(sections) else None
    return (
        [ReleaseNoteItem(version=item.version, date=_to_dt(item.date), is_prerelease=False,
                         url=None, body_markdown=item.body_markdown)],
        since,
    )
