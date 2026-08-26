from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import QuitAttempt, QuitAttemptStatus, User
from app.services.progress import as_utc


@dataclass(frozen=True)
class QuitAttemptMetrics:
    current_seconds: int
    best_seconds: int
    total_seconds: int
    attempts: int


class QuitAttemptService:
    async def current(self, session: AsyncSession, user_id: int) -> QuitAttempt | None:
        return await session.scalar(
            select(QuitAttempt).where(
                QuitAttempt.user_id == user_id,
                QuitAttempt.active_marker.is_(True),
            )
        )

    async def start_program(
        self,
        session: AsyncSession,
        user: User,
        now: datetime | None = None,
    ) -> QuitAttempt:
        moment = now or datetime.now(timezone.utc)
        current = await self.current(session, user.id)
        if user.program_started_at is None:
            user.program_started_at = moment
        if current is not None:
            user.quit_started_at = current.started_at
            return current

        attempt_count = await session.scalar(
            select(func.count(QuitAttempt.id)).where(QuitAttempt.user_id == user.id)
        )
        started_at = user.quit_started_at if not attempt_count and user.quit_started_at else moment
        attempt = QuitAttempt(
            user_id=user.id,
            started_at=started_at,
            status=QuitAttemptStatus.ACTIVE,
            active_marker=True,
        )
        session.add(attempt)
        user.quit_started_at = started_at
        await session.flush()
        return attempt

    async def restart(
        self,
        session: AsyncSession,
        user: User,
        now: datetime | None = None,
    ) -> QuitAttempt:
        current = await self.current(session, user.id)
        if current is not None:
            return current
        moment = now or datetime.now(timezone.utc)
        attempt = QuitAttempt(
            user_id=user.id,
            started_at=moment,
            status=QuitAttemptStatus.ACTIVE,
            active_marker=True,
        )
        session.add(attempt)
        user.quit_started_at = moment
        await session.flush()
        return attempt

    async def close_as_relapsed(
        self,
        session: AsyncSession,
        user: User,
        reason: str,
        now: datetime | None = None,
    ) -> QuitAttempt | None:
        attempt = await self.current(session, user.id)
        if attempt is None:
            return None
        moment = now or datetime.now(timezone.utc)
        attempt.ended_at = moment
        attempt.status = QuitAttemptStatus.RELAPSED
        attempt.end_reason = reason
        attempt.active_marker = None
        user.quit_started_at = None
        await session.flush()
        return attempt

    async def metrics(
        self,
        session: AsyncSession,
        user_id: int,
        now: datetime | None = None,
    ) -> QuitAttemptMetrics:
        moment = now or datetime.now(timezone.utc)
        attempts = (
            await session.scalars(
                select(QuitAttempt)
                .where(QuitAttempt.user_id == user_id)
                .order_by(QuitAttempt.started_at)
            )
        ).all()
        durations: list[int] = []
        current_seconds = 0
        for attempt in attempts:
            end = attempt.ended_at or moment
            seconds = max(0, int((as_utc(end) - as_utc(attempt.started_at)).total_seconds()))
            durations.append(seconds)
            if attempt.active_marker:
                current_seconds = seconds
        return QuitAttemptMetrics(
            current_seconds=current_seconds,
            best_seconds=max(durations, default=0),
            total_seconds=sum(durations),
            attempts=len(attempts),
        )


quit_attempt_service = QuitAttemptService()
