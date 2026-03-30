"""Service for loading and serving project documentation as manual articles."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from app.schemas.docs import DocsArticleInfo, DocsArticleResponse, DocsGroupInfo

logger = logging.getLogger(__name__)

_SUPPORTED_LANGS = {"de", "en"}
_FALLBACK_LANG = "de"


class DocsService:
    """Loads manual-index.json and serves markdown articles from the docs/ directory."""

    def __init__(self, docs_dir: Path | None = None) -> None:
        if docs_dir is None:
            docs_dir = Path(__file__).resolve().parent.parent.parent.parent / "docs"
        self._docs_dir = docs_dir
        self._index_path = self._docs_dir / "manual-index.json"
        self._cached_raw: dict | None = None
        self._cached_mtime: float = 0.0
        self._slug_map: dict[str, dict] = {}

    def _load_index(self) -> dict:
        try:
            mtime = self._index_path.stat().st_mtime
        except FileNotFoundError:
            logger.warning("manual-index.json not found at %s", self._index_path)
            return {"groups": []}

        if self._cached_raw is not None and mtime == self._cached_mtime:
            return self._cached_raw

        raw = json.loads(self._index_path.read_text(encoding="utf-8"))
        self._cached_raw = raw
        self._cached_mtime = mtime
        self._rebuild_slug_map(raw)
        return raw

    def _rebuild_slug_map(self, raw: dict) -> None:
        slug_map: dict[str, dict] = {}
        for group in raw.get("groups", []):
            group_id = group.get("id", "")
            group_vis = group.get("visibility", "all")
            safe_articles = []
            for article in group.get("articles", []):
                path = article.get("path", "")
                if ".." in path.split("/"):
                    logger.warning("Rejected article with path traversal: %s", path)
                    continue
                slug = article.get("slug", "")
                if not slug:
                    continue
                slug_map[slug] = {
                    "path": path,
                    "group_id": group_id,
                    "group_visibility": group_vis,
                    "titleDe": article.get("titleDe", slug),
                    "titleEn": article.get("titleEn", slug),
                    "icon": article.get("icon", "file-text"),
                }
                safe_articles.append(article)
            group["articles"] = safe_articles
        self._slug_map = slug_map

    def _resolve_lang(self, lang: str) -> str:
        code = lang.split("-")[0].lower() if lang else _FALLBACK_LANG
        return code if code in _SUPPORTED_LANGS else _FALLBACK_LANG

    def get_index(self, lang: str, is_admin: bool) -> list[DocsGroupInfo]:
        raw = self._load_index()
        resolved = self._resolve_lang(lang)

        label_key = f"label{'En' if resolved == 'en' else 'De'}"
        title_key = f"title{'En' if resolved == 'en' else 'De'}"

        groups: list[DocsGroupInfo] = []
        for g in sorted(raw.get("groups", []), key=lambda x: x.get("order", 99)):
            if g.get("visibility") == "admin" and not is_admin:
                continue
            articles = [
                DocsArticleInfo(
                    slug=a["slug"],
                    title=a.get(title_key, a.get("titleDe", a["slug"])),
                    icon=a.get("icon", "file-text"),
                )
                for a in sorted(g.get("articles", []), key=lambda x: x.get("order", 99))
            ]
            groups.append(DocsGroupInfo(
                id=g["id"],
                label=g.get(label_key, g.get("labelDe", g["id"])),
                icon=g.get("icon", "folder"),
                articles=articles,
            ))
        return groups

    def get_article(self, slug: str, lang: str, is_admin: bool) -> Optional[DocsArticleResponse]:
        self._load_index()
        meta = self._slug_map.get(slug)
        if meta is None:
            return None

        if meta["group_visibility"] == "admin" and not is_admin:
            return None

        resolved = self._resolve_lang(lang)
        title_key = f"title{'En' if resolved == 'en' else 'De'}"

        article_path = self._docs_dir / f"{meta['path']}.{resolved}.md"
        if not article_path.is_file() and resolved != _FALLBACK_LANG:
            article_path = self._docs_dir / f"{meta['path']}.{_FALLBACK_LANG}.md"

        if not article_path.is_file():
            logger.warning("Article file not found: %s", article_path)
            return None

        content = article_path.read_text(encoding="utf-8")
        return DocsArticleResponse(
            content=content,
            title=meta.get(title_key, meta.get("titleDe", slug)),
            slug=slug,
            group=meta["group_id"],
        )
