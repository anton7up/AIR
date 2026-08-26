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

