from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User

CURRENT_PERSONAL_DATA_CONSENT_VERSION = "1.0"
PERSONAL_DATA_CONSENT_PATH = "/personal-data-consent"


def has_current_personal_data_consent(user: User) -> bool:
    return bool(
        user.personal_data_consent_at is not None
        and user.personal_data_consent_version
        == CURRENT_PERSONAL_DATA_CONSENT_VERSION
    )


def require_current_personal_data_consent(user: User) -> None:
    if not has_current_personal_data_consent(user):
        raise HTTPException(
            status.HTTP_428_PRECONDITION_REQUIRED,
            "Требуется согласие на обработку персональных данных",
        )


async def find_telegram_user(session: AsyncSession, telegram_id: int) -> User | None:
    return await session.scalar(select(User).where(User.telegram_id == telegram_id))


async def get_or_create_telegram_user(
    session: AsyncSession,
    *,
    telegram_id: int,
    first_name: str,
    username: str | None,
) -> User:
    user = await find_telegram_user(session, telegram_id)
    if user is None:
        user = User(
            telegram_id=telegram_id,
            telegram_first_name=first_name,
            username=username,
        )
        session.add(user)
        await session.flush()
    else:
        user.telegram_first_name = first_name
        user.username = username
    return user


async def accept_personal_data_consent(
    session: AsyncSession,
    user: User,
    *,
    now: datetime | None = None,
) -> User:
    if not has_current_personal_data_consent(user):
        user.personal_data_consent_at = now or datetime.now(timezone.utc)
        user.personal_data_consent_version = CURRENT_PERSONAL_DATA_CONSENT_VERSION
        await session.flush()
    return user


def personal_data_consent_url(mini_app_url: str | None) -> str | None:
    if not mini_app_url:
        return None
    parts = urlsplit(mini_app_url)
    if not parts.scheme or not parts.netloc:
        return None
    return urlunsplit(
        (parts.scheme, parts.netloc, PERSONAL_DATA_CONSENT_PATH, "", "")
    )
