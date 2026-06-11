#!/usr/bin/env python3
"""只读审计：知识库文件 frontmatter 的 slug / category 与代码按路径生成值的分歧清单。

背景：`knowledge_service._scan` 故意**不读** frontmatter 的 `slug` / `category`，而是按
文件路径 / 文件夹自己生成（slug = 路径各段用 `__` 拼后 normalize，category_key = 第一层文件夹），
以避免改文章 URL / 断 [[]] 关联。于是文件里写的 slug/category 可能和实际使用的对不上、成为死数据。

本脚本把每个文件「frontmatter 声明的值」与「代码实际使用的值」逐个比对，列出分歧，供人工决定
是否清理 markdown。**纯只读**：不改任何 markdown、不动 URL、不碰数据库、不联网。

复用生产逻辑（单一事实来源）：`split_frontmatter` / `normalize_slug` 直接 import 自
`app.services.knowledge_service`，保证与线上 slug/category 生成一字不差。

用法（在装了依赖的环境里跑，例如一次性容器）：
    docker run --rm -v "$PWD":/app -w /app \\
      -v "$PWD/../knowledge":/knowledge:ro -e DEEPCOFFEE_KNOWLEDGE_DIR=/knowledge \\
      deepcoffee-api:latest python scripts/audit_frontmatter_slugs.py
可选参数：--knowledge-dir <路径> 覆盖知识库目录；--csv <路径> 同时导出 CSV。
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

# 让 `import app.*` 可用：把 deepcoffee-api 目录（scripts 的上一级）放进 sys.path。
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.services.knowledge_service import normalize_slug, split_frontmatter  # noqa: E402


def _fm_value(meta: dict, key: str) -> str | None:
    """读 frontmatter 标量值并转成可比对的字符串；缺失 / 空 → None。"""
    value = meta.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _code_slug(rel_without_suffix: Path) -> str:
    # 与 knowledge_service._scan 第 267 行完全一致。
    return normalize_slug("__".join(rel_without_suffix.parts))


def audit(knowledge_dir: Path) -> tuple[list[dict], dict]:
    """返回 (分歧行列表, 统计字典)。每个分歧行含 path / field / code_value / frontmatter_value。"""
    rows: list[dict] = []
    scanned = 0
    declared_slug = 0
    declared_category = 0

    for path in sorted(knowledge_dir.rglob("*.md")):
        rel = path.relative_to(knowledge_dir)
        # 跳过规则与 _scan 一致：index.md 与 stylesheets/ 不算文章。
        if rel.name == "index.md" or "stylesheets" in rel.parts:
            continue
        scanned += 1

        meta, _ = split_frontmatter(path.read_text(encoding="utf-8"))
        rel_without_suffix = rel.with_suffix("")
        code_slug = _code_slug(rel_without_suffix)
        code_category_key = rel.parts[0] if rel.parts else "general"

        fm_slug = _fm_value(meta, "slug")
        fm_category = _fm_value(meta, "category")

        if fm_slug is not None:
            declared_slug += 1
            if fm_slug != code_slug:
                rows.append(
                    {"path": str(rel), "field": "slug", "code_value": code_slug, "frontmatter_value": fm_slug}
                )
        if fm_category is not None:
            declared_category += 1
            if fm_category != code_category_key:
                rows.append(
                    {
                        "path": str(rel),
                        "field": "category",
                        "code_value": code_category_key,
                        "frontmatter_value": fm_category,
                    }
                )

    stats = {
        "scanned": scanned,
        "declared_slug": declared_slug,
        "declared_category": declared_category,
        "slug_divergences": sum(1 for r in rows if r["field"] == "slug"),
        "category_divergences": sum(1 for r in rows if r["field"] == "category"),
    }
    return rows, stats


def _print_report(rows: list[dict], stats: dict, knowledge_dir: Path) -> None:
    print(f"知识库目录：{knowledge_dir}")
    print(
        f"扫描文章 {stats['scanned']} 篇 | 声明 slug 的 {stats['declared_slug']} 篇 | "
        f"声明 category 的 {stats['declared_category']} 篇"
    )
    print(f"分歧：slug {stats['slug_divergences']} 处 | category {stats['category_divergences']} 处")
    print("-" * 72)
    if not rows:
        print("没有分歧：所有声明了 slug/category 的文件都与代码生成值一致。")
        return
    for r in rows:
        print(f"[{r['field']} 分歧] {r['path']}")
        print(f"    代码实际用:  {r['code_value']}")
        print(f"    frontmatter: {r['frontmatter_value']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="知识库 frontmatter slug/category 分歧只读审计")
    parser.add_argument("--knowledge-dir", type=Path, default=None, help="覆盖知识库目录（默认读 settings）")
    parser.add_argument("--csv", type=Path, default=None, help="可选：把分歧清单导出为 CSV")
    args = parser.parse_args()

    knowledge_dir = (args.knowledge_dir or get_settings().resolved_knowledge_dir).resolve()
    if not knowledge_dir.exists():
        print(f"知识库目录不存在：{knowledge_dir}", file=sys.stderr)
        return 1

    rows, stats = audit(knowledge_dir)
    _print_report(rows, stats, knowledge_dir)

    if args.csv is not None:
        with args.csv.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=["path", "field", "code_value", "frontmatter_value"])
            writer.writeheader()
            writer.writerows(rows)
        print("-" * 72)
        print(f"已导出 CSV：{args.csv}  （{len(rows)} 行）")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
