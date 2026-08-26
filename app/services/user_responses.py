from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import UserResponse, UserResponseType

CUSTOM_PREFIX = "custom:"
MAX_USER_RESPONSE_LENGTH = 500
ACTION_TYPES = {
    UserResponseType.COPING_ACTION,
    UserResponseType.REPLACEMENT,
    UserResponseType.PLAN_ACTION,
    UserResponseType.SOCIAL_RESPONSE,
    UserResponseType.LAPSE_PLAN,
}


class UserResponseValidationError(ValueError):
    pass


def normalize_user_text(value: str) -> str:
    text = re.sub(r"\s+", " ", value).strip()
    if not text:
        raise UserResponseValidationError("Напиши свой вариант")
    if len(text) > MAX_USER_RESPONSE_LENGTH:
        raise UserResponseValidationError(
            f"Ответ должен быть не длиннее {MAX_USER_RESPONSE_LENGTH} символов"
        )
    return text


def deduplication_key(value: str) -> str:
    normalized = normalize_user_text(value).casefold()
    return re.sub(r"[\s.!?…,:;]+$", "", normalized).strip()


def custom_value(text: str) -> str:
    return CUSTOM_PREFIX + normalize_user_text(text)


def custom_text(value: object) -> str | None:
    if not isinstance(value, str) or not value.startswith(CUSTOM_PREFIX):
        return None
    return normalize_user_text(value[len(CUSTOM_PREFIX) :])


def deduplicate_display_values(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = normalize_user_text(value)
        key = deduplication_key(text)
        if key not in seen:
            seen.add(key)
            result.append(text.rstrip(".!?…") + ".")
    return result


class UserResponseMemory:
    async def remember(
        self,
        session: AsyncSession,
        *,
        user_id: int,
        response_type: UserResponseType | str,
        value: str,
        source: str,
        source_ref: str | None = None,
        context_id: str | None = None,
        parent_response_id: int | None = None,
        focus: str | None = None,
        increment_usage: bool = True,
    ) -> UserResponse:
        kind = UserResponseType(response_type)
        text = normalize_user_text(value)
        normalized = deduplication_key(text)
        query = select(UserResponse).where(
            UserResponse.user_id == user_id,
            UserResponse.response_type == kind,
            UserResponse.normalized_value == normalized,
        )
        query = query.where(
            UserResponse.context_id.is_(None)
            if context_id is None
            else UserResponse.context_id == context_id,
            UserResponse.parent_response_id.is_(None)
            if parent_response_id is None
            else UserResponse.parent_response_id == parent_response_id,
            UserResponse.focus.is_(None) if focus is None else UserResponse.focus == focus,
        )
        existing = await session.scalar(query.order_by(UserResponse.id).limit(1))
        now = datetime.now(timezone.utc)
        if existing is not None:
            existing.value = text
            existing.last_used_at = now
            if increment_usage:
                existing.usage_count += 1
            await session.flush()
            return existing
        response = UserResponse(
            user_id=user_id,
            response_type=kind,
            value=text,
            normalized_value=normalized,
            context_id=context_id,
            parent_response_id=parent_response_id,
            focus=focus,
            source=source,
            source_ref=source_ref,
            usage_count=1,
            last_used_at=now,
        )
        session.add(response)
        await session.flush()
        return response

    async def get(self, session: AsyncSession, user_id: int, response_id: int) -> UserResponse | None:
        return await session.scalar(
            select(UserResponse).where(
                UserResponse.id == response_id, UserResponse.user_id == user_id
            )
        )

    async def ranked(
        self,
        session: AsyncSession,
        *,
        user_id: int,
        response_types: Iterable[UserResponseType | str],
        context_id: str | None = None,
        parent_response_id: int | None = None,
        focus: str | None = None,
        limit: int = 5,
    ) -> list[UserResponse]:
        kinds = [UserResponseType(item) for item in response_types]
        rows = list(
            (
                await session.scalars(
                    select(UserResponse).where(
                        UserResponse.user_id == user_id,
                        UserResponse.response_type.in_(kinds),
                    )
                )
            ).all()
        )

        def score(item: UserResponse) -> tuple[float, int, float, int]:
            exact_reason = 1 if parent_response_id and item.parent_response_id == parent_response_id else 0
            same_context = 1 if context_id and item.context_id == context_id else 0
            general = 1 if item.context_id is None else 0
            focus_match = 1 if not focus or item.focus in (None, focus) else 0
            average_effect = (
                item.effectiveness_sum / item.effectiveness_samples
                if item.effectiveness_samples
                else 0.0
            )
            rank: float = exact_reason * 10000 + same_context * 3000 + general * 300 + focus_match * 100
            rank += average_effect * 40 + min(item.usage_count, 20)
            return rank, item.usage_count, item.last_used_at.timestamp(), item.id

        relevant = [
            item
            for item in rows
            if (not focus or item.focus in (None, focus))
            and (
                item.context_id is None
                or context_id is None
                or item.context_id == context_id
            )
        ]
        ranked_rows = sorted(relevant, key=score, reverse=True)
        result: list[UserResponse] = []
        seen_values: set[str] = set()
        for item in ranked_rows:
            if item.normalized_value in seen_values:
                continue
            seen_values.add(item.normalized_value)
            result.append(item)
            if len(result) >= max(1, min(limit, 20)):
                break
        return result

    async def record_effectiveness(
        self, session: AsyncSession, response_id: int, effect_delta: int
    ) -> None:
        response = await session.get(UserResponse, response_id)
        if response is None or response.response_type not in ACTION_TYPES:
            return
        response.effectiveness_sum += effect_delta
        response.effectiveness_samples += 1
        response.last_used_at = datetime.now(timezone.utc)
        await session.flush()


user_response_memory = UserResponseMemory()
