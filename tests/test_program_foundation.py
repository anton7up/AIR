from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.mini_app import (
    achievement_payload,
    complete_program_day,
    restart_quit_attempt,
)
from app.api.mini_app import dashboard as dashboard_endpoint
from app.api.mini_app import progress as progress_endpoint
from app.db.base import Base
from app.db.models import (
    LapseType,
    NicotineDesireLog,
    NicotineLapse,
    NicotineType,
    ProgramDayCompletion,
    ProgramProfile,
    QuitAttempt,
    QuitAttemptStatus,
    SmokingProfile,
    SosAction,
    SosSession,
    User,
)
from app.services.program.engine import ProgramValidationError, program_engine
from app.services.quit_attempts import quit_attempt_service
from app.services.support import SupportValidationError, support_service


async def make_session(tmp_path) -> tuple[AsyncSession, object]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'program.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    return sessions(), engine


async def make_user(session: AsyncSession) -> tuple[User, SmokingProfile]:
    user = User(telegram_id=100, telegram_first_name="Alex")
    session.add(user)
    await session.flush()
    profile = SmokingProfile(
        user_id=user.id,
        nicotine_type=NicotineType.CIGARETTES,
        years_of_use=Decimal("4"),
        daily_units=Decimal("10"),
        consumption_parameters={"unit": "cigarette"},
        cost_parameters={},
        monthly_expense=Decimal("3000"),
        yearly_expense=Decimal("36000"),
        lifetime_expense=Decimal("144000"),
        projected_five_year_expense=Decimal("180000"),
    )
    session.add(profile)
    await session.flush()
    return user, profile


@pytest.mark.asyncio
async def test_program_start_is_idempotent_and_creates_one_attempt(tmp_path) -> None:
    session, engine = await make_session(tmp_path)
    async with session:
        user, _ = await make_user(session)
        first_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
        first = await quit_attempt_service.start_program(session, user, first_time)
        second = await quit_attempt_service.start_program(
            session, user, first_time + timedelta(hours=2)
        )
        await session.commit()
        count = await session.scalar(select(func.count(QuitAttempt.id)))
        assert first.id == second.id
        assert count == 1
        assert user.program_started_at == first_time
        assert user.quit_started_at == first_time
    await engine.dispose()


@pytest.mark.asyncio
async def test_dashboard_distinguishes_new_active_and_post_lapse_states(tmp_path) -> None:
    session, engine = await make_session(tmp_path)
    async with session:
        user, smoking_profile = await make_user(session)
        new_state = await dashboard_endpoint((user, smoking_profile, session))
        assert new_state["has_active_attempt"] is False
        assert new_state["number_of_attempts"] == 0

        await quit_attempt_service.start_program(
            session, user, datetime(2026, 8, 16, 12, tzinfo=timezone.utc)
        )
        active_state = await dashboard_endpoint((user, smoking_profile, session))
        assert active_state["has_active_attempt"] is True
        assert active_state["number_of_attempts"] == 1

        await support_service.register_lapse(
            session, user, LapseType.SINGLE, "stress", None
        )
        post_lapse_state = await dashboard_endpoint((user, smoking_profile, session))
        assert post_lapse_state["has_active_attempt"] is False
        assert post_lapse_state["number_of_attempts"] == 1
    await engine.dispose()


@pytest.mark.asyncio
async def test_day_one_state_resumes_and_saves_personalization(tmp_path) -> None:
    session, engine = await make_session(tmp_path)
    async with session:
        user, smoking_profile = await make_user(session)
        await quit_attempt_service.start_program(session, user)
        sequence = [
            ("start", None),
            ("quit_reasons", ["health", "sport"]),
            ("primary_quit_reason", "sport"),
            ("trigger_intro", None),
            ("user_triggers", ["coffee", "stress", "social"]),
        ]
        for step_id, value in sequence:
            state = await program_engine.save_step(session, user, 1, step_id, value)
        assert state.current_step == "primary_triggers"
        reopened = await program_engine.day_payload(session, user, 1)
        assert reopened["current_step"] == "primary_triggers"

        with pytest.raises(ProgramValidationError):
            await program_engine.save_step(
                session,
                user,
                1,
                "primary_triggers",
                ["coffee", "stress", "social", "morning"],
            )
        await program_engine.save_step(
            session, user, 1, "primary_triggers", ["coffee", "stress", "social"]
        )
        await program_engine.save_step(session, user, 1, "trigger_cards")
        await program_engine.save_step(
            session, user, 1, "nicotine_beliefs", ["relax", "break"]
        )
        await program_engine.save_step(session, user, 1, "belief_ack")
        await program_engine.save_step(
            session, user, 1, "quit_concerns", ["stress", "lapse_fear"]
        )
        await program_engine.save_step(session, user, 1, "summary")
        final_state = await program_engine.save_step(session, user, 1, "task")
        assert final_state.current_step == "completion"
        await complete_program_day(1, (user, smoking_profile, session))
        await complete_program_day(1, (user, smoking_profile, session))
        await session.commit()
        profile = await session.scalar(
            select(ProgramProfile).where(ProgramProfile.user_id == user.id)
        )
        assert profile is not None
        assert profile.quit_reasons == ["health", "sport"]
        assert profile.primary_quit_reason == "sport"
        assert profile.user_triggers == ["coffee", "stress", "social"]
        assert profile.primary_triggers == ["coffee", "stress", "social"]
        assert profile.nicotine_beliefs == ["relax", "break"]
        assert profile.quit_concerns == ["stress", "lapse_fear"]
        assert final_state.completed is True
        assert await session.scalar(select(func.count(ProgramDayCompletion.id))) == 1
    await engine.dispose()


@pytest.mark.asyncio
async def test_desire_and_sos_capture_personalization_data(tmp_path) -> None:
    session, engine = await make_session(tmp_path)
    async with session:
        user, _ = await make_user(session)
        await quit_attempt_service.start_program(session, user)
        desire = await support_service.log_desire(
            session, user, 8, "stress", "tension", "После встречи"
        )
        sos = await support_service.start_sos(session, user, 9, "stress")
        await support_service.complete_sos(
            session, sos, "breathing", None, 5, False
        )
        await session.commit()
        assert desire.intensity == 8
        assert desire.trigger_id == "stress"
        assert desire.emotion == "tension"
        assert sos.intensity_before == 9
        assert sos.intensity_after == 5
        assert sos.support_type == "breathing"
        assert sos.finished_at is not None
        assert await session.scalar(select(func.count(NicotineDesireLog.id))) == 1
        assert await session.scalar(select(func.count(SosSession.id))) == 1
        assert await session.scalar(select(func.count(SosAction.id))) == 1
        with pytest.raises(SupportValidationError):
            await support_service.log_desire(session, user, 11, None, None, None)
    await engine.dispose()


@pytest.mark.asyncio
async def test_lapse_keeps_program_and_allows_new_attempt(tmp_path) -> None:
    session, engine = await make_session(tmp_path)
    async with session:
        user, _ = await make_user(session)
        first = await quit_attempt_service.start_program(session, user)
        session.add(ProgramDayCompletion(user_id=user.id, day_number=1))
        await session.flush()
        program_start = user.program_started_at
        lapse = await support_service.register_lapse(
            session, user, LapseType.SINGLE, "stress", None
        )
        assert lapse.quit_attempt_id == first.id
        assert first.status == QuitAttemptStatus.RELAPSED
        assert user.quit_started_at is None
        assert await quit_attempt_service.current(session, user.id) is None
        restart_time = datetime(2026, 8, 16, 12, tzinfo=timezone.utc)
        second = await quit_attempt_service.restart(session, user, restart_time)
        second_again = await quit_attempt_service.restart(session, user)
        metrics = await quit_attempt_service.metrics(
            session, user.id, second.started_at + timedelta(minutes=4)
        )
        await session.commit()
        assert second.id == second_again.id
        assert second.id != first.id
        assert second.started_at == restart_time
        assert second.status == QuitAttemptStatus.ACTIVE
        assert second.ended_at is None
        assert user.program_started_at == program_start
        assert await session.scalar(select(func.count(ProgramDayCompletion.id))) == 1
        assert await session.scalar(select(func.count(QuitAttempt.id))) == 2
        assert await session.scalar(select(func.count(NicotineLapse.id))) == 1
        assert await session.scalar(
            select(func.count(QuitAttempt.id)).where(
                QuitAttempt.user_id == user.id,
                QuitAttempt.active_marker.is_(True),
            )
        ) == 1
        assert metrics.current_seconds == 240
    await engine.dispose()


@pytest.mark.asyncio
async def test_lapse_restart_endpoint_is_idempotent_and_preserves_attempt_history(
    tmp_path,
) -> None:
    session, engine = await make_session(tmp_path)
    async with session:
        user, smoking_profile = await make_user(session)
        user_id = user.id
        first = await quit_attempt_service.start_program(
            session,
            user,
            datetime(2026, 8, 16, 10, tzinfo=timezone.utc),
        )
        first_id = first.id
        await support_service.register_lapse(
            session, user, LapseType.SINGLE, "stress", None
        )

        first_restart = await restart_quit_attempt(
            "restart-request-one", (user, smoking_profile, session)
        )
        repeated_restart = await restart_quit_attempt(
            "restart-request-one", (user, smoking_profile, session)
        )

        attempts = list(
            (
                await session.scalars(
                    select(QuitAttempt)
                    .where(QuitAttempt.user_id == user_id)
                    .order_by(QuitAttempt.id)
                )
            ).all()
        )
        assert first_restart["id"] == repeated_restart["id"]
        assert len(attempts) == 2
        assert attempts[0].id == first_id
        assert attempts[0].status == QuitAttemptStatus.RELAPSED
        assert attempts[0].active_marker is None
        assert attempts[1].status == QuitAttemptStatus.ACTIVE
        assert attempts[1].active_marker is True
        assert sum(attempt.active_marker is True for attempt in attempts) == 1

        await session.refresh(user)
        await session.refresh(smoking_profile)
        restarted_dashboard = await dashboard_endpoint(
            (user, smoking_profile, session)
        )
        assert restarted_dashboard["has_active_attempt"] is True
        assert restarted_dashboard["number_of_attempts"] == 2

        await quit_attempt_service.close_as_relapsed(
            session, user, "second lapse", datetime(2026, 8, 17, tzinfo=timezone.utc)
        )
        second_restart = await restart_quit_attempt(
            "restart-request-two", (user, smoking_profile, session)
        )
        assert second_restart["id"] != first_restart["id"]
        assert await session.scalar(
            select(func.count(QuitAttempt.id)).where(QuitAttempt.user_id == user_id)
        ) == 3
        assert await session.scalar(
            select(func.count(QuitAttempt.id)).where(
                QuitAttempt.user_id == user_id,
                QuitAttempt.active_marker.is_(True),
            )
        ) == 1
    await engine.dispose()


@pytest.mark.asyncio
async def test_sos_keeps_repeated_actions_in_one_ordered_session(tmp_path) -> None:
    session, engine = await make_session(tmp_path)
    async with session:
        user, _ = await make_user(session)
        await quit_attempt_service.start_program(session, user)
        sos = await support_service.start_sos(session, user, 9, "stress")
        first = await support_service.start_sos_action(
            session, sos, "breathing", None
        )
        await support_service.complete_sos_action(session, first)
        second = await support_service.start_sos_action(
            session, sos, "breathing", None
        )
        await support_service.complete_sos_action(session, second)
        third = await support_service.start_sos_action(
            session, sos, "change_activity", "water"
        )
        await support_service.complete_sos_action(session, third)
        fourth = await support_service.start_sos_action(
            session, sos, "breathing", None
        )
        await support_service.complete_sos_action(session, fourth)
        await support_service.finish_sos(session, sos, 4, False)
        await session.commit()

        actions = (
            await session.scalars(
                select(SosAction)
                .where(SosAction.sos_session_id == sos.id)
                .order_by(SosAction.sequence_number)
            )
        ).all()
        assert [action.sequence_number for action in actions] == [1, 2, 3, 4]
        assert [action.support_type for action in actions] == [
            "breathing",
            "breathing",
            "change_activity",
            "breathing",
        ]
        assert actions[2].support_action == "water"
        assert all(action.completed_at is not None for action in actions)
        assert sos.intensity_before == 9
        assert sos.intensity_after == 4
        assert sos.finished_at is not None
    await engine.dispose()


@pytest.mark.asyncio
async def test_attempt_metrics_keep_current_best_total_and_count(tmp_path) -> None:
    session, engine = await make_session(tmp_path)
    async with session:
        user, _ = await make_user(session)
        now = datetime(2026, 8, 16, 12, tzinfo=timezone.utc)
        for started_at, ended_at in (
            (now - timedelta(days=20), now - timedelta(days=17)),
            (now - timedelta(days=10), now - timedelta(days=3)),
        ):
            ended_attempt = QuitAttempt(
                user_id=user.id,
                started_at=started_at,
                status=QuitAttemptStatus.ACTIVE,
                active_marker=True,
            )
            session.add(ended_attempt)
            await session.flush()
            ended_attempt.ended_at = ended_at
            ended_attempt.status = QuitAttemptStatus.RELAPSED
            ended_attempt.active_marker = None
            await session.flush()
        session.add(
            QuitAttempt(
                user_id=user.id,
                started_at=now - timedelta(days=2),
                status=QuitAttemptStatus.ACTIVE,
                active_marker=True,
            )
        )
        await session.flush()
        metrics = await quit_attempt_service.metrics(session, user.id, now)
        assert metrics.current_seconds == 2 * 86400
        assert metrics.best_seconds == 7 * 86400
        assert metrics.total_seconds == 12 * 86400
        assert metrics.attempts == 3
    await engine.dispose()


def test_achievements_use_durable_history_instead_of_current_streak() -> None:
    achievements = {
        item["id"]: item
        for item in achievement_payload(
            best_streak_seconds=7 * 86400,
            completed_program_days={1, 7},
            sos_count=1,
            desire_count=3,
        )
    }
    assert achievements["first_step"]["unlocked"] is True
    assert achievements["24h"]["unlocked"] is True
    assert achievements["3d"]["unlocked"] is True
    assert achievements["7d"]["unlocked"] is True
    assert achievements["14d"]["unlocked"] is False
    assert achievements["sos"]["unlocked"] is True
    assert achievements["three_desires"]["unlocked"] is True


def test_personalized_trigger_cards_keep_prepared_content_and_compact_custom_order() -> None:
    custom_one = "custom:После разговора с мамой"
    custom_two = "custom:Когда остаюсь один"
    cards = program_engine._cards_for(
        {
            "primary_triggers": [
                "stress",
                custom_one,
                "driving",
                custom_two,
            ]
        }
    )

    assert [card["id"] for card in cards] == [
        "stress",
        custom_one,
        "driving",
        custom_two,
    ]
    assert cards[0]["why_it_happens"]
    assert cards[0]["first_tip"]
    assert cards[1] == {
        "id": custom_one,
        "title": "После разговора с мамой",
        "short_explanation": "",
        "why_it_happens": "",
        "first_tip": "",
    }
    assert cards[2]["why_it_happens"]
    assert cards[3]["title"] == "Когда остаюсь один"
    assert cards[3]["why_it_happens"] == ""


def test_personalized_trigger_cards_do_not_skip_custom_only_screen() -> None:
    cards = program_engine._cards_for(
        {"primary_triggers": ["custom:После разговора с мамой"]}
    )

    assert len(cards) == 1
    assert cards[0]["title"] == "После разговора с мамой"
    assert not cards[0]["why_it_happens"]


def test_starting_map_uses_custom_text_and_hides_bare_sentinels() -> None:
    summary = program_engine._summary_for(
        {
            "primary_quit_reason": "custom:Мама",
            "primary_triggers": ["custom:После разговора с мамой", "other"],
            "nicotine_beliefs": ["custom:Пауза для себя", "__other__"],
            "quit_concerns": ["custom:Остаться без поддержки", "user_defined"],
        }
    )

    assert summary == {
        "primary_reason": "Мама",
        "primary_triggers": ["После разговора с мамой"],
        "beliefs": ["Пауза для себя"],
        "concerns": ["Остаться без поддержки"],
    }


@pytest.mark.parametrize(
    ("completed", "earned", "locked"),
    [
        (set(), set(), {"first_step", "7d", "14d", "21d", "30d"}),
        ({7}, {"7d"}, {"first_step", "14d", "21d", "30d"}),
        ({14}, {"14d"}, {"first_step", "7d", "21d", "30d"}),
        ({1, 7, 14, 21, 30}, {"first_step", "7d", "14d", "21d", "30d"}, set()),
    ],
)
def test_program_milestones_require_exact_day_completion(
    completed: set[int], earned: set[str], locked: set[str]
) -> None:
    achievements = {
        item["id"]: item["unlocked"]
        for item in achievement_payload(100 * 86400, completed, 0, 0)
    }
    assert all(achievements[item] is True for item in earned)
    assert all(achievements[item] is False for item in locked)


@pytest.mark.asyncio
async def test_program_achievement_survives_lapse_and_attempt_restart(tmp_path) -> None:
    session, engine = await make_session(tmp_path)
    async with session:
        user, smoking_profile = await make_user(session)
        await quit_attempt_service.start_program(
            session, user, datetime.now(timezone.utc) - timedelta(days=7)
        )
        session.add(ProgramDayCompletion(user_id=user.id, day_number=7))
        await session.flush()

        await support_service.register_lapse(
            session, user, LapseType.SINGLE, "stress", None
        )
        after_lapse = await progress_endpoint((user, smoking_profile, session))
        assert next(item for item in after_lapse["achievements"] if item["id"] == "7d")["unlocked"] is True

        await quit_attempt_service.restart(session, user)
        after_restart = await progress_endpoint((user, smoking_profile, session))
        assert next(item for item in after_restart["achievements"] if item["id"] == "7d")["unlocked"] is True
        assert await session.scalar(
            select(func.count(ProgramDayCompletion.id)).where(
                ProgramDayCompletion.user_id == user.id,
                ProgramDayCompletion.day_number == 7,
            )
        ) == 1
    await engine.dispose()
