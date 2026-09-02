from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from app.onboarding.schema import Question


def choices_keyboard(question: Question) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=option.label, callback_data=f"answer:{question.key}:{index}")]
            for index, option in enumerate(question.options)
        ]
    )


def open_air_keyboard(mini_app_url: str | None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[_open_air_button(mini_app_url)]])


def _open_air_button(mini_app_url: str | None) -> InlineKeyboardButton:
    return (
        InlineKeyboardButton(text="Открыть AIR", web_app=WebAppInfo(url=mini_app_url))
        if mini_app_url
        else InlineKeyboardButton(text="Открыть AIR", callback_data="mini_app:not_ready")
    )


def onboarding_resume_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Продолжить знакомство",
                    callback_data="onboarding:continue",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Начать сначала",
                    callback_data="onboarding:restart_request",
                )
            ],
        ]
    )


def onboarding_restart_confirmation_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Начать сначала",
                    callback_data="onboarding:restart_confirm",
                )
            ],
            [InlineKeyboardButton(text="Отмена", callback_data="onboarding:restart_cancel")],
        ]
    )


def returning_user_keyboard(mini_app_url: str | None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_open_air_button(mini_app_url)],
            [
                InlineKeyboardButton(
                    text="Изменить ответы знакомства",
                    callback_data="onboarding:repeat_request",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Поддержка",
                    callback_data="onboarding:open_support",
                )
            ],
        ]
    )


def repeat_onboarding_confirmation_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Пройти анкету заново",
                    callback_data="onboarding:repeat_confirm",
                )
            ],
            [InlineKeyboardButton(text="Отмена", callback_data="onboarding:repeat_cancel")],
        ]
    )


def consent_keyboard(document_url: str | None) -> InlineKeyboardMarkup:
    document_button = (
        InlineKeyboardButton(
            text="Согласие на обработку персональных данных",
            url=document_url,
        )
        if document_url
        else InlineKeyboardButton(
            text="Согласие на обработку персональных данных",
            callback_data="consent:document_unavailable",
        )
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [document_button],
            [InlineKeyboardButton(text="Согласен", callback_data="consent:accept")],
            [InlineKeyboardButton(text="Не согласен", callback_data="consent:decline")],
        ]
    )


def consent_declined_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Вернуться", callback_data="consent:return")],
            [InlineKeyboardButton(text="Закрыть", callback_data="consent:close")],
        ]
    )
