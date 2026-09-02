from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import IdempotencyRecord

logger = logging.getLogger(__name__)
IDEMPOTENCY_RETENTION_DAYS = 30


class _OperationLockPool:
    def __init__(self) -> None:
        self._guard = asyncio.Lock()
        self._locks: dict[tuple[int, str, str], tuple[asyncio.Lock, int]] = {}

    @asynccontextmanager
    async def lock(self, key: tuple[int, str, str]):
        async with self._guard:
            lock, users = self._locks.get(key, (asyncio.Lock(), 0))
            self._locks[key] = (lock, users + 1)
        await lock.acquire()
        try:
            yield
        finally:
            lock.release()
            async with self._guard:
                current, users = self._locks[key]
                if users == 1:
                    self._locks.pop(key, None)
                else:
                    self._locks[key] = (current, users - 1)


_operation_locks = _OperationLockPool()


class IdempotencyConflictError(ValueError):
    pass


def canonical_request_hash(payload: object) -> str:
    encoded = json.dumps(
        jsonable_encoder(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


async def execute_idempotent(
    session: AsyncSession,
    *,
    user_id: int,
    operation_type: str,
    idempotency_key: str,
    payload: object,
    operation: Callable[[], Awaitable[dict[str, Any]]],
) -> dict[str, Any]:
    """Execute an event and persist its response in the same DB transaction."""
    async with _operation_locks.lock((user_id, operation_type, idempotency_key)):
        return await _execute_idempotent_locked(
            session,
            user_id=user_id,
            operation_type=operation_type,
            idempotency_key=idempotency_key,
            payload=payload,
            operation=operation,
        )


async def _execute_idempotent_locked(
    session: AsyncSession,
    *,
    user_id: int,
    operation_type: str,
    idempotency_key: str,
    payload: object,
    operation: Callable[[], Awaitable[dict[str, Any]]],
) -> dict[str, Any]:
    request_hash = canonical_request_hash(payload)

    # Authentication dependencies perform reads first. End that read transaction
    # so concurrent SQLite requests race on the unique INSERT, not on read->write
    # transaction upgrades (which can otherwise surface as `database is locked`).
    await session.commit()

    record = IdempotencyRecord(
        user_id=user_id,
        operation_type=operation_type,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        response_json={},
        expires_at=datetime.now(timezone.utc)
        + timedelta(days=IDEMPOTENCY_RETENTION_DAYS),
    )
    session.add(record)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        existing = await session.scalar(
            select(IdempotencyRecord).where(
                IdempotencyRecord.user_id == user_id,
                IdempotencyRecord.operation_type == operation_type,
                IdempotencyRecord.idempotency_key == idempotency_key,
            )
        )
        if existing is None:
            raise
        if existing.request_hash != request_hash:
            logger.warning(
                "Idempotency conflict rejected: user_id=%s operation=%s",
                user_id,
                operation_type,
            )
            raise IdempotencyConflictError(
                "Idempotency-Key уже использован с другими данными"
            ) from None
        return dict(existing.response_json)

    try:
        response = await operation()
        record.response_json = jsonable_encoder(response)
        await session.commit()
        return response
    except Exception:
        await session.rollback()
        raise
