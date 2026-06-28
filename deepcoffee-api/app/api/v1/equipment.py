"""我的器具：用户单件器具库存的查看与维护。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_member
from app.core.db import get_session
from app.core.errors import AppError
from app.core.security import AuthenticatedUser, get_current_user
from app.models.tables import UserEquipmentItem
from app.repositories.entities import entity_repository
from app.repositories.profiles import profile_repository
from app.repositories.equipment import _clean, _norm, equipment_repository
from app.schemas.equipment import EquipmentCreateRequest, EquipmentItem, EquipmentUpdateRequest
from app.services.entity_resolver import EQUIPMENT_CATEGORIES

router = APIRouter(prefix="/equipment", tags=["equipment"], dependencies=[Depends(require_member)])


@router.get("/catalog")
async def equipment_catalog(
    session: AsyncSession = Depends(get_session),
) -> dict[str, list[str]]:
    """公共器具目录（可穷尽实体的规范名），按类别给前端下拉直接选。

    与「我的器具」合并展示（目录 ∪ 用户已存）；用户输入别名/简写时由后端解析归一到这些规范名。
    """
    out: dict[str, list[str]] = {}
    for category in EQUIPMENT_CATEGORIES:
        items = await entity_repository.list(session, entity_type=category, status="active")
        out[category] = sorted({e.canonical_name for e in items if e.canonical_name})
    return out


async def _get_own(session: AsyncSession, user_id: str, equipment_id: str) -> UserEquipmentItem:
    row = await session.get(UserEquipmentItem, equipment_id)
    if row is None or row.user_id != user_id:
        raise AppError(404, "equipment_not_found", "Equipment item not found.")
    return row


@router.get("", response_model=list[EquipmentItem])
async def list_equipment(
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[EquipmentItem]:
    rows = await equipment_repository.list_for_user(session, user.id)
    return [EquipmentItem.model_validate(row) for row in rows]


@router.post("", response_model=EquipmentItem)
async def create_equipment(
    payload: EquipmentCreateRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> EquipmentItem:
    await profile_repository.get_or_create(session, user.id, user.email)
    row = await equipment_repository.upsert(
        session,
        user_id=user.id,
        category=payload.category,
        name=payload.name,
        notes=payload.notes,
        is_default=payload.is_default,
    )
    await session.refresh(row)
    return EquipmentItem.model_validate(row)


@router.patch("/{equipment_id}", response_model=EquipmentItem)
async def update_equipment(
    equipment_id: str,
    payload: EquipmentUpdateRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> EquipmentItem:
    row = await _get_own(session, user.id, equipment_id)
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise AppError(400, "empty_update", "Provide at least one field to update.")

    new_category = updates.pop("category", row.category)
    new_name = _clean(updates.pop("name", row.name))
    if not new_name:
        raise AppError(400, "invalid_equipment_name", "Equipment name is required.")
    duplicate = await equipment_repository.find_by_name(
        session, user_id=user.id, category=new_category, name=new_name
    )
    if duplicate and duplicate.id != row.id:
        raise AppError(409, "equipment_already_exists", "This equipment item already exists.")

    row.category = new_category
    row.name = new_name
    row.normalized_name = _norm(new_name)
    if "notes" in updates:
        row.notes = updates["notes"] or None
    is_default = updates.pop("is_default", None)
    if is_default is True:
        await session.flush()
        await equipment_repository.set_default(session, user_id=user.id, equipment_id=row.id)
    elif is_default is False:
        row.is_default = False
    await session.flush()
    await session.refresh(row)
    return EquipmentItem.model_validate(row)


@router.delete("/{equipment_id}")
async def delete_equipment(
    equipment_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, bool]:
    row = await _get_own(session, user.id, equipment_id)
    await session.delete(row)
    await session.flush()
    return {"deleted": True}
