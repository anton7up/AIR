from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.mini_app import router as mini_app_router
from app.core.config import get_settings
from app.db.session import init_db


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await init_db()
    yield


app = FastAPI(title="AIR API", version="0.1.0", lifespan=lifespan)
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["X-Telegram-Init-Data", "X-Dev-Telegram-Id", "Content-Type"],
)
app.include_router(mini_app_router)

mini_app_dist = Path(__file__).resolve().parents[2] / "miniapp" / "dist"
if mini_app_dist.is_dir():
    app.mount("/mini-app", StaticFiles(directory=mini_app_dist, html=True), name="mini-app")


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
