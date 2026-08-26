from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.mini_app import support_service
from app.db.base import Base
from app.db.models import NicotineType, SmokingProfile, SosAction, SosSession, User
from app.services.support import MIN_EFFECTIVENESS_SAMPLE_SIZE


async def make_context(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'sos-analytics.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session = async_sessionmaker(engine, expire_on_commit=False)()
    user = User(telegram_id=700, telegram_first_name="SOS")
    session.add(user)
    await session.flush()
    profile = SmokingProfile(
        user_id=user.id,
        nicotine_type=NicotineType.CIGARETTES,
        years_of_use=Decimal("2"),
        daily_units=Decimal("8"),
        consumption_parameters={},
        cost_parameters={},
        monthly_expense=Decimal("2400"),
        yearly_expense=Decimal("28800"),
        lifetime_expense=Decimal("57600"),
        projected_five_year_expense=Decimal("144000"),
    )
    session.add(profile)
    await session.flush()
    return user, session, engine


async def record_action(session, user, trigger: str, tool: str, before: int, after: int):
    sos = await support_service.start_sos(session, user, before, trigger)
    action = await support_service.start_sos_action(session, sos, tool, None)
    await support_service.complete_sos_action(session, action, after)
    await support_service.finish_sos(session, sos, after, False)
    return action


@pytest.mark.parametrize(
    ("before", "after", "effect"),
    [(8, 5, 3), (5, 5, 0), (5, 7, -2)],
)
def test_sos_action_effect_delta(before: int, after: int, effect: int) -> None:
    action = SosAction(
        sos_session_id=1,
        support_type="breathing",
        sequence_number=1,
        intensity_before=before,
        intensity_after=after,
    )
    assert action.effect_delta == effect


@pytest.mark.asyncio
async def test_legacy_action_counts_as_usage_but_not_effectiveness(tmp_path) -> None:
    user, session, engine = await make_context(tmp_path)
    async with session:
        sos = await support_service.start_sos(session, user, 8, "stress")
        session.add(
            SosAction(
                sos_session_id=sos.id,
                support_type="breathing",
                sequence_number=1,
                started_at=sos.started_at,
                completed_at=sos.started_at,
            )
        )
        await session.flush()
        analytics = await support_service.tool_analytics(session, user.id)
        assert analytics["usage_count"] == {"breathing": 1}
        assert analytics["overall"] == {}
        assert analytics["best_overall_tool"] is None
    await engine.dispose()


@pytest.mark.asyncio
async def test_minimum_sample_size_controls_overall_and_trigger_best(tmp_path) -> None:
    user, session, engine = await make_context(tmp_path)
    async with session:
        for _ in range(MIN_EFFECTIVENESS_SAMPLE_SIZE - 1):
            await record_action(session, user, "stress", "change_activity", 8, 4)
        analytics = await support_service.tool_analytics(session, user.id)
        assert analytics["best_overall_tool"] is None
        assert analytics["best_tool_by_trigger"] == {}

        await record_action(session, user, "stress", "change_activity", 8, 4)
        for _ in range(MIN_EFFECTIVENESS_SAMPLE_SIZE):
            await record_action(session, user, "stress", "breathing", 8, 7)
        analytics = await support_service.tool_analytics(session, user.id)
        assert analytics["best_overall_tool"] == "change_activity"
        assert analytics["best_tool_by_trigger"]["stress"] == "change_activity"
        assert analytics["overall"]["change_activity"] == {
            "sample_size": 3,
            "average_effect": 4.0,
        }
    await engine.dispose()


@pytest.mark.asyncio
async def test_trigger_best_can_override_overall_best(tmp_path) -> None:
    user, session, engine = await make_context(tmp_path)
    async with session:
        for _ in range(3):
            await record_action(session, user, "stress", "change_activity", 8, 4)
            await record_action(session, user, "stress", "breathing", 8, 7)
        for _ in range(9):
            await record_action(session, user, "coffee", "breathing", 9, 3)
        analytics = await support_service.tool_analytics(session, user.id)
        assert analytics["best_overall_tool"] == "breathing"
        assert analytics["best_tool_by_trigger"]["stress"] == "change_activity"
    await engine.dispose()


@pytest.mark.asyncio
async def test_repeated_actions_keep_one_session_and_chain_intensity(tmp_path) -> None:
    user, session, engine = await make_context(tmp_path)
    async with session:
        sos = await support_service.start_sos(session, user, 9, "stress")
        first = await support_service.start_sos_action(session, sos, "breathing", None)
        await support_service.complete_sos_action(session, first, 7)
        second = await support_service.start_sos_action(session, sos, "breathing", None)
        await support_service.complete_sos_action(
            session, second, 5, {"cycles": 4, "ended_early": False}
        )
        await support_service.finish_sos(session, sos, 5, False)

        assert first.sos_session_id == second.sos_session_id == sos.id
        assert [first.sequence_number, second.sequence_number] == [1, 2]
        assert first.intensity_before == 9
        assert first.intensity_after == 7
        assert second.intensity_before == 7
        assert second.intensity_after == 5
        assert second.metadata_json == {"cycles": 4, "ended_early": False}
        assert first.trigger_id == "stress"
        assert second.trigger_id == "stress"
        assert sos.trigger_id == "stress"
        assert await session.scalar(
            select(func.count(SosSession.id)).where(SosSession.user_id == user.id)
        ) == 1
        assert sos.intensity_after == 5
        assert sos.finished_at is not None
    await engine.dispose()


@pytest.mark.asyncio
async def test_air_cloud_record_persists_and_never_decreases(tmp_path) -> None:
    user, session, engine = await make_context(tmp_path)
    async with session:
        sos = await support_service.start_sos(session, user, 8, "stress")
        action = await support_service.start_sos_action(
            session, sos, "distraction", None
        )
        first, is_new = await support_service.record_air_cloud_result(
            session, action, user.id, 386, 24, 47
        )
        assert is_new is True
        assert first == {
            "game": "air_cloud_jump",
            "height": 386,
            "best_height": 386,
            "jumps": 24,
            "duration_seconds": 47,
            "boosts_used": 0,
        }
        assert await support_service.air_cloud_best_height(session, user.id) == 386

        retry, is_new = await support_service.record_air_cloud_result(
            session, action, user.id, 120, 8, 14
        )
        assert is_new is False
        assert retry["height"] == 120
        assert retry["best_height"] == 386
        assert await support_service.air_cloud_best_height(session, user.id) == 386
    await engine.dispose()


@pytest.mark.asyncio
async def test_air_cloud_record_ignores_legacy_game_metadata(tmp_path) -> None:
    user, session, engine = await make_context(tmp_path)
    async with session:
        sos = await support_service.start_sos(session, user, 7, "boredom")
        legacy = await support_service.start_sos_action(
            session, sos, "distraction", None
        )
        legacy.metadata_json = {
            "hits": 35,
            "max_streak": 11,
            "duration_seconds": 60,
        }
        await session.flush()
        assert await support_service.air_cloud_best_height(session, user.id) == 0

        cloud = await support_service.start_sos_action(
            session, sos, "distraction", None
        )
        metadata, is_new = await support_service.record_air_cloud_result(
            session, cloud, user.id, 742, 39, 70
        )
        assert is_new is True
        assert metadata["best_height"] == 742
        assert legacy.metadata_json["hits"] == 35
    await engine.dispose()
