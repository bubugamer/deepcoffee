"""把聊天图片上传到 Supabase Storage 公开桶，返回公开 URL（跨设备回看）。

vision 仍用请求里的 base64；这里另存一份到图床，URL 记进会话历史。
service role key 上传，绕过 RLS。未配 Supabase / 上传失败 → 跳过该图，绝不阻断聊天。
"""

from __future__ import annotations

import asyncio
import base64
import logging
import re
from uuid import uuid4

import httpx

from app.core.config import Settings
from app.services.multimodal import image_data_urls

logger = logging.getLogger(__name__)

BUCKET = "chat-images"
_EXT = {"image/jpeg": "jpg", "image/jpg": "jpg", "image/png": "png", "image/webp": "webp", "image/gif": "gif"}
_DATA_URL_RE = re.compile(r"^data:([^;]+);base64,(.+)$", re.DOTALL)


def _decode(data_url: str) -> tuple[bytes, str] | None:
    m = _DATA_URL_RE.match(data_url)
    if not m:
        return None
    mime = m.group(1).lower()
    try:
        return base64.b64decode(m.group(2)), mime
    except (ValueError, TypeError):
        return None


async def _upload_one(client: httpx.AsyncClient, base: str, key: str, user_id: str, data_url: str) -> str | None:
    decoded = _decode(data_url)
    if decoded is None:
        return None
    raw, mime = decoded
    path = f"{user_id}/{uuid4().hex}.{_EXT.get(mime, 'jpg')}"
    try:
        resp = await client.post(
            f"{base}/storage/v1/object/{BUCKET}/{path}",
            content=raw,
            # 新版 sb_secret_ 密钥不是 JWT：storage 对象接口必须带 apikey 头鉴权，
            # 只发 Authorization 会被当 JWT 解码报「Invalid Compact JWS」。
            headers={
                "apikey": key,
                "Authorization": f"Bearer {key}",
                "Content-Type": mime,
                "x-upsert": "true",
            },
        )
        if resp.status_code >= 400:
            logger.warning("chat image upload failed (%s): %s", resp.status_code, resp.text[:200])
            return None
    except Exception as exc:  # noqa: BLE001 — 图床不可用不阻断聊天
        logger.warning("chat image upload error: %s", exc)
        return None
    return f"{base}/storage/v1/object/public/{BUCKET}/{path}"


async def upload_chat_images(
    attachments: list[dict] | None, *, user_id: str, settings: Settings
) -> list[str]:
    """上传本轮所有图片附件，返回成功的公开 URL 列表（保持顺序，失败的略过）。"""
    base = (settings.supabase_url or "").rstrip("/")
    key = settings.supabase_secret_key
    data_urls = image_data_urls(attachments)
    if not base or not key or not data_urls:
        return []
    # trust_env=False：直连 Supabase，不受本机代理干扰（Cloud Run 上无代理，无副作用）。
    async with httpx.AsyncClient(timeout=20, trust_env=False) as client:
        results = await asyncio.gather(*(_upload_one(client, base, key, user_id, d) for d in data_urls))
    return [u for u in results if u]
