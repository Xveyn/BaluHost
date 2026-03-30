"""Pydantic models for the documentation API."""

from pydantic import BaseModel


class DocsArticleInfo(BaseModel):
    """Article metadata as returned in the index."""
    slug: str
    title: str
    icon: str


class DocsGroupInfo(BaseModel):
    """Group of articles with label and icon."""
    id: str
    label: str
    icon: str
    articles: list[DocsArticleInfo]


class DocsIndexResponse(BaseModel):
    """Response for GET /api/docs/index."""
    groups: list[DocsGroupInfo]


class DocsArticleResponse(BaseModel):
    """Response for GET /api/docs/article/{slug}."""
    content: str
    title: str
    slug: str
    group: str
