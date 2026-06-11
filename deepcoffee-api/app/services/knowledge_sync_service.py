"""知识库同步管线：公共实体库 → Markdown（提案 mark-applied 时触发）。

这条管线**不同于**用户/AI 直接编辑知识库——它只把已审核进入公共实体库的结构化实体事实，
写入或更新 Markdown 词条，并在 `knowledge_sync_records` 留同步轨迹。

Beta 取「记账优先」：计算目标 Markdown 内容与 content_hash 并 upsert 同步记录；只有当知识库
目录可写（`write=True` 且非只读挂载）时才真正落盘。这样在 Docker 只读挂载下也不会报错，
同步意图仍完整记录，将来切到可写卷即可真正生成/更新文件。
"""

from __future__ import annotations

import hashlib
import logging
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import KnowledgeSyncRecord, PublicEntity

logger = logging.getLogger(__name__)

# entity_type → 知识库子目录。
_TYPE_DIR = {
    "roaster": "roasters",
    "coffee_source": "coffee-sources",
    "green_bean_merchant": "green-merchants",
    "origin": "origins",
    "varietal": "varietals",
    "process_method": "processing",
    "roaster_product": "roaster-products",
    "green_bean_product": "green-bean-products",
}


def _slug(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").strip().lower()
    value = re.sub(r"[^\w.-]+", "-", value, flags=re.UNICODE)
    return re.sub(r"-{2,}", "-", value).strip("-") or "entity"


class KnowledgeSyncService:
    def default_path(self, entity: PublicEntity) -> str:
        sub = _TYPE_DIR.get(entity.entity_type, "entities")
        return f"{sub}/{_slug(entity.canonical_name)}.md"

    def render_markdown(self, entity: PublicEntity) -> str:
        lines = [
            "---",
            f"title: {entity.canonical_name}",
            f"entity_type: {entity.entity_type}",
            "scope: public",
            "status: active",
            "visibility: support",
            "indexable: true",
            "knowledge_role: entity_seed",
            "search:",
            "  exclude: true",
            "---",
            "",
            f"# {entity.canonical_name}",
            "",
        ]
        if entity.summary:
            lines.append(entity.summary)
        else:
            lines.append("这是一条公共实体资料，用于帮助系统识别豆袋、豆卡和冲煮记录中的实体名称。")
        return "\n".join(lines) + "\n"

    async def sync_entity(
        self,
        session: AsyncSession,
        entity_id: str,
        *,
        markdown_path: str | None = None,
        knowledge_dir: Path | None = None,
        write: bool = False,
    ) -> KnowledgeSyncRecord | None:
        entity = await session.get(PublicEntity, entity_id)
        if entity is None:
            return None
        path = markdown_path or self.default_path(entity)
        content = self.render_markdown(entity)
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

        result = await session.execute(
            select(KnowledgeSyncRecord).where(
                KnowledgeSyncRecord.entity_id == entity_id,
                KnowledgeSyncRecord.markdown_path == path,
            )
        )
        record = result.scalar_one_or_none()
        unchanged = record is not None and record.content_hash == content_hash

        if record is None:
            record = KnowledgeSyncRecord(
                entity_id=entity_id, sync_target="markdown", markdown_path=path
            )
            session.add(record)
        record.content_hash = content_hash
        record.last_synced_at = datetime.now(timezone.utc)
        record.status = "unchanged" if unchanged else "synced"

        if write and knowledge_dir is not None:
            try:
                target = knowledge_dir / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
                record.status = "written"
            except OSError as exc:  # 只读挂载等：记账保留，落盘失败不抛
                logger.warning("knowledge sync write skipped for %s: %s", path, exc)
                record.status = "write_skipped"

        await session.flush()
        await session.refresh(record)
        return record


knowledge_sync_service = KnowledgeSyncService()
