#!/usr/bin/env python3
"""把知识库文章「相关页面/相关条目/相关阅读」段里的纯文本标题改写成真 markdown 链接。

背景：早期文章的相关条目写成 `- 标题 — 描述` 纯文本，前端渲染后不可点击。
本脚本扫描 knowledge/ 建立「文件名词干 → 知识库根相对路径」索引，对相关段落里
唯一命中的标题改写为 `- [标题](category/文件.md) — 描述`（根相对路径，前端
resolveMarkdownHref 按根解析）。歧义/未命中的条目原样保留并报告。

用法（仓库根目录执行）：
    python3 scripts/linkify_knowledge_links.py            # dry-run，只报告
    python3 scripts/linkify_knowledge_links.py --apply    # 真写
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

KNOWLEDGE = Path(__file__).resolve().parents[1] / "knowledge"
RELATED_HEADINGS = re.compile(r"^##\s*(相关页面|相关条目|相关阅读|相关文章)\s*$")
# `- 标题 — 描述`（破折号可为 — 或 –，描述可空）；标题里不含 [ ] ( ) 才视为纯文本
BULLET = re.compile(r"^(\s*-\s+)([^\[\]()—–]+?)(\s*[—–]\s*.*)?$")


def build_index() -> dict[str, list[str]]:
    index: dict[str, list[str]] = {}
    for path in sorted(KNOWLEDGE.rglob("*.md")):
        rel = path.relative_to(KNOWLEDGE)
        if rel.name == "index.md" or "stylesheets" in rel.parts:
            continue
        index.setdefault(rel.stem, []).append(str(rel).replace("\\", "/"))
    return index


def process(path: Path, index: dict[str, list[str]], apply: bool) -> tuple[int, list[str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    in_related = False
    changed = 0
    notes: list[str] = []
    for i, line in enumerate(lines):
        if line.startswith("## "):
            in_related = bool(RELATED_HEADINGS.match(line))
            continue
        if not in_related:
            continue
        m = BULLET.match(line)
        if not m:
            continue
        title = m.group(2).strip()
        targets = index.get(title)
        if not targets:
            notes.append(f"  未命中: {title!r}")
            continue
        if len(targets) > 1:
            notes.append(f"  歧义: {title!r} -> {targets}")
            continue
        lines[i] = f"{m.group(1)}[{title}]({targets[0]}){m.group(3) or ''}"
        changed += 1
    if changed and apply:
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return changed, notes


def main() -> None:
    apply = "--apply" in sys.argv
    index = build_index()
    total = 0
    for path in sorted(KNOWLEDGE.rglob("*.md")):
        rel = path.relative_to(KNOWLEDGE)
        if rel.name == "index.md" or "stylesheets" in rel.parts:
            continue
        changed, notes = process(path, index, apply)
        if changed or notes:
            print(f"{rel}: {'改写' if apply else '可改写'} {changed} 条")
            for note in notes:
                print(note)
        total += changed
    print(f"\n{'已改写' if apply else '可改写'}合计 {total} 条{'' if apply else '（dry-run，--apply 真写）'}")


if __name__ == "__main__":
    main()
