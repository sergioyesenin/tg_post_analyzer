from __future__ import annotations

from copy import deepcopy

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from agents.reporter import ReportConfig
from db.models import AppSetting
from services.settings_defaults import get_canonical_defaults
from services.settings_validation import validate_setting_payload


DEFAULT_SETTINGS: dict[str, dict] = get_canonical_defaults()


def _merge_dict(base: dict, extra: dict | None) -> dict:
    out = deepcopy(base)
    if not isinstance(extra, dict):
        return out
    for key, value in extra.items():
        out[key] = value
    return out


async def get_setting(session: AsyncSession, key: str) -> dict:
    row = (await session.execute(select(AppSetting).where(AppSetting.key == key))).scalar_one_or_none()
    default = deepcopy(DEFAULT_SETTINGS.get(key, {}))
    if row is None:
        return validate_setting_payload(key, default) if key in DEFAULT_SETTINGS else default
    merged = _merge_dict(default, row.value_json if isinstance(row.value_json, dict) else {})
    return validate_setting_payload(key, merged) if key in DEFAULT_SETTINGS else merged


async def get_all_settings(session: AsyncSession) -> dict[str, dict]:
    result: dict[str, dict] = {k: deepcopy(v) for k, v in DEFAULT_SETTINGS.items()}
    rows = (await session.execute(select(AppSetting))).scalars().all()
    for row in rows:
        merged = _merge_dict(result.get(row.key, {}), row.value_json if isinstance(row.value_json, dict) else {})
        result[row.key] = validate_setting_payload(row.key, merged) if row.key in DEFAULT_SETTINGS else merged
    return result


async def upsert_setting(
    session: AsyncSession,
    *,
    key: str,
    value_json: dict,
    description: str | None = None,
    updated_by_user_id: int | None = None,
) -> AppSetting:
    stmt = (
        insert(AppSetting)
        .values(
            key=key,
            value_json=value_json,
            description=description,
            updated_by_user_id=updated_by_user_id,
        )
        .on_conflict_do_update(
            index_elements=[AppSetting.key],
            set_={
                "value_json": value_json,
                "description": description,
                "updated_by_user_id": updated_by_user_id,
            },
        )
        .returning(AppSetting.id)
    )
    setting_id = (await session.execute(stmt)).scalar_one()
    setting = await session.get(AppSetting, setting_id)
    if setting is None:
        raise RuntimeError("AppSetting upsert failed")
    return setting


def report_config_from_settings(settings_payload: dict) -> ReportConfig:
    reports = settings_payload.get("reports", {})
    return ReportConfig(
        min_comments=int(reports.get("min_comments", DEFAULT_SETTINGS["reports"]["min_comments"])),
        report_word_target=int(reports.get("report_word_target", DEFAULT_SETTINGS["reports"]["report_word_target"])),
        report_word_min=int(reports.get("report_word_min", DEFAULT_SETTINGS["reports"]["report_word_min"])),
        report_word_max=int(reports.get("report_word_max", DEFAULT_SETTINGS["reports"]["report_word_max"])),
    )
