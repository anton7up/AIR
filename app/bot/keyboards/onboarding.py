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
    button = (
        InlineKeyboardButton(text="Открыть AIR", web_app=WebAppInfo(url=mini_app_url))
        if mini_app_url
        else InlineKeyboardButton(text="Открыть AIR", callback_data="mini_app:not_ready")
    )
    return InlineKeyboardMarkup(inline_keyboard=[[button]])


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
