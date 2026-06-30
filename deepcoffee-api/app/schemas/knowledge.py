from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class KnowledgeCategory(BaseModel):
    key: str
    label: str
    count: int
    sub: str = ""
    href: str = ""


class RelatedArticle(BaseModel):
    slug: str
    title: str


class ArticleSummary(BaseModel):
    slug: str
    title: str
    category: str
    category_key: str
    summary: str
    updated_at: datetime
    path: str
    cat: str
    desc: str
    updated: str


class ArticleSection(BaseModel):
    id: str
    heading: str
    body: str | None = None
    items: list[str] | None = None


class TocItem(BaseModel):
    id: str
    title: str
    level: int


class ArticleDetail(ArticleSummary):
    markdown: str
    sections: list[ArticleSection]
    toc: list[TocItem]
    related: list[RelatedArticle]


class KnowledgeAskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    session_id: str | None = None


class KnowledgeFileSelectRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class CandidateFile(BaseModel):
    slug: str
    title: str
    category: str
    path: str
    score: float
    reasons: list[str]


class KnowledgeSource(BaseModel):
    slug: str
    title: str
    path: str
    excerpt: str


class GroundingDoc(BaseModel):
    """喂给模型的「整篇正文」grounding（已去 frontmatter、按长度护栏截断）。"""

    slug: str
    title: str
    content: str
    model_notes: list[str] = Field(default_factory=list)


class KnowledgeAskResponse(BaseModel):
    answer: str
    sources: list[KnowledgeSource]
    selected_files: list[CandidateFile]
    from_knowledge_base: bool
    trace_id: str
