from aiogram import Router

from app.bot.handlers import onboarding


def get_router() -> Router:
    router = Router()
    router.include_router(onboarding.router)
    return router

