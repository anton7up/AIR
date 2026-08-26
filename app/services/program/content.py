from app.services.program.day_01 import DAY_01
from app.services.program.days_02_07 import DAYS_02_07
from app.services.program.days_08_14 import DAYS_08_14
from app.services.program.days_15_21 import DAYS_15_21
from app.services.program.days_22_30 import DAYS_22_30
from app.services.program.interactive_content import apply_interactive_content
from app.services.program.labels import register_program_labels
from app.services.program.schema import ProgramDay, StepOption

PROGRAM_LENGTH = 30
ALL_PROGRAM_DAYS = apply_interactive_content(
    (DAY_01, *DAYS_02_07, *DAYS_08_14, *DAYS_15_21, *DAYS_22_30)
)
PROGRAM_DAYS: dict[int, ProgramDay] = {day.number: day for day in ALL_PROGRAM_DAYS}
register_program_labels(ALL_PROGRAM_DAYS)

QUIT_REASONS = (
    StepOption("health", "❤️ Здоровье"),
    StepOption("money", "💰 Деньги"),
    StepOption("sport", "🏃 Спорт и физическая форма"),
    StepOption("appearance", "✨ Внешность"),
    StepOption("family", "👨‍👩‍👧 Семья / отношения"),
    StepOption("freedom", "🕊 Свобода от зависимости"),
    StepOption("tired", "😤 Просто надоело зависеть"),
    StepOption("control", "🧠 Хочу лучше себя контролировать"),
    StepOption("other", "➕ Другое"),
)

TRIGGER_OPTIONS = (
    StepOption("morning", "☀️ После пробуждения"),
    StepOption("coffee", "☕ С кофе"),
    StepOption("after_meal", "🍽 После еды"),
    StepOption("work_study", "💻 Работа / учёба"),
    StepOption("stress", "😰 Когда нервничаю"),
    StepOption("boredom", "😑 Когда скучно"),
    StepOption("alcohol", "🍺 С алкоголем"),
    StepOption("social", "👥 В компании"),
    StepOption("before_sleep", "🌙 Перед сном"),
    StepOption("driving", "🚗 За рулём / в дороге"),
    StepOption("entertainment", "🎮 Игры / отдых"),
    StepOption("other", "➕ Другое"),
)

NICOTINE_BELIEFS = (
    StepOption("relax", "🧘 Помогает расслабиться"),
    StepOption("focus", "🧠 Помогает сосредоточиться"),
    StepOption("stress_relief", "😌 Снимает стресс"),
    StepOption("pleasure", "😊 Даёт удовольствие"),
    StepOption("break", "⏸ Даёт повод сделать перерыв"),
    StepOption("socialize", "👥 Помогает общаться"),
    StepOption("boredom", "😑 Спасает от скуки"),
    StepOption("energy", "⚡ Бодрит / даёт энергию"),
    StepOption("habit", "🔁 Это просто привычка"),
    StepOption("unknown", "🤷 Уже сам не знаю"),
    StepOption("other", "➕ Другое"),
)

QUIT_CONCERNS = (
    StepOption("strong_desire", "Сильное желание никотина"),
    StepOption("irritability", "Раздражительность"),
    StepOption("stress", "Стресс"),
    StepOption("concentration", "Проблемы с концентрацией"),
    StepOption("boredom", "Скука"),
    StepOption("alcohol", "Алкоголь / вечеринки"),
    StepOption("social", "Компания людей, которые употребляют никотин"),
    StepOption("weight", "Набор веса"),
    StepOption("lapse_fear", "Страх сорваться"),
    StepOption("identity", "Не представляю жизнь без никотина"),
    StepOption("other", "Другое"),
)

EMOTIONS = (
    StepOption("tension", "Напряжение"),
    StepOption("boredom", "Скука"),
    StepOption("irritation", "Раздражение"),
    StepOption("sadness", "Грусть"),
    StepOption("fatigue", "Усталость"),
    StepOption("neutral", "Всё нормально"),
    StepOption("other", "Другое"),
)

TRIGGER_CARDS: dict[str, dict[str, str]] = {
    option.id: {
        "id": option.id,
        "title": option.label,
        "short_explanation": "Эта ситуация могла стать привычным сигналом к никотину.",
        "why_it_happens": "Когда ситуация и никотин много раз повторяются вместе, мозг может связать их в один сценарий.",
        "first_tip": "Мы будем менять именно эту связку, сохраняя важные для тебя части привычного дня.",
    }
    for option in TRIGGER_OPTIONS
}
TRIGGER_CARDS["coffee"] |= {
    "why_it_happens": "Если кофе и никотин много раз шли вместе, они могли превратиться в один привычный сценарий.",
    "first_tip": "Не обязательно отказываться от кофе. Позже мы изменим связку «кофе → никотин».",
}
TRIGGER_CARDS["stress"] |= {
    "why_it_happens": "Мозг мог запомнить последовательность «стресс → никотин».",
    "first_tip": "В AIR мы постепенно найдём другие способы проходить напряжение без автоматической реакции.",
}
TRIGGER_CARDS["social"] |= {
    "why_it_happens": "Никотин может быть связан не только с веществом, но и с ритуалом общения и перерыва.",
    "first_tip": "Наша задача — сохранить общение, но отделить его от никотина.",
}

REASON_MOTIVATION = {
    "sport": "В первый день ты выбрал спорт одной из главных причин. Сейчас нужно пройти только этот конкретный момент.",
    "money": "Ты решил перестать регулярно отдавать деньги зависимости. Это решение всё ещё с тобой.",
    "freedom": "Ты говорил, что устал подстраивать день под никотин. Сейчас ты возвращаешь себе свободу выбора.",
    "default": "В первый день ты сохранил важную причину отказа. Сейчас не нужно принимать решение заново.",
}


def get_program_day(number: int) -> ProgramDay | None:
    return PROGRAM_DAYS.get(number)
