from aiogram import Bot, Dispatcher

from app.bot.handlers import get_router
from app.core.config import Settings
from app.db.session import init_db


async def run_bot(settings: Settings) -> None:
    if settings.bot_token is None or not settings.bot_token.get_secret_value():
        raise RuntimeError("BOT_TOKEN is not configured. Add it to the local .env file.")
    await init_db()
    bot = Bot(token=settings.bot_token.get_secret_value())
    dispatcher = Dispatcher()
    dispatcher.include_router(get_router())
    try:
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()

