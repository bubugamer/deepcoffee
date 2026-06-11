from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app


def test_knowledge_categories_and_articles_use_markdown_files() -> None:
    client = TestClient(create_app())

    categories = client.get("/v1/knowledge/categories")
    assert categories.status_code == 200
    category_payload = categories.json()
    assert any(item["key"] == "guides" for item in category_payload)
    assert not any(item["key"] == "roasters" for item in category_payload)

    articles = client.get("/v1/knowledge/articles", params={"q": "瑰夏"})
    assert articles.status_code == 200
    article_payload = articles.json()
    assert article_payload
    geisha = next((a for a in article_payload if "瑰夏" in a["summary"] or "瑰夏" in a["title"]), None)
    assert geisha is not None

    slug = geisha["slug"]
    detail = client.get(f"/v1/knowledge/articles/{slug}")
    assert detail.status_code == 200
    detail_payload = detail.json()
    assert "瑰夏" in detail_payload["markdown"]
    assert detail_payload["toc"]
    assert detail_payload["sections"]


def test_knowledge_select_files_and_local_answer() -> None:
    client = TestClient(create_app())
    headers = {"Authorization": "Bearer dev:knowledge-user-1:knowledge@example.com"}

    selected = client.post("/v1/knowledge/select-files", json={"question": "瑰夏为什么有花香"})
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


def test_frontmatter_stripped_from_summary_and_detail() -> None:
    client = TestClient(create_app())
    articles = client.get("/v1/knowledge/articles", params={"q": "瑰夏"}).json()
    assert articles
    art = articles[0]
    # 摘要不再是 frontmatter（不以 "title:" 开头、不含 YAML 键）
    assert not art["summary"].startswith("title:")
    assert "entity_type" not in art["summary"]

    detail = client.get(f"/v1/knowledge/articles/{art['slug']}").json()
    # 详情正文已剥 frontmatter：不以 "---" 开头、不含 YAML 键
    assert not detail["markdown"].lstrip().startswith("---")
    assert "entity_type:" not in detail["markdown"]
    assert "source_quality:" not in detail["markdown"]


def test_alias_helps_select_files() -> None:
    client = TestClient(create_app())
    candidates = client.post("/v1/knowledge/select-files", json={"question": "Geisha"}).json()
    assert candidates
    geisha = next((c for c in candidates if "瑰夏" in c["title"] or "Geisha" in c["title"] or "品种" in c["title"]), None)
    assert geisha is not None
    # 命中原因里应有别名命中（aliases: Geisha/Gesha）
    assert any(r.startswith("alias:") for r in geisha["reasons"])


def test_support_articles_are_searchable_but_not_listed() -> None:
    client = TestClient(create_app())

    listed = client.get("/v1/knowledge/articles", params={"q": "Tim Wendelboe"}).json()
    assert not any("Tim Wendelboe" in item["title"] for item in listed)

    candidates = client.post("/v1/knowledge/select-files", json={"question": "Tim Wendelboe 是谁"}).json()
    assert any("Tim Wendelboe" in item["title"] for item in candidates)


def test_green_bean_product_support_detail_has_chinese_category() -> None:
    client = TestClient(create_app())

    detail = client.get("/v1/knowledge/articles/green-bean-products__project-origin-cm-selections")
    assert detail.status_code == 200
    assert detail.json()["category"] == "生豆商产品"
