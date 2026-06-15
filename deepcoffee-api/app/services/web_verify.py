"""联网核实 web_verify（§9）的「综合」阶段：把检索到的来源摘要喂模型，产出带来源的回答。

设计同全局约定：有模型用模型、没有就回退（由调用方降级）。本模块只做「综合」一步，
检索在 web_search.py。模型被严格约束为只依据给定来源综合、不用记忆补；来源不足要诚实说明。
"""

from __future__ import annotations

import logging

from app.prompts import WEB_VERIFY_SYSTEM, WEB_VERIFY_USER_TEMPLATE
from app.services.multimodal import build_user_content, image_unavailable_note, select_model_for_images
from app.services.model_gateway import ModelGateway, model_gateway
from app.services.web_search import WebSource

logger = logging.getLogger(__name__)


def format_sources(sources: list[WebSource]) -> str:
    """拼成提示词里的 {source_summaries}：每条含标题 / 链接 / 时间 / 摘要。"""
    lines: list[str] = []
    for i, s in enumerate(sources, 1):
        when = s.published or f"访问于 {s.accessed}"
        lines.append(
            f"[{i}] {s.title}\n    链接：{s.url}\n    时间：{when}\n    摘要：{s.snippet or '（无摘要）'}"
        )
    return "\n\n".join(lines)


async def verify_with_model(
    question: str,
    sources: list[WebSource],
    *,
    model: str,
    image_context: dict | None = None,
    image_urls: list[str] | None = None,
    history: list[dict[str, str]] | None = None,
    vision_model: str | None = None,
    gateway: ModelGateway | None = None,
) -> str | None:
    """成功返回带来源的综合回答；网关不可用 / 无来源 / 出错返回 None。"""
    gw = gateway or model_gateway
    if not gw.enabled or not sources:
        return None
    use_images = bool(image_urls and vision_model and gw.vision_enabled)
    image_note = image_context or (
        "本轮用户附带了图片。请直接查看图片，判断用户问题是否引用了图片；如果图片与核实任务无关、"
        "看不清或不能从来源确认，就明确说明，不要编造图片里的品牌、文字或事实。"
        if use_images
        else image_unavailable_note(image_urls, vision_model)
    )
    user_content = WEB_VERIFY_USER_TEMPLATE.format(
        question=question, image_context=image_note, source_summaries=format_sources(sources)
    )
    model_to_use = select_model_for_images(text_model=model, vision_model=vision_model if use_images else None, image_urls=image_urls)
    messages = [{"role": "system", "content": WEB_VERIFY_SYSTEM}]
    if history:
        messages.extend(history)
    messages.append(
        {"role": "user", "content": build_user_content(user_content, image_urls if use_images else None)}
    )
    try:
        result = await gw.chat(
            model=model_to_use, messages=messages, temperature=0.2, max_tokens=900
        )
    except Exception as exc:  # noqa: BLE001 — 模型失败即降级（调用方退回知识库）
        logger.warning("web_verify model synthesis failed, fallback: %s", exc)
        return None
    text = (result.content or "").strip()
    return text or None
