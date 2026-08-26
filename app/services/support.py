from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    LapseType,
    NicotineDesireLog,
    NicotineLapse,
    ProgramProfile,
    SosAction,
    SosSession,
    User,
    UserResponse,
)
from app.services.quit_attempts import quit_attempt_service
from app.services.user_responses import ACTION_TYPES, user_response_memory


class SupportValidationError(ValueError):
    pass


SUPPORT_TYPES = {
    "breathing",
    "distraction",
    "change_activity",
    "replacement_action",
    "motivation",
    "personal_plan",
    "ai_support",
}
MIN_EFFECTIVENESS_SAMPLE_SIZE = 3
AIR_CLOUD_GAME_ID = "air_cloud_jump"


def validate_intensity(value: int) -> int:
    if value < 1 or value > 10:
        raise SupportValidationError("Intensity must be between 1 and 10")
    return value


class SupportService:
    async def air_cloud_best_height(
        self,
        session: AsyncSession,
        user_id: int,
    ) -> int:
        actions = (
            await session.scalars(
                select(SosAction)
                .join(SosSession, SosSession.id == SosAction.sos_session_id)
                .where(
                    SosSession.user_id == user_id,
                    SosAction.support_type == "distraction",
                )
            )
        ).all()
        best = 0
        for action in actions:
            metadata = action.metadata_json
            if not isinstance(metadata, dict) or metadata.get("game") != AIR_CLOUD_GAME_ID:
                continue
            value = metadata.get("best_height", metadata.get("height", 0))
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                best = max(best, max(0, int(value)))
        return best

    async def record_air_cloud_result(
        self,
        session: AsyncSession,
        action: SosAction,
        user_id: int,
        height: int,
        jumps: int,
        duration_seconds: int,
        boosts_used: int = 0,
    ) -> tuple[dict[str, object], bool]:
        if action.support_type != "distraction":
            raise SupportValidationError("SOS action is not a distraction game")
        previous_best = await self.air_cloud_best_height(session, user_id)
        safe_height = max(0, height)
        best_height = max(previous_best, safe_height)
        metadata: dict[str, object] = {
            "game": AIR_CLOUD_GAME_ID,
            "height": safe_height,
            "best_height": best_height,
            "jumps": max(0, jumps),
            "duration_seconds": max(0, duration_seconds),
            "boosts_used": max(0, boosts_used),
        }
        action.metadata_json = metadata
        await session.flush()
        return metadata, safe_height > previous_best

    async def program_profile(
        self, session: AsyncSession, user_id: int
    ) -> ProgramProfile | None:
        return await session.scalar(
            select(ProgramProfile).where(ProgramProfile.user_id == user_id)
        )

    async def log_desire(
        self,
        session: AsyncSession,
        user: User,
        intensity: int,
        trigger_id: str | None,
        emotion: str | None,
        note: str | None,
    ) -> NicotineDesireLog:
        attempt = await quit_attempt_service.current(session, user.id)
        entry = NicotineDesireLog(
            user_id=user.id,
            quit_attempt_id=attempt.id if attempt else None,
            intensity=validate_intensity(intensity),
            trigger_id=trigger_id,
            emotion=emotion,
            note=(note or "").strip() or None,
        )
        session.add(entry)
        await session.flush()
        return entry

    async def start_sos(
        self,
        session: AsyncSession,
        user: User,
        intensity_before: int,
        trigger_id: str | None,
        reason_response_id: int | None = None,
    ) -> SosSession:
        attempt = await quit_attempt_service.current(session, user.id)
        reason = None
        if reason_response_id is not None:
            reason = await user_response_memory.get(session, user.id, reason_response_id)
            if reason is None or reason.response_type.value not in {"trigger", "reason"}:
                raise SupportValidationError("Сохранённая причина не найдена")
        entry = SosSession(
            user_id=user.id,
            quit_attempt_id=attempt.id if attempt else None,
            exercise_type="pending",
            started_at=datetime.now(timezone.utc),
            intensity_before=validate_intensity(intensity_before),
            trigger_id=trigger_id,
            reason_response_id=reason.id if reason else None,
        )
        session.add(entry)
        await session.flush()
        return entry

    async def complete_sos(
        self,
        session: AsyncSession,
        entry: SosSession,
        support_type: str,
        support_action: str | None,
        intensity_after: int,
        nicotine_used_after: bool | None,
    ) -> SosSession:
        action = await self.start_sos_action(
            session, entry, support_type, support_action
        )
        await self.complete_sos_action(session, action, intensity_after)
        return await self.finish_sos(
            session, entry, intensity_after, nicotine_used_after
        )

    async def start_sos_action(
        self,
        session: AsyncSession,
        entry: SosSession,
        support_type: str,
        support_action: str | None,
        user_response_id: int | None = None,
        now: datetime | None = None,
    ) -> SosAction:
        if support_type not in SUPPORT_TYPES:
            raise SupportValidationError("Unknown support type")
        if entry.finished_at is not None:
            raise SupportValidationError("SOS session is already completed")
        last_sequence = await session.scalar(
            select(func.max(SosAction.sequence_number)).where(
                SosAction.sos_session_id == entry.id
            )
        )
        previous_intensity = await session.scalar(
            select(SosAction.intensity_after)
            .where(
                SosAction.sos_session_id == entry.id,
                SosAction.intensity_after.is_not(None),
            )
            .order_by(SosAction.sequence_number.desc())
            .limit(1)
        )
        response = None
        if user_response_id is not None:
            if entry.trigger_id == "driving":
                raise SupportValidationError(
                    "Во время вождения доступны только проверенные безопасные варианты"
                )
            response = await session.scalar(
                select(UserResponse)
                .join(User, User.id == UserResponse.user_id)
                .where(
                    UserResponse.id == user_response_id,
                    User.id == entry.user_id,
                )
            )
            if response is None or response.response_type not in ACTION_TYPES:
                raise SupportValidationError("Сохранённое действие не найдено")
        action = SosAction(
            sos_session_id=entry.id,
            support_type=support_type,
            support_action=support_action,
            user_response_id=response.id if response else None,
            trigger_id=entry.trigger_id,
            intensity_before=previous_intensity or entry.intensity_before,
            started_at=now or datetime.now(timezone.utc),
            sequence_number=int(last_sequence or 0) + 1,
        )
        session.add(action)
        await session.flush()
        return action

    async def complete_sos_action(
        self,
        session: AsyncSession,
        action: SosAction,
        intensity_after: int | None = None,
        metadata: dict[str, object] | None = None,
        now: datetime | None = None,
    ) -> SosAction:
        was_completed = action.completed_at is not None
        if intensity_after is not None:
            action.intensity_after = validate_intensity(intensity_after)
        if metadata is not None:
            action.metadata_json = metadata
        if action.completed_at is None:
            action.completed_at = now or datetime.now(timezone.utc)
        if not was_completed and action.user_response_id is not None and action.effect_delta is not None:
            await user_response_memory.record_effectiveness(
                session, action.user_response_id, action.effect_delta
            )
        await session.flush()
        return action

    async def update_sos_trigger(
        self,
        session: AsyncSession,
        entry: SosSession,
        trigger_id: str | None,
        action_id: int | None = None,
    ) -> SosSession:
        entry.trigger_id = trigger_id
        if action_id is not None:
            action = await session.scalar(
                select(SosAction).where(
                    SosAction.id == action_id,
                    SosAction.sos_session_id == entry.id,
                )
            )
            if action is None:
                raise SupportValidationError("SOS action not found")
            action.trigger_id = trigger_id
        await session.flush()
        return entry

    async def tool_analytics(
        self,
        session: AsyncSession,
        user_id: int,
    ) -> dict[str, object]:
        rows = (
            await session.execute(
                select(SosAction, SosSession.trigger_id)
                .join(SosSession, SosSession.id == SosAction.sos_session_id)
                .where(SosSession.user_id == user_id)
            )
        ).all()
        usage: dict[str, int] = {}
        overall: dict[str, list[int]] = {}
        by_trigger: dict[str, dict[str, list[int]]] = {}
        for action, session_trigger in rows:
            usage[action.support_type] = usage.get(action.support_type, 0) + 1
            effect = action.effect_delta
            if action.completed_at is None or effect is None:
                continue
            overall.setdefault(action.support_type, []).append(effect)
            trigger_id = action.trigger_id or session_trigger
            if trigger_id:
                by_trigger.setdefault(trigger_id, {}).setdefault(
                    action.support_type, []
                ).append(effect)

        def summaries(groups: dict[str, list[int]]) -> dict[str, dict[str, float | int]]:
            return {
                support_type: {
                    "sample_size": len(effects),
                    "average_effect": round(sum(effects) / len(effects), 2),
                }
                for support_type, effects in groups.items()
            }

        def best(groups: dict[str, list[int]]) -> str | None:
            eligible = [
                (sum(effects) / len(effects), len(effects), support_type)
                for support_type, effects in groups.items()
                if len(effects) >= MIN_EFFECTIVENESS_SAMPLE_SIZE
            ]
            if not eligible:
                return None
            return max(eligible, key=lambda item: (item[0], item[1], item[2]))[2]

        return {
            "minimum_sample_size": MIN_EFFECTIVENESS_SAMPLE_SIZE,
            "usage_count": usage,
            "overall": summaries(overall),
            "by_trigger": {
                trigger_id: summaries(groups) for trigger_id, groups in by_trigger.items()
            },
            "best_overall_tool": best(overall),
            "best_tool_by_trigger": {
                trigger_id: winner
                for trigger_id, groups in by_trigger.items()
                if (winner := best(groups)) is not None
            },
        }

    async def finish_sos(
        self,
        session: AsyncSession,
        entry: SosSession,
        intensity_after: int,
        nicotine_used_after: bool | None,
        now: datetime | None = None,
    ) -> SosSession:
        latest_action = await session.scalar(
            select(SosAction)
            .where(SosAction.sos_session_id == entry.id)
            .order_by(SosAction.sequence_number.desc())
            .limit(1)
        )
        if latest_action is not None:
            entry.exercise_type = latest_action.support_type
            entry.support_type = latest_action.support_type
            entry.support_action = latest_action.support_action
        entry.intensity_after = validate_intensity(intensity_after)
        entry.nicotine_used_after = nicotine_used_after
        entry.finished_at = now or datetime.now(timezone.utc)
        await session.flush()
        return entry

    async def register_lapse(
        self,
        session: AsyncSession,
        user: User,
        lapse_type: LapseType,
        trigger_id: str | None,
        note: str | None,
    ) -> NicotineLapse:
        attempt = await quit_attempt_service.current(session, user.id)
        moment = datetime.now(timezone.utc)
        lapse = NicotineLapse(
            user_id=user.id,
            quit_attempt_id=attempt.id if attempt else None,
            occurred_at=moment,
            lapse_type=lapse_type,
            trigger_id=trigger_id,
            note=(note or "").strip() or None,
        )
        session.add(lapse)
        await quit_attempt_service.close_as_relapsed(
            session, user, reason=lapse_type.value, now=moment
        )
        await session.flush()
        return lapse


support_service = SupportService()
