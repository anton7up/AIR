from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from app.db.models import UserResponseType
from app.services.program.labels import format_program_id, format_program_value
from app.services.user_responses import deduplicate_display_values

PLAN_CATEGORY_LABELS = {key: format_program_id(key) for key in (
    "stress", "coffee", "after_meal", "work_study", "social", "alcohol",
    "boredom", "before_sleep", "strong_craving", "lapse", "general",
)}
TRIGGER_TO_PLAN_CATEGORY = {
    "stress": "stress", "coffee": "coffee", "after_meal": "after_meal",
    "work_study": "work_study", "social": "social", "alcohol": "alcohol",
    "boredom": "boredom", "before_sleep": "before_sleep",
}
ACTION_RESPONSE_TYPES = {
    UserResponseType.COPING_ACTION.value, UserResponseType.REPLACEMENT.value,
    UserResponseType.PLAN_ACTION.value, UserResponseType.SOCIAL_RESPONSE.value,
    UserResponseType.LAPSE_PLAN.value,
}
REASON_RESPONSE_TYPES = {UserResponseType.TRIGGER.value, UserResponseType.REASON.value}


@dataclass(frozen=True)
class PlanSource:
    day: int
    key: str
    category: str
    fields: tuple[str, ...] = ()
    specialized: bool = True


@dataclass(frozen=True)
class ReasonSource:
    day: int
    key: str
    category: str
    fields: tuple[str, ...] = ()


# Only executable actions are listed as plan sources. Reasons and thresholds are separate.
PLAN_SOURCES = (
    PlanSource(2, "personal_habit_loop", "general", ("alternative",), False),
    PlanSource(3, "pause_plan", "strong_craving"),
    PlanSource(5, "trigger_plan", "general", ("first_action", "backup_action")),
    PlanSource(6, "changed_routine", "general"),
    PlanSource(8, "relaxation_breakdown", "stress", ("replacement",)),
    PlanSource(11, "break_replacement", "work_study"),
    PlanSource(12, "boredom_menu", "boredom", ("one_minute", "three_minutes", "ten_minutes")),
    PlanSource(13, "evening_ritual", "before_sleep"),
    PlanSource(15, "stress_plan", "stress", ("first_action", "backup_action")),
    PlanSource(16, "emotion_need_action", "stress", ("action",)),
    PlanSource(17, "social_first_reply", "social"),
    PlanSource(17, "social_second_reply", "social"),
    PlanSource(18, "evening_plan", "social", ("offer_response", "exit")),
    PlanSource(19, "after_meal_plan", "after_meal", ("new_action",)),
    PlanSource(20, "movement_switch", "general"),
    PlanSource(22, "one_time_risk_followup", "strong_craving"),
    PlanSource(22, "one_time_coping_followup", "strong_craving"),
    PlanSource(23, "post_lapse_choice", "lapse"),
    PlanSource(24, "lapse_analysis", "lapse", ("next_action",)),
    PlanSource(25, "unexpected_desire_response", "strong_craving"),
    PlanSource(26, "state_need_action", "general", ("action",)),
    PlanSource(27, "scenario_decision_one", "general"),
    PlanSource(27, "scenario_decision_two", "social"),
    PlanSource(27, "scenario_decision_three", "strong_craving"),
    PlanSource(28, "warning_response", "strong_craving"),
    PlanSource(29, "protection_plan", "strong_craving", ("strong_desire",)),
    PlanSource(29, "protection_plan", "stress", ("stress",)),
    PlanSource(29, "protection_plan", "social", ("social",)),
    PlanSource(29, "protection_plan", "strong_craving", ("one_time",)),
    PlanSource(29, "protection_plan", "lapse", ("lapse",)),
    PlanSource(29, "protection_replacement", "general"),
    PlanSource(30, "keep_next", "general"),
    PlanSource(30, "most_useful_strategy", "general"),
)
REASON_SOURCES = (
    ReasonSource(2, "personal_habit_loop", "general", ("first_signal",)),
    ReasonSource(8, "relaxation_breakdown", "stress", ("before",)),
    ReasonSource(16, "emotion_need_action", "stress", ("emotion",)),
    ReasonSource(18, "evening_plan", "social", ("risk",)),
    ReasonSource(19, "after_meal_plan", "after_meal", ("usual",)),
    ReasonSource(24, "lapse_analysis", "lapse", ("main_factor",)),
    ReasonSource(26, "state_need_action", "general", ("state",)),
    ReasonSource(28, "warning_priority", "strong_craving"),
)


def resolve_day18_scenario(trigger_ids: Iterable[str]) -> dict[str, str]:
    triggers = set(trigger_ids)
    if "alcohol" in triggers:
        return {"id": "alcohol", "category": "alcohol", "title": "Алкоголь / вечеринка", "body": "Ты отмечал алкоголь среди сложных ситуаций. Подготовим спокойный план для вечера заранее."}
    if "social" in triggers:
        return {"id": "social", "category": "social", "title": "Компания", "body": "Ты отмечал компанию среди сложных ситуаций. Подготовим ответ на предложение и способ выйти из давления."}
    if "before_sleep" in triggers:
        return {"id": "before_sleep", "category": "before_sleep", "title": "Вечернее время", "body": "Ты отмечал время перед сном. Подготовим план для сложного вечера без предположений об алкоголе."}
    return {"id": "neutral", "category": "general", "title": "Сложная вечерняя ситуация", "body": "Это нейтральная репетиция ситуации повышенного риска. Компания или алкоголь могут быть примерами, но AIR не считает их твоими триггерами без данных."}


def _state_parts(state: Any) -> tuple[int, dict[str, Any]]:
    if isinstance(state, dict):
        return int(state.get("day_number", 0)), dict(state.get("state_json") or {})
    return int(state.day_number), dict(state.state_json or {})


def _raw_values(value: Any, fields: tuple[str, ...]) -> list[Any]:
    if isinstance(value, dict):
        return [value.get(key) for key in fields] if fields else []
    if fields:
        return []
    return value if isinstance(value, list) else [value]


def _display_values(value: Any, fields: tuple[str, ...]) -> list[str]:
    return [format_program_value(item) for item in _raw_values(value, fields) if item not in (None, "", [], {})]


def _response_parts(response: Any) -> dict[str, Any]:
    if isinstance(response, dict):
        return response
    return {
        "id": response.id,
        "response_type": getattr(response.response_type, "value", response.response_type),
        "value": response.value,
        "context_id": response.context_id,
        "parent_response_id": response.parent_response_id,
        "source_ref": response.source_ref,
        "effectiveness_sum": response.effectiveness_sum,
        "effectiveness_samples": response.effectiveness_samples,
        "usage_count": response.usage_count,
    }


def build_personal_plan(
    states: Iterable[Any], *, primary_triggers: Iterable[str] = (), responses: Iterable[Any] = ()
) -> dict[str, Any]:
    by_day = {day: answers for day, answers in map(_state_parts, states)}
    day18 = resolve_day18_scenario(primary_triggers)
    history: list[dict[str, Any]] = []
    reasons: dict[str, list[str]] = {}
    for source in PLAN_SOURCES:
        category = day18["category"] if source.day == 18 else source.category
        steps = _display_values(by_day.get(source.day, {}).get(source.key), source.fields)
        if steps:
            history.append({
                "category": category,
                "category_label": PLAN_CATEGORY_LABELS.get(category, format_program_id(category)),
                "title": PLAN_CATEGORY_LABELS.get(category, format_program_id(category)),
                "reasons": [], "steps": deduplicate_display_values(steps),
                "source_day": source.day, "source_key": source.key,
                "priority": (2000 if source.specialized else 1000) + source.day,
            })
    for reason_source in REASON_SOURCES:
        category = day18["category"] if reason_source.day == 18 else reason_source.category
        reasons.setdefault(category, []).extend(
            _display_values(
                by_day.get(reason_source.day, {}).get(reason_source.key),
                reason_source.fields,
            )
        )

    response_rows = [_response_parts(item) for item in responses]
    response_by_id = {item.get("id"): item for item in response_rows}
    for item in response_rows:
        response_type = str(item.get("response_type", ""))
        category = str(item.get("context_id") or "general")
        if response_type in REASON_RESPONSE_TYPES:
            reasons.setdefault(category, []).append(str(item.get("value", "")))
        if response_type not in ACTION_RESPONSE_TYPES:
            continue
        parent = response_by_id.get(item.get("parent_response_id"))
        if parent and str(parent.get("response_type")) in REASON_RESPONSE_TYPES:
            reasons.setdefault(category, []).append(str(parent.get("value", "")))
        samples = int(item.get("effectiveness_samples") or 0)
        average = int(item.get("effectiveness_sum") or 0) / samples if samples else 0
        history.append({
            "category": category,
            "category_label": PLAN_CATEGORY_LABELS.get(category, format_program_id(category)),
            "title": PLAN_CATEGORY_LABELS.get(category, format_program_id(category)),
            "reasons": [], "steps": deduplicate_display_values([str(item.get("value", ""))]),
            "source_day": 0, "source_key": str(item.get("source_ref") or "user_response"),
            "priority": 20_000 + round(average * 100) + int(item.get("usage_count") or 0),
        })

    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in history:
        grouped.setdefault(item["category"], []).append(item)
    selected: dict[str, dict[str, Any]] = {}
    for category, category_items in grouped.items():
        ordered = sorted(category_items, key=lambda item: item["priority"], reverse=True)
        steps = deduplicate_display_values(step for item in ordered for step in item["steps"])[:5]
        if steps:
            top = dict(ordered[0])
            top["steps"] = steps
            top["reasons"] = deduplicate_display_values(reasons.get(category, []))[:3]
            selected[category] = top
    items = sorted(selected.values(), key=lambda item: (-item["priority"], item["category"]))
    return {"items": items, "by_category": {item["category"]: item for item in items}, "history": history, "strategy_count": len(items), "has_plan": bool(items)}


def contextual_plan(plan: dict[str, Any], trigger_id: str | None) -> dict[str, Any] | None:
    if not trigger_id:
        return None
    category = TRIGGER_TO_PLAN_CATEGORY.get(trigger_id)
    if not category:
        return None
    item = plan.get("by_category", {}).get(category)
    return item if isinstance(item, dict) else None
