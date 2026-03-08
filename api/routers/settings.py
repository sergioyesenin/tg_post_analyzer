from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import AppSetting
from deps import get_session, require_roles
from schemas.settings import AppSettingOut, AppSettingUpdateIn
from services.auth import AuthUser, write_audit_log
from services.settings_store import DEFAULT_SETTINGS, get_all_settings, upsert_setting
from services.settings_validation import validate_setting_payload

router = APIRouter()


@router.get("/", response_model=list[AppSettingOut])
async def list_settings(
    _: AuthUser = Depends(require_roles("admin")),
    session: AsyncSession = Depends(get_session),
):
    rows = (await session.execute(select(AppSetting).order_by(AppSetting.key.asc()))).scalars().all()
    return [
        AppSettingOut(
            key=row.key,
            value_json=row.value_json if isinstance(row.value_json, dict) else {},
            description=row.description,
            updated_by_user_id=row.updated_by_user_id,
            updated_at=row.updated_at,
        )
        for row in rows
    ]


@router.get("/effective")
async def effective_settings(
    _: AuthUser = Depends(require_roles("admin", "analyst")),
    session: AsyncSession = Depends(get_session),
):
    return await get_all_settings(session)


@router.put("/{key}", response_model=AppSettingOut)
async def update_setting(
    key: str,
    data: AppSettingUpdateIn,
    current_user: AuthUser = Depends(require_roles("admin")),
    session: AsyncSession = Depends(get_session),
):
    """
    Supported keys: ingest, reports, retention, jobs, api, monitor, features.
    """
    if key not in DEFAULT_SETTINGS:
        raise HTTPException(status_code=404, detail=f"Unknown setting key: {key}")
    current_payload = await get_all_settings(session)
    base = current_payload.get(key, DEFAULT_SETTINGS[key])
    merged_payload = dict(base)
    merged_payload.update(data.value_json or {})
    try:
        normalized_payload = validate_setting_payload(key, merged_payload)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid setting payload: {exc}") from exc
    saved = await upsert_setting(
        session,
        key=key,
        value_json=normalized_payload,
        description=data.description,
        updated_by_user_id=current_user.id,
    )
    await write_audit_log(
        session,
        action="settings.update",
        actor_user_id=current_user.id,
        target_type="app_setting",
        target_id=key,
        details={"value_json": normalized_payload},
    )
    await session.commit()
    return AppSettingOut(
        key=saved.key,
        value_json=saved.value_json if isinstance(saved.value_json, dict) else {},
        description=saved.description,
        updated_by_user_id=saved.updated_by_user_id,
        updated_at=saved.updated_at,
    )
