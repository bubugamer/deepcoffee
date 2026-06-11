from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import jwt
from fastapi import Depends, Header
from jwt import PyJWKClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.core.errors import AppError


@dataclass(frozen=True)
class AuthenticatedUser:
    id: str
    email: str | None = None
    role: str | None = None
    claims: dict[str, Any] | None = None


def _extract_bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise AppError(401, "missing_auth_token", "Missing Bearer token.")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise AppError(401, "invalid_auth_header", "Authorization must use Bearer token.")
    return token.strip()


def _user_from_claims(claims: dict[str, Any]) -> AuthenticatedUser:
    user_id = claims.get("sub") or claims.get("user_id")
    if not user_id:
        raise AppError(401, "invalid_auth_token", "Token does not identify a user.")
    return AuthenticatedUser(
        id=str(user_id),
        email=claims.get("email"),
        role=claims.get("role") or claims.get("aal"),
        claims=claims,
    )


def _decode_dev_token(token: str) -> AuthenticatedUser:
    # Local development token: "dev:<user_id>:<email>"
    _, _, rest = token.partition(":")
    user_id, _, email = rest.partition(":")
    if not user_id:
        raise AppError(401, "invalid_auth_token", "Invalid local development token.")
    return AuthenticatedUser(
        id=user_id,
        email=email or None,
        role="authenticated",
        claims={"sub": user_id, "email": email},
    )


def _decode_unsigned_token(token: str) -> AuthenticatedUser:
    # Local fallback only: decode without verifying signature.
    try:
        claims = jwt.decode(token, options={"verify_signature": False, "verify_aud": False})
    except jwt.PyJWTError as exc:
        raise AppError(401, "invalid_auth_token", "Invalid local development token.") from exc
    return _user_from_claims(claims)


@lru_cache(maxsize=4)
def _jwks_client(jwks_url: str) -> PyJWKClient:
    # PyJWKClient caches signing keys internally; cache the client per URL too.
    return PyJWKClient(jwks_url, cache_keys=True)


def _verify_supabase_jwt(token: str, settings: Settings) -> dict[str, Any]:
    # New Supabase projects sign with asymmetric keys (ES256) exposed via JWKS.
    try:
        signing_key = _jwks_client(settings.supabase_jwks_url).get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256", "RS256"],
            options={"verify_aud": False},
        )
    except jwt.PyJWTError as exc:
        raise AppError(401, "invalid_auth_token", "Invalid or expired token.") from exc
    except Exception as exc:  # JWKS fetch / key resolution failures
        raise AppError(401, "auth_verification_failed", "Could not verify the token.") from exc


def decode_user_token(token: str, settings: Settings) -> AuthenticatedUser:
    # Local development tokens (never accepted in production).
    if token.startswith("dev:") and not settings.is_production:
        return _decode_dev_token(token)

    # Real Supabase verification: asymmetric (JWKS/ES256) preferred, HS256 legacy fallback.
    if settings.supabase_jwks_url:
        return _user_from_claims(_verify_supabase_jwt(token, settings))

    if settings.supabase_jwt_secret:
        try:
            claims = jwt.decode(
                token,
                settings.supabase_jwt_secret,
                algorithms=settings.jwt_algorithms,
                options={"verify_aud": False},
            )
        except jwt.PyJWTError as exc:
            raise AppError(401, "invalid_auth_token", "Invalid or expired token.") from exc
        return _user_from_claims(claims)

    if settings.is_production:
        raise AppError(500, "auth_not_configured", "Authentication is not configured.")
    return _decode_unsigned_token(token)


async def get_current_user(
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> AuthenticatedUser:
    token = _extract_bearer_token(authorization)
    return decode_user_token(token, settings)


async def require_admin(
    user: AuthenticatedUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
) -> AuthenticatedUser:
    # 管理员来源有二：环境变量兜底名单，或 user_profiles.role == "admin"
    # （后者由 bootstrap 邀请码注册流程写入，见 services/bootstrap.py）。
    from app.models.tables import UserProfile  # 延迟导入，避免 core ↔ models 循环依赖

    profile = await session.get(UserProfile, user.id)
    if profile is not None and profile.status == "disabled":
        raise AppError(403, "account_disabled", "账号已被禁用，如有疑问请联系管理员。")
    if user.id in settings.admin_user_ids:
        return user
    if profile is not None and profile.role == "admin":
        return user
    # 本地开发便利：未配名单时任何登录用户视为管理员；生产环境一律拒绝。
    if not settings.admin_user_ids and not settings.is_production:
        return user
    raise AppError(403, "admin_required", "Admin access required.")
