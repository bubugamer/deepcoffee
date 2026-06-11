"""Helpers for passing a user's original image attachments into model calls.

Attachments are part of the current user turn, not a pre-classified action result.
These helpers keep image extraction and OpenAI-compatible multimodal message
assembly in one place so each Coffea capability can decide whether images matter.
"""

from __future__ import annotations

from typing import Any


def to_data_url(*, data_url: str | None = None, image_base64: str | None = None, mime_type: str | None = None) -> str | None:
    """Normalize an image attachment into a base64 data URI accepted by the vision model."""
    if data_url and data_url.startswith("data:"):
        return data_url
    if image_base64:
        return f"data:{mime_type or 'image/jpeg'};base64,{image_base64}"
    return None


def image_data_urls(attachments: list[dict[str, Any]] | None) -> list[str]:
    """Extract usable image data URIs from Coffea attachments.

    Pure remote URLs are intentionally ignored because the configured vision
    channel expects inline base64 data URIs.
    """
    urls: list[str] = []
    for attachment in attachments or []:
        if not isinstance(attachment, dict):
            continue
        url = to_data_url(
            data_url=attachment.get("data_url"),
            image_base64=attachment.get("image_base64"),
            mime_type=attachment.get("mime_type"),
        )
        if url:
            urls.append(url)
    return urls


def build_user_content(text: str, image_urls: list[str] | None = None) -> str | list[dict[str, Any]]:
    """Build OpenAI-compatible user content.

    Text-only calls keep the old string shape. Calls with images use multimodal
    content blocks so the same user turn can reach the selected role unchanged.
    """
    urls = [u for u in image_urls or [] if u]
    if not urls:
        return text
    content: list[dict[str, Any]] = [{"type": "text", "text": text}]
    content.extend({"type": "image_url", "image_url": {"url": url}} for url in urls)
    return content


def select_model_for_images(*, text_model: str, vision_model: str | None, image_urls: list[str] | None) -> str:
    """Use the vision model only when the current turn actually contains images."""
    if image_urls and vision_model:
        return vision_model
    return text_model


def image_unavailable_note(image_urls: list[str] | None, vision_model: str | None) -> str:
    """Return a short prompt note when images exist but no vision model is configured."""
    if image_urls and not vision_model:
        return "本轮用户附带了图片，但当前视觉模型不可用；不要假装看过图片，只能根据文字和已有上下文回答。"
    return "（无）"
