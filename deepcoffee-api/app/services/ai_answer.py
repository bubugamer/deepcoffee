"""Use the configured model gateway to answer from knowledge-base excerpts.

设计：**有模型用模型、没有就回退本地**。调用方先用本地知识库选文件 + 摘录拿到 grounding
来源,再调这里;任何失败（网关未配、模型报错）都返回 None,调用方退回本地摘录式回答。

模型被严格约束为「只依据提供的知识库摘录作答」,降低幻觉。
"""

from __future__ import annotations

import logging

from app.prompts import KNOWLEDGE_ANSWER_SYSTEM
from app.schemas.knowledge import GroundingDoc
from app.services.multimodal import build_user_content, image_unavailable_note, select_model_for_images
from app.services.model_gateway import ModelGateway, is_provider_quota_error, model_gateway

logger = logging.getLogger(__name__)

# 提示词集中在 app/prompts（与 docs/deepcoffee-ai-prompts.md §3 逐字一致）。
_SYSTEM_PROMPT = KNOWLEDGE_ANSWER_SYSTEM


async def answer_with_model(
    question: str,
    grounding: list[GroundingDoc],
    *,
    model: str,
    image_urls: list[str] | None = None,
    vision_model: str | None = None,
    gateway: ModelGateway | None = None,
    failure_reasons: list[str] | None = None,
) -> str | None:
    """成功返回模型答案字符串；任何条件不满足或出错返回 None（调用方回退本地）。

    grounding 是选中知识库文章的**整篇正文**（已去 frontmatter、按长度护栏截断）。
    failure_reasons：可选收集器，命中服务端模型 key 配额/欠费时追加 "provider_quota"，
    调用方据此在降级答案里显式提示用户（用户额度已在 DeepCoffee 内部提前门禁，这里不涉及）。
    """
    gw = gateway or model_gateway
    if not gw.enabled or not grounding:
        return None
    docs = "\n\n".join(f"【{d.title}】\n{d.content}" for d in grounding)
    use_images = bool(image_urls and vision_model and gw.vision_enabled)
    image_note = (
        "本轮用户附带了图片。请结合图片判断用户问题是否引用了图片；如果图片与问题无关、"
        "看不清或不能提供知识库依据，就明确说明不依赖图片，不要编造图片内容。"
        if use_images
        else image_unavailable_note(image_urls, vision_model)
    )
    user_text = f"知识库文章内容：\n{docs}\n\n本轮图片说明：\n{image_note}\n\n用户问题：{question}"
    model_to_use = select_model_for_images(text_model=model, vision_model=vision_model if use_images else None, image_urls=image_urls)
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": build_user_content(user_text, image_urls if use_images else None)},
    ]
    try:
        result = await gw.chat(model=model_to_use, messages=messages, temperature=0.3, max_tokens=700)
    except Exception as exc:  # noqa: BLE001 — 模型失败即回退本地，不影响问答可用性
        if is_provider_quota_error(exc):
            # 服务端模型 key 配额/欠费：ERROR 级（Sentry 可捕获），管理员需充值。
            logger.error("knowledge model answer blocked by provider quota/balance: %s", exc)
            if failure_reasons is not None:
                failure_reasons.append("provider_quota")
        else:
            logger.warning("knowledge model answer failed, falling back to local: %s", exc)
        return None
    answer = (result.content or "").strip()
    return answer or None
