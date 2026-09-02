from decimal import Decimal

WELCOME = (
    "Привет, {first_name}! Я AIR. Помогу спокойно разобраться с привычкой "
    "и постепенно двигаться к жизни без никотина. Для начала отвечай на несколько вопросов."
)

PERSONAL_DATA_CONSENT = (
    "Перед началом\n\n"
    "AIR использует твои ответы, чтобы персонализировать программу,\n"
    "отслеживать прогресс и подбирать поддержку в моменты тяги к никотину.\n\n"
    "Подробнее: Согласие на обработку персональных данных"
)

PERSONAL_DATA_CONSENT_DECLINED = (
    "Без согласия на обработку персональных данных\n"
    "AIR не сможет персонализировать программу.\n\n"
    "Ты можешь вернуться и изменить решение."
)

ONBOARDING_RESUME = (
    "Мы уже начали знакомство с тобой.\n"
    "Что хочешь сделать?"
)

ONBOARDING_RESTART_CONFIRMATION = (
    "Начать знакомство сначала?\n\n"
    "Текущие ответы незавершённой анкеты будут сброшены. "
    "Программа и прогресс AIR не изменятся."
)

RETURNING_USER = (
    "С возвращением в AIR.\n"
    "Твоя программа и прогресс сохранены."
)

REPEAT_ONBOARDING_CONFIRMATION = (
    "Ты можешь пройти вводную анкету заново.\n"
    "Это обновит твой профиль, но не сбросит прогресс программы,\n"
    "подписку и историю AIR."
)

EDIT_PROFILE_CONFIRMATION = (
    "Изменить информацию\n\n"
    "Ты можешь заново пройти короткую анкету.\n"
    "Мы обновим твои ответы, но прогресс программы\n"
    "и доступ к AIR сохранятся."
)

INVALID_CHOICE = "Пожалуйста, выбери один из вариантов с помощью кнопок."


def format_money(value: Decimal) -> str:
    return f"{int(value.quantize(Decimal('1'))):,}".replace(",", " ") + " ₽"


def purchase_examples(amount: Decimal) -> str:
    value = int(amount)
    examples: list[str] = []
    if value >= 100_000:
        examples.append("хороший ноутбук или большой отпуск")
    elif value >= 30_000:
        examples.append("небольшое путешествие или полезный курс")
    else:
        examples.append("приятные покупки, отдых или новое увлечение")
    if value >= 500_000:
        examples.append("первоначальный взнос на крупную покупку")
    return "Например: " + "; ".join(examples) + "."


def result_message(monthly: Decimal, yearly: Decimal, lifetime: Decimal, five_year: Decimal) -> str:
    return (
        f"За всё время на никотин ушло примерно <b>{format_money(lifetime)}</b>.\n\n"
        f"{purchase_examples(lifetime)}\n\n"
        "Эти деньги уже в прошлом — переживать об этом не нужно. Намного важнее то, "
        "сколько ты можешь сохранить в будущем. AIR поможет тебе постепенно отказаться "
        "от никотина и начать двигаться дальше.\n\n"
        f"Сейчас это около <b>{format_money(monthly)}</b> в месяц и "
        f"<b>{format_money(yearly)}</b> в год.\n\n"
        f"При текущем темпе за следующие 5 лет на никотин может уйти ещё примерно "
        f"<b>{format_money(five_year)}</b>."
    )

MINI_APP_NOT_READY = "Mini App скоро появится. Твой результат уже сохранён в AIR."
