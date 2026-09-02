from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def support_intro_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Написать сообщение", callback_data="support:write"
                )
            ],
            [InlineKeyboardButton(text="Отмена", callback_data="support:cancel")],
        ]
    )


def active_ticket_keyboard(ticket_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Продолжить обращение",
                    callback_data=f"support:user_reply:{ticket_id}",
                )
            ],
            [InlineKeyboardButton(text="Отмена", callback_data="support:cancel")],
        ]
    )


def admin_ticket_keyboard(ticket_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Ответить",
                    callback_data=f"support:admin_reply:{ticket_id}",
                ),
                InlineKeyboardButton(
                    text="Закрыть",
                    callback_data=f"support:admin_close:{ticket_id}",
                ),
            ]
        ]
    )


def user_reply_keyboard(ticket_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Ответить в поддержку",
                    callback_data=f"support:user_reply:{ticket_id}",
                )
            ]
        ]
    )
