"""我的器具：用户器具资料的查看与维护。

数据来源有二：对话里 bean_recommend_params 闭环自动保存（equipment_repository.upsert），
以及本路由的手动增删改。两边共用同一张 user_equipment_profiles 表。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_member
from app.core.db import get_session
from app.core.errors import AppError
from app.core.security import AuthenticatedUser, get_current_user
from app.models.tables import UserEquipmentProfile
from app.repositories.equipment import equipment_repository
from app.schemas.equipment import EquipmentCreateRequest, EquipmentProfile, EquipmentUpdateRequest

router = APIRouter(prefix="/equipment", tags=["equipment"], dependencies=[Depends(require_member)])


async def _get_own(session: AsyncSession, user_id: str, equipment_id: str) -> UserEquipmentProfile:
    row = await session.get(UserEquipmentProfile, equipment_id)
    if row is None or row.user_id != user_id:
        raise AppError(404, "equipment_not_found", "Equipment profile not found.")
    return row


@router.get("", response_model=list[EquipmentProfile])
async def list_equipment(
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[EquipmentProfile]:
    rows = await equipment_repository.list_for_user(session, user.id)
    return [EquipmentProfile.model_validate(row) for row in rows]


@router.post("", response_model=EquipmentProfile)
async def create_equipment(
    payload: EquipmentCreateRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> EquipmentProfile:
    # 与对话自动保存同一条 upsert 路径：(brew_method, grinder, filter_media) 相同则合并而非重复建。
    row = await equipment_repository.upsert(
        session,
        user_id=user.id,
        brew_method=payload.brew_method,
        grinder=payload.grinder,
        filter_media=payload.filter_media,
        water=payload.water,
        label=payload.label,
    )
    # created_at / updated_at 由数据库生成，flush 后需 refresh 才能序列化
    await session.refresh(row)
    return EquipmentProfile.model_validate(row)


@router.patch("/{equipment_id}", response_model=EquipmentProfile)
async def update_equipment(
    equipment_id: str,
    payload: EquipmentUpdateRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> EquipmentProfile:
    row = await _get_own(session, user.id, equipment_id)
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise AppError(400, "empty_update", "Provide at least one field to update.")
    # is_default=True 走 set_default 维护单默认不变量；False 允许回到「无默认」状态。
    is_default = updates.pop("is_default", None)
    for key, value in updates.items():
        setattr(row, key, value)
    if is_default is True:
        await equipment_repository.set_default(session, user_id=user.id, equipment_id=row.id)
    elif is_default is False:
        row.is_default = False
    await session.flush()
    await session.refresh(row)
    return EquipmentProfile.model_validate(row)


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
