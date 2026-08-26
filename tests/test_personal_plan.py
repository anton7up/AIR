from app.services.program.labels import format_program_id
from app.services.program.personal_plan import (
    build_personal_plan,
    contextual_plan,
    resolve_day18_scenario,
)


def state(day: int, answers: dict) -> dict:
    return {"day_number": day, "state_json": answers}


def test_personal_plan_prefers_day_29_and_retains_history() -> None:
    plan = build_personal_plan([
        state(3, {"pause_plan": "water"}),
        state(15, {"stress_plan": {"first_action": "walk", "backup_action": "breathing"}}),
        state(29, {"protection_plan": {"stress": "Позвоню другу", "strong_desire": "Открою SOS"}}),
    ])
    assert plan["by_category"]["stress"]["source_day"] == 29
    assert plan["by_category"]["strong_craving"]["source_day"] == 29
    assert {item["source_day"] for item in plan["history"]} >= {3, 15, 29}


def test_later_specialized_plan_beats_earlier_and_general() -> None:
    plan = build_personal_plan([
        state(2, {"personal_habit_loop": {"alternative": "water"}}),
        state(8, {"relaxation_replacement": "breathing"}),
        state(15, {"stress_plan": {"first_action": "walk"}}),
    ])
    assert plan["by_category"]["stress"]["source_day"] == 15
    assert plan["by_category"]["general"]["source_day"] == 2


def test_contextual_plan_never_uses_another_trigger() -> None:
    plan = build_personal_plan([state(15, {"stress_plan": {"first_action": "walk"}})])
    assert contextual_plan(plan, "stress") is not None
    assert contextual_plan(plan, "coffee") is None


def test_day_18_scenario_priority_and_neutral_wording() -> None:
    assert resolve_day18_scenario(["alcohol", "social"])["id"] == "alcohol"
    social = resolve_day18_scenario(["social"])
    assert social["id"] == "social" and "алкогол" not in social["body"].lower()
    assert resolve_day18_scenario(["before_sleep"])["id"] == "before_sleep"
    neutral = resolve_day18_scenario(["coffee"])
    assert neutral["id"] == "neutral"
    assert "не считает их твоими триггерами" in neutral["body"]


def test_formatter_covers_known_internal_values() -> None:
    assert format_program_id("motivation") == "Мотивация"
    assert format_program_id("both") == "Руки и рот"
    assert format_program_id("after_meal") == "После еды"
    assert "_" not in format_program_id("unknown_internal_value")


def test_personal_plan_never_exposes_nested_internal_ids() -> None:
    raw_ids = {"main_factor", "next_action", "automatic", "walk", "strong_craving"}
    plan = build_personal_plan([
        state(24, {"lapse_analysis": {"main_factor": "automatic", "next_action": "walk"}}),
        state(29, {"protection_plan": {"strong_desire": "water"}}),
    ])
    visible = " ".join(
        value
        for item in plan["items"]
        for value in [item["category_label"], item["title"], *item["steps"]]
    )
    assert not any(raw_id in visible for raw_id in raw_ids)
