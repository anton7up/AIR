from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    DevProgramDayState,
    NicotineDesireLog,
    NicotineLapse,
    ProgramDayCompletion,
    ProgramDayState,
    ProgramProfile,
    SmokingProfile,
    SosAction,
    SosSession,
    User,
    UserResponse,
)
from app.services.program.content import (
    EMOTIONS,
    NICOTINE_BELIEFS,
    PROGRAM_DAYS,
    PROGRAM_LENGTH,
    QUIT_CONCERNS,
    QUIT_REASONS,
    TRIGGER_CARDS,
    TRIGGER_OPTIONS,
)
from app.services.program.labels import (
    CUSTOM_SENTINELS,
    format_program_id,
    resolve_user_facing_value,
)
from app.services.program.personal_plan import build_personal_plan, resolve_day18_scenario
from app.services.program.schema import ProgramDay, ProgramStep, StepOption
from app.services.progress import as_utc
from app.services.quit_attempts import quit_attempt_service
from app.services.user_responses import (
    CUSTOM_PREFIX,
    UserResponseValidationError,
    custom_text,
    custom_value,
    normalize_user_text,
    user_response_memory,
)

OPTION_SOURCES: dict[str, tuple[StepOption, ...]] = {
    "quit_reasons": QUIT_REASONS,
    "triggers": TRIGGER_OPTIONS,
    "beliefs": NICOTINE_BELIEFS,
    "concerns": QUIT_CONCERNS,
    "emotions": EMOTIONS,
}
PROFILE_FIELDS = {
    "quit_reasons",
    "primary_quit_reason",
    "user_triggers",
    "primary_triggers",
    "nicotine_beliefs",
    "quit_concerns",
}
LEGACY_STEP_TARGETS = {(30, "next_30_day_rule"): "d30_result"}


class ProgramValidationError(ValueError):
    pass


class ProgramEngine:
    @staticmethod
    def _current_step_id(day: ProgramDay, current_step: str) -> str:
        """Resolve removed legacy steps without rewriting stored user state."""

        if any(step.id == current_step for step in day.steps):
            return current_step
        return LEGACY_STEP_TARGETS.get((day.number, current_step), day.steps[0].id)

    def current_day(self, user: User, now: datetime | None = None) -> int:
        if user.program_started_at is None:
            return 1
        moment = as_utc(now or datetime.now(timezone.utc))
        elapsed = max(0, int((moment - as_utc(user.program_started_at)).total_seconds()))
        return min(PROGRAM_LENGTH, elapsed // 86400 + 1)

    def get_day(self, number: int) -> ProgramDay | None:
        return PROGRAM_DAYS.get(number)

    async def get_or_create_state(
        self,
        session: AsyncSession,
        user_id: int,
        day: ProgramDay,
        *,
        dev_preview: bool = False,
    ) -> ProgramDayState | DevProgramDayState:
        state_model = DevProgramDayState if dev_preview else ProgramDayState
        state = cast(
            ProgramDayState | DevProgramDayState | None,
            await session.scalar(
                select(state_model).where(
                    state_model.user_id == user_id,
                    state_model.day_number == day.number,
                )
            ),
        )
        if state is None:
            state = cast(
                ProgramDayState | DevProgramDayState,
                state_model(
                    user_id=user_id,
                    day_number=day.number,
                    current_step=day.steps[0].id,
                    state_json={},
                ),
            )
            session.add(state)
            await session.flush()
        return state

    async def get_or_create_profile(
        self, session: AsyncSession, user_id: int
    ) -> ProgramProfile:
        profile = await session.scalar(
            select(ProgramProfile).where(ProgramProfile.user_id == user_id)
        )
        if profile is None:
            profile = ProgramProfile(user_id=user_id)
            session.add(profile)
            await session.flush()
        return profile

    def _option_lookup(self, source: str) -> dict[str, StepOption]:
        base_source = source.removeprefix("selected:")
        source_map = {
            "quit_reasons": QUIT_REASONS,
            "user_triggers": TRIGGER_OPTIONS,
        }
        options = OPTION_SOURCES.get(base_source, source_map.get(base_source, ()))
        if not options:
            options = next(
                (
                    step.options
                    for day in PROGRAM_DAYS.values()
                    for step in day.steps
                    if step.id == base_source
                ),
                (),
            )
        return {option.id: option for option in options}

    def _dynamic_options(
        self, source: str, context: dict[str, Any]
    ) -> list[dict[str, str]]:
        profile: ProgramProfile | None = context.get("profile")
        if source == "profile:primary_triggers":
            selected = list(profile.primary_triggers or []) if profile else []
            selected = selected or ["stress", "coffee", "after_meal"]
            lookup = {option.id: option.label for option in TRIGGER_OPTIONS}
            return [{"id": item, "label": lookup[item]} for item in selected if item in lookup]
        if source == "profile:nicotine_beliefs":
            selected = list(profile.nicotine_beliefs or []) if profile else []
            selected = selected[:4] or ["habit", "relax", "break"]
            lookup = {option.id: option.label for option in NICOTINE_BELIEFS}
            return [{"id": item, "label": lookup[item]} for item in selected if item in lookup]
        if source == "analytics:challenge":
            trigger_ids = [context.get("frequent_trigger")]
            if profile:
                trigger_ids.extend(profile.primary_triggers or [])
            trigger_ids.extend(["strong_desire", "other"])
            lookup = {option.id: option.label for option in TRIGGER_OPTIONS}
            lookup |= {"strong_desire": "⚡ Сильное желание", "other": "Другая ситуация"}
            unique = list(dict.fromkeys(item for item in trigger_ids if item))
            return [{"id": item, "label": lookup.get(item, item)} for item in unique[:6]]
        if source == "history:strategies":
            return context["strategy_options"]
        if source == "history:plan_sections":
            return context["plan_section_options"]
        if source == "history:rules":
            return context["rule_options"]
        return []

    def options_for(
        self,
        step: ProgramStep,
        answers: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> list[dict[str, str]]:
        if not step.options_source:
            return [{"id": option.id, "label": option.label} for option in step.options]
        if step.options_source.startswith("selected:"):
            source_key = step.options_source.split(":", 1)[1]
            selected = answers.get(source_key, [])
            lookup = self._option_lookup(step.options_source)
            return [
                {
                    "id": item,
                    "label": (
                        lookup[item].label
                        if item in lookup
                        else (custom_text(item) or item)
                    ),
                }
                for item in selected
                if item in lookup or custom_text(item)
            ]
        if context and ":" in step.options_source:
            dynamic = self._dynamic_options(step.options_source, context)
            if dynamic:
                return dynamic
        return [
            {"id": option.id, "label": option.label}
            for option in OPTION_SOURCES.get(step.options_source, ())
        ]

    @staticmethod
    def _custom_answer_text(value: object) -> str | None:
        try:
            return custom_text(value)
        except UserResponseValidationError:
            return None

    def _cards_for(self, answers: dict[str, Any]) -> list[dict[str, str]]:
        cards: list[dict[str, str]] = []
        for trigger in answers.get("primary_triggers", []):
            custom = self._custom_answer_text(trigger)
            if custom:
                cards.append(
                    {
                        "id": str(trigger),
                        "title": custom,
                        "short_explanation": "",
                        "why_it_happens": "",
                        "first_tip": "",
                    }
                )
            elif (
                isinstance(trigger, str)
                and trigger.casefold() not in CUSTOM_SENTINELS
                and trigger in TRIGGER_CARDS
            ):
                cards.append(dict(TRIGGER_CARDS[trigger]))
        return cards

    def _summary_for(self, answers: dict[str, Any]) -> dict[str, list[str] | str | None]:
        reason_lookup = self._option_lookup("quit_reasons")
        trigger_lookup = self._option_lookup("user_triggers")
        belief_lookup = {option.id: option for option in NICOTINE_BELIEFS}
        concern_lookup = {option.id: option for option in QUIT_CONCERNS}

        def labels(key: str, lookup: dict[str, StepOption]) -> list[str]:
            result: list[str] = []
            for item in answers.get(key, []):
                custom = self._custom_answer_text(item)
                if custom:
                    result.append(custom)
                elif (
                    isinstance(item, str)
                    and item.casefold() not in CUSTOM_SENTINELS
                    and item in lookup
                ):
                    result.append(lookup[item].label)
            return result

        primary = answers.get("primary_quit_reason")
        primary_custom = self._custom_answer_text(primary)
        return {
            "primary_reason": (
                primary_custom
                if primary_custom
                else reason_lookup[primary].label
                if isinstance(primary, str)
                and primary.casefold() not in CUSTOM_SENTINELS
                and primary in reason_lookup
                else None
            ),
            "primary_triggers": labels("primary_triggers", trigger_lookup),
            "beliefs": labels("nicotine_beliefs", belief_lookup),
            "concerns": labels("quit_concerns", concern_lookup),
        }

    def _labels(self, values: list[str], options: tuple[StepOption, ...]) -> list[str]:
        lookup = {option.id: option.label for option in options}
        result: list[str] = []
        for value in values:
            custom = self._custom_answer_text(value)
            if custom:
                result.append(custom)
            elif value.casefold() not in CUSTOM_SENTINELS and value in lookup:
                result.append(lookup[value])
        return result

    def _personalized_insight(
        self, key: str | None, context: dict[str, Any]
    ) -> dict[str, Any]:
        profile: ProgramProfile | None = context["profile"]
        triggers = list(profile.primary_triggers or []) if profile else []
        beliefs = set(profile.nicotine_beliefs or []) if profile else set()
        concerns = set(profile.quit_concerns or []) if profile else set()
        trigger_labels = self._labels(triggers, TRIGGER_OPTIONS)
        primary_trigger = trigger_labels[0] if trigger_labels else None
        primary_trigger_is_custom = bool(
            triggers and self._custom_answer_text(triggers[0])
        )
        frequent_trigger = context.get("frequent_trigger_label")
        desire_count = context["desire_count"]
        lapse_count = context["lapse_count"]

        fallback = {
            "title": "Пока собираем наблюдения",
            "body": "Данных пока недостаточно для уверенного персонального вывода. Используй упражнение как гипотезу и проверь её в реальной ситуации.",
            "is_fallback": True,
        }
        if key in {"habit_loop", "primary_trigger", "automatic_ritual"}:
            if primary_trigger:
                if primary_trigger_is_custom:
                    return {
                        "title": primary_trigger,
                        "body": "",
                        "is_fallback": False,
                    }
                return {"title": primary_trigger, "body": f"Ты отметил «{primary_trigger}» среди сложных ситуаций. Возьмём её как рабочий пример, не считая окончательным выводом.", "is_fallback": False}
            return fallback
        if key == "first_seconds":
            return {"title": "Твоя пауза может быть очень короткой", "body": "Даже несколько секунд между сигналом и действием уже создают место для выбора. Здесь не требуется выдерживать желание любой ценой.", "is_fallback": False}
        if key == "withdrawal":
            selected = self._labels(list(concerns), QUIT_CONCERNS)
            if selected:
                return {"title": "Ты заранее отмечал несколько опасений", "body": "В твоей стартовой карте: " + ", ".join(selected[:3]) + ". Сегодня сравни их с реальными ощущениями, не предполагая, что они обязательно должны появиться.", "is_fallback": False}
            return fallback
        belief_map = {
            "relax_belief": ("relax", "В начале ты отмечал связь никотина с расслаблением. Сегодня не спорим с ощущением, а разбираем его состав."),
            "focus_belief": ("focus", "Ты отмечал концентрацию среди ожидаемых эффектов. Небольшой эксперимент поможет проверить эту связь на одном рабочем цикле."),
            "pleasure_belief": ("pleasure", "Ты связывал никотин с удовольствием. Сейчас можно спокойно уточнить, какие части этого переживания были важнее всего."),
            "break_belief": ("break", "В стартовой карте никотин был связан с поводом для перерыва. Сохраним паузу, меняя только автоматическое условие."),
        }
        if key in belief_map:
            belief, text = belief_map[key]
            if belief in beliefs:
                return {"title": "Это связано с твоим ответом Дня 1", "body": text, "is_fallback": False}
            return {"title": "Даже если это не было главной причиной", "body": "Эта распространённая связь может работать в отдельных ситуациях. Рассмотри упражнение как проверку, а не утверждение о тебе.", "is_fallback": True}
        trigger_key_map = {
            "boredom": "boredom", "evening": "before_sleep", "stress": "stress",
            "social": "social", "alcohol": "alcohol", "after_meal": "after_meal",
        }
        if key in trigger_key_map:
            if key == "alcohol":
                scenario = context["day18_scenario"]
                return {
                    "title": scenario["title"],
                    "body": scenario["body"],
                    "is_fallback": scenario["id"] == "neutral",
                }
            trigger_id = trigger_key_map[key]
            label = next((item.label for item in TRIGGER_OPTIONS if item.id == trigger_id), trigger_id)
            observed = trigger_id in triggers or context.get("frequent_trigger") == trigger_id
            if observed:
                return {"title": label, "body": "Эта ситуация есть в твоей стартовой карте или повторяется в записях. Подготовим для неё конкретный следующий шаг.", "is_fallback": False}
            return {"title": "Подготовка на будущее", "body": "Эта ситуация пока не выделяется в твоих данных. Упражнение можно использовать как профилактический сценарий без предположения, что триггер у тебя сильный.", "is_fallback": True}
        if key in {"emotion", "real_need"}:
            if frequent_trigger:
                return {"title": f"Частый сигнал в записях: {frequent_trigger}", "body": "Это только повторение в доступных данных, не диагноз. Используй его как один пример для упражнения.", "is_fallback": False}
            return fallback
        if key == "movement":
            return {"title": "Минимальный шаг важнее идеального", "body": "Выбери движение, которое доступно в твоём обычном месте и не требует подготовки.", "is_fallback": False}
        if key == "post_lapse":
            if lapse_count:
                trigger = context.get("last_lapse_trigger_label") or "ситуация не указана"
                return {"title": "Есть реальный эпизод для спокойного разбора", "body": f"Последний сохранённый эпизод: {trigger}. Следующее действие остаётся отдельным выбором и не обнуляет пройденный путь.", "is_fallback": False}
            return {"title": "Это безопасная симуляция", "body": "Сохранённых эпизодов нет. Мы разберём гипотетическую ситуацию и не будем создавать запись об употреблении.", "is_fallback": True}
        if key == "one_time":
            reason = profile.primary_quit_reason if profile else None
            reason_custom = self._custom_answer_text(reason)
            if reason_custom:
                return {
                    "title": reason_custom,
                    "body": "",
                    "is_fallback": False,
                }
            reason_label = next(
                (item.label for item in QUIT_REASONS if item.id == reason), None
            )
            if reason_label:
                return {"title": "Твоя сохранённая причина", "body": f"В День 1 главным ориентиром было: {reason_label}. Не нужно принимать это решение заново в сложный момент.", "is_fallback": False}
            return fallback
        if key == "lapse_review":
            if lapse_count:
                trigger = context.get("last_lapse_trigger_label") or "триггер не указан"
                return {"title": "Есть реальный эпизод для разбора", "body": f"Последний сохранённый эпизод: {trigger}. Разбирай последовательность без оценки себя.", "is_fallback": False}
            return {"title": "Эпизодов не зафиксировано", "body": f"Используем безопасную симуляцию: {primary_trigger or frequent_trigger or 'выбери наиболее вероятную сложную ситуацию'}. AIR не будет придумывать событие, которого не было.", "is_fallback": True}
        if key == "unexpected_desire":
            if desire_count:
                return {"title": f"Записей желаний: {desire_count}", "body": "Посмотри, было ли среди них желание после спокойного периода. Само его появление не отменяет изменившуюся реакцию.", "is_fallback": False}
            return fallback
        if key == "risk_scenario":
            scenario = context.get("last_lapse_trigger_label") or frequent_trigger or primary_trigger
            if scenario:
                return {"title": f"Ситуация: {scenario}", "body": "Источник выбран по приоритету: последний эпизод, частые записи, затем стартовый триггер. Это репетиция, а не прогноз.", "is_fallback": False}
            return fallback
        if key == "warning_signs":
            return {"title": "Не больше трёх сигналов", "body": "Выбирай только те признаки, которые относятся к твоему опыту. Их задача — раньше добавить поддержку, а не постоянно ждать срыва.", "is_fallback": not bool(desire_count or lapse_count)}
        if key == "protection_plan":
            plan = context["personal_plan"]
            if plan["has_plan"]:
                return {"title": f"Стратегий в личном плане: {plan['strategy_count']}", "body": "Ниже — лучшие доступные стратегии по каждой ситуации. День 29 можно использовать, чтобы заменить или уточнить любой пункт.", "is_fallback": False, "plan_items": plan["items"]}
            return fallback
        return fallback

    def _checkpoint_cards(self, key: str | None, context: dict[str, Any]) -> list[dict[str, str]]:
        profile: ProgramProfile | None = context["profile"]
        cards: list[dict[str, str]] = []

        def add(label: str, value: object, note: str = "") -> None:
            cards.append({"label": label, "value": str(value), "note": note})

        add("Записей желаний", context["desire_count"], "Фактические записи в AIR")
        if context.get("frequent_trigger_label"):
            add("Частый триггер", context["frequent_trigger_label"], "Повторение в записях, не причинный вывод")
        if context.get("average_intensity") is not None:
            add("Средняя интенсивность", f"{context['average_intensity']:.1f} / 10")
        add("SOS-сессий", context["sos_count"])
        if context["sos_action_count"]:
            add("Действий в SOS", context["sos_action_count"])
        add("Попыток", context["attempts"])
        add("Лучшая серия", self._format_duration(context["best_seconds"]))
        if key in {"week_two", "week_three", "final"} and profile:
            if profile.primary_quit_reason:
                label = next((item.label for item in QUIT_REASONS if item.id == profile.primary_quit_reason), profile.primary_quit_reason)
                add("Главная причина", resolve_user_facing_value(label), "Ответ Дня 1")
            initial_triggers = self._labels(list(profile.primary_triggers or []), TRIGGER_OPTIONS)
            if initial_triggers:
                add("Стартовые триггеры", ", ".join(initial_triggers[:3]), "Ответ Дня 1")
        if key in {"week_three", "final"} and profile:
            initial_beliefs = self._labels(list(profile.nicotine_beliefs or []), NICOTINE_BELIEFS)
            if initial_beliefs:
                add("Стартовые убеждения", ", ".join(initial_beliefs[:3]), "Сравни со своим сегодняшним опытом")
        if key == "final":
            add("Текущая серия", self._format_duration(context["current_seconds"]))
            add("Всего времени без никотина", self._format_duration(context["total_seconds"]))
            add("Пройдено дней", f"{context['completed_days']} / {PROGRAM_LENGTH}")
            if context["lapse_count"]:
                add("Зафиксировано эпизодов", context["lapse_count"], "История сохранена без осуждения")
            if context.get("money_saved") is not None:
                add("Сохранено в текущей попытке", f"≈ {context['money_saved']:,} ₽".replace(",", " "))
            if context.get("units_avoided") is not None:
                add("Не использовано единиц", f"≈ {context['units_avoided']}")
            if context.get("best_sos_tool"):
                add("Самый полезный инструмент SOS", self._label_for_id(context["best_sos_tool"]), "По сохранённому снижению интенсивности")
            if context["personal_plan"]["strategy_count"]:
                add("Стратегий в личном плане", context["personal_plan"]["strategy_count"])
        if not cards:
            add("Данных пока мало", "Это нормально", "Продолжай отмечать реальные эпизоды без попытки угадать закономерность")
        return cards

    @staticmethod
    def _format_duration(seconds: int) -> str:
        days, remainder = divmod(max(0, seconds), 86400)
        hours = remainder // 3600
        return f"{days} д {hours} ч"

    def _label_for_id(self, value: str) -> str:
        for options in OPTION_SOURCES.values():
            for option in options:
                if option.id == value:
                    return option.label
        for day in PROGRAM_DAYS.values():
            for program_step in day.steps:
                for option in program_step.options:
                    if option.id == value:
                        return option.label
                for field in program_step.content.get("fields", []):
                    for option in field.get("options", []):
                        if option.get("id") == value:
                            return str(option.get("label", value))
        static = {
            "wait_two": "Подождать 2 минуты",
            "sos": "Если желание сильное — открыть SOS",
            "lapse": "Эпизод употребления",
            "program_continues": "Продолжается с текущего дня",
        }
        return static.get(value, format_program_id(value))

    def _answer_value(self, reference: str, answers: dict[str, Any], context: dict[str, Any]) -> Any:
        if reference.startswith("static:"):
            static_value = reference.split(":", 1)[1]
            if static_value == "lapse":
                return context.get("lapse_scenario_label", self._label_for_id(static_value))
            return static_value
        if reference.startswith("context:"):
            return context.get(reference.split(":", 1)[1])
        if reference.startswith("coalesce:"):
            for key in reference.split(":", 1)[1].split(","):
                if answers.get(key):
                    return answers[key]
            return None
        root, _, nested = reference.partition(".")
        value = answers.get(root)
        if nested and isinstance(value, dict):
            return value.get(nested)
        return value

    def _display_value(self, value: Any) -> str:
        if isinstance(value, str):
            if value.strip().casefold() in CUSTOM_SENTINELS:
                return "Не указано"
            known = self._label_for_id(value)
            if known != "Свой вариант" and known != "Сохранённый вариант":
                return known
        return resolve_user_facing_value(value)

    def _result_payload(
        self, step: ProgramStep, answers: dict[str, Any], context: dict[str, Any]
    ) -> dict[str, Any]:
        items = []
        for item in step.content.get("items", []):
            value = self._answer_value(item["answer"], answers, context)
            if value is not None:
                items.append(
                    {
                        "label": item["label"],
                        "value": self._display_value(value),
                        "raw": value,
                    }
                )
        return {
            "title": step.title,
            "style": step.content.get("style", "plan"),
            "items": items,
        }

    def _field_options(
        self,
        field: dict[str, Any],
        context: dict[str, Any],
        current: dict[str, Any] | None = None,
    ) -> list[dict[str, str]]:
        options = list(field.get("options", []))
        source = field.get("options_source")
        if source:
            options = self._dynamic_options(source, context)
        excluded_key = field.get("exclude_answer")
        excluded = current.get(excluded_key) if current and excluded_key else None
        return [option for option in options if option.get("id") != excluded]

    def step_payload(
        self, step: ProgramStep, answers: dict[str, Any], context: dict[str, Any]
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": step.id,
            "type": step.type,
            "title": step.title,
            "body": step.body,
            "required": step.required,
            "max_selections": step.max_selections,
            "button_text": step.button_text,
            "options": self.options_for(step, answers, context),
            "value": answers.get(step.id),
            "content": dict(step.content),
        }
        response_type = step.content.get("response_type")
        if response_type:
            payload["content"]["remembered_options"] = self._remembered_options(
                context,
                response_type=response_type,
                response_context=step.content.get("response_context"),
            )
        if step.type == "personalized_cards":
            payload["cards"] = self._cards_for(answers)
        if step.type == "personalized_summary":
            payload["summary"] = self._summary_for(answers)
        if step.type == "personalized_insight":
            payload["insight"] = self._personalized_insight(step.personalization_key, context)
        if step.type == "selected_insights":
            selected = answers.get(step.content.get("source_step", ""), [])
            insight_map = step.content.get("insights", {})
            payload["insights"] = []
            for item in selected:
                if item in insight_map:
                    payload["insights"].append(
                        {"id": item, "text": insight_map[item]}
                    )
                else:
                    custom = self._custom_answer_text(item)
                    if custom:
                        payload["insights"].append(
                            {"id": item, "text": custom}
                        )
        if step.type == "checkpoint":
            payload["analytics"] = self._checkpoint_cards(step.personalization_key, context)
        if step.type == "plan_builder":
            current = answers.get(step.id) if isinstance(answers.get(step.id), dict) else {}
            payload["builder_fields"] = [
                {
                    "id": field["id"],
                    "label": field["label"],
                    "options": self._field_options(field, context, current),
                    "exclude_answer": field.get("exclude_answer"),
                    "response_type": field.get("response_type"),
                    "allow_other": bool(field.get("allow_other")),
                    "other_placeholder": field.get("other_placeholder"),
                    "response_context": field.get("response_context"),
                    "remembered_options": self._remembered_options(
                        context,
                        response_type=field.get("response_type"),
                        response_context=field.get("response_context"),
                    ),
                }
                for field in step.content.get("fields", [])
            ]
        if step.type == "comparison":
            items = self._dynamic_options(step.content["items_source"], context)
            payload["comparison"] = {
                "items": items or step.content.get("fallback_items", []),
                "scale": step.content.get("scale", []),
            }
        if step.type == "result_card":
            payload["result"] = self._result_payload(step, answers, context)
        if step.type == "structured_input" and not payload["value"]:
            payload["value"] = self._prefill_structured_step(step, context)
        if step.id == "post_lapse_thought":
            if context["lapse_count"]:
                payload["title"] = "После сохранённого эпизода: что происходит в голове?"
                payload["body"] = "Разберём реальный эпизод без осуждения и без обнуления пути."
            else:
                payload["title"] = "Представь гипотетический единичный эпизод. Что могло бы произойти в голове?"
                payload["body"] = "Это только симуляция. AIR не создаст запись об употреблении."
        return payload

    @staticmethod
    def _remembered_options(
        context: dict[str, Any], *, response_type: str | None, response_context: str | None
    ) -> list[dict[str, Any]]:
        if not response_type:
            return []
        rows: list[UserResponse] = context.get("user_responses", [])
        relevant = [
            row
            for row in rows
            if row.response_type.value == response_type
            and (
                response_context is None
                or row.context_id is None
                or row.context_id == response_context
            )
        ]
        relevant.sort(
            key=lambda row: (
                1 if response_context and row.context_id == response_context else 0,
                row.usage_count,
                as_utc(row.last_used_at).timestamp(),
                row.id,
            ),
            reverse=True,
        )
        return [{"id": row.id, "value": row.value} for row in relevant[:5]]

    def _prefill_structured_step(
        self, step: ProgramStep, context: dict[str, Any]
    ) -> dict[str, str] | None:
        if step.content.get("prefill_source") != "protection_plan":
            return None
        plan = context["personal_plan"]
        mappings = {
            "strong_desire": "strong_craving",
            "stress": "stress",
            "social": "social",
            "one_time": "strong_craving",
            "lapse": "lapse",
        }
        prefill = {
            target: " → ".join(plan["by_category"][category]["steps"])
            for target, category in mappings.items()
            if category in plan["by_category"]
        }
        return prefill or None

    def _collect_strategy_ids(self, value: Any) -> list[str]:
        known = {"walk", "breathing", "water", "change_place", "music", "contact", "sos", "outside", "brush", "stretch", "stairs"}
        if isinstance(value, str):
            return [value] if value in known else []
        if isinstance(value, dict):
            return [item for nested in value.values() for item in self._collect_strategy_ids(nested)]
        if isinstance(value, list):
            return [item for nested in value for item in self._collect_strategy_ids(nested)]
        return []

    async def _context(
        self, session: AsyncSession, user: User, *, dev_preview: bool = False
    ) -> dict[str, Any]:
        profile = await session.scalar(
            select(ProgramProfile).where(ProgramProfile.user_id == user.id)
        )
        desires = list(
            (await session.scalars(
                select(NicotineDesireLog).where(NicotineDesireLog.user_id == user.id)
            )).all()
        )
        triggers = [entry.trigger_id for entry in desires if entry.trigger_id]
        frequent_trigger = Counter(triggers).most_common(1)[0][0] if triggers else None
        trigger_lookup = {option.id: option.label for option in TRIGGER_OPTIONS}
        sos_count = int(await session.scalar(select(func.count(SosSession.id)).where(SosSession.user_id == user.id)) or 0)
        sos_action_count = int(await session.scalar(select(func.count(SosAction.id)).join(SosSession).where(SosSession.user_id == user.id)) or 0)
        lapses = list((await session.scalars(select(NicotineLapse).where(NicotineLapse.user_id == user.id).order_by(NicotineLapse.occurred_at.desc()))).all())
        states = list(
            (
                await session.scalars(
                    select(ProgramDayState)
                    .where(ProgramDayState.user_id == user.id)
                    .order_by(ProgramDayState.day_number)
                )
            ).all()
        )
        responses = list(
            (
                await session.scalars(
                    select(UserResponse).where(UserResponse.user_id == user.id)
                )
            ).all()
        )
        all_answers: dict[str, Any] = {}
        for production_state in states:
            all_answers.update(production_state.state_json or {})
        if dev_preview:
            dev_states = list(
                (
                    await session.scalars(
                        select(DevProgramDayState).where(
                            DevProgramDayState.user_id == user.id
                        ).order_by(DevProgramDayState.day_number)
                    )
                ).all()
            )
            for dev_state in dev_states:
                all_answers.update(dev_state.state_json or {})
            profile = cast(
                ProgramProfile,
                SimpleNamespace(
                    **{
                        field: all_answers.get(
                            field,
                            getattr(
                                profile,
                                field,
                                [] if field != "primary_quit_reason" else None,
                            ),
                        )
                        for field in PROFILE_FIELDS
                    }
                ),
            )
        strategy_ids = list(dict.fromkeys(self._collect_strategy_ids(all_answers)))
        sos_actions = list(
            (
                await session.scalars(
                    select(SosAction)
                    .join(SosSession)
                    .where(SosSession.user_id == user.id)
                    .order_by(SosAction.started_at.desc())
                )
            ).all()
        )
        strategy_ids.extend(action.support_action or action.support_type for action in sos_actions)
        strategy_ids = list(dict.fromkeys(strategy_ids))
        if not strategy_ids:
            strategy_ids = ["walk", "breathing", "sos"]
        strategy_options = [
            {"id": item, "label": self._label_for_id(item)}
            for item in strategy_ids[:7]
        ]
        plan_keys = [
            "trigger_plan", "stress_plan", "social_response", "evening_plan",
            "after_meal_plan", "one_time_plan", "warning_plan", "boredom_menu",
            "break_replacement", "movement_switch",
        ]
        plan_sections = [key for key in plan_keys if all_answers.get(key)]
        plan_section_options = [
            {"id": key, "label": self._label_for_id(key)} for key in plan_sections
        ] or [{"id": "sos", "label": "При сильном желании — SOS"}]
        rule_options = []
        for key in plan_sections[:6]:
            rule_options.append(
                {"id": key, "label": f"Сохраняю: {self._display_value(all_answers[key])}"}
            )
        if not rule_options:
            rule_options = [
                {"id": "sos", "label": "При сильном желании сразу открываю SOS"},
                {"id": "pause", "label": "Сначала делаю паузу, затем решаю"},
            ]
        personal_plan = build_personal_plan(
            states,
            primary_triggers=(profile.primary_triggers or []) if profile else [],
            responses=responses,
        )
        effects: dict[str, list[int]] = {}
        for action in sos_actions:
            if action.effect_delta is not None and action.completed_at is not None:
                effects.setdefault(action.support_type, []).append(action.effect_delta)
        best_sos_tool = max(
            effects,
            key=lambda support_type: sum(effects[support_type]) / len(effects[support_type]),
            default=None,
        )
        metrics = await quit_attempt_service.metrics(session, user.id)
        completed_days = int(await session.scalar(select(func.count(ProgramDayCompletion.id)).where(ProgramDayCompletion.user_id == user.id)) or 0)
        smoking_profile = await session.scalar(select(SmokingProfile).where(SmokingProfile.user_id == user.id))
        money_saved: int | None = None
        units_avoided: int | None = None
        if smoking_profile and metrics.current_seconds > 0:
            days = Decimal(metrics.current_seconds) / Decimal(86400)
            money_saved = round(float(Decimal(smoking_profile.yearly_expense) / Decimal(365) * days))
            units_avoided = round(float(Decimal(smoking_profile.daily_units or 0) * days))
        return {
            "profile": profile,
            "desire_count": len(desires),
            "average_intensity": (sum(item.intensity for item in desires) / len(desires)) if desires else None,
            "frequent_trigger": frequent_trigger,
            "frequent_trigger_label": trigger_lookup.get(frequent_trigger or ""),
            "sos_count": sos_count,
            "sos_action_count": sos_action_count,
            "lapse_count": len(lapses),
            "last_lapse_trigger_label": trigger_lookup.get(lapses[0].trigger_id or "") if lapses else None,
            "attempts": metrics.attempts,
            "current_seconds": metrics.current_seconds,
            "best_seconds": metrics.best_seconds,
            "total_seconds": metrics.total_seconds,
            "completed_days": completed_days,
            "money_saved": money_saved,
            "units_avoided": units_avoided,
            "all_answers": all_answers,
            "user_responses": responses,
            "strategy_options": strategy_options,
            "plan_section_options": plan_section_options,
            "rule_options": rule_options,
            "primary_trigger": trigger_lookup.get(
                (profile.primary_triggers or [""])[0] if profile else "", "Сложная ситуация"
            ),
            "lapse_or_simulation": (
                f"Реальный эпизод: {trigger_lookup.get(lapses[0].trigger_id or '', 'триггер не указан')}"
                if lapses
                else f"Симуляция: {trigger_lookup.get(frequent_trigger or '', 'вероятная сложная ситуация')}"
            ),
            "rare_trigger": trigger_lookup.get(triggers[-1], "Редкий или новый контекст") if triggers else "Редкий или новый контекст",
            "risk_scenario": context_risk if (context_risk := (trigger_lookup.get(lapses[0].trigger_id or "") if lapses else trigger_lookup.get(frequent_trigger or "") or (trigger_lookup.get((profile.primary_triggers or [""])[0]) if profile else None))) else "Сложная ситуация",
            "protection_plan": personal_plan,
            "personal_plan": personal_plan,
            "best_sos_tool": best_sos_tool,
            "day18_scenario": resolve_day18_scenario(
                profile.primary_triggers or [] if profile else []
            ),
            "lapse_scenario_label": (
                "Сохранённый эпизод употребления" if lapses else "Гипотетическая ситуация"
            ),
        }

    async def day_payload(
        self,
        session: AsyncSession,
        user: User,
        day_number: int,
        *,
        dev_preview: bool = False,
    ) -> dict[str, Any]:
        day = self.get_day(day_number)
        if day is None:
            raise ProgramValidationError("Материалы этого дня пока недоступны")
        state = await self.get_or_create_state(
            session, user.id, day, dev_preview=dev_preview
        )
        answers = dict(state.state_json or {})
        context = await self._context(session, user, dev_preview=dev_preview)
        current_step = self._current_step_id(day, state.current_step)
        step_index = next(
            (index for index, step in enumerate(day.steps) if step.id == current_step),
            0,
        )
        desire_count = await session.scalar(
            select(func.count(NicotineDesireLog.id)).where(
                NicotineDesireLog.user_id == user.id,
                NicotineDesireLog.created_at >= (user.program_started_at or user.registered_at),
            )
        )
        return {
            "number": day.number,
            "title": day.title,
            "short_description": day.short_description,
            "achievement": day.achievement,
            "task_title": day.task_title,
            "task_description": day.task_description,
            "task_progress": min(3, int(desire_count or 0)),
            "current_step": current_step,
            "step_index": step_index,
            "total_steps": len(day.steps),
            "completed": state.completed,
            "dev_preview": dev_preview,
            "evidence_category": day.evidence_category,
            "step": self.step_payload(day.steps[step_index], answers, context),
        }

    def _validate(
        self,
        step: ProgramStep,
        value: Any,
        answers: dict[str, Any],
        context: dict[str, Any],
    ) -> Any:
        options = {option["id"] for option in self.options_for(step, answers, context)}
        allow_other = bool(step.content.get("allow_other"))

        def validate_choice(item: str) -> str:
            if allow_other and item.startswith(CUSTOM_PREFIX):
                try:
                    return custom_value(item[len(CUSTOM_PREFIX) :])
                except UserResponseValidationError as exc:
                    raise ProgramValidationError(str(exc)) from exc
            if item not in options or (allow_other and item == "other"):
                raise ProgramValidationError("Такого варианта нет в этом шаге")
            return item

        if step.type in {"multi_select", "ordered_select"}:
            if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
                raise ProgramValidationError("Выбери один или несколько вариантов")
            normalized = [validate_choice(item) for item in value]
            unique = list(dict.fromkeys(normalized))
            if step.required and not unique:
                raise ProgramValidationError("Выбери хотя бы один вариант")
            effective_max = step.max_selections
            if effective_max and len(unique) > effective_max:
                raise ProgramValidationError(f"Выбери не больше {effective_max} вариантов")
            if step.type == "ordered_select" and step.required and step.max_selections and len(unique) != step.max_selections:
                raise ProgramValidationError(f"Выбери ровно {step.max_selections} вариантов")
            return unique
        if step.type in {"single_select", "priority_select", "action_picker", "scenario_choice"}:
            if not isinstance(value, str):
                raise ProgramValidationError("Выбери один доступный вариант")
            return validate_choice(value)
        if step.type == "text":
            if value is None:
                if step.required:
                    raise ProgramValidationError("Напиши ответ перед продолжением")
                return None
            if not isinstance(value, str) or len(value) > 2000:
                raise ProgramValidationError("Не удалось сохранить этот текст")
            normalized_text = value.strip() or None
            if step.required and normalized_text is None:
                raise ProgramValidationError("Напиши ответ перед продолжением")
            return normalized_text
        if step.type == "scale":
            if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 10:
                raise ProgramValidationError("Выбери значение от 1 до 10")
            return value
        if step.type == "structured_input":
            if value is None and not step.required:
                return self._prefill_structured_step(step, context) or {}
            if not isinstance(value, dict):
                raise ProgramValidationError("Заполни поля этого шага")
            fields = step.content.get("fields", [])
            normalized_fields: dict[str, str] = {}
            for field in fields:
                field_id = field.get("id")
                if not isinstance(field_id, str):
                    raise ProgramValidationError("Не удалось распознать одно из полей")
                item = value.get(field_id)
                if item is None:
                    item = ""
                if not isinstance(item, str) or len(item) > 2000:
                    raise ProgramValidationError("Не удалось сохранить один из ответов")
                if field.get("response_type"):
                    try:
                        item = normalize_user_text(item) if item.strip() else ""
                    except UserResponseValidationError as exc:
                        raise ProgramValidationError(str(exc)) from exc
                else:
                    item = item.strip()
                if step.required and not item:
                    raise ProgramValidationError("Заполни все поля перед продолжением")
                if item:
                    normalized_fields[field_id] = item
            return normalized_fields
        if step.type == "plan_builder":
            return self._validate_plan_builder(step, value, context, allow_partial=False)
        if step.type == "comparison":
            if not isinstance(value, dict):
                raise ProgramValidationError("Выбери ответ для каждого сравнения")
            items = self._dynamic_options(step.content["items_source"], context) or step.content.get("fallback_items", [])
            item_ids = {item["id"] for item in items}
            scale_ids = {item["id"] for item in step.content.get("scale", [])}
            if set(value) != item_ids or any(item not in scale_ids for item in value.values()):
                raise ProgramValidationError("Заполни каждый пункт сравнения")
            return dict(value)
        return value

    def _validate_plan_builder(
        self,
        step: ProgramStep,
        value: Any,
        context: dict[str, Any],
        *,
        allow_partial: bool,
    ) -> dict[str, str]:
        if not isinstance(value, dict):
            raise ProgramValidationError("Выбери пункты для своего плана")
        normalized_plan: dict[str, str] = {}
        for field in step.content.get("fields", []):
            field_id = field.get("id")
            if not isinstance(field_id, str):
                raise ProgramValidationError("Не удалось распознать пункт плана")
            selected = value.get(field_id)
            if selected is None and allow_partial:
                continue
            available = {
                option["id"]
                for option in self._field_options(field, context, value)
            }
            if not isinstance(selected, str):
                raise ProgramValidationError("Заполни план доступными вариантами")
            if field.get("allow_other") and selected.startswith(CUSTOM_PREFIX):
                try:
                    normalized_plan[field_id] = custom_value(selected[len(CUSTOM_PREFIX) :])
                except UserResponseValidationError as exc:
                    raise ProgramValidationError(str(exc)) from exc
            elif selected not in available or (field.get("allow_other") and selected == "other"):
                raise ProgramValidationError("Заполни план доступными вариантами")
            else:
                normalized_plan[field_id] = selected
        return normalized_plan

    async def _remember_program_responses(
        self,
        session: AsyncSession,
        user_id: int,
        day_number: int,
        step: ProgramStep,
        value: Any,
        *,
        increment_usage: bool = True,
    ) -> None:
        configs: list[tuple[dict[str, Any], str, str]] = []
        if step.type in {
            "multi_select", "ordered_select", "single_select", "priority_select",
            "action_picker", "scenario_choice",
        }:
            values = value if isinstance(value, list) else [value]
            for item in values:
                text = custom_text(item)
                if text:
                    configs.append((step.content, step.id, text))
        elif step.type in {"plan_builder", "structured_input"} and isinstance(value, dict):
            for field in step.content.get("fields", []):
                field_id = field.get("id")
                item = value.get(field_id) if isinstance(field_id, str) else None
                text = custom_text(item) if step.type == "plan_builder" else item if isinstance(item, str) else None
                if text and field.get("response_type"):
                    configs.append((field, f"{step.id}.{field_id}", text))

        remembered_reasons: list[int] = []
        for config, source_ref, text in configs:
            response_type = config.get("response_type")
            if not isinstance(response_type, str):
                continue
            parent_response_id = (
                remembered_reasons[-1]
                if remembered_reasons
                and response_type in {"coping_action", "replacement", "plan_action", "social_response", "lapse_plan"}
                else None
            )
            remembered = await user_response_memory.remember(
                session,
                user_id=user_id,
                response_type=response_type,
                value=text,
                source="program",
                source_ref=f"day:{day_number}:{source_ref}",
                context_id=config.get("response_context"),
                parent_response_id=parent_response_id,
                increment_usage=increment_usage,
            )
            if response_type in {"trigger", "reason"}:
                remembered_reasons.append(remembered.id)

    async def save_step_draft(
        self,
        session: AsyncSession,
        user: User,
        day_number: int,
        step_id: str,
        value: Any,
        *,
        dev_preview: bool = False,
    ) -> ProgramDayState | DevProgramDayState:
        day = self.get_day(day_number)
        if day is None:
            raise ProgramValidationError("Материалы этого дня пока недоступны")
        state = await self.get_or_create_state(session, user.id, day, dev_preview=dev_preview)
        current_step_id = self._current_step_id(day, state.current_step)
        step = next((item for item in day.steps if item.id == current_step_id), None)
        if step is None or step.id != step_id:
            raise ProgramValidationError("Сначала заверши текущий шаг")
        context = await self._context(session, user, dev_preview=dev_preview)
        normalized = (
            self._validate_plan_builder(step, value, context, allow_partial=True)
            if step.type == "plan_builder"
            else self._validate(step, value, dict(state.state_json or {}), context)
        )
        answers = dict(state.state_json or {})
        answers[step.id] = normalized
        state.state_json = answers
        if not dev_preview:
            await self._remember_program_responses(
                session,
                user.id,
                day_number,
                step,
                normalized,
                increment_usage=True,
            )
            if step.id in PROFILE_FIELDS:
                profile = await self.get_or_create_profile(session, user.id)
                setattr(profile, step.id, normalized)
        await session.flush()
        return state

    async def save_step(
        self,
        session: AsyncSession,
        user: User,
        day_number: int,
        step_id: str,
        value: Any = None,
        *,
        dev_preview: bool = False,
    ) -> ProgramDayState | DevProgramDayState:
        day = self.get_day(day_number)
        if day is None:
            raise ProgramValidationError("Материалы этого дня пока недоступны")
        state = await self.get_or_create_state(
            session, user.id, day, dev_preview=dev_preview
        )
        current_step = self._current_step_id(day, state.current_step)
        current_index = next(
            (index for index, step in enumerate(day.steps) if step.id == current_step),
            0,
        )
        step = day.steps[current_index]
        if step.id != step_id:
            raise ProgramValidationError("Сначала заверши текущий шаг")
        answers = dict(state.state_json or {})
        context = await self._context(session, user, dev_preview=dev_preview)
        selectable_types = {
            "multi_select", "single_select", "priority_select", "action_picker",
            "scenario_choice", "ordered_select", "comparison", "plan_builder",
            "text", "scale", "structured_input",
        }
        if step.type in selectable_types:
            previous_value = answers.get(step.id)
            answers[step.id] = self._validate(step, value, answers, context)
            if not dev_preview:
                await self._remember_program_responses(
                    session,
                    user.id,
                    day_number,
                    step,
                    answers[step.id],
                    increment_usage=previous_value != answers[step.id],
                )
        if step.type == "result_card":
            result_key = step.content.get("result_key")
            if isinstance(result_key, str) and result_key not in answers:
                result_data = self._result_payload(step, answers, context)
                answers[result_key] = {
                    item["label"]: item["raw"] for item in result_data["items"]
                }
        state.state_json = answers
        if step.id in PROFILE_FIELDS and not dev_preview:
            profile = await self.get_or_create_profile(session, user.id)
            setattr(profile, step.id, answers[step.id])
        if current_index < len(day.steps) - 1:
            target = step.branches.get(str(value)) or step.next_step_id
            if target:
                if not any(candidate.id == target for candidate in day.steps):
                    raise ProgramValidationError("Не удалось открыть следующий шаг")
                state.current_step = target
            else:
                state.current_step = day.steps[current_index + 1].id
        await session.flush()
        return state


program_engine = ProgramEngine()
