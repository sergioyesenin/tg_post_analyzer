from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import delete, insert, select, update
from sqlalchemy.exc import IntegrityError

from db.models import AuthRateLimitBucket
from db.session import engine

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _rate_limit_exception(*, retry_after: int) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Too many authentication attempts",
        headers={"Retry-After": str(retry_after)},
    )


def _rate_limit_unavailable_exception() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Authentication rate limiting is temporarily unavailable",
    )


class PostgresRateLimiter:
    _MAX_INSERT_RETRIES = 2

    def __init__(self) -> None:
        self._table = AuthRateLimitBucket.__table__

    async def check(self, *, scope: str, key: str, limit: int, window_seconds: int) -> None:
        now = _utcnow()
        window_start = now - timedelta(seconds=window_seconds)

        for _ in range(self._MAX_INSERT_RETRIES):
            async with engine.begin() as conn:
                row = (
                    await conn.execute(
                        select(
                            self._table.c.window_started_at,
                            self._table.c.attempt_count,
                        )
                        .where(
                            self._table.c.scope == scope,
                            self._table.c.bucket_key == key,
                        )
                        .with_for_update()
                    )
                ).first()

                if row is None:
                    try:
                        await conn.execute(
                            insert(self._table).values(
                                scope=scope,
                                bucket_key=key,
                                attempt_count=1,
                                window_started_at=now,
                                updated_at=now,
                            )
                        )
                        return
                    except IntegrityError:
                        continue

                bucket_window_started_at = _as_utc(row.window_started_at)
                if bucket_window_started_at < window_start:
                    await conn.execute(
                        update(self._table)
                        .where(
                            self._table.c.scope == scope,
                            self._table.c.bucket_key == key,
                        )
                        .values(
                            attempt_count=1,
                            window_started_at=now,
                            updated_at=now,
                        )
                    )
                    return

                if int(row.attempt_count) >= limit:
                    retry_after = max(
                        1,
                        int((bucket_window_started_at + timedelta(seconds=window_seconds) - now).total_seconds()),
                    )
                    raise _rate_limit_exception(retry_after=retry_after)

                await conn.execute(
                    update(self._table)
                    .where(
                        self._table.c.scope == scope,
                        self._table.c.bucket_key == key,
                    )
                    .values(
                        attempt_count=int(row.attempt_count) + 1,
                        updated_at=now,
                    )
                )
                return

        async with engine.begin() as conn:
            row = (
                await conn.execute(
                    select(
                        self._table.c.window_started_at,
                        self._table.c.attempt_count,
                    ).where(
                        self._table.c.scope == scope,
                        self._table.c.bucket_key == key,
                    )
                )
            ).first()
            if row is None:
                await conn.execute(
                    insert(self._table).values(
                        scope=scope,
                        bucket_key=key,
                        attempt_count=1,
                        window_started_at=now,
                        updated_at=now,
                    )
                )
                return

            bucket_window_started_at = _as_utc(row.window_started_at)
            if bucket_window_started_at < window_start:
                await conn.execute(
                    update(self._table)
                    .where(
                        self._table.c.scope == scope,
                        self._table.c.bucket_key == key,
                    )
                    .values(
                        attempt_count=1,
                        window_started_at=now,
                        updated_at=now,
                    )
                )
                return

            if int(row.attempt_count) >= limit:
                retry_after = max(
                    1,
                    int((bucket_window_started_at + timedelta(seconds=window_seconds) - now).total_seconds()),
                )
                raise _rate_limit_exception(retry_after=retry_after)

            await conn.execute(
                update(self._table)
                .where(
                    self._table.c.scope == scope,
                    self._table.c.bucket_key == key,
                )
                .values(
                    attempt_count=int(row.attempt_count) + 1,
                    updated_at=now,
                )
            )

    async def clear(self) -> None:
        async with engine.begin() as conn:
            await conn.execute(delete(self._table))


class AuthRateLimiter:
    def __init__(self) -> None:
        self._shared_backend = PostgresRateLimiter()

    async def check(self, *, scope: str, key: str, limit: int, window_seconds: int) -> None:
        try:
            await self._shared_backend.check(scope=scope, key=key, limit=limit, window_seconds=window_seconds)
        except HTTPException:
            raise
        except Exception:
            logger.exception(
                "Auth rate limiter shared backend failed for scope=%s; rejecting auth request without local fallback",
                scope,
            )
            raise _rate_limit_unavailable_exception()

    async def clear(self) -> None:
        try:
            await self._shared_backend.clear()
        except Exception:
            logger.exception("Failed to clear shared auth rate limiter backend")


auth_rate_limiter = AuthRateLimiter()


async def reset_auth_rate_limits() -> None:
    await auth_rate_limiter.clear()
