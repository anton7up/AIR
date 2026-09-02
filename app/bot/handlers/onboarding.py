from typing import Any

from aiogram import F, Router
from aiogram.enums import ChatType, ParseMode
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.types import User as TelegramUser

from app.bot.keyboards.onboarding import (
    choices_keyboard,
    consent_declined_keyboard,
    consent_keyboard,
    open_air_keyboard,
)
from app.bot.states.onboarding import OnboardingStates
from app.bot.texts.messages import (
    INVALID_CHOICE,
    MINI_APP_NOT_READY,
    PERSONAL_DATA_CONSENT,
    PERSONAL_DATA_CONSENT_DECLINED,
    WELCOME,
    result_message,
)
from app.core.config import get_settings
from app.db.repositories import UserRepository
from app.db.session import session_factory
from app.onboarding.engine import InvalidAnswer, OnboardingEngine
from app.onboarding.schema import InputType, Question
from app.services.consent import (
    accept_personal_data_consent,
    find_telegram_user,
    get_or_create_telegram_user,
    has_current_personal_data_consent,
    personal_data_consent_url,
)
from app.services.expenses import ExpenseCalculator

router = Router(name="onboarding")
engine = OnboardingEngine()
calculator = ExpenseCalculator()


async def send_question(message: Message, question: Question) -> None:
    keyboard = choices_keyboard(question) if question.input_type is InputType.CHOICE else None
    suffix = "\n\nОтправь ответ числом." if question.input_type is InputType.NUMBER else ""
    await message.answer(question.text + suffix, reply_markup=keyboard)


async def begin_questions(message: Message, state: FSMContext, first_name: str) -> None:
    await message.answer(WELCOME.format(first_name=first_name))
    question = engine.first_question()
    await state.set_state(OnboardingStates.answering)
    await state.update_data(current_question=question.key, answers={})
    await send_question(message, question)


async def show_consent(message: Message, state: FSMContext) -> None:
    await state.set_state(OnboardingStates.awaiting_consent)
    document_url = personal_data_consent_url(get_settings().mini_app_url)
    await message.answer(
        PERSONAL_DATA_CONSENT,
        reply_markup=consent_keyboard(document_url),
    )


@router.message(CommandStart(), F.chat.type == ChatType.PRIVATE)
async def start_onboarding(message: Message, state: FSMContext) -> None:
    if message.chat.type != ChatType.PRIVATE:
        return
    await state.clear()
    telegram_user = message.from_user
    if telegram_user is None:
        await message.answer("Не удалось прочитать данные Telegram. Попробуй /start ещё раз.")
        return
    async with session_factory() as session:
        user = await get_or_create_telegram_user(
            session,
            telegram_id=telegram_user.id,
            first_name=telegram_user.first_name,
            username=telegram_user.username,
        )
        accepted = has_current_personal_data_consent(user)
        await session.commit()
    if accepted:
        await begin_questions(message, state, telegram_user.first_name)
        return
    await show_consent(message, state)


@router.callback_query(OnboardingStates.awaiting_consent, F.data == "consent:accept")
async def accept_consent(callback: CallbackQuery, state: FSMContext) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer()
        return
    telegram_user = callback.from_user
    async with session_factory() as session:
        user = await get_or_create_telegram_user(
            session,
            telegram_id=telegram_user.id,
            first_name=telegram_user.first_name,
            username=telegram_user.username,
        )
        await accept_personal_data_consent(session, user)
        await session.commit()
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    await begin_questions(callback.message, state, telegram_user.first_name)


@router.callback_query(OnboardingStates.awaiting_consent, F.data == "consent:decline")
async def decline_consent(callback: CallbackQuery, state: FSMContext) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer()
        return
    await state.set_state(OnboardingStates.consent_declined)
    await callback.answer()
    await callback.message.edit_text(
        PERSONAL_DATA_CONSENT_DECLINED,
        reply_markup=consent_declined_keyboard(),
    )


@router.callback_query(OnboardingStates.consent_declined, F.data == "consent:return")
async def return_to_consent(callback: CallbackQuery, state: FSMContext) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer()
        return
    await state.set_state(OnboardingStates.awaiting_consent)
    await callback.answer()
    await callback.message.edit_text(
        PERSONAL_DATA_CONSENT,
        reply_markup=consent_keyboard(
            personal_data_consent_url(get_settings().mini_app_url)
        ),
    )


@router.callback_query(OnboardingStates.consent_declined, F.data == "consent:close")
async def close_consent(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer("AIR будет рядом, когда ты решишь вернуться.")
    if isinstance(callback.message, Message):
        await callback.message.edit_reply_markup(reply_markup=None)


@router.callback_query(F.data == "consent:document_unavailable")
async def consent_document_unavailable(callback: CallbackQuery) -> None:
    await callback.answer("Документ скоро будет доступен.", show_alert=True)


async def accept_answer(
    message: Message,
    state: FSMContext,
    question: Question,
    answer: Any,
    telegram_user: TelegramUser | None,
) -> None:
    if telegram_user is None:
        await message.answer("Не удалось прочитать данные Telegram. Попробуй /start ещё раз.")
        await state.clear()
        return
    async with session_factory() as session:
        user = await find_telegram_user(session, telegram_user.id)
        if user is None or not has_current_personal_data_consent(user):
            await state.clear()
            await show_consent(message, state)
            return
    data = await state.get_data()
    answers = dict(data.get("answers", {}))
    answers[question.key] = answer
    next_question = engine.next_question(question, answer)
    if next_question is not None:
        await state.update_data(current_question=next_question.key, answers=answers)
        await send_question(message, next_question)
        return

    result = calculator.calculate(answers)
    async with session_factory() as session:
        await UserRepository(session).save_onboarding(
            telegram_id=telegram_user.id,
            first_name=telegram_user.first_name,
            username=telegram_user.username,
            answers=answers,
            result=result,
        )
    await state.clear()
    await message.answer(
        result_message(result.monthly, result.yearly, result.lifetime, result.five_year_projection),
        parse_mode=ParseMode.HTML,
        reply_markup=open_air_keyboard(get_settings().mini_app_url),
    )


@router.callback_query(OnboardingStates.answering, F.data.startswith("answer:"))
async def handle_choice(callback: CallbackQuery, state: FSMContext) -> None:
    if not isinstance(callback.message, Message) or callback.data is None:
        await callback.answer()
        return
    data = await state.get_data()
    current_key = data.get("current_question")
    _, callback_key, raw_index = callback.data.split(":", maxsplit=2)
    if callback_key != current_key:
        await callback.answer("Этот вопрос уже пройден.")
        return
    question = engine.question(current_key)
    try:
        answer = engine.choice_answer(question, int(raw_index))
    except (InvalidAnswer, ValueError):
        await callback.answer(INVALID_CHOICE)
        return
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    await accept_answer(callback.message, state, question, answer, callback.from_user)


@router.message(OnboardingStates.answering)
async def handle_number(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    question = engine.question(data["current_question"])
    if question.input_type is not InputType.NUMBER or message.text is None:
        await message.answer(INVALID_CHOICE)
        return
    try:
        answer = engine.parse_text_answer(question, message.text)
    except InvalidAnswer as exc:
        await message.answer(str(exc))
        return
    await accept_answer(message, state, question, answer, message.from_user)


@router.callback_query(F.data == "mini_app:not_ready")
async def mini_app_placeholder(callback: CallbackQuery) -> None:
    await callback.answer(MINI_APP_NOT_READY, show_alert=True)
