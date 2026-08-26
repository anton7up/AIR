from dataclasses import replace
from typing import Any

from app.services.program.response_config import (
    FIELD_RESPONSE_CONFIG,
    STEP_RESPONSE_CONFIG,
    STRUCTURED_RESPONSE_CONFIG,
)
from app.services.program.schema import ProgramDay, ProgramStep, StepOption


def opts(*items: tuple[str, str]) -> tuple[StepOption, ...]:
    return tuple(StepOption(option_id, label) for option_id, label in items)


ACTIONS = opts(
    ("walk", "🚶 Пройтись 3–5 минут"),
    ("breathing", "🌬 Сделать спокойное дыхание"),
    ("water", "💧 Выпить воды"),
    ("change_place", "🚪 Сменить место"),
    ("music", "🎵 Включить музыку"),
    ("contact", "💬 Связаться с человеком"),
    ("sos", "🆘 Открыть SOS"),
)

SOS_THRESHOLDS = opts(
    ("5", "При желании 5+"),
    ("6", "При желании 6+"),
    ("7", "При желании 7+"),
    ("8", "При желании 8+"),
)


def field(
    field_id: str,
    label: str,
    field_options: tuple[StepOption, ...] = (),
    *,
    options_source: str | None = None,
    exclude_answer: str | None = None,
) -> dict[str, Any]:
    return {
        "id": field_id,
        "label": label,
        "options": [{"id": item.id, "label": item.label} for item in field_options],
        "options_source": options_source,
        "exclude_answer": exclude_answer,
    }


def plan_builder(
    step_id: str,
    title: str,
    *fields: dict[str, Any],
    body: str = "Выбирай то, что реально проще использовать. План можно уточнять позже.",
) -> ProgramStep:
    return ProgramStep(
        step_id,
        "plan_builder",
        title,
        body,
        required=True,
        content={"fields": list(fields)},
    )


def choice(
    step_id: str,
    title: str,
    step_options: tuple[StepOption, ...] = (),
    *,
    body: str = "",
    options_source: str | None = None,
    step_type: str = "single_select",
    max_selections: int | None = None,
    reactions: dict[str, str] | None = None,
    branches: dict[str, str] | None = None,
    next_step_id: str | None = None,
) -> ProgramStep:
    return ProgramStep(
        step_id,
        step_type,
        title,
        body,
        options=step_options,
        required=True,
        max_selections=max_selections,
        options_source=options_source,
        content={"reactions": reactions or {}},
        branches=branches or {},
        next_step_id=next_step_id,
    )


def ordered(
    step_id: str,
    title: str,
    step_options: tuple[StepOption, ...],
    count: int,
) -> ProgramStep:
    return ProgramStep(
        step_id,
        "ordered_select",
        title,
        "Нажимай по порядку. Повторно выбранный пункт можно убрать.",
        options=step_options,
        required=True,
        max_selections=count,
        content={"selection_count": count},
    )


def comparison(
    step_id: str,
    title: str,
    *,
    items_source: str,
    scale: tuple[StepOption, ...],
    fallback_items: tuple[StepOption, ...],
) -> ProgramStep:
    return ProgramStep(
        step_id,
        "comparison",
        title,
        "Для каждого пункта выбери вариант, который ближе всего сейчас.",
        required=True,
        content={
            "items_source": items_source,
            "fallback_items": [
                {"id": item.id, "label": item.label} for item in fallback_items
            ],
            "scale": [{"id": item.id, "label": item.label} for item in scale],
        },
    )


def result(
    number: int,
    title: str,
    result_key: str,
    *items: tuple[str, str],
    style: str = "plan",
) -> ProgramStep:
    return ProgramStep(
        f"d{number}_result",
        "result_card",
        title,
        "Вот конкретный инструмент, который получился из твоих выборов.",
        content={
            "result_key": result_key,
            "style": style,
            "items": [{"answer": answer, "label": label} for answer, label in items],
        },
    )


def rebuild(base: ProgramDay, interactive: tuple[ProgramStep, ...]) -> ProgramDay:
    intro = next(step for step in base.steps if step.id.endswith("_intro"))
    theory = next(step for step in base.steps if step.type == "theory")
    context = next(
        (
            step
            for step in base.steps
            if step.type in {"personalized_insight", "checkpoint"}
        ),
        None,
    )
    task = next((step for step in base.steps if step.type == "task"), None)
    summary = next(
        (step for step in base.steps if step.id.endswith("_summary")), None
    )
    completion = base.steps[-1]
    steps = (intro, theory, *((context,) if context else ()), *interactive)
    if task:
        steps += (task,)
    if summary:
        steps += (summary,)
    steps += (completion,)
    return replace(base, steps=tuple(_with_response_config(step) for step in steps))


def _config_payload(config: Any) -> dict[str, Any]:
    return {
        "response_type": config.response_type,
        "allow_other": config.allow_other,
        "other_placeholder": config.placeholder,
        "response_context": config.context_id,
    }


def _with_response_config(step: ProgramStep) -> ProgramStep:
    content = dict(step.content)
    config = STEP_RESPONSE_CONFIG.get(step.id)
    if config:
        content.update(_config_payload(config))
    if step.type == "plan_builder":
        fields = []
        for field_item in content.get("fields", []):
            enriched = dict(field_item)
            field_config = FIELD_RESPONSE_CONFIG.get((step.id, str(field_item.get("id"))))
            if field_config:
                enriched.update(_config_payload(field_config))
            fields.append(enriched)
        content["fields"] = fields
    if step.type == "structured_input":
        fields = []
        for field_item in content.get("fields", []):
            enriched = dict(field_item)
            field_config = STRUCTURED_RESPONSE_CONFIG.get((step.id, str(field_item.get("id"))))
            if field_config:
                enriched.update(_config_payload(field_config))
            fields.append(enriched)
        content["fields"] = fields
    return replace(step, content=content)


LOOP_FIRST = opts(
    ("thought", "💭 Мысль «хочу никотин»"),
    ("tension", "😣 Напряжение"),
    ("automatic", "🤖 Действую почти автоматически"),
    ("break", "⏸ Хочется сделать перерыв"),
    ("boredom", "😑 Становится скучно"),
    ("join", "👥 Хочется присоединиться к другим"),
)

PAUSE_OPTIONS = opts(
    ("wait", "⏳ Дать себе 2 минуты"),
    ("change_place", "🚪 Сменить место"),
    ("water", "💧 Выпить воды"),
    ("breathing", "🌬 Сделать спокойное дыхание"),
    ("sos", "🆘 Открыть SOS"),
)


INTERACTIONS: dict[int, tuple[ProgramStep, ...]] = {
    2: (
        plan_builder(
            "personal_habit_loop",
            "Собери свою новую петлю",
            field("trigger", "С какой ситуации начнём?", options_source="profile:primary_triggers"),
            field("first_signal", "Что обычно появляется первым?", LOOP_FIRST),
            field("expected", "Что ожидаешь получить?", options_source="profile:nicotine_beliefs"),
            field("alternative", "Что поставим вместо последнего действия?", ACTIONS),
        ),
        result(
            2,
            "Твоя новая петля",
            "personal_habit_loop",
            ("personal_habit_loop.trigger", "Триггер"),
            ("personal_habit_loop.first_signal", "Первый сигнал"),
            ("personal_habit_loop.expected", "Ожидание"),
            ("personal_habit_loop.alternative", "Новое действие"),
        ),
    ),
    3: (
        choice(
            "usual_high_desire_response",
            "Представь желание 7/10. Что обычно произошло бы первым?",
            opts(
                ("use", "Сразу употребил бы"),
                ("distract", "Попробовал бы отвлечься"),
                ("wait", "Немного подождал бы"),
                ("sos", "Открыл бы SOS"),
                ("depends", "Зависит от ситуации"),
            ),
            reactions={
                "use": "Это привычная быстрая реакция. Сегодня добавим перед ней небольшой промежуток.",
                "distract": "У тебя уже есть попытка переключить сценарий — сделаем её конкретнее.",
                "wait": "Пауза уже появляется. Закрепим, что делать внутри неё.",
                "sos": "SOS уже стал доступным вариантом, а не последней мерой.",
                "depends": "Контекст действительно важен. Выберем минимальный шаг, доступный чаще всего.",
            },
        ),
        choice("pause_plan", "Что готов попробовать в следующий такой момент?", PAUSE_OPTIONS, step_type="action_picker"),
        result(
            3,
            "Моя пауза перед действием",
            "pause_plan",
            ("pause_plan", "Сначала"),
            ("static:wait_two", "Затем"),
            ("static:sos", "Если желание остаётся сильным"),
        ),
    ),
    4: (
        choice(
            "noticed_changes",
            "Что ты сейчас замечаешь?",
            opts(
                ("irritability", "😠 Раздражительность"),
                ("restlessness", "😟 Беспокойство"),
                ("focus", "🧠 Сложнее сосредоточиться"),
                ("sleep", "🌙 Изменился сон"),
                ("appetite", "🍽 Изменился аппетит"),
                ("desire", "⚡ Сильное желание"),
                ("fatigue", "😴 Усталость"),
                ("none", "Ничего из этого"),
            ),
            step_type="multi_select",
        ),
        choice("main_change", "Что сегодня мешает больше всего?", options_source="selected:noticed_changes", step_type="priority_select"),
        choice("change_response", "Какой шаг попробуешь сегодня?", ACTIONS, step_type="action_picker"),
        result(4, "Что попробую сегодня", "withdrawal_plan", ("main_change", "Главная сложность"), ("change_response", "Мой шаг")),
    ),
    5: (
        plan_builder(
            "trigger_plan",
            "План для главного триггера",
            field("first_action", "Что сделаешь первым?", ACTIONS),
            field("backup_action", "Если желание останется сильным?", ACTIONS, exclude_answer="first_action"),
            field("sos_threshold", "Когда сразу открывать SOS?", SOS_THRESHOLDS),
        ),
        result(5, "Твой план для сложной ситуации", "trigger_plan", ("context:primary_trigger", "Триггер"), ("trigger_plan.first_action", "Сначала"), ("trigger_plan.backup_action", "Запасной шаг"), ("trigger_plan.sos_threshold", "SOS")),
    ),
    6: (
        choice("automatic_trigger", "Какой ритуал работает наиболее автоматически?", options_source="profile:primary_triggers", step_type="priority_select"),
        choice("changed_routine", "Какое одно звено проще изменить?", opts(("different_place", "Сделать привычное действие в другом месте"), ("water_first", "Сначала выпить воды"), ("stand_up", "Сразу встать и сменить действие"), ("five_minutes", "Заменить первые 5 минут"), ("walk", "Сделать короткую прогулку")), step_type="action_picker"),
        result(6, "Редактор автопилота", "routine_change", ("automatic_trigger", "Было"), ("changed_routine", "Теперь попробуем")),
    ),
    7: (
        choice("week_one_challenge", "Что оказалось самым сложным?", options_source="analytics:challenge", step_type="priority_select"),
        choice("week_one_help", "Что пока помогало больше всего?", options_source="history:strategies", step_type="priority_select"),
        result(7, "Первая неделя AIR", "week_one_result", ("week_one_challenge", "Самая сложная ситуация"), ("week_one_help", "Что использовал")),
    ),
    8: (
        plan_builder(
            "relaxation_breakdown",
            "Разбери один эпизод",
            field("before", "Что было до?", opts(("stress", "😰 Стресс"), ("fatigue", "😴 Усталость"), ("irritation", "😠 Раздражение"), ("desire", "⚡ Сильное желание"), ("conflict", "💥 Конфликт"), ("normal", "Обычное состояние"))),
            field("after", "Что изменилось после?", opts(("calmer", "Стало спокойнее"), ("pause", "Появилась пауза"), ("urge_down", "Снизилось желание"), ("left", "Вышел из ситуации"), ("problem_stayed", "Проблема осталась"), ("unclear", "Не уверен"))),
            field("replacement", "Что полезного сохраним без никотина?", opts(("pause", "⏸ Паузу"), ("leave", "🚪 Выйти"), ("walk", "🚶 Пройтись"), ("breathing", "🌬 Дыхание"), ("talk", "💬 Поговорить"))),
        ),
        result(8, "Что сохраним без никотина", "relaxation_replacement", ("relaxation_breakdown.before", "До"), ("relaxation_breakdown.after", "После"), ("relaxation_breakdown.replacement", "Полезная часть"), style="comparison"),
    ),
    9: (
        choice("focus_context", "Когда никотин сильнее связан с концентрацией?", opts(("start", "Перед началом работы"), ("hard_task", "Сложная задача"), ("deadline", "Дедлайн"), ("fatigue", "Усталость"), ("break", "Перерыв"), ("return", "После отвлечения")), step_type="priority_select"),
        choice("focus_experiment_start", "Эксперимент: 20 минут одной задачи, затем обычный перерыв", opts(("start", "▶️ Начать эксперимент"), ("later", "Сохранить и попробовать позже")), reactions={"start": "Таймер не обязателен: выбери одну задачу и не меняй её до конца короткого цикла.", "later": "План сохранён без давления. Его можно проверить в удобный рабочий момент."}),
        choice("focus_experiment", "Как прошло?", opts(("much_worse", "Заметно хуже"), ("worse", "Немного хуже"), ("same", "Примерно так же"), ("better", "Немного лучше"), ("much_better", "Заметно лучше"), ("later", "Пока не пробовал"))),
        result(9, "Результат эксперимента", "focus_result", ("focus_context", "Контекст"), ("focus_experiment", "Наблюдение"), style="experiment"),
    ),
    10: (
        choice("pleasure_components", "Что именно было приятным? Выбери до трёх", opts(("sensation", "Вкус или ощущение"), ("pause", "Пауза"), ("social", "Общение"), ("outside", "Выход на улицу"), ("reward", "Чувство награды"), ("ritual", "Привычный ритуал"), ("relief", "Прекращение желания"), ("unknown", "Не знаю")), step_type="multi_select", max_selections=3),
        choice("pleasure_replacement", "Что хочешь сохранить в новой форме?", options_source="selected:pleasure_components", step_type="priority_select"),
        result(10, "Удовольствие без старого условия", "pleasure_plan", ("pleasure_components", "Из чего состояло"), ("pleasure_replacement", "Что сохраняю")),
    ),
}

INTERACTIONS.update(
    {
        11: (
            choice(
                "break_replacement",
                "Что должно быть в хорошем перерыве? Выбери два пункта",
                opts(
                    ("outside", "🌳 Выйти"),
                    ("walk", "🚶 Пройтись"),
                    ("water", "💧 Напиток"),
                    ("music", "🎵 Музыка"),
                    ("talk", "💬 Поговорить"),
                    ("window", "🪟 Посмотреть в окно"),
                    ("quiet", "📵 Посидеть без телефона"),
                ),
                step_type="ordered_select",
                max_selections=2,
            ),
            result(
                11,
                "Твой новый перерыв",
                "break_replacement",
                ("break_replacement", "Два элемента перерыва"),
            ),
        ),
        12: (
            plan_builder(
                "boredom_menu",
                "Собери меню от скуки",
                field("one_minute", "На 1 минуту", opts(("water", "💧 Вода"), ("stand", "Встать и сменить положение"), ("music", "🎵 Один трек"), ("stretch", "Короткая разминка"))),
                field("three_minutes", "На 3 минуты", opts(("walk", "🚶 Пройтись"), ("music", "🎵 Музыка"), ("small_task", "🧹 Маленькое дело"), ("message", "💬 Написать человеку"))),
                field("ten_minutes", "На 10 минут", opts(("outside", "🌳 Выйти на улицу"), ("walk", "🚶 Прогулка"), ("game", "🎮 Короткое занятие"), ("talk", "📞 Разговор"))),
            ),
            result(12, "Моё меню от скуки", "boredom_menu", ("boredom_menu.one_minute", "1 минута"), ("boredom_menu.three_minutes", "3 минуты"), ("boredom_menu.ten_minutes", "10 минут"), style="menu"),
        ),
        13: (
            ordered(
                "evening_ritual",
                "Выбери три действия в нужном порядке",
                opts(
                    ("shower", "🚿 Душ"),
                    ("water", "🍵 Чай или вода"),
                    ("music", "🎵 Музыка"),
                    ("book", "📖 Книга"),
                    ("air", "🪟 Проветрить"),
                    ("phone", "📵 Убрать телефон"),
                    ("walk", "🚶 Короткая прогулка"),
                    ("prepare", "🎒 Подготовить вещи на завтра"),
                ),
                3,
            ),
            result(13, "Твой вечерний сценарий", "evening_ritual", ("evening_ritual", "Порядок действий"), style="sequence"),
        ),
        14: (
            comparison(
                "trigger_comparison",
                "Как сейчас по сравнению с Днём 1?",
                items_source="profile:primary_triggers",
                fallback_items=opts(("stress", "Стресс"), ("coffee", "Кофе")),
                scale=opts(("much_easier", "Намного легче"), ("easier", "Немного легче"), ("same", "Примерно так же"), ("harder", "Сложнее"), ("unclear", "Пока не понимаю")),
            ),
            choice("belief_less_convincing", "Какое убеждение стало менее убедительным?", options_source="profile:nicotine_beliefs", step_type="priority_select"),
            result(14, "Что изменилось за две недели", "two_week_change", ("trigger_comparison", "Триггеры сейчас"), ("belief_less_convincing", "Убеждение для проверки"), style="comparison"),
        ),
        15: (
            plan_builder(
                "stress_plan",
                "Собери SOS-lite план",
                field("first_action", "Что используешь первым?", ACTIONS),
                field("backup_action", "Что будет запасным вариантом?", ACTIONS, exclude_answer="first_action"),
                field("sos_threshold", "Когда сразу открывать SOS?", SOS_THRESHOLDS),
            ),
            result(15, "Мой стресс-план", "stress_plan", ("stress_plan.first_action", "1. Сначала"), ("stress_plan.backup_action", "2. Запасной вариант"), ("stress_plan.sos_threshold", "3. SOS")),
        ),
        16: (
            plan_builder(
                "emotion_need_action",
                "Эмоция → потребность → действие",
                field("emotion", "Что чаще выводит из равновесия?", opts(("anger", "😠 Злость"), ("irritation", "😤 Раздражение"), ("fatigue", "😴 Усталость"), ("anxiety", "😟 Тревога"), ("sadness", "😔 Грусть"), ("tension", "😣 Напряжение"))),
                field("need", "Что обычно нужно в такой момент?", opts(("pause", "⏸ Пауза"), ("alone", "🚪 Побыть одному"), ("talk", "💬 Поговорить"), ("movement", "🚶 Движение"), ("rest", "🛋 Отдых"), ("solve", "🧩 Решить проблему"))),
                field("action", "Какой первый шаг подходит?", ACTIONS),
            ),
            result(16, "Мой ответ на эмоцию", "emotion_need_action", ("emotion_need_action.emotion", "Эмоция"), ("emotion_need_action.need", "Мне нужно"), ("emotion_need_action.action", "Первый шаг")),
        ),
        17: (
            choice("social_first_reply", "Кто-то предлагает тебе никотин. Что отвечаешь?", opts(("now_free", "«Нет, я сейчас без никотина»"), ("quit", "«Я отказался»"), ("dont_want", "«Не хочу»"), ("later", "«Потом»"), ("gesture", "Просто отказаться жестом")), step_type="scenario_choice", reactions={"later": "Такой ответ оставляет предложение открытым. Следующий шаг поможет сделать границу яснее.", "gesture": "Короткий жест может быть достаточным, если тебе комфортно не объяснять решение."}),
            choice("social_second_reply", "В ответ слышишь: «Да ладно, один раз». Что дальше?", opts(("really_no", "«Нет, правда не хочу»"), ("decision", "«Я решил не употреблять»"), ("change_topic", "Сменить тему"), ("leave", "Уйти к другим людям")), step_type="scenario_choice"),
            result(17, "Моя фраза", "social_response", ("social_first_reply", "Первый ответ"), ("social_second_reply", "Если продолжают уговаривать"), style="dialogue"),
        ),
        18: (
            plan_builder(
                "evening_plan",
                "План риск-ситуации",
                field("risk", "Что делает ситуацию сложной?", opts(("control", "Меньше контроля"), ("company", "Компания"), ("ritual", "Привычный ритуал"), ("nearby", "Рядом употребляют"), ("outside", "Хочется выйти со всеми"), ("desire", "Сильнее желание"))),
                field("offer_response", "Если предложат, что сделаешь?", opts(("short_no", "Коротко откажусь"), ("change_topic", "Сменю тему"), ("leave", "Отойду"), ("contact", "Напишу человеку"), ("sos", "Открою SOS"))),
                field("sos_threshold", "Когда открыть SOS?", opts(("first", "При первом желании"), ("5", "При 5+"), ("7", "При 7+"), ("agree", "Когда почувствую, что могу согласиться"))),
                field("exit", "Если становится слишком сложно?", opts(("change_place", "Сменить место"), ("short_leave", "Уйти ненадолго"), ("contact", "Написать человеку"), ("home", "Уйти домой"), ("sos", "Открыть SOS"))),
            ),
            result(18, "План сложного вечера", "evening_plan", ("evening_plan.risk", "Главный риск"), ("evening_plan.offer_response", "Если предложат"), ("evening_plan.sos_threshold", "SOS"), ("evening_plan.exit", "Если слишком сложно")),
        ),
        19: (
            plan_builder(
                "after_meal_plan",
                "Измени продолжение после еды",
                field("usual", "Что обычно происходит?", opts(("automatic", "Автоматически хочется никотина"), ("outside", "Хочется выйти"), ("mouth", "Хочется чем-то занять рот"), ("habit", "Просто привычка"), ("pause", "Желание сделать паузу"))),
                field("new_action", "Что поставим сразу после еды?", opts(("clean", "🍽 Встать и убрать"), ("brush", "🪥 Почистить зубы"), ("water", "💧 Выпить воды"), ("walk", "🚶 Короткая прогулка"), ("other_place", "🚪 Перейти в другое место"))),
            ),
            result(19, "Новый сценарий после еды", "after_meal_plan", ("after_meal_plan.usual", "Было"), ("after_meal_plan.new_action", "Теперь"), style="before_after"),
        ),
        20: (
            choice("movement_switch", "Что ты реально готов сделать при желании?", opts(("walk_3", "🚶 3 минуты ходьбы"), ("walk_5", "🚶 5 минут ходьбы"), ("stairs", "🪜 Пройти по лестнице"), ("stretch", "🤸 Короткая разминка"), ("outside", "🌳 Выйти на воздух")), step_type="action_picker"),
            choice("movement_try_now", "Попробовать сейчас?", opts(("now", "▶️ Да, попробовать"), ("later", "Сохранить на потом")), reactions={"now": "Сделай выбранное движение, затем просто оцени, стало ли желание другим.", "later": "Стратегия сохранена без принуждения. Она будет доступна в будущей поддержке."}),
            choice("movement_effect", "Что изменилось?", opts(("lower", "Желание стало слабее"), ("same", "Осталось примерно тем же"), ("different", "Стало ощущаться иначе"), ("later", "Пока не пробовал"))),
            result(20, "Мой переключатель", "movement_result", ("movement_switch", "Движение"), ("movement_effect", "Наблюдение"), style="experiment"),
        ),
        21: (
            comparison(
                "belief_reassessment",
                "Как ты воспринимаешь свои убеждения сейчас?",
                items_source="profile:nicotine_beliefs",
                fallback_items=opts(("habit", "Это просто привычка"), ("relax", "Помогает расслабиться")),
                scale=opts(("agree", "Полностью согласен"), ("mostly", "Скорее согласен"), ("unsure", "Уже не уверен"), ("mostly_not", "Скорее не согласен"), ("not", "Больше не согласен")),
            ),
            result(21, "Твоя новая карта убеждений", "belief_reassessment", ("belief_reassessment", "Раньше → сейчас"), style="comparison"),
        ),
    }
)

INTERACTIONS.update(
    {
        22: (
            choice(
                "one_time_first",
                "Возникает мысль: «Наверное, один раз уже можно». Что делаешь?",
                opts(("agree", "Согласиться с мыслью"), ("sos", "🆘 Открыть SOS"), ("wait", "⏳ Подождать 5 минут"), ("leave", "🚪 Сменить ситуацию"), ("reason", "🎯 Вспомнить причину отказа")),
                step_type="scenario_choice",
                reactions={
                    "agree": "Этот вариант быстро возвращает старое действие. Посмотрим, что можно сделать до продолжения.",
                    "sos": "Ты добавляешь поддержку до того, как мысль превратилась в действие.",
                    "wait": "Пауза не спорит с мыслью, но даёт время выбрать следующий шаг.",
                    "leave": "Смена контекста уменьшает количество старых подсказок вокруг.",
                    "reason": "Твоя причина помогает не принимать то же решение заново.",
                },
                branches={"agree": "one_time_risk_followup", "sos": "one_time_coping_followup", "wait": "one_time_coping_followup", "leave": "one_time_coping_followup", "reason": "one_time_coping_followup"},
            ),
            choice("one_time_risk_followup", "До следующего действия ещё есть момент. Что выберешь сейчас?", ACTIONS, step_type="scenario_choice", next_step_id="d22_result"),
            choice("one_time_coping_followup", "Через минуту желание всё ещё есть. Что дальше?", ACTIONS, step_type="scenario_choice", next_step_id="d22_result"),
            result(22, "Мой план «один раз»", "one_time_plan", ("one_time_first", "Первая реакция"), ("coalesce:one_time_risk_followup,one_time_coping_followup", "Следующий шаг")),
        ),
        23: (
            choice("post_lapse_thought", "Ты всё-таки употребил никотин один раз. Что происходит в голове?", opts(("lost", "«Всё пропало»"), ("continue", "«Раз уж начал, продолжу»"), ("more", "«Ничего страшного, можно ещё»"), ("stop", "«Нужно остановиться сейчас»")), step_type="scenario_choice", reactions={"lost": "Эта мысль превращает один эпизод в оценку всего пути. Но следующие решения ещё не приняты.", "continue": "Продолжение — отдельное решение, а не неизбежное следствие первого эпизода.", "more": "Следующее исключение может снова усилить старый сценарий. Между эпизодами остаётся точка выбора.", "stop": "Ты замечаешь точку, где один эпизод ещё можно не превращать в продолжение."}),
            choice("post_lapse_choice", "Какое следующее действие полезнее?", opts(("continue", "Продолжить употребление"), ("hide", "Скрыть эпизод"), ("log", "Зафиксировать в AIR"), ("restart_day_one", "Начать программу заново с Дня 1"), ("log_restart", "Зафиксировать и решить, когда начать новый отсчёт")), step_type="scenario_choice", reactions={"continue": "Этот вариант оставляет старую цепочку активной. AIR сохраняет возможность остановиться сейчас.", "hide": "Без записи сложнее увидеть триггер. История AIR не осуждает и не сбрасывает программу.", "log": "Фиксация сохраняет факт и позволяет спокойно разобрать контекст.", "restart_day_one": "Пройденные знания не нужно стирать: программа продолжается с текущего дня.", "log_restart": "Так эпизод становится данными, а новый отсчёт остаётся отдельным решением."}),
            result(23, "Как AIR работает после эпизода", "post_lapse_plan", ("static:lapse", "Событие"), ("post_lapse_choice", "Следующий шаг"), ("static:program_continues", "Программа"), style="sequence"),
        ),
        24: (
            plan_builder(
                "lapse_analysis",
                "Разбор без оценки себя",
                field("main_factor", "Что сыграло главную роль?", opts(("desire", "Сильное желание"), ("stress", "Стресс"), ("social", "Компания"), ("alcohol", "Алкоголь"), ("automatic", "Автоматический ритуал"), ("one_time", "Мысль «один раз»"), ("no_plan", "Не использовал план или SOS"))),
                field("next_action", "Что изменить в похожей ситуации?", ACTIONS),
            ),
            result(24, "Что я попробую в следующий раз", "lapse_analysis", ("context:lapse_or_simulation", "Основа разбора"), ("lapse_analysis.main_factor", "Главный фактор"), ("lapse_analysis.next_action", "Следующий шаг")),
        ),
        25: (
            choice("unexpected_feature", "Что больше всего удивляет в таких моментах?", opts(("strength", "Сила желания"), ("situation", "Сама ситуация"), ("returned", "Что желание вернулось спустя время"), ("should_pass", "Мысль «уже должно было пройти»"), ("nothing", "Ничего")), step_type="priority_select"),
            choice("unexpected_desire_response", "Что сделаем, если это повторится?", ACTIONS, step_type="action_picker"),
            result(25, "План на неожиданное желание", "unexpected_desire_plan", ("context:rare_trigger", "Необычный сигнал"), ("unexpected_feature", "Что удивляет"), ("unexpected_desire_response", "Первый шаг")),
        ),
        26: (
            plan_builder(
                "state_need_action",
                "Состояние → потребность → действие",
                field("state", "Какое состояние ближе?", opts(("tired", "😴 Устал"), ("angry", "😠 Злюсь"), ("stress", "😰 Стресс"), ("bored", "😑 Скучно"), ("sad", "😔 Грустно"), ("lonely", "👤 Одиноко"))),
                field("need", "Что тебе сейчас скорее нужно?", opts(("rest", "Отдых"), ("pause", "Пауза"), ("talk", "Разговор"), ("movement", "Движение"), ("food", "Еда"), ("solve", "Решить конкретную проблему"), ("change", "Сменить обстановку"))),
                field("action", "Какой первый шаг выберешь?", ACTIONS),
            ),
            result(26, "Что мне сейчас нужно", "state_need_action", ("state_need_action.state", "Состояние"), ("state_need_action.need", "Потребность"), ("state_need_action.action", "Первый шаг")),
        ),
        27: (
            choice("scenario_decision_one", "Ты в сложной ситуации, желание 6/10. Что делаешь первым?", ACTIONS, step_type="scenario_choice", reactions={"sos": "Ты подключаешь поддержку до пика желания.", "walk": "Смена места даёт дополнительное время перед решением."}),
            choice("scenario_decision_two", "Через 10 минут тебе предлагают никотин. Что отвечаешь?", opts(("short_no", "Коротко отказаться"), ("explain", "Объяснить своё решение"), ("later", "Сказать «потом»"), ("leave", "Отойти к другим людям"), ("accept", "Согласиться")), step_type="scenario_choice", reactions={"later": "Ответ оставляет предложение открытым. Более ясная граница может уменьшить повторные уговоры.", "accept": "Этот вариант возвращает старое действие, но следующий выбор всё ещё можно изменить."}),
            choice("scenario_decision_three", "Желание выросло до 8/10. Какой следующий шаг?", ACTIONS, step_type="scenario_choice"),
            result(27, "Твой маршрут", "complex_scenario", ("context:risk_scenario", "Ситуация"), ("scenario_decision_one", "Решение 1"), ("scenario_decision_two", "Решение 2"), ("scenario_decision_three", "Решение 3"), style="scenario"),
        ),
        28: (
            choice("warning_signs", "Какие ранние сигналы могут появиться? Выбери до четырёх", opts(("stop_logging", "Перестаю отмечать желания"), ("stop_sos", "Перестаю использовать SOS"), ("one_time", "Чаще думаю «один раз можно»"), ("stress", "Сильный стресс"), ("alcohol", "Алкоголь"), ("nearby", "Чаще нахожусь рядом с никотином"), ("sleep", "Хуже сплю"), ("control", "Думаю, что полностью всё контролирую")), step_type="multi_select", max_selections=4),
            choice("warning_priority", "Какой сигнал обычно появляется раньше остальных?", options_source="selected:warning_signs", step_type="priority_select"),
            choice("warning_response", "Что можно сделать уже на этом этапе?", ACTIONS, step_type="action_picker"),
            result(28, "Мой ранний сигнал", "warning_plan", ("warning_priority", "Ранний сигнал"), ("warning_response", "Ранний ответ")),
        ),
        29: (
            ProgramStep(
                "protection_plan",
                "structured_input",
                "Проверь и дополни свой план",
                "AIR собрал доступные стратегии. Можно оставить их, сократить или заменить своими словами.",
                required=False,
                content={"prefill_source": "protection_plan", "fields": [
                    {"id": "strong_desire", "label": "Если желание сильное", "placeholder": "Первый и запасной шаг"},
                    {"id": "stress", "label": "Если стресс", "placeholder": "Мой короткий маршрут"},
                    {"id": "social", "label": "Если предлагают", "placeholder": "Фраза и действие"},
                    {"id": "one_time", "label": "Если думаю «один раз»", "placeholder": "Первые пять минут"},
                    {"id": "lapse", "label": "Если был эпизод", "placeholder": "Как остановлю продолжение"},
                ]},
            ),
            comparison(
                "protection_plan_review",
                "Проверь собранные AIR планы",
                items_source="history:plan_sections",
                fallback_items=opts(("sos", "При сильном желании — SOS"), ("trigger", "План главного триггера")),
                scale=opts(("keep", "Оставить"), ("replace", "Заменить готовой альтернативой")),
            ),
            choice("protection_replacement", "Если что-то хочется заменить, выбери универсальную альтернативу", ACTIONS, step_type="action_picker"),
            result(29, "Мой план AIR", "protection_plan", ("protection_plan", "Мой план"), ("protection_plan_review", "Проверка"), ("protection_replacement", "Запасная альтернатива"), style="protection"),
        ),
        30: (
            choice("final_change", "Что изменилось за эти 30 дней?", opts(("understand_triggers", "Я лучше понимаю свои триггеры"), ("manage_craving", "Мне легче проходить тягу"), ("working_switches", "Я нашёл рабочие способы переключаться"), ("confident_free", "Я увереннее чувствую себя без никотина"), ("hard_moments", "Я научился проходить сложные моменты"), ("understand_dependence", "Я лучше понимаю свою зависимость")), step_type="multi_select", max_selections=6),
            choice("keep_next", "Что хочешь сохранить дальше?", opts(("use_sos", "Использовать SOS при сильной тяге"), ("use_personal_plan", "Пользоваться своим планом"), ("notice_triggers", "Продолжать замечать триггеры"), ("watch_progress", "Следить за прогрессом"), ("return_techniques", "Возвращаться к рабочим техникам")), step_type="multi_select", max_selections=5),
            choice("most_useful_strategy", "Какая стратегия оказалась самой полезной?", options_source="history:strategies", step_type="priority_select"),
            result(30, "Что я сохраняю после программы", "final_rule", ("final_change", "Что изменилось"), ("keep_next", "Что сохраняю"), ("most_useful_strategy", "Полезная стратегия")),
        ),
    }
)


def apply_interactive_content(days: tuple[ProgramDay, ...]) -> tuple[ProgramDay, ...]:
    return tuple(
        rebuild(day, INTERACTIONS[day.number])
        if day.number in INTERACTIONS
        else replace(day, steps=tuple(_with_response_config(step) for step in day.steps))
        for day in days
    )
