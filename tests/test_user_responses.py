from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models import ProgramDayState, User, UserResponse, UserResponseType
from app.services.program.content import PROGRAM_DAYS
from app.services.program.engine import ProgramValidationError, program_engine
from app.services.program.personal_plan import build_personal_plan
from app.services.support import SupportValidationError, support_service
from app.services.user_responses import (
    MAX_USER_RESPONSE_LENGTH,
    UserResponseValidationError,
    deduplicate_display_values,
    normalize_user_text,
    user_response_memory,
)


async def memory_context(tmp_path, name: str = "responses.db"):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / name}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    session = session_factory()
    user = User(telegram_id=90210, telegram_first_name="AIR")
    session.add(user)
    await session.flush()
    return user, session, session_factory, engine


def test_user_text_normalization_deduplication_and_max_length() -> None:
    assert normalize_user_text("  Выйти   на улицу \n на 5 минут  ") == "Выйти на улицу на 5 минут"
    assert deduplicate_display_values(
        ["Сделать паузу", " сделать   паузу. ", "СДЕЛАТЬ ПАУЗУ!"]
    ) == ["Сделать паузу."]
    with pytest.raises(UserResponseValidationError):
        normalize_user_text("я" * (MAX_USER_RESPONSE_LENGTH + 1))


def test_personal_plan_never_turns_reason_into_step_and_deduplicates_actions() -> None:
    responses = [
        {"id": 1, "response_type": "reason", "value": "Усталость", "context_id": "stress", "parent_response_id": None, "source_ref": "day:16:emotion", "effectiveness_sum": 0, "effectiveness_samples": 0, "usage_count": 1},
        {"id": 2, "response_type": "coping_action", "value": "Сделать паузу", "context_id": "stress", "parent_response_id": 1, "source_ref": "day:16:action", "effectiveness_sum": 0, "effectiveness_samples": 0, "usage_count": 1},
        {"id": 3, "response_type": "plan_action", "value": " сделать паузу. ", "context_id": "stress", "parent_response_id": 1, "source_ref": "day:29:stress", "effectiveness_sum": 0, "effectiveness_samples": 0, "usage_count": 1},
        {"id": 4, "response_type": "reflection", "value": "Стал спокойнее", "context_id": "stress", "parent_response_id": None, "source_ref": "day:30:final_change", "effectiveness_sum": 0, "effectiveness_samples": 0, "usage_count": 1},
    ]
    plan = build_personal_plan([], responses=responses)
    stress = plan["by_category"]["stress"]
    assert stress["reasons"] == ["Усталость."]
    assert stress["steps"] == ["Сделать паузу."]
    assert "Усталость." not in stress["steps"]
    assert "Стал спокойнее." not in stress["steps"]


@pytest.mark.asyncio
async def test_memory_persists_deduplicates_and_ranks_exact_reason(tmp_path) -> None:
    user, session, session_factory, engine = await memory_context(tmp_path)
    async with session:
        reason_a = await user_response_memory.remember(
            session, user_id=user.id, response_type="reason", value="Созвон с начальником",
            source="sos", context_id="stress",
        )
        reason_b = await user_response_memory.remember(
            session, user_id=user.id, response_type="reason", value="Устал после работы",
            source="sos", context_id="stress",
        )
        action_a = await user_response_memory.remember(
            session, user_id=user.id, response_type="coping_action", value="Пройтись 5 минут",
            source="sos", context_id="stress", parent_response_id=reason_a.id,
        )
        action_b = await user_response_memory.remember(
            session, user_id=user.id, response_type="coping_action", value="Выпить воды",
            source="sos", context_id="stress", parent_response_id=reason_b.id,
        )
        await user_response_memory.remember(
            session, user_id=user.id, response_type="coping_action", value=" пройтись  5 минут. ",
            source="sos", context_id="stress", parent_response_id=reason_a.id,
        )
        await user_response_memory.record_effectiveness(session, action_a.id, 4)
        await user_response_memory.record_effectiveness(session, action_b.id, 7)
        await session.commit()
        assert await session.scalar(
            select(func.count(UserResponse.id)).where(
                UserResponse.response_type == UserResponseType.COPING_ACTION
            )
        ) == 2

    async with session_factory() as reopened:
        exact_a = await user_response_memory.ranked(
            reopened, user_id=user.id, response_types=["coping_action"],
            context_id="stress", parent_response_id=reason_a.id,
        )
        exact_b = await user_response_memory.ranked(
            reopened, user_id=user.id, response_types=["coping_action"],
            context_id="stress", parent_response_id=reason_b.id,
        )
        assert exact_a[0].id == action_a.id
        assert exact_b[0].id == action_b.id
        assert exact_a[0].usage_count == 2
        assert exact_a[0].effectiveness_sum == 4
    await engine.dispose()


@pytest.mark.asyncio
async def test_custom_action_effectiveness_is_recorded_once_and_driving_rejects_it(tmp_path) -> None:
    user, session, _, engine = await memory_context(tmp_path, "action-effect.db")
    async with session:
        action_response = await user_response_memory.remember(
            session, user_id=user.id, response_type="coping_action",
            value="Выйти и пройтись пять минут", source="sos", context_id="stress",
        )
        sos = await support_service.start_sos(session, user, 8, "stress")
        action = await support_service.start_sos_action(
            session, sos, "change_activity", f"user_response:{action_response.id}",
            action_response.id,
        )
        await support_service.complete_sos_action(session, action, 4)
        await support_service.complete_sos_action(session, action, 4)
        assert action_response.effectiveness_sum == 4
        assert action_response.effectiveness_samples == 1

        driving = await support_service.start_sos(session, user, 7, "driving")
        with pytest.raises(SupportValidationError):
            await support_service.start_sos_action(
                session, driving, "change_activity", f"user_response:{action_response.id}",
                action_response.id,
            )
    await engine.dispose()


@pytest.mark.asyncio
async def test_program_single_and_multi_other_are_normalized_and_remembered(tmp_path) -> None:
    user, session, session_factory, engine = await memory_context(tmp_path, "program-other.db")
    async with session:
        await program_engine.save_step(session, user, 1, "start", None)
        await program_engine.save_step(
            session, user, 1, "quit_reasons", ["health", "custom:  Свобода   выбора  "]
        )
        state = await program_engine.save_step(
            session, user, 1, "primary_quit_reason", "custom:Свобода выбора"
        )
        await session.commit()
        assert state.state_json["quit_reasons"] == ["health", "custom:Свобода выбора"]
        assert state.state_json["primary_quit_reason"] == "custom:Свобода выбора"

    async with session_factory() as reopened:
        rows = list((await reopened.scalars(select(UserResponse))).all())
        assert len(rows) == 1
        assert rows[0].response_type == UserResponseType.MOTIVATION
        assert rows[0].value == "Свобода выбора"
        assert rows[0].usage_count == 2
        saved = await reopened.scalar(select(ProgramDayState))
        assert saved is not None
        assert saved.state_json["quit_reasons"][1] == "custom:Свобода выбора"
    await engine.dispose()


@pytest.mark.asyncio
async def test_program_custom_draft_persists_without_advancing_or_double_counting(tmp_path) -> None:
    user, session, session_factory, engine = await memory_context(tmp_path, "program-draft.db")
    async with session:
        await program_engine.save_step(session, user, 1, "start", None)
        draft = await program_engine.save_step_draft(
            session, user, 1, "quit_reasons", ["custom:Мама"]
        )
        await session.commit()
        assert draft.current_step == "quit_reasons"
        assert draft.state_json["quit_reasons"] == ["custom:Мама"]

    async with session_factory() as reopened:
        remembered = await reopened.scalar(select(UserResponse))
        assert remembered is not None
        assert remembered.value == "Мама"
        assert remembered.usage_count == 1
        advanced = await program_engine.save_step(
            reopened, user, 1, "quit_reasons", ["custom:Мама"]
        )
        await reopened.commit()
        assert advanced.current_step != "quit_reasons"
        assert remembered.usage_count == 1
    await engine.dispose()


@pytest.mark.asyncio
async def test_custom_trigger_card_survives_reload_and_remains_in_user_responses(tmp_path) -> None:
    user, session, session_factory, engine = await memory_context(tmp_path, "custom-card-reload.db")
    async with session:
        await program_engine.save_step(session, user, 1, "start", None)
        await program_engine.save_step(session, user, 1, "quit_reasons", ["health"])
        await program_engine.save_step(session, user, 1, "primary_quit_reason", "health")
        await program_engine.save_step(session, user, 1, "trigger_intro", None)
        await program_engine.save_step(
            session,
            user,
            1,
            "user_triggers",
            ["driving", "custom:После разговора с мамой"],
        )
        await program_engine.save_step(
            session,
            user,
            1,
            "primary_triggers",
            ["driving", "custom:После разговора с мамой"],
        )
        await session.commit()

    async with session_factory() as reopened:
        payload = await program_engine.day_payload(reopened, user, 1)
        cards = payload["step"]["cards"]
        responses = list((await reopened.scalars(select(UserResponse))).all())

        assert payload["current_step"] == "trigger_cards"
        assert [card["title"] for card in cards] == [
            "🚗 За рулём / в дороге",
            "После разговора с мамой",
        ]
        assert cards[0]["why_it_happens"]
        assert cards[1]["why_it_happens"] == ""
        assert any(response.value == "После разговора с мамой" for response in responses)
    await engine.dispose()


@pytest.mark.asyncio
async def test_program_other_rejects_empty_and_too_long_text(tmp_path) -> None:
    user, session, _, engine = await memory_context(tmp_path, "program-invalid.db")
    async with session:
        await program_engine.save_step(session, user, 1, "start", None)
        with pytest.raises(ProgramValidationError):
            await program_engine.save_step(session, user, 1, "quit_reasons", ["custom:   "])
        with pytest.raises(ProgramValidationError):
            await program_engine.save_step(
                session, user, 1, "quit_reasons", ["custom:" + "я" * (MAX_USER_RESPONSE_LENGTH + 1)]
            )
    await engine.dispose()


def test_all_choice_questions_have_deterministic_semantic_config() -> None:
    choice_types = {
        "multi_select", "single_select", "priority_select", "action_picker",
        "scenario_choice", "ordered_select",
    }
    allowed_types = {item.value for item in UserResponseType}
    for day_number, day in PROGRAM_DAYS.items():
        for step in day.steps:
            if step.type in choice_types:
                assert step.content.get("response_type") in allowed_types, (day_number, step.id)
                assert "allow_other" in step.content, (day_number, step.id)
            if step.type in {"plan_builder", "structured_input"}:
                for field in step.content.get("fields", []):
                    assert field.get("response_type") in allowed_types, (day_number, step.id, field["id"])
                    assert "allow_other" in field, (day_number, step.id, field["id"])


@pytest.mark.asyncio
async def test_remembered_program_options_are_limited_and_context_relevant(tmp_path) -> None:
    user, session, _, engine = await memory_context(tmp_path, "remembered-options.db")
    async with session:
        now = datetime.now(timezone.utc)
        for index in range(7):
            row = await user_response_memory.remember(
                session, user_id=user.id, response_type="replacement",
                value=f"Мой перерыв {index}", source="program", context_id="work_study",
            )
            row.last_used_at = now - timedelta(minutes=index)
        await user_response_memory.remember(
            session, user_id=user.id, response_type="replacement",
            value="Только перед сном", source="program", context_id="before_sleep",
        )
        await session.flush()
        context = {"user_responses": list((await session.scalars(select(UserResponse))).all())}
        remembered = program_engine._remembered_options(
            context, response_type="replacement", response_context="work_study"
        )
        assert len(remembered) == 5
        assert all(item["value"] != "Только перед сном" for item in remembered)
    await engine.dispose()
