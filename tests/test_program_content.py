import json
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models import (
    NicotineDesireLog,
    NicotineType,
    ProgramDayState,
    ProgramProfile,
    SmokingProfile,
    User,
)
from app.services.program.content import PROGRAM_DAYS, PROGRAM_LENGTH
from app.services.program.engine import ProgramValidationError, program_engine

CHECKPOINT_DAYS = {7, 14, 21, 30}
FORBIDDEN_MEDICATION_TERMS = {
    "варениклин",
    "бупропион",
    "цитизин",
    "цитизиниклин",
    "никотиновый пластырь",
    "никотиновая жвачка",
    "никотинзамест",
    "дозировка",
    "таблетки для отказа",
}


def text_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [item for nested in value.values() for item in text_values(nested)]
    if isinstance(value, (list, tuple)):
        return [item for nested in value for item in text_values(nested)]
    return []


def test_all_30_days_are_complete_unique_and_serializable() -> None:
    assert PROGRAM_LENGTH == 30
    assert sorted(PROGRAM_DAYS) == list(range(1, 31))
    assert len({day.number for day in PROGRAM_DAYS.values()}) == 30

    all_step_ids: list[str] = []
    supported_types = {
        "start", "info", "theory", "single_select", "multi_select", "scale",
        "text", "structured_input", "personalized_cards", "personalized_summary",
        "personalized_insight", "selected_insights", "checkpoint", "task", "completion",
        "priority_select", "action_picker", "ordered_select", "plan_builder",
        "comparison", "scenario_choice", "result_card",
    }
    for day in PROGRAM_DAYS.values():
        assert day.title.strip()
        assert day.short_description.strip()
        theory_steps = [step for step in day.steps if step.type == "theory"]
        assert len(theory_steps) == 1
        assert theory_steps[0].body.strip()
        assert len(theory_steps[0].body.split()) >= (120 if day.number in CHECKPOINT_DAYS or day.number == 1 else 140)
        assert day.evidence_category.strip()
        assert day.evidence_notes.strip()
        assert len({step.id for step in day.steps}) == len(day.steps)
        assert all(step.type in supported_types for step in day.steps)
        all_step_ids.extend(step.id for step in day.steps)
        json.dumps(asdict(day), ensure_ascii=False)

    assert len(all_step_ids) == len(set(all_step_ids))


def test_user_content_has_no_placeholders_medication_advice_or_duplicate_theory() -> None:
    theories: list[str] = []
    for day in PROGRAM_DAYS.values():
        serialized = asdict(day)
        user_text = " ".join(text_values(serialized)).lower()
        assert "todo" not in user_text
        assert "lorem ipsum" not in user_text
        assert "скоро в air" not in user_text
        assert "просто потерпи" not in user_text
        assert "курильщик" not in user_text
        assert "тяга к сигарете" not in user_text
        for term in FORBIDDEN_MEDICATION_TERMS:
            assert term not in user_text
        theories.append(next(step.body for step in day.steps if step.type == "theory"))
    assert len(theories) == len(set(theories))


@pytest.mark.asyncio
async def test_personalization_and_checkpoint_use_real_data_with_honest_fallback(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'content.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        user = User(
            telegram_id=200,
            telegram_first_name="Ира",
            program_started_at=datetime.now(timezone.utc) - timedelta(days=29),
        )
        session.add(user)
        await session.flush()
        session.add(SmokingProfile(
            user_id=user.id,
            nicotine_type=NicotineType.CIGARETTES,
            years_of_use=Decimal("3"),
            daily_units=Decimal("10"),
            consumption_parameters={},
            cost_parameters={},
            monthly_expense=Decimal("3000"),
            yearly_expense=Decimal("36000"),
            lifetime_expense=Decimal("108000"),
            projected_five_year_expense=Decimal("180000"),
        ))
        session.add(ProgramProfile(
            user_id=user.id,
            primary_quit_reason="health",
            primary_triggers=["stress"],
            nicotine_beliefs=["relax"],
        ))
        session.add(NicotineDesireLog(user_id=user.id, intensity=8, trigger_id="stress"))
        await session.flush()

        day_two = PROGRAM_DAYS[2]
        state = ProgramDayState(
            user_id=user.id,
            day_number=2,
            current_step="d2_personal",
            state_json={},
        )
        session.add(state)
        await session.flush()
        personalized = await program_engine.day_payload(session, user, 2)
        assert personalized["step"]["insight"]["is_fallback"] is False
        assert "нервничаю" in personalized["step"]["insight"]["title"].lower()

        day_seven = PROGRAM_DAYS[7]
        session.add(ProgramDayState(
            user_id=user.id,
            day_number=7,
            current_step="d7_checkpoint",
            state_json={},
        ))
        await session.flush()
        checkpoint = await program_engine.day_payload(session, user, 7)
        values = {item["label"]: item["value"] for item in checkpoint["step"]["analytics"]}
        assert values["Записей желаний"] == "1"
        assert "нервничаю" in values["Частый триггер"].lower()

        fallback_context = await program_engine._context(session, user)
        fallback_context["profile"] = None
        fallback_context["desire_count"] = 0
        fallback_context["frequent_trigger"] = None
        fallback_context["frequent_trigger_label"] = None
        insight = program_engine._personalized_insight("primary_trigger", fallback_context)
        assert insight["is_fallback"] is True
        assert "недостаточно" in insight["body"].lower()
        assert day_two.number == 2 and day_seven.number == 7
    await engine.dispose()


@pytest.mark.asyncio
async def test_plan_builder_answers_are_validated_and_saved(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'structured.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        user = User(telegram_id=201, telegram_first_name="Макс")
        session.add(user)
        await session.flush()
        state = ProgramDayState(
            user_id=user.id,
            day_number=2,
            current_step="personal_habit_loop",
            state_json={},
        )
        session.add(state)
        await session.flush()
        with pytest.raises(ProgramValidationError):
            await program_engine.save_step(
                session, user, 2, "personal_habit_loop", {"trigger": "stress"}
            )
        value = {
            "trigger": "stress",
            "first_signal": "thought",
            "expected": "habit",
            "alternative": "walk",
        }
        saved = await program_engine.save_step(
            session, user, 2, "personal_habit_loop", value
        )
        persisted = await session.scalar(
            select(ProgramDayState).where(ProgramDayState.id == saved.id)
        )
        assert persisted is not None
        assert persisted.state_json["personal_habit_loop"] == value
    await engine.dispose()
