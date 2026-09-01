from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.admin import router as admin_router
from app.api.mini_app import router as mini_app_router
from app.api.payments import router as payments_router
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
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["X-Telegram-Init-Data", "X-Dev-Telegram-Id", "Content-Type"],
)
app.include_router(mini_app_router)
app.include_router(payments_router)
app.include_router(admin_router)

mini_app_dist = Path(__file__).resolve().parents[2] / "miniapp" / "dist"


@app.get("/admin/payments", include_in_schema=False)
@app.get("/admin/payments/", include_in_schema=False)
async def admin_payments_page() -> FileResponse:
    index_file = mini_app_dist / "index.html"
    if not index_file.is_file():
        raise HTTPException(status_code=404, detail="Admin frontend is not built")
    return FileResponse(index_file)


if mini_app_dist.is_dir():
    app.mount("/mini-app", StaticFiles(directory=mini_app_dist, html=True), name="mini-app")


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
