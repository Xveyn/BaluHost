"""Tests for the documentation API endpoints."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.docs import DocsService


class TestDocsService:

    def _make_docs_dir(self, tmp_path: Path) -> Path:
        docs = tmp_path / "docs"
        docs.mkdir()
        index = {
            "groups": [
                {
                    "id": "guides", "labelDe": "Anleitungen", "labelEn": "Guides",
                    "icon": "book", "order": 1, "visibility": "all",
                    "articles": [{"slug": "intro", "path": "guides/INTRO", "titleDe": "Einführung", "titleEn": "Introduction", "icon": "file-text", "order": 1}],
                },
                {
                    "id": "admin-only", "labelDe": "Admin", "labelEn": "Admin",
                    "icon": "lock", "order": 2, "visibility": "admin",
                    "articles": [{"slug": "secrets", "path": "admin/SECRETS", "titleDe": "Geheimnisse", "titleEn": "Secrets", "icon": "key", "order": 1}],
                },
            ]
        }
        (docs / "manual-index.json").write_text(json.dumps(index), encoding="utf-8")
        guides = docs / "guides"
        guides.mkdir()
        (guides / "INTRO.de.md").write_text("# Einführung\n\nHallo Welt", encoding="utf-8")
        (guides / "INTRO.en.md").write_text("# Introduction\n\nHello World", encoding="utf-8")
        admin = docs / "admin"
        admin.mkdir()
        (admin / "SECRETS.de.md").write_text("# Geheimnisse\n\nNur für Admins", encoding="utf-8")
        return docs

    def test_load_index_returns_all_groups(self, tmp_path):
        docs = self._make_docs_dir(tmp_path)
        svc = DocsService(docs_dir=docs)
        index = svc.get_index(lang="de", is_admin=True)
        assert len(index) == 2
        assert index[0].id == "guides"
        assert index[1].id == "admin-only"

    def test_load_index_filters_admin_groups_for_regular_user(self, tmp_path):
        docs = self._make_docs_dir(tmp_path)
        svc = DocsService(docs_dir=docs)
        index = svc.get_index(lang="de", is_admin=False)
        assert len(index) == 1
        assert index[0].id == "guides"

    def test_get_index_resolves_german_labels(self, tmp_path):
        docs = self._make_docs_dir(tmp_path)
        svc = DocsService(docs_dir=docs)
        index = svc.get_index(lang="de", is_admin=False)
        assert index[0].label == "Anleitungen"
        assert index[0].articles[0].title == "Einführung"

    def test_get_index_resolves_english_labels(self, tmp_path):
        docs = self._make_docs_dir(tmp_path)
        svc = DocsService(docs_dir=docs)
        index = svc.get_index(lang="en", is_admin=False)
        assert index[0].label == "Guides"
        assert index[0].articles[0].title == "Introduction"

    def test_get_index_falls_back_to_de_for_unknown_lang(self, tmp_path):
        docs = self._make_docs_dir(tmp_path)
        svc = DocsService(docs_dir=docs)
        index = svc.get_index(lang="fr", is_admin=False)
        assert index[0].label == "Anleitungen"

    def test_get_article_returns_content(self, tmp_path):
        docs = self._make_docs_dir(tmp_path)
        svc = DocsService(docs_dir=docs)
        article = svc.get_article(slug="intro", lang="de", is_admin=False)
        assert article is not None
        assert "Einführung" in article.content
        assert article.slug == "intro"
        assert article.group == "guides"

    def test_get_article_returns_english_content(self, tmp_path):
        docs = self._make_docs_dir(tmp_path)
        svc = DocsService(docs_dir=docs)
        article = svc.get_article(slug="intro", lang="en", is_admin=False)
        assert article is not None
        assert "Hello World" in article.content

    def test_get_article_falls_back_to_de_when_lang_missing(self, tmp_path):
        docs = self._make_docs_dir(tmp_path)
        svc = DocsService(docs_dir=docs)
        article = svc.get_article(slug="secrets", lang="en", is_admin=True)
        assert article is not None
        assert "Nur für Admins" in article.content

    def test_get_article_returns_none_for_unknown_slug(self, tmp_path):
        docs = self._make_docs_dir(tmp_path)
        svc = DocsService(docs_dir=docs)
        assert svc.get_article(slug="nonexistent", lang="de", is_admin=False) is None

    def test_get_article_returns_none_for_admin_slug_as_regular_user(self, tmp_path):
        docs = self._make_docs_dir(tmp_path)
        svc = DocsService(docs_dir=docs)
        assert svc.get_article(slug="secrets", lang="de", is_admin=False) is None

    def test_rejects_path_traversal_in_index(self, tmp_path):
        docs = tmp_path / "docs"
        docs.mkdir()
        bad_index = {
            "groups": [{"id": "evil", "labelDe": "Evil", "labelEn": "Evil", "icon": "x", "order": 1, "visibility": "all",
                "articles": [{"slug": "evil", "path": "../../../etc/passwd", "titleDe": "Evil", "titleEn": "Evil", "icon": "x", "order": 1}]}]
        }
        (docs / "manual-index.json").write_text(json.dumps(bad_index), encoding="utf-8")
        svc = DocsService(docs_dir=docs)
        index = svc.get_index(lang="de", is_admin=True)
        assert len(index[0].articles) == 0


# ---------------------------------------------------------------------------
# API route integration tests
# ---------------------------------------------------------------------------

@pytest.fixture
def _docs_dir_with_articles(tmp_path):
    """Create a temporary docs directory and patch DocsService to use it."""
    docs = tmp_path / "docs"
    docs.mkdir()
    index = {
        "groups": [
            {
                "id": "guides", "labelDe": "Anleitungen", "labelEn": "Guides",
                "icon": "book", "order": 1, "visibility": "all",
                "articles": [{"slug": "intro", "path": "guides/INTRO", "titleDe": "Einführung", "titleEn": "Introduction", "icon": "file-text", "order": 1}],
            },
            {
                "id": "admin-only", "labelDe": "Admin", "labelEn": "Admin",
                "icon": "lock", "order": 2, "visibility": "admin",
                "articles": [{"slug": "secrets", "path": "admin/SECRETS", "titleDe": "Geheimnisse", "titleEn": "Secrets", "icon": "key", "order": 1}],
            },
        ]
    }
    (docs / "manual-index.json").write_text(json.dumps(index), encoding="utf-8")
    guides = docs / "guides"
    guides.mkdir()
    (guides / "INTRO.de.md").write_text("# Einführung\n\nHallo", encoding="utf-8")
    (guides / "INTRO.en.md").write_text("# Introduction\n\nHello", encoding="utf-8")
    admin = docs / "admin"
    admin.mkdir()
    (admin / "SECRETS.de.md").write_text("# Secrets\n\nAdmin only", encoding="utf-8")
    with patch("app.api.routes.docs._get_docs_service") as mock:
        mock.return_value = DocsService(docs_dir=docs)
        yield


class TestDocsIndexEndpoint:
    def test_returns_index_for_admin(self, client, admin_headers, _docs_dir_with_articles):
        resp = client.get("/api/docs/index?lang=de", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["groups"]) == 2

    def test_filters_admin_groups_for_regular_user(self, client, user_headers, _docs_dir_with_articles):
        resp = client.get("/api/docs/index?lang=de", headers=user_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["groups"]) == 1
        assert data["groups"][0]["id"] == "guides"

    def test_resolves_english_labels(self, client, user_headers, _docs_dir_with_articles):
        resp = client.get("/api/docs/index?lang=en", headers=user_headers)
        assert resp.status_code == 200
        assert resp.json()["groups"][0]["label"] == "Guides"

    def test_requires_auth(self, client, _docs_dir_with_articles):
        resp = client.get("/api/docs/index")
        assert resp.status_code == 401


class TestDocsArticleEndpoint:
    def test_returns_article_content(self, client, user_headers, _docs_dir_with_articles):
        resp = client.get("/api/docs/article/intro?lang=de", headers=user_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "Einführung" in data["content"]
        assert data["slug"] == "intro"
        assert data["group"] == "guides"

    def test_returns_english_article(self, client, user_headers, _docs_dir_with_articles):
        resp = client.get("/api/docs/article/intro?lang=en", headers=user_headers)
        assert resp.status_code == 200
        assert "Hello" in resp.json()["content"]

    def test_returns_404_for_unknown_slug(self, client, user_headers, _docs_dir_with_articles):
        resp = client.get("/api/docs/article/nonexistent?lang=de", headers=user_headers)
        assert resp.status_code == 404

    def test_returns_403_for_admin_article_as_regular_user(self, client, user_headers, _docs_dir_with_articles):
        resp = client.get("/api/docs/article/secrets?lang=de", headers=user_headers)
        assert resp.status_code == 403

    def test_admin_can_access_admin_article(self, client, admin_headers, _docs_dir_with_articles):
        resp = client.get("/api/docs/article/secrets?lang=de", headers=admin_headers)
        assert resp.status_code == 200
        assert "Admin only" in resp.json()["content"]

    def test_requires_auth(self, client, _docs_dir_with_articles):
        resp = client.get("/api/docs/article/intro")
        assert resp.status_code == 401
