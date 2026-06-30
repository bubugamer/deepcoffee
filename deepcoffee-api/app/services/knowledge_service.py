from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timezone
from functools import lru_cache
from pathlib import Path
from uuid import uuid4

import yaml
from fastapi import Depends

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.schemas.knowledge import (
    ArticleDetail,
    ArticleSection,
    ArticleSummary,
    CandidateFile,
    GroundingDoc,
    KnowledgeAskResponse,
    KnowledgeCategory,
    KnowledgeSource,
    RelatedArticle,
    TocItem,
)


def split_frontmatter(raw: str) -> tuple[dict, str]:
    """切出开头的 YAML frontmatter（--- … ---）。返回 (meta, body)。无 frontmatter 则 ({}, raw)。

    这是 frontmatter 剥离的唯一入口：扫描时切一刀，下游全用 body + meta，不再碰原始元数据。
    """
    if not raw.startswith("---"):
        return {}, raw
    lines = raw.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, raw
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            block = "\n".join(lines[1:i])
            body = "\n".join(lines[i + 1 :]).lstrip("\n")
            try:
                meta = yaml.safe_load(block) or {}
            except yaml.YAMLError:
                meta = {}
            return (meta if isinstance(meta, dict) else {}), body
    return {}, raw


# 内部章节标题模式：写给维护者/AI 的说明，不该出现在用户可见正文与模型 grounding 里。
# 内容侧应避免再写这类章节；这里是服务端兜底（展示、sections、toc、grounding 全部干净）。
_INTERNAL_SECTION_PATTERNS = (
    re.compile(r"^Deep\s*Coffee\s*从中使用", re.IGNORECASE),
    re.compile(r"^内部(说明|备注|维护)"),
)


def drop_internal_sections(markdown: str) -> str:
    """按 ## 标题整段剔除内部章节（到下一个同级标题或文末）。"""
    lines = markdown.splitlines()
    kept: list[str] = []
    skipping = False
    for line in lines:
        h2 = re.match(r"^##\s+(.+?)\s*$", line)
        if h2:
            heading = h2.group(1).strip()
            skipping = any(p.search(heading) for p in _INTERNAL_SECTION_PATTERNS)
            if skipping:
                continue
        if not skipping:
            kept.append(line)
    return "\n".join(kept).strip("\n") + ("\n" if kept else "")


def strip_internal_source_lines(markdown: str) -> str:
    """删除「## 来源」段中指向内部素材文件（resources/…）的列表项。

    用户可见的来源里不该出现内部文件路径；公开链接与站内文章来源原样保留。
    只在「## 来源」段内生效，遇到下一个 ## 标题即退出该段。
    若整段「来源」剔除内部条目后已无任何实质内容，则连标题一并去掉，
    避免页面/目录/章节里残留一个下面空空的「来源」标题。
    """
    lines = markdown.splitlines()
    kept: list[str] = []
    sources_heading: str | None = None  # 「来源」标题行，待该段结束再决定是否保留
    sources_body: list[str] = []  # 「来源」段去掉内部条目后剩下的行

    def flush_sources() -> None:
        nonlocal sources_heading, sources_body
        if sources_heading is None:
            return
        if any(line.strip() for line in sources_body):
            kept.append(sources_heading)
            kept.extend(sources_body)
        sources_heading = None
        sources_body = []

    for line in lines:
        h2 = re.match(r"^##\s+(.+?)\s*$", line)
        if h2:
            flush_sources()
            if h2.group(1).strip() == "来源":
                sources_heading = line
                continue
            kept.append(line)
            continue
        if sources_heading is not None:
            if "resources/" in line:
                continue
            sources_body.append(line)
            continue
        kept.append(line)
    flush_sources()
    return "\n".join(kept).strip("\n") + ("\n" if kept else "")


def _meta_str(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _meta_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _meta_date(value: object) -> datetime | None:
    """frontmatter 的 last_updated 可能是 'YYYY-MM-DD' 字符串或 YAML 解析出的 date。"""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None

CATEGORY_LABELS = {
    "guides": "冲煮指南",
    "origins": "产区",
    "varietals": "品种",
    "processing": "处理法",
    "coffee-sources": "咖啡来源",
    "green-merchants": "生豆商与寻豆机构",
    "green-bean-products": "生豆商产品",
    "equipment": "器具",
    "brewing": "烘焙与冲煮",
    "roasters": "烘焙商",
    "roaster-products": "代表产品",
    "standards": "标准",
    "competitions": "赛事",
    "figures": "人物",
}

MODEL_NOTE_SUFFIX = "_model_notes.md"


def normalize_slug(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).strip().lower()
    value = re.sub(r"[^\w.-]+", "-", value, flags=re.UNICODE)
    value = re.sub(r"-{2,}", "-", value).strip("-")
    return value or "article"


def heading_id(value: str) -> str:
    return normalize_slug(value)


def plain_text(markdown: str) -> str:
    text = re.sub(r"```.*?```", " ", markdown, flags=re.DOTALL)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\[\[([^\]]+)\]\]", r"\1", text)
    text = re.sub(r"[*_>#-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def extract_title(markdown: str, fallback: str) -> str:
    for line in markdown.splitlines():
        match = re.match(r"^#\s+(.+?)\s*$", line)
        if match:
            return match.group(1).strip()
    return fallback


def extract_summary(markdown: str, limit: int = 180) -> str:
    for raw in markdown.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("- ") or line.startswith(">"):
            continue
        text = plain_text(line)
        if text:
            return text[:limit]
    return plain_text(markdown)[:limit]


def extract_toc(markdown: str) -> list[TocItem]:
    toc: list[TocItem] = []
    for line in markdown.splitlines():
        match = re.match(r"^(#{2,4})\s+(.+?)\s*$", line)
        if not match:
            continue
        title = match.group(2).strip()
        toc.append(TocItem(id=heading_id(title), title=title, level=len(match.group(1))))
    return toc


def extract_sections(markdown: str) -> list[ArticleSection]:
    sections: list[ArticleSection] = []
    current_heading: str | None = None
    body_lines: list[str] = []
    items: list[str] = []

    def flush() -> None:
        nonlocal body_lines, items, current_heading
        if not current_heading:
            return
        body = plain_text("\n".join(body_lines)) or None
        sections.append(
            ArticleSection(
                id=heading_id(current_heading),
                heading=current_heading,
                body=body,
                items=items or None,
            )
        )
        body_lines = []
        items = []

    for line in markdown.splitlines():
        h2 = re.match(r"^##\s+(.+?)\s*$", line)
        if h2:
            flush()
            current_heading = h2.group(1).strip()
            continue
        if current_heading is None:
            continue
        bullet = re.match(r"^\s*[-*]\s+(.+)$", line)
        if bullet:
            items.append(plain_text(bullet.group(1)))
        elif line.strip().startswith("### "):
            body_lines.append(line.strip().lstrip("#").strip())
        else:
            body_lines.append(line)

    flush()
    return sections


def extract_wiki_links(markdown: str) -> list[str]:
    links = []
    for match in re.finditer(r"\[\[([^\]]+)\]\]", markdown):
        target = match.group(1).split("|", 1)[0].strip()
        if target and target not in links:
            links.append(target)
    return links


def search_terms(question: str) -> list[str]:
    normalized = question.lower()
    raw_terms = re.findall(r"[a-z0-9][a-z0-9.-]*|[\u4e00-\u9fff]{2,}", normalized, flags=re.IGNORECASE)
    terms: list[str] = []
    for term in raw_terms:
        terms.append(term)
        if re.fullmatch(r"[\u4e00-\u9fff]+", term) and len(term) > 2:
            terms.extend(term[index : index + 2] for index in range(len(term) - 1))
    unique: list[str] = []
    for term in terms:
        if term not in unique:
            unique.append(term)
    return unique or [normalized]


@dataclass(frozen=True)
class ArticleDocument:
    summary: ArticleSummary
    markdown: str  # 已去 frontmatter 的正文
    sections: list[ArticleSection]
    toc: list[TocItem]
    wiki_links: list[str]
    aliases: list[str]
    visibility: str
    indexable: bool
    audience: str | None = None
    target_slug: str | None = None
    is_model_note: bool = False


def _meta_bool(value: object, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "no", "n", "off"}:
            return False
    return default


def _model_note_target_slug(rel: Path, meta: dict) -> str | None:
    target = _meta_str(meta.get("target"))
    if target:
        target_rel = rel.parent / target
    elif rel.name.endswith(MODEL_NOTE_SUFFIX):
        target_rel = rel.parent / f"{rel.name[: -len(MODEL_NOTE_SUFFIX)]}.md"
    else:
        return None
    return normalize_slug("__".join(target_rel.with_suffix("").parts))


class KnowledgeService:
    def __init__(self, knowledge_dir: Path) -> None:
        self.knowledge_dir = knowledge_dir
        self._articles: dict[str, ArticleDocument] | None = None

    def reload(self) -> None:
        self._articles = None
        self._articles = self._scan()

    @property
    def articles(self) -> dict[str, ArticleDocument]:
        if self._articles is None:
            self._articles = self._scan()
        return self._articles

    def _scan(self) -> dict[str, ArticleDocument]:
        if not self.knowledge_dir.exists():
            raise AppError(500, "knowledge_dir_missing", f"Knowledge directory not found: {self.knowledge_dir}")

        documents: dict[str, ArticleDocument] = {}
        for path in sorted(self.knowledge_dir.rglob("*.md")):
            rel = path.relative_to(self.knowledge_dir)
            if rel.name == "index.md" or "stylesheets" in rel.parts:
                continue

            raw = path.read_text(encoding="utf-8")
            # frontmatter 在此切一刀：markdown 是干净正文，meta 是结构化元数据。
            meta, markdown = split_frontmatter(raw)
            # 内部章节兜底剔除：下游（展示/章节/目录/grounding）全部派生自干净正文。
            markdown = drop_internal_sections(markdown)
            # 来源段里指向内部素材（resources/）的条目也剔除，避免暴露内部路径。
            markdown = strip_internal_source_lines(markdown)
            rel_without_suffix = rel.with_suffix("")
            # slug / category 仍由路径 / 文件夹决定（不读 meta.slug / meta.category，避免改 URL、断关联）。
            slug = normalize_slug("__".join(rel_without_suffix.parts))
            category_key = rel.parts[0] if rel.parts else "general"
            category = CATEGORY_LABELS.get(category_key, category_key)
            # 更新时间优先用 frontmatter last_updated（比文件 mtime 稳），否则退 mtime。
            updated_at = _meta_date(meta.get("last_updated")) or datetime.fromtimestamp(
                path.stat().st_mtime, tz=timezone.utc
            )
            title = _meta_str(meta.get("title")) or extract_title(markdown, rel_without_suffix.name)
            summary = extract_summary(markdown)
            aliases = _meta_list(meta.get("aliases"))
            visibility = (_meta_str(meta.get("visibility")) or "public").lower()
            audience = (_meta_str(meta.get("audience")) or "").lower() or None
            is_model_note = rel.name.endswith(MODEL_NOTE_SUFFIX) or visibility == "model" or audience == "model"
            if is_model_note:
                visibility = "model"
            # visibility=support 的页面不出现在用户文章列表，但仍可作为 AI grounding 和来源页打开。
            indexable = _meta_bool(meta.get("indexable"), default=visibility in {"public", "support"})
            if is_model_note:
                indexable = False
            target_slug = _model_note_target_slug(rel, meta) if is_model_note else None

            article_summary = ArticleSummary(
                slug=slug,
                title=title,
                category=category,
                category_key=category_key,
                summary=summary,
                updated_at=updated_at,
                path=str(rel),
                cat=category,
                desc=summary,
                updated=updated_at.date().isoformat(),
            )
            documents[slug] = ArticleDocument(
                summary=article_summary,
                markdown=markdown,
                sections=extract_sections(markdown),
                toc=extract_toc(markdown),
                wiki_links=extract_wiki_links(markdown),
                aliases=aliases,
                visibility=visibility,
                indexable=indexable,
                audience=audience,
                target_slug=target_slug,
                is_model_note=is_model_note,
            )
        return documents

    def _public_documents(self) -> list[ArticleDocument]:
        return [document for document in self.articles.values() if document.visibility == "public"]

    def _indexable_documents(self) -> list[ArticleDocument]:
        return [document for document in self.articles.values() if document.indexable]

    def _model_notes_for(self, slug: str) -> list[ArticleDocument]:
        return sorted(
            (
                document
                for document in self.articles.values()
                if document.is_model_note and document.target_slug == slug
            ),
            key=lambda document: document.summary.path,
        )

    def list_categories(self) -> list[KnowledgeCategory]:
        by_category: dict[str, list[ArticleSummary]] = {}
        for document in self._public_documents():
            by_category.setdefault(document.summary.category_key, []).append(document.summary)

        categories: list[KnowledgeCategory] = []
        for key, items in sorted(by_category.items()):
            label = CATEGORY_LABELS.get(key, key)
            sub = "、".join(item.title for item in items[:3])
            categories.append(
                KnowledgeCategory(
                    key=key,
                    label=label,
                    count=len(items),
                    sub=sub,
                    href=f"/knowledge?category={key}",
                )
            )
        return categories

    def list_articles(self, category: str | None = None, q: str | None = None) -> list[ArticleSummary]:
        items = [document.summary for document in self._public_documents()]
        if category:
            normalized = category.strip().lower()
            items = [
                item
                for item in items
                if item.category_key.lower() == normalized or item.category.lower() == normalized
            ]
        if q:
            query = q.strip().lower()
            matched: list[ArticleSummary] = []
            for document in self._public_documents():
                item = document.summary
                aliases = " ".join(document.aliases).lower()
                if (
                    query in item.title.lower()
                    or query in item.summary.lower()
                    or query in item.path.lower()
                    or query in aliases
                    or query in document.markdown.lower()
                ):
                    matched.append(item)
            items = matched
        return sorted(items, key=lambda item: (item.category_key, item.title))

    def get_article(self, slug: str) -> ArticleDetail:
        document = self.articles.get(slug)
        if not document or document.visibility not in {"public", "support"}:
            raise AppError(404, "article_not_found", "Article not found.")
        related = self._related_articles(document)
        return ArticleDetail(
            **document.summary.model_dump(),
            markdown=document.markdown,
            sections=document.sections,
            toc=document.toc,
            related=related,
        )

    def select_files(self, question: str, limit: int = 5) -> list[CandidateFile]:
        terms = search_terms(question)
        candidates: list[CandidateFile] = []
        for document in self._indexable_documents():
            summary = document.summary
            haystacks = {
                "title": summary.title.lower(),
                "aliases": " ".join(document.aliases).lower(),
                "summary": summary.summary.lower(),
                "path": summary.path.lower(),
                "body": document.markdown.lower(),
            }
            score = 0.0
            reasons: list[str] = []
            for term in terms:
                if term in haystacks["title"]:
                    score += 6
                    reasons.append(f"title:{term}")
                if haystacks["aliases"] and term in haystacks["aliases"]:
                    score += 5
                    reasons.append(f"alias:{term}")
                if term in haystacks["summary"]:
                    score += 3
                    reasons.append(f"summary:{term}")
                if term in haystacks["path"]:
                    score += 2
                    reasons.append(f"path:{term}")
                body_hits = haystacks["body"].count(term)
                if body_hits:
                    score += min(body_hits, 8)
                    reasons.append(f"body:{term}")
            if score > 0:
                candidates.append(
                    CandidateFile(
                        slug=summary.slug,
                        title=summary.title,
                        category=summary.category,
                        path=summary.path,
                        score=score,
                        reasons=reasons[:6],
                    )
                )
        return sorted(candidates, key=lambda item: item.score, reverse=True)[:limit]

    def build_grounding(self, slugs: list[str], settings: Settings) -> list[GroundingDoc]:
        """方案三：把选中文件的**整篇干净正文**作为 grounding 喂模型，带长度护栏。

        - 最多取 `kb_grounding_docs` 篇；
        - 单篇超 `kb_max_chars_per_doc` 在 `##` 章节边界截断（不硬切句子）；
        - 总长超 `kb_max_context_chars` 则截尾，控 token / 成本。
        """
        docs: list[GroundingDoc] = []
        total = 0
        for slug in slugs[: max(0, settings.kb_grounding_docs)]:
            document = self.articles.get(slug)
            if document is None or not document.indexable:
                continue
            content = document.markdown.strip()
            if len(content) > settings.kb_max_chars_per_doc:
                content = self._truncate_at_section(content, settings.kb_max_chars_per_doc)
            remaining = settings.kb_max_context_chars - total
            if remaining <= 0:
                break
            if len(content) > remaining:
                content = content[:remaining].rstrip()
            if not content:
                continue
            model_notes = [
                note.markdown.strip()
                for note in self._model_notes_for(slug)
                if note.markdown.strip()
            ]
            docs.append(
                GroundingDoc(
                    slug=slug,
                    title=document.summary.title,
                    content=content,
                    model_notes=model_notes,
                )
            )
            total += len(content)
        return docs

    @staticmethod
    def _truncate_at_section(content: str, limit: int) -> str:
        cut = content[:limit]
        idx = cut.rfind("\n## ")
        if idx > limit * 0.5:  # 章节边界离上限不太远才用，否则直接硬截
            return cut[:idx].rstrip()
        return cut.rstrip()

    def answer_question(self, question: str) -> KnowledgeAskResponse:
        trace_id = f"kb_{uuid4().hex[:12]}"
        selected = self.select_files(question, limit=3)
        if not selected:
            return KnowledgeAskResponse(
                answer="知识库里暂时没有找到足够相关的内容。",
                sources=[],
                selected_files=[],
                from_knowledge_base=False,
                trace_id=trace_id,
            )

        sources: list[KnowledgeSource] = []
        answer_parts = ["我在知识库里找到了这些相关内容："]
        for candidate in selected:
            document = self.articles[candidate.slug]
            excerpt = self._best_excerpt(document.markdown, question)
            sources.append(
                KnowledgeSource(
                    slug=candidate.slug,
                    title=candidate.title,
                    path=candidate.path,
                    excerpt=excerpt,
                )
            )
            answer_parts.append(f"- {candidate.title}: {excerpt}")

        answer_parts.append("当前本地回答只基于 Markdown 知识库摘录；接入模型网关后会生成更自然的完整回答。")
        return KnowledgeAskResponse(
            answer="\n".join(answer_parts),
            sources=sources,
            selected_files=selected,
            from_knowledge_base=True,
            trace_id=trace_id,
        )

    def _best_excerpt(self, markdown: str, question: str, limit: int = 220) -> str:
        terms = search_terms(question)
        paragraphs = [plain_text(part) for part in re.split(r"\n\s*\n", markdown) if plain_text(part)]
        for term in terms:
            for paragraph in paragraphs:
                if term in paragraph.lower():
                    return paragraph[:limit]
        return (paragraphs[0] if paragraphs else plain_text(markdown))[:limit]

    def _related_articles(self, document: ArticleDocument) -> list[RelatedArticle]:
        lookup: dict[str, ArticleSummary] = {}
        for other in self._public_documents():
            summary = other.summary
            lookup[summary.title] = summary
            lookup[Path(summary.path).stem] = summary

        related: list[RelatedArticle] = []
        for link in document.wiki_links:
            match = lookup.get(link)
            if match and match.slug != document.summary.slug:
                related.append(RelatedArticle(slug=match.slug, title=match.title))

        if related:
            return related[:5]

        same_category = [
            other.summary
            for other in self._public_documents()
            if other.summary.category_key == document.summary.category_key and other.summary.slug != document.summary.slug
        ]
        return [RelatedArticle(slug=item.slug, title=item.title) for item in same_category[:5]]


@lru_cache(maxsize=8)
def get_cached_knowledge_service(knowledge_dir: str) -> KnowledgeService:
    return KnowledgeService(Path(knowledge_dir))


def get_knowledge_service(settings: Settings = Depends(get_settings)) -> KnowledgeService:
    return get_cached_knowledge_service(str(settings.resolved_knowledge_dir))
