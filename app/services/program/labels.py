import re
from collections.abc import Iterable
from typing import Any

RUSSIAN_LABELS: dict[str, str] = {
    "motivation": "Мотивация",
    "both": "Руки и рот",
    "mouth": "Рот",
    "hands": "Руки",
    "water": "Выпить воды",
    "object": "Взять предмет в руки",
    "stress": "Стресс",
    "coffee": "Кофе",
    "after_meal": "После еды",
    "work_study": "Работа / учёба",
    "social": "Компания",
    "alcohol": "Алкоголь / вечеринка",
    "before_sleep": "Перед сном",
    "boredom": "Скука",
    "strong_craving": "Сильное желание",
    "strong_desire": "Сильное желание",
    "general": "Общий план",
    "lapse": "После эпизода",
    "breathing": "Спокойное дыхание",
    "distraction": "Поиграть",
    "change_activity": "Переключиться",
    "replacement_action": "Занять рот / руки",
    "ai_support": "Поговорить с AIR",
    "walk": "Пройтись",
    "walk_3": "Пройтись 3 минуты",
    "walk_5": "Пройтись 5 минут",
    "change_place": "Сменить место",
    "music": "Включить музыку",
    "contact": "Связаться с человеком",
    "sos": "Открыть SOS",
    "outside": "Выйти на воздух",
    "brush": "Почистить зубы",
    "stretch": "Сделать короткую разминку",
    "stairs": "Пройти по лестнице",
    "pause": "Сделать паузу",
    "other": "Другое",
    "one_time": "Мысль «один раз»",
    "trigger_plan": "План для главного триггера",
    "stress_plan": "План при стрессе",
    "social_response": "Ответ в компании",
    "evening_plan": "План сложного вечера",
    "after_meal_plan": "План после еды",
    "one_time_plan": "План на мысль «один раз»",
    "warning_plan": "План раннего сигнала",
    "boredom_menu": "План при скуке",
    "break_replacement": "Новый рабочий перерыв",
    "movement_switch": "Переключение движением",
    "protection_plan": "Мой план защиты",
    "final_rule": "Правило на будущее",
    "personal_plan": "Мой план",
    "final_change": "Что изменилось",
    "keep_next": "Что сохраняю дальше",
    "most_useful_strategy": "Самая полезная стратегия",
    "next_30_day_rule": "Правило на следующие 30 дней",
    "understand_triggers": "Я лучше понимаю свои триггеры",
    "manage_craving": "Мне легче проходить тягу",
    "working_switches": "Я нашёл рабочие способы переключаться",
    "confident_free": "Я увереннее чувствую себя без никотина",
    "hard_moments": "Я научился проходить сложные моменты",
    "understand_dependence": "Я лучше понимаю свою зависимость",
    "use_sos": "Использовать SOS при сильной тяге",
    "use_personal_plan": "Пользоваться своим планом",
    "notice_triggers": "Продолжать замечать триггеры",
    "watch_progress": "Следить за прогрессом",
    "return_techniques": "Возвращаться к рабочим техникам",
    "trigger": "Триггер",
    "first_signal": "Первый сигнал",
    "expected": "Ожидаемый эффект",
    "alternative": "Новое действие",
    "primary_triggers": "Основные триггеры",
    "saved_actions": "Сохранённые действия",
}

CUSTOM_SENTINELS = frozenset(
    {"custom", "other", "user_defined", "own", "other_option", "custom_value", "__other__"}
)
CUSTOM_TEXT_KEYS = ("custom_text", "custom_value", "user_text", "other_text", "text")


def _custom_text_from_mapping(value: dict[str, Any]) -> str | None:
    for key in CUSTOM_TEXT_KEYS:
        candidate = value.get(key)
        if (
            isinstance(candidate, str)
            and candidate.strip()
            and candidate.strip().casefold() not in CUSTOM_SENTINELS
        ):
            return candidate.strip()
    for key, candidate in value.items():
        if (
            (key.endswith("_custom") or key.endswith("_custom_text"))
            and isinstance(candidate, str)
            and candidate.strip()
        ):
            return candidate.strip()
    return None


def resolve_user_facing_value(value: Any, custom_text_value: str | None = None) -> str:
    """Resolve current and legacy custom-answer shapes without exposing sentinels."""
    preferred = custom_text_value.strip() if custom_text_value and custom_text_value.strip() else None
    if value is None:
        return "Пока нет данных"
    if isinstance(value, str):
        if value.startswith("custom:"):
            return value.removeprefix("custom:").strip() or preferred or "Свой вариант"
        cleaned = value.strip()
        if cleaned.casefold() in CUSTOM_SENTINELS:
            return preferred or "Свой вариант"
        return format_program_id(cleaned)
    if isinstance(value, list):
        rendered = [resolve_user_facing_value(item) for item in value]
        return " → ".join(item for item in rendered if item)
    if isinstance(value, dict):
        nested_text = _custom_text_from_mapping(value)
        if "value" in value:
            return resolve_user_facing_value(value["value"], nested_text)
        visible = [
            (key, item)
            for key, item in value.items()
            if item not in (None, "", [], {})
            and key not in CUSTOM_TEXT_KEYS
            and not key.endswith("_custom")
            and not key.endswith("_custom_text")
        ]
        if len(visible) == 1 and str(visible[0][1]).strip().casefold() in CUSTOM_SENTINELS:
            return nested_text or "Свой вариант"
        return " · ".join(
            f"{format_program_id(str(key))}: {resolve_user_facing_value(item, nested_text)}"
            for key, item in visible
        ) or nested_text or "Пока нет данных"
    return str(value)


def format_program_id(value: str) -> str:
    """Return a user-facing Russian label without leaking an internal identifier."""
    if value.startswith("custom:"):
        return value.removeprefix("custom:").strip() or "Свой вариант"
    if value.strip().casefold() in CUSTOM_SENTINELS:
        return "Свой вариант"
    if value in RUSSIAN_LABELS:
        return RUSSIAN_LABELS[value]
    cleaned = value.strip()
    if not cleaned:
        return "Не указано"
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", cleaned) or re.search(
        r"[a-z][A-Z]", cleaned
    ):
        return "Сохранённый вариант"
    return cleaned


def format_program_value(value: Any) -> str:
    return resolve_user_facing_value(value)


def register_program_labels(days: Iterable[Any]) -> None:
    """Register every configured option and field label in the shared formatter."""

    for day in days:
        for step in day.steps:
            for option in step.options:
                RUSSIAN_LABELS.setdefault(option.id, option.label)
            for field in step.content.get("fields", []):
                field_id = field.get("id")
                field_label = field.get("label")
                if isinstance(field_id, str) and isinstance(field_label, str):
                    RUSSIAN_LABELS.setdefault(field_id, field_label)
                for option in field.get("options", []):
                    option_id = option.get("id")
                    option_label = option.get("label")
                    if isinstance(option_id, str) and isinstance(option_label, str):
                        RUSSIAN_LABELS.setdefault(option_id, option_label)
            for collection in ("fallback_items", "scale"):
                for option in step.content.get(collection, []):
                    option_id = option.get("id")
                    option_label = option.get("label")
                    if isinstance(option_id, str) and isinstance(option_label, str):
                        RUSSIAN_LABELS.setdefault(option_id, option_label)
