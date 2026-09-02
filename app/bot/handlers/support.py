from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, ForceReply, Message

from app.bot.keyboards.support import active_ticket_keyboard, support_intro_keyboard
from app.bot.states.support import SupportStates
from app.bot.texts.support import (
    SUPPORT_ALREADY_OPEN,
    SUPPORT_CLOSED_USER,
    SUPPORT_INTRO,
    SUPPORT_PROMPT,
    SUPPORT_SENT,
    SUPPORT_UNAVAILABLE,
)
from app.core.config import Settings, get_settings
from app.db.models import SupportSenderType, User
from app.db.session import session_factory
from app.services.consent import get_or_create_telegram_user
from app.services.support_delivery import (
    SupportConfigurationError,
    admin_is_authorized,
    send_admin_reply_to_user,
    send_ticket_to_admin,
    support_admin_chat_id,
)
from app.services.support_tickets import support_ticket_service

router = Router(name="support")
logger = logging.getLogger(__name__)


@router.message(
    Command("chatid"),
    F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}),
)
async def chat_id_command(message: Message) -> None:
    await message.answer(f"Chat ID: {message.chat.id}")


def callback_ticket_id(data: str | None, prefix: str) -> int | None:
    if not data or not data.startswith(prefix):
        return None
    try:
        ticket_id = int(data.removeprefix(prefix))
    except ValueError:
        return None
    return ticket_id if ticket_id > 0 else None


def configured_settings() -> Settings | None:
    settings = get_settings()
    try:
        support_admin_chat_id(settings)
    except SupportConfigurationError:
        return None
    return settings


async def open_support_flow(message: Message, state: FSMContext) -> None:
    await state.clear()
    if configured_settings() is None:
        await message.answer(SUPPORT_UNAVAILABLE)
        return
    telegram_user = message.from_user
    if telegram_user is None:
        await message.answer(SUPPORT_UNAVAILABLE)
        return
    async with session_factory() as session:
        user = await get_or_create_telegram_user(
            session,
            telegram_id=telegram_user.id,
            first_name=telegram_user.first_name,
            username=telegram_user.username,
        )
        active_ticket = await support_ticket_service.active_ticket(session, user.id)
        await session.commit()
    if active_ticket is not None:
        await message.answer(
            SUPPORT_ALREADY_OPEN,
            reply_markup=active_ticket_keyboard(active_ticket.id),
        )
        return
    await message.answer(SUPPORT_INTRO, reply_markup=support_intro_keyboard())


@router.message(Command("support"))
async def support_command(message: Message, state: FSMContext) -> None:
    await open_support_flow(message, state)


@router.message(F.text.regexp(r"^/start(?:@\w+)?\s+support$"))
async def support_deep_link(message: Message, state: FSMContext) -> None:
    await open_support_flow(message, state)


@router.callback_query(F.data == "support:write")
async def start_support_message(callback: CallbackQuery, state: FSMContext) -> None:
    if configured_settings() is None:
        await callback.answer(SUPPORT_UNAVAILABLE, show_alert=True)
        return
    await state.set_state(SupportStates.waiting_user_message)
    await state.update_data(support_ticket_id=None)
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(SUPPORT_PROMPT)


@router.callback_query(F.data == "support:cancel")
async def cancel_support(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer("Отменено")
    if isinstance(callback.message, Message):
        await callback.message.edit_reply_markup(reply_markup=None)


@router.callback_query(F.data.startswith("support:user_reply:"))
async def continue_support(callback: CallbackQuery, state: FSMContext) -> None:
    ticket_id = callback_ticket_id(callback.data, "support:user_reply:")
    if ticket_id is None or callback.from_user is None:
        await callback.answer("Обращение не найдено", show_alert=True)
        return
    async with session_factory() as session:
        ticket = await support_ticket_service.get_active_ticket(session, ticket_id)
        user = await session.get(User, ticket.user_id) if ticket else None
        if user is None or user.telegram_id != callback.from_user.id:
            await callback.answer("Обращение недоступно", show_alert=True)
            return
    await state.set_state(SupportStates.waiting_user_message)
    await state.update_data(support_ticket_id=ticket_id)
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.answer(SUPPORT_PROMPT)


@router.message(SupportStates.waiting_user_message)
async def receive_support_message(
    message: Message, state: FSMContext, bot: Bot
) -> None:
    settings = configured_settings()
    if settings is None:
        await message.answer(SUPPORT_UNAVAILABLE)
        return
    if message.from_user is None or not message.text or not message.text.strip():
        await message.answer("Отправь, пожалуйста, одно текстовое сообщение.")
        return
    text = message.text.strip()
    state_data = await state.get_data()
    requested_ticket_id = state_data.get("support_ticket_id")
    try:
        async with session_factory() as session:
            user = await get_or_create_telegram_user(
                session,
                telegram_id=message.from_user.id,
                first_name=message.from_user.first_name,
                username=message.from_user.username,
            )
            ticket = None
            if isinstance(requested_ticket_id, int):
                ticket = await support_ticket_service.get_active_ticket(
                    session, requested_ticket_id
                )
                if ticket is not None and ticket.user_id != user.id:
                    ticket = None
            if ticket is None:
                ticket = await support_ticket_service.active_ticket(session, user.id)
            continuation = ticket is not None
            if ticket is None:
                ticket = await support_ticket_service.create_ticket(session, user.id)
            await support_ticket_service.add_message(
                session, ticket, SupportSenderType.USER, text
            )
            access = await support_ticket_service.access_summary(
                session, user, settings
            )
            await send_ticket_to_admin(
                bot,
                settings,
                ticket,
                user,
                access,
                text,
                continuation=continuation,
            )
            await session.commit()
    except (SupportConfigurationError, TelegramAPIError):
        logger.exception("Unable to deliver AIR support ticket to admin chat")
        await message.answer(SUPPORT_UNAVAILABLE)
        return
    await state.clear()
    await message.answer(SUPPORT_SENT)


@router.callback_query(F.data.startswith("support:admin_reply:"))
async def start_admin_reply(callback: CallbackQuery, state: FSMContext) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer()
        return
    settings = get_settings()
    if not admin_is_authorized(
        settings,
        telegram_id=callback.from_user.id,
        chat_id=callback.message.chat.id,
    ):
        await callback.answer("Недостаточно прав", show_alert=True)
        return
    ticket_id = callback_ticket_id(callback.data, "support:admin_reply:")
    if ticket_id is None:
        await callback.answer("Обращение не найдено", show_alert=True)
        return
    async with session_factory() as session:
        ticket = await support_ticket_service.get_active_ticket(session, ticket_id)
    if ticket is None:
        await callback.answer("Обращение уже закрыто", show_alert=True)
        return
    await state.set_state(SupportStates.waiting_admin_reply)
    await state.update_data(support_ticket_id=ticket_id)
    await callback.answer()
    await callback.message.answer(
        f"Напиши ответ для обращения #{ticket_id}.",
        reply_markup=ForceReply(
            selective=True, input_field_placeholder="Ответ пользователю"
        ),
    )


@router.message(SupportStates.waiting_admin_reply)
async def receive_admin_reply(message: Message, state: FSMContext, bot: Bot) -> None:
    settings = get_settings()
    if message.from_user is None or not admin_is_authorized(
        settings,
        telegram_id=message.from_user.id,
        chat_id=message.chat.id,
    ):
        await message.answer("Недостаточно прав")
        await state.clear()
        return
    if not message.text or not message.text.strip():
        await message.answer("Ответ должен быть текстовым сообщением.")
        return
    state_data = await state.get_data()
    ticket_id = state_data.get("support_ticket_id")
    if not isinstance(ticket_id, int):
        await message.answer("Обращение не найдено")
        await state.clear()
        return
    try:
        async with session_factory() as session:
            ticket = await support_ticket_service.get_active_ticket(session, ticket_id)
            user = await session.get(User, ticket.user_id) if ticket else None
            if ticket is None or user is None:
                await message.answer("Обращение уже закрыто или не найдено")
                await state.clear()
                return
            await support_ticket_service.add_message(
                session,
                ticket,
                SupportSenderType.ADMIN,
                message.text.strip(),
            )
            await send_admin_reply_to_user(
                bot, user, ticket, message.text.strip()
            )
            await session.commit()
    except TelegramAPIError:
        logger.exception("Unable to deliver AIR support reply to user")
        await message.answer("Не удалось доставить ответ пользователю.")
        return
    await state.clear()
    await message.answer(f"Ответ по обращению #{ticket_id} отправлен.")


@router.callback_query(F.data.startswith("support:admin_close:"))
async def close_support_ticket(
    callback: CallbackQuery, state: FSMContext, bot: Bot
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer()
        return
    settings = get_settings()
    if not admin_is_authorized(
        settings,
        telegram_id=callback.from_user.id,
        chat_id=callback.message.chat.id,
    ):
        await callback.answer("Недостаточно прав", show_alert=True)
        return
    ticket_id = callback_ticket_id(callback.data, "support:admin_close:")
    if ticket_id is None:
        await callback.answer("Обращение не найдено", show_alert=True)
        return
    async with session_factory() as session:
        ticket = await support_ticket_service.get_active_ticket(session, ticket_id)
        user = await session.get(User, ticket.user_id) if ticket else None
        if ticket is None or user is None:
            await callback.answer("Обращение уже закрыто", show_alert=True)
            return
        await support_ticket_service.close_ticket(session, ticket)
        await session.commit()
    await state.clear()
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(f"Обращение #{ticket_id} закрыто.")
    try:
        await bot.send_message(user.telegram_id, SUPPORT_CLOSED_USER)
    except TelegramAPIError:
        logger.exception("Unable to notify user about closed AIR support ticket")
