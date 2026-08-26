from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ResponseConfig:
    response_type: str
    allow_other: bool
    placeholder: str = "Напиши свой вариант"
    context_id: str | None = None


def cfg(
    response_type: str,
    allow_other: bool = True,
    placeholder: str = "Напиши свой вариант",
    context_id: str | None = None,
) -> ResponseConfig:
    return ResponseConfig(response_type, allow_other, placeholder, context_id)


# Deterministic semantic classification for every choice-like program question.
# Questions with fixed technical answers stay in the registry with allow_other=False.
STEP_RESPONSE_CONFIG: dict[str, ResponseConfig] = {
    "quit_reasons": cfg("motivation", placeholder="Напиши свою причину отказа"),
    "primary_quit_reason": cfg("motivation", placeholder="Напиши главную причину"),
    "user_triggers": cfg("trigger", placeholder="Опиши свою ситуацию"),
    "primary_triggers": cfg("trigger", placeholder="Опиши самую сложную ситуацию"),
    "nicotine_beliefs": cfg("reason", placeholder="Напиши, что ещё даёт тебе никотин"),
    "quit_concerns": cfg("reason", placeholder="Напиши, что ещё тебя беспокоит"),
    "usual_high_desire_response": cfg("reflection", placeholder="Напиши, что обычно происходит"),
    "pause_plan": cfg("coping_action", placeholder="Напиши свой первый шаг"),
    "noticed_changes": cfg("reason", placeholder="Напиши, что ещё замечаешь"),
    "main_change": cfg("reason", placeholder="Напиши главную сложность"),
    "change_response": cfg("coping_action", placeholder="Напиши свой шаг"),
    "automatic_trigger": cfg("trigger", placeholder="Опиши свой автоматический ритуал"),
    "changed_routine": cfg("coping_action", placeholder="Напиши, что изменишь"),
    "week_one_challenge": cfg("reason", placeholder="Напиши, что было самым сложным"),
    "week_one_help": cfg("coping_action", placeholder="Напиши, что тебе помогало"),
    "focus_context": cfg("reason", placeholder="Опиши свой рабочий контекст", context_id="work_study"),
    "focus_experiment_start": cfg("general", False),
    "focus_experiment": cfg("reflection", placeholder="Напиши, как прошёл эксперимент"),
    "pleasure_components": cfg("reason", placeholder="Напиши, что ещё было ценным"),
    "pleasure_replacement": cfg("replacement", placeholder="Напиши, что хочешь сохранить"),
    "break_replacement": cfg("replacement", placeholder="Напиши свой элемент перерыва", context_id="work_study"),
    "evening_ritual": cfg("plan_action", placeholder="Напиши свой вечерний шаг", context_id="before_sleep"),
    "belief_less_convincing": cfg("reflection", placeholder="Напиши своё изменившееся убеждение"),
    "social_first_reply": cfg("social_response", placeholder="Напиши свою первую фразу", context_id="social"),
    "social_second_reply": cfg("social_response", placeholder="Напиши свой ответ", context_id="social"),
    "movement_switch": cfg("coping_action", placeholder="Напиши своё движение"),
    "movement_try_now": cfg("general", False),
    "movement_effect": cfg("reflection", placeholder="Напиши, что изменилось"),
    "one_time_first": cfg("plan_action", placeholder="Напиши свою первую реакцию", context_id="strong_craving"),
    "one_time_risk_followup": cfg("plan_action", placeholder="Напиши свой следующий шаг", context_id="strong_craving"),
    "one_time_coping_followup": cfg("plan_action", placeholder="Напиши свой следующий шаг", context_id="strong_craving"),
    "post_lapse_thought": cfg("reflection", placeholder="Напиши свою мысль"),
    "post_lapse_choice": cfg("lapse_plan", placeholder="Напиши полезное следующее действие", context_id="lapse"),
    "unexpected_feature": cfg("reflection", placeholder="Напиши, что тебя удивляет"),
    "unexpected_desire_response": cfg("plan_action", placeholder="Напиши свой первый шаг", context_id="strong_craving"),
    "scenario_decision_one": cfg("plan_action", placeholder="Напиши первое действие"),
    "scenario_decision_two": cfg("social_response", placeholder="Напиши свой ответ", context_id="social"),
    "scenario_decision_three": cfg("plan_action", placeholder="Напиши следующий шаг"),
    "warning_signs": cfg("reason", placeholder="Напиши свой ранний сигнал", context_id="strong_craving"),
    "warning_priority": cfg("reason", placeholder="Напиши самый ранний сигнал", context_id="strong_craving"),
    "warning_response": cfg("plan_action", placeholder="Напиши раннее действие", context_id="strong_craving"),
    "protection_replacement": cfg("plan_action", placeholder="Напиши запасную альтернативу"),
    "final_change": cfg("reflection", placeholder="Напиши, что изменилось именно для тебя"),
    "keep_next": cfg("plan_action", placeholder="Напиши, что хочешь сохранить дальше"),
    "most_useful_strategy": cfg("coping_action", placeholder="Напиши свою полезную стратегию"),
}


FIELD_RESPONSE_CONFIG: dict[tuple[str, str], ResponseConfig] = {
    ("personal_habit_loop", "trigger"): cfg("trigger", placeholder="Опиши свою ситуацию"),
    ("personal_habit_loop", "first_signal"): cfg("reason", placeholder="Напиши свой первый сигнал"),
    ("personal_habit_loop", "expected"): cfg("reason", placeholder="Напиши своё ожидание"),
    ("personal_habit_loop", "alternative"): cfg("coping_action", placeholder="Напиши своё новое действие"),
    ("trigger_plan", "first_action"): cfg("plan_action", placeholder="Напиши первый шаг"),
    ("trigger_plan", "backup_action"): cfg("plan_action", placeholder="Напиши запасной шаг"),
    ("trigger_plan", "sos_threshold"): cfg("general", False),
    ("relaxation_breakdown", "before"): cfg("reason", placeholder="Напиши, что было до"),
    ("relaxation_breakdown", "after"): cfg("reflection", placeholder="Напиши, что изменилось"),
    ("relaxation_breakdown", "replacement"): cfg("replacement", placeholder="Напиши, что хочешь сохранить", context_id="stress"),
    ("boredom_menu", "one_minute"): cfg("coping_action", placeholder="Напиши действие на минуту", context_id="boredom"),
    ("boredom_menu", "three_minutes"): cfg("coping_action", placeholder="Напиши действие на три минуты", context_id="boredom"),
    ("boredom_menu", "ten_minutes"): cfg("coping_action", placeholder="Напиши действие на десять минут", context_id="boredom"),
    ("stress_plan", "first_action"): cfg("plan_action", placeholder="Напиши первый шаг", context_id="stress"),
    ("stress_plan", "backup_action"): cfg("plan_action", placeholder="Напиши запасной шаг", context_id="stress"),
    ("stress_plan", "sos_threshold"): cfg("general", False),
    ("emotion_need_action", "emotion"): cfg("reason", placeholder="Напиши своё состояние", context_id="stress"),
    ("emotion_need_action", "need"): cfg("reason", placeholder="Напиши, что тебе нужно", context_id="stress"),
    ("emotion_need_action", "action"): cfg("coping_action", placeholder="Напиши первый шаг", context_id="stress"),
    ("evening_plan", "risk"): cfg("reason", placeholder="Напиши, что делает ситуацию сложной"),
    ("evening_plan", "offer_response"): cfg("social_response", placeholder="Напиши свой ответ", context_id="social"),
    ("evening_plan", "sos_threshold"): cfg("general", False),
    ("evening_plan", "exit"): cfg("coping_action", placeholder="Напиши, как выйдешь из ситуации"),
    ("after_meal_plan", "usual"): cfg("reason", placeholder="Напиши, что обычно происходит", context_id="after_meal"),
    ("after_meal_plan", "new_action"): cfg("plan_action", placeholder="Напиши новое действие", context_id="after_meal"),
    ("lapse_analysis", "main_factor"): cfg("reason", placeholder="Напиши главную причину", context_id="lapse"),
    ("lapse_analysis", "next_action"): cfg("lapse_plan", placeholder="Напиши следующий шаг", context_id="lapse"),
    ("state_need_action", "state"): cfg("reason", placeholder="Напиши своё состояние"),
    ("state_need_action", "need"): cfg("reason", placeholder="Напиши свою потребность"),
    ("state_need_action", "action"): cfg("coping_action", placeholder="Напиши первый шаг"),
}


STRUCTURED_RESPONSE_CONFIG: dict[tuple[str, str], ResponseConfig] = {
    ("protection_plan", "strong_desire"): cfg("plan_action", context_id="strong_craving"),
    ("protection_plan", "stress"): cfg("plan_action", context_id="stress"),
    ("protection_plan", "social"): cfg("social_response", context_id="social"),
    ("protection_plan", "one_time"): cfg("plan_action", context_id="strong_craving"),
    ("protection_plan", "lapse"): cfg("lapse_plan", context_id="lapse"),
}
