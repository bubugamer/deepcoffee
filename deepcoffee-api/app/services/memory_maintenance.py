"""记忆后台维护：会话摘要（L2）+ 用户画像抽取（L3）。

在对话响应返回后由 FastAPI BackgroundTasks 异步跑：用独立 DB session、独立事务，
绝不阻塞对话、也绝不因失败影响对话（任何异常只记日志 + 回滚）。
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.db import get_sessionmaker
from app.repositories.brews import brew_record_repository
from app.repositories.coffea_sessions import coffea_session_repository
from app.repositories.user_memories import user_memory_repository
from app.services import memory_extract, session_summary
from app.services.memory_context import build_history

logger = logging.getLogger(__name__)

# 抽取时回看的最近对话轮数（比注入窗口宽一点，给抽取更多上下文）。
_EXTRACT_DIALOG_TURNS = 20


async def run_memory_maintenance(
    *,
    user_id: str,
    session_id: str,
    dropped_turns: list[dict[str, Any]],
    do_extract: bool,
    model: str,
) -> None:
    """后台维护：摘要（若有被裁老对话）+ 画像抽取（若本轮该抽）。独立 session，失败不外抛。"""
    if not dropped_turns and not do_extract:
        return
    sessionmaker = get_sessionmaker()
    try:
        async with sessionmaker() as session:
            cs = await coffea_session_repository.get(session, user_id=user_id, session_id=session_id)
            if cs is None:
                return

            # L2 会话摘要：把被移出窗口的老对话增量并入主题式摘要。
            if dropped_turns:
                new_summary = await session_summary.update_summary(
                    existing_summary=cs.summary,
                    dropped_turns=dropped_turns,
                    model=model,
                )
                if new_summary is not None:
                    coffea_session_repository.set_summary(cs, new_summary)

            # L3 画像抽取：从最近对话 + 冲煮记录沉淀稳定偏好 / 事实，去重 upsert。
            if do_extract:
                existing = await user_memory_repository.list_active(session, user_id)
                _, dialog_text = build_history(cs.recent_messages, max_turns=_EXTRACT_DIALOG_TURNS)
                brews, _ = await brew_record_repository.list(
                    session, user_id=user_id, page=1, page_size=5
                )
                candidates = await memory_extract.extract_memories(
                    recent_dialog=dialog_text,
                    recent_brews=[b.model_dump(mode="json") for b in brews],
                    existing_memories=[m.content for m in existing],
                    model=model,
                )
                for c in candidates:
                    await user_memory_repository.upsert(
                        session,
                        user_id=user_id,
                        kind=c["kind"],
                        content=c["content"],
                        confidence=c["confidence"],
                        source="dialog",
                    )

            await session.commit()
    except Exception as exc:  # noqa: BLE001 — 后台维护失败绝不影响对话
        logger.warning("memory maintenance failed for user %s: %s", user_id, exc)
