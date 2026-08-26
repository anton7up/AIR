from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.mini_app import complete_program_day, support_context
from app.db.base import Base
from app.db.models import (
    NicotineLapse,
    NicotineType,
    ProgramDayCompletion,
    ProgramDayState,
    ProgramProfile,
    SmokingProfile,
    User,
)
from app.services.program.content import PROGRAM_DAYS
from app.services.program.engine import program_engine

INPUT_TYPES = {
    "single_select",
    "multi_select",
    "priority_select",
    "action_picker",
    "ordered_select",
    "plan_builder",
    "comparison",
    "scenario_choice",
    "scale",
}


def test_every_day_is_keyboard_free_and_has_a_concrete_result() -> None:
    for number, day in PROGRAM_DAYS.items():
        assert not any(
            step.required and step.type in {"text", "structured_input"}
            for step in day.steps
        )
        assert any(
            step.type in {"result_card", "personalized_summary"}
            for step in day.steps
        ), f"Day {number} has no personalized result"
        for step in day.steps:
            assert len({option.id for option in step.options}) == len(step.options)
            if step.type == "plan_builder":
                for builder_field in step.content["fields"]:
                    ids = [option["id"] for option in builder_field["options"]]
                    assert len(ids) == len(set(ids))


def test_scenario_graphs_have_valid_targets_and_no_loops() -> None:
    for day in PROGRAM_DAYS.values():
        ids = [step.id for step in day.steps]
        graph: dict[str, set[str]] = {step.id: set() for step in day.steps}
        for index, step in enumerate(day.steps):
            targets = set(step.branches.values())
            if step.next_step_id:
                targets.add(step.next_step_id)
            elif index < len(day.steps) - 1:
                targets.add(day.steps[index + 1].id)
            assert targets <= set(ids)
            assert step.id not in targets
            graph[step.id] = targets

        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(
            node: str,
            current_graph: dict[str, set[str]] = graph,
            current_visiting: set[str] = visiting,
            current_visited: set[str] = visited,
            day_number: int = day.number,
        ) -> None:
            if node in current_visiting:
                raise AssertionError(f"Cycle in day {day_number}: {node}")
            if node in current_visited:
                return
            current_visiting.add(node)
            for target in current_graph[node]:
                visit(target)
            current_visiting.remove(node)
            current_visited.add(node)

        visit(day.steps[0].id)


def first_valid_value(step: dict[str, Any]) -> Any:
    step_type = step["type"]
    if step_type in {"single_select", "priority_select", "action_picker", "scenario_choice"}:
        return step["options"][0]["id"]
    if step_type == "multi_select":
        return [step["options"][0]["id"]]
    if step_type == "ordered_select":
        count = step["max_selections"] or 1
        return [option["id"] for option in step["options"][:count]]
    if step_type == "scale":
        return 1
    if step_type == "plan_builder":
        selected: dict[str, str] = {}
        for builder_field in step["builder_fields"]:
            excluded = selected.get(builder_field.get("exclude_answer") or "")
            selected[builder_field["id"]] = next(
                option["id"]
                for option in builder_field["options"]
                if option["id"] != excluded
            )
        return selected
    if step_type == "comparison":
        first = step["comparison"]["scale"][0]["id"]
        return {item["id"]: first for item in step["comparison"]["items"]}
    return None


def visible_step_text(step: dict[str, Any]) -> str:
    values: list[object] = [
        step.get("title", ""),
        step.get("body", ""),
        step.get("button_text", ""),
    ]
    values.extend(option.get("label", "") for option in step.get("options", []))
    for field in step.get("builder_fields", []):
        values.append(field.get("label", ""))
        values.extend(option.get("label", "") for option in field.get("options", []))
    comparison = step.get("comparison") or {}
    values.extend(item.get("label", "") for item in comparison.get("items", []))
    values.extend(item.get("label", "") for item in comparison.get("scale", []))
    insight = step.get("insight") or {}
    values.extend([insight.get("title", ""), insight.get("body", "")])
    for item in insight.get("plan_items", []):
        values.extend([item.get("category_label", ""), *item.get("steps", [])])
    for card in step.get("analytics", []):
        values.extend([card.get("label", ""), card.get("value", ""), card.get("note", "")])
    result = step.get("result") or {}
    values.append(result.get("title", ""))
    for item in result.get("items", []):
        values.extend([item.get("label", ""), item.get("value", "")])
    summary = step.get("summary") or {}
    values.extend(value for value in summary.values() if isinstance(value, str))
    for value in summary.values():
        if isinstance(value, list):
            values.extend(value)
    return "\n".join(str(value) for value in values if value)


def configured_internal_ids() -> set[str]:
    identifiers: set[str] = set()
    for day in PROGRAM_DAYS.values():
        for step in day.steps:
            identifiers.add(step.id)
            identifiers.update(option.id for option in step.options)
            for field in step.content.get("fields", []):
                if isinstance(field.get("id"), str):
                    identifiers.add(field["id"])
                identifiers.update(
                    option["id"]
                    for option in field.get("options", [])
                    if isinstance(option.get("id"), str)
                )
    return {value for value in identifiers if not value.isdigit()}


@pytest.mark.asyncio
async def test_full_program_can_be_completed_without_typing(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'happy-path.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        user = User(
            telegram_id=300,
            telegram_first_name="Лена",
            program_started_at=datetime.now(timezone.utc) - timedelta(days=30),
        )
        session.add(user)
        await session.flush()
        smoking_profile = SmokingProfile(
            user_id=user.id,
            nicotine_type=NicotineType.CIGARETTES,
            years_of_use=Decimal("5"),
            daily_units=Decimal("10"),
            consumption_parameters={},
            cost_parameters={},
            monthly_expense=Decimal("3000"),
            yearly_expense=Decimal("36000"),
            lifetime_expense=Decimal("180000"),
            projected_five_year_expense=Decimal("180000"),
        )
        session.add(smoking_profile)
        await session.flush()

        all_rendered: list[str] = []
        day_30_rendered: list[str] = []
        for day_number in range(1, 31):
            seen: set[str] = set()
            while True:
                payload = await program_engine.day_payload(session, user, day_number)
                step = payload["step"]
                all_rendered.append(visible_step_text(step))
                if day_number == 30:
                    day_30_rendered.append(visible_step_text(step))
                if step["type"] == "completion":
                    break
                assert step["id"] not in seen, f"Loop in day {day_number}"
                seen.add(step["id"])
                if step["type"] == "text":
                    raise AssertionError(f"Day {day_number} requires keyboard input")
                value = first_valid_value(step)
                await program_engine.save_step(
                    session, user, day_number, step["id"], value
                )
            await complete_program_day(
                day_number, (user, smoking_profile, session)
            )

        await session.commit()
        assert await session.scalar(
            select(func.count(ProgramDayCompletion.id)).where(
                ProgramDayCompletion.user_id == user.id
            )
        ) == 30
        assert await session.scalar(
            select(func.count(NicotineLapse.id)).where(NicotineLapse.user_id == user.id)
        ) == 0

        states = list(
            (
                await session.scalars(
                    select(ProgramDayState).where(
                        ProgramDayState.user_id == user.id
                    )
                )
            ).all()
        )
        answers = {
            key: value
            for state in states
            for key, value in (state.state_json or {}).items()
        }
        assert set(answers["personal_habit_loop"]) >= {
            "trigger", "first_signal", "expected", "alternative"
        }
        assert set(answers["trigger_plan"]) >= {
            "first_action", "backup_action", "sos_threshold"
        }
        assert set(answers["boredom_menu"]) == {
            "one_minute", "three_minutes", "ten_minutes"
        }
        assert set(answers["stress_plan"]) >= {
            "first_action", "backup_action", "sos_threshold"
        }
        assert answers["social_response"]
        assert answers["evening_plan"]
        assert answers["belief_reassessment"]
        assert answers["lapse_analysis"]
        assert answers["complex_scenario"]
        assert answers["protection_plan"]
        assert answers["final_rule"]
        assert "next_30_day_rule" not in answers
        visible_day_30 = "\n".join(day_30_rendered)
        forbidden_internal_values = {
            "Checkpoint",
            "final_change",
            "keep_next",
            "most_useful_strategy",
            "next_30_day_rule",
            "final_rule",
            "understand_triggers",
            "manage_craving",
            "working_switches",
            "confident_free",
            "hard_moments",
            "understand_dependence",
            "use_sos",
            "use_personal_plan",
            "notice_triggers",
            "watch_progress",
            "return_techniques",
            "personal_plan",
            "protection_plan",
            "ai_support",
        }
        assert not {
            value for value in forbidden_internal_values if value in visible_day_30
        }
        visible_program = "\n".join(all_rendered)
        assert not {
            value for value in configured_internal_ids() if value in visible_program
        }
    await engine.dispose()


def test_day_30_has_no_next_thirty_days_rule_step() -> None:
    day = PROGRAM_DAYS[30]
    assert "next_30_day_rule" not in {step.id for step in day.steps}
    assert all("следующие 30 дней" not in step.title.lower() for step in day.steps)


@pytest.mark.asyncio
async def test_legacy_day_30_rule_state_resumes_at_result_without_rewrite(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'legacy-day-30.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        user = User(
            telegram_id=399,
            telegram_first_name="Ира",
            program_started_at=datetime.now(timezone.utc) - timedelta(days=30),
        )
        session.add(user)
        await session.flush()
        state = ProgramDayState(
            user_id=user.id,
            day_number=30,
            current_step="next_30_day_rule",
            state_json={"next_30_day_rule": "use_sos"},
        )
        session.add(state)
        await session.commit()

        payload = await program_engine.day_payload(session, user, 30)

        assert payload["current_step"] == "d30_result"
        assert payload["step"]["type"] == "result_card"
        assert state.current_step == "next_30_day_rule"
        assert state.state_json["next_30_day_rule"] == "use_sos"
    await engine.dispose()


@pytest.mark.asyncio
async def test_saved_stress_plan_personalizes_sos(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'sos-plan.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        user = User(telegram_id=301, telegram_first_name="Олег")
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
        session.add(
            ProgramDayState(
                user_id=user.id,
                day_number=15,
                current_step="d15_result",
                state_json={
                    "stress_plan": {
                        "first_action": "walk",
                        "backup_action": "breathing",
                        "sos_threshold": "7",
                    }
                },
            )
        )
        await session.flush()
        payload = await support_context((user, profile, session))
        assert payload["recommendations"]["stress"][0]["action_id"] == "walk"
        assert "раньше выбрал" in payload["recommendations"]["stress"][0]["reason"]
    await engine.dispose()


@pytest.mark.asyncio
async def test_day_two_plan_is_first_for_matching_sos_trigger(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'sos-loop.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        user = User(telegram_id=302, telegram_first_name="Анна")
        session.add(user)
        await session.flush()
        session.add(
            ProgramProfile(
                user_id=user.id,
                primary_triggers=["work_study"],
                nicotine_beliefs=[],
            )
        )
        session.add(
            ProgramDayState(
                user_id=user.id,
                day_number=2,
                current_step="d2_result",
                state_json={
                    "personal_habit_loop": {
                        "trigger": "work_study",
                        "first_signal": "thought",
                        "expected": "relaxation",
                        "alternative": "walk",
                    }
                },
            )
        )
        await session.flush()
        payload = await support_context((user, None, session))
        recommendation = payload["recommendations"]["work_study"][0]
        assert recommendation["action_id"] == "walk"
        assert "Дне 2" in recommendation["reason"]
    await engine.dispose()
