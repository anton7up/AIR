from typing import Any

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.types import User as TelegramUser

from app.bot.keyboards.onboarding import choices_keyboard, open_air_keyboard
from app.bot.states.onboarding import OnboardingStates
from app.bot.texts.messages import (
    INVALID_CHOICE,
    MINI_APP_NOT_READY,
    WELCOME,
    result_message,
)
from app.core.config import get_settings
from app.db.repositories import UserRepository
from app.db.session import session_factory
from app.onboarding.engine import InvalidAnswer, OnboardingEngine
from app.onboarding.schema import InputType, Question
from app.services.expenses import ExpenseCalculator

router = Router(name="onboarding")
engine = OnboardingEngine()
calculator = ExpenseCalculator()


async def send_question(message: Message, question: Question) -> None:
    keyboard = choices_keyboard(question) if question.input_type is InputType.CHOICE else None
    suffix = "\n\nОтправь ответ числом." if question.input_type is InputType.NUMBER else ""
    await message.answer(question.text + suffix, reply_markup=keyboard)


@router.message(CommandStart())
async def start_onboarding(message: Message, state: FSMContext) -> None:
    await state.clear()
    first_name = message.from_user.first_name if message.from_user else "друг"
    await message.answer(WELCOME.format(first_name=first_name))
    question = engine.first_question()
    await state.set_state(OnboardingStates.answering)
    await state.update_data(current_question=question.key, answers={})
    await send_question(message, question)


async def accept_answer(
    message: Message,
    state: FSMContext,
    question: Question,
    answer: Any,
    telegram_user: TelegramUser | None,
) -> None:
    data = await state.get_data()
    answers = dict(data.get("answers", {}))
    answers[question.key] = answer
    next_question = engine.next_question(question, answer)
    if next_question is not None:
        await state.update_data(current_question=next_question.key, answers=answers)
        await send_question(message, next_question)
        return

    if telegram_user is None:
        await message.answer("Не удалось прочитать данные Telegram. Попробуй /start ещё раз.")
        await state.clear()
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
