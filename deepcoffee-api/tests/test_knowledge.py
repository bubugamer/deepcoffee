from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient
from sqlalchemy import update

from app.core.db import get_sessionmaker
from app.main import create_app
from app.models.tables import UserProfile


def _headers(user_id: str, email: str | None = None) -> dict[str, str]:
    return {"Authorization": f"Bearer dev:{user_id}:{email or f'{user_id}@example.com'}"}


def _set_plan(user_id: str, plan: str) -> None:
    async def _run() -> None:
        async with get_sessionmaker()() as session:
            await session.execute(update(UserProfile).where(UserProfile.id == user_id).values(plan=plan))
            await session.commit()

    asyncio.run(_run())


def _max_headers(client: TestClient, user_id: str = "knowledge-max") -> dict[str, str]:
    headers = _headers(user_id)
    assert client.get("/v1/me", headers=headers).status_code == 200
    _set_plan(user_id, "max")
    return headers


def test_knowledge_categories_and_articles_use_markdown_files() -> None:
    client = TestClient(create_app())
    headers = _max_headers(client)

    categories = client.get("/v1/knowledge/categories", headers=headers)
    assert categories.status_code == 200
    category_payload = categories.json()
    assert any(item["key"] == "guides" for item in category_payload)
    assert not any(item["key"] == "roasters" for item in category_payload)

    articles = client.get("/v1/knowledge/articles", headers=headers, params={"q": "瑰夏"})
    assert articles.status_code == 200
    article_payload = articles.json()
    assert article_payload
    geisha = next((a for a in article_payload if "瑰夏" in a["summary"] or "瑰夏" in a["title"]), None)
    assert geisha is not None

    slug = geisha["slug"]
    detail = client.get(f"/v1/knowledge/articles/{slug}", headers=headers)
    assert detail.status_code == 200
    detail_payload = detail.json()
    assert "瑰夏" in detail_payload["markdown"]
    assert detail_payload["toc"]
    assert detail_payload["sections"]


def test_knowledge_select_files_and_local_answer() -> None:
    client = TestClient(create_app())
    max_headers = _max_headers(client, "knowledge-select-max")
    headers = _headers("knowledge-user-1", "knowledge@example.com")

    selected = client.post("/v1/knowledge/select-files", headers=max_headers, json={"question": "瑰夏为什么有花香"})
    assert selected.status_code == 200
    selected_payload = selected.json()
    assert selected_payload
    assert selected_payload[0]["score"] > 0

    answer = client.post("/v1/knowledge/ask", headers=headers, json={"question": "瑰夏为什么有花香"})
    assert answer.status_code == 200
    answer_payload = answer.json()
    assert answer_payload["from_knowledge_base"] is True
    assert answer_payload["sources"]
    assert answer_payload["trace_id"].startswith("kb_")

    quota = client.get("/v1/me/quota", headers=headers)
    assert quota.status_code == 200
    assert quota.json()["ai_used"] == 1

    cited_slug = answer_payload["sources"][0]["slug"]
    cited_detail = client.get(f"/v1/knowledge/articles/{cited_slug}", headers=headers)
    assert cited_detail.status_code == 200

    uncited = client.get("/v1/knowledge/articles/brewing__v60手冲冲煮指南", headers=headers)
    if cited_slug != "brewing__v60手冲冲煮指南":
        assert uncited.status_code == 403
        assert uncited.json()["error"]["code"] == "upgrade_required"


def test_frontmatter_stripped_from_summary_and_detail() -> None:
    client = TestClient(create_app())
    headers = _max_headers(client, "knowledge-frontmatter-max")
    articles = client.get("/v1/knowledge/articles", headers=headers, params={"q": "瑰夏"}).json()
    assert articles
    art = articles[0]
    # 摘要不再是 frontmatter（不以 "title:" 开头、不含 YAML 键）
    assert not art["summary"].startswith("title:")
    assert "entity_type" not in art["summary"]

    detail = client.get(f"/v1/knowledge/articles/{art['slug']}", headers=headers).json()
    # 详情正文已剥 frontmatter：不以 "---" 开头、不含 YAML 键
    assert not detail["markdown"].lstrip().startswith("---")
    assert "entity_type:" not in detail["markdown"]
    assert "source_quality:" not in detail["markdown"]


def test_alias_helps_select_files() -> None:
    client = TestClient(create_app())
    headers = _max_headers(client, "knowledge-alias-max")
    candidates = client.post("/v1/knowledge/select-files", headers=headers, json={"question": "Geisha"}).json()
    assert candidates
    geisha = next((c for c in candidates if "瑰夏" in c["title"] or "Geisha" in c["title"] or "品种" in c["title"]), None)
    assert geisha is not None
    # 命中原因里应有别名命中（aliases: Geisha/Gesha）
    assert any(r.startswith("alias:") for r in geisha["reasons"])


def test_support_articles_are_searchable_but_not_listed() -> None:
    client = TestClient(create_app())
    headers = _max_headers(client, "knowledge-support-max")

    listed = client.get("/v1/knowledge/articles", headers=headers, params={"q": "Tim Wendelboe"}).json()
    assert not any("Tim Wendelboe" in item["title"] for item in listed)

    candidates = client.post("/v1/knowledge/select-files", headers=headers, json={"question": "Tim Wendelboe 是谁"}).json()
    assert any("Tim Wendelboe" in item["title"] for item in candidates)


def test_roaster_product_support_detail_has_chinese_category() -> None:
    client = TestClient(create_app())
    headers = _max_headers(client, "knowledge-rp-max")

    detail = client.get("/v1/knowledge/articles/roaster-products__onyx-monarch", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["category"] == "代表产品"


def test_internal_content_not_served_to_users() -> None:
    """内部维护说明不下发：代码路径/AI 使用逻辑/「Deep Coffee 从中使用什么」章节。"""
    client = TestClient(create_app())
    headers = _max_headers(client, "knowledge-internal-max")

    grinder = client.get("/v1/knowledge/articles/equipment__grinders__磨豆机刻度对照表", headers=headers)
    assert grinder.status_code == 200, grinder.text
    md = grinder.json()["markdown"]
    assert "grinder_scales" not in md
    assert "deepcoffee-api" not in md
    assert "Coffea 会" not in md
    assert "刻度对照表" in md  # 正文主体还在

    bop = client.get("/v1/knowledge/articles/competitions__best-of-panama", headers=headers)
    assert bop.status_code == 200, bop.text
    bop_md = bop.json()["markdown"]
    assert "从中使用什么" not in bop_md
    assert all("从中使用什么" not in s["heading"] for s in bop.json()["sections"])
    assert all("从中使用什么" not in t["title"] for t in bop.json()["toc"])


def test_drop_internal_sections_strips_future_internal_blocks() -> None:
    """服务端兜底：即使内容侧再混入内部章节，扫描时也会整段剔除。"""
    from app.services.knowledge_service import drop_internal_sections

    md = (
        "# 标题\n\n正文。\n\n## Deep Coffee 从中使用什么\n\n内部说明。\n\n"
        "## 内部维护说明\n\n同步约定。\n\n## 正常章节\n\n保留内容。\n"
    )
    out = drop_internal_sections(md)
    assert "从中使用什么" not in out and "内部说明" not in out and "同步约定" not in out
    assert "正常章节" in out and "保留内容" in out and "正文。" in out


def test_related_section_links_are_real_markdown_links() -> None:
    """「相关页面」已链接化：V60 指南的相关条目应是 [标题](路径.md) 形式。"""
    client = TestClient(create_app())
    headers = _max_headers(client, "knowledge-related-max")
    detail = client.get("/v1/knowledge/articles/brewing__v60手冲冲煮指南", headers=headers)
    assert detail.status_code == 200, detail.text
    md = detail.json()["markdown"]
    assert "[手冲用水科学](brewing/手冲用水科学.md)" in md
