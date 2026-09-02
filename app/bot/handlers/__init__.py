from aiogram import Router

from app.bot.handlers import onboarding, support


def get_router() -> Router:
    router = Router()
    router.include_router(support.router)
    router.include_router(onboarding.router)
    return router
