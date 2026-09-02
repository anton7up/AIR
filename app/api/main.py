from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response

from app.api.admin import router as admin_router
from app.api.mini_app import router as mini_app_router
from app.api.payments import router as payments_router
from app.core.config import get_settings
from app.core.security import (
    ProductionTrustedHostMiddleware,
    SecurityHeadersMiddleware,
    SecurityMiddleware,
)
from app.db.session import init_db


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await init_db()
    yield


def documentation_config(production: bool) -> dict[str, str | None]:
    return {
        "docs_url": None if production else "/docs",
        "redoc_url": None if production else "/redoc",
        "openapi_url": None if production else "/openapi.json",
    }


settings = get_settings()
_documentation = documentation_config(settings.is_production)
app = FastAPI(
    title="AIR API",
    version="0.1.0",
    lifespan=lifespan,
    docs_url=_documentation["docs_url"],
    redoc_url=_documentation["redoc_url"],
    openapi_url=_documentation["openapi_url"],
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=[
        "X-Telegram-Init-Data",
        "X-Dev-Telegram-Id",
        "Idempotency-Key",
        "Content-Type",
    ],
)
if settings.is_production:
    app.add_middleware(
        ProductionTrustedHostMiddleware,
        allowed_hosts=settings.production_host_list,
    )
app.add_middleware(SecurityHeadersMiddleware, production=settings.is_production)
app.add_middleware(
    SecurityMiddleware,
    trusted_proxy_cidrs=settings.trusted_proxy_cidrs,
    max_request_body_bytes=settings.max_request_body_bytes,
)
app.include_router(mini_app_router)
app.include_router(payments_router)
app.include_router(admin_router)


@app.exception_handler(HTTPException)
async def standardized_http_error(
    request: Request, exc: HTTPException
) -> Response:
    if exc.status_code == 429:
        raw_retry_after = (exc.headers or {}).get("Retry-After", "1")
        try:
            retry_after = max(1, int(raw_retry_after))
        except ValueError:
            retry_after = 1
        return JSONResponse(
            status_code=429,
            headers={"Retry-After": str(retry_after)},
            content={"detail": "Too many requests", "retry_after": retry_after},
        )
    return await http_exception_handler(request, exc)

mini_app_dist = Path(__file__).resolve().parents[2] / "miniapp" / "dist"


@app.get("/admin/payments", include_in_schema=False)
@app.get("/admin/payments/", include_in_schema=False)
async def admin_payments_page() -> FileResponse:
    index_file = mini_app_dist / "index.html"
    if not index_file.is_file():
        raise HTTPException(status_code=404, detail="Admin frontend is not built")
    return FileResponse(index_file)


@app.get("/personal-data-consent", include_in_schema=False)
@app.get("/personal-data-consent/", include_in_schema=False)
@app.get("/privacy", include_in_schema=False)
@app.get("/privacy/", include_in_schema=False)
@app.get("/offer", include_in_schema=False)
@app.get("/offer/", include_in_schema=False)
@app.get("/terms", include_in_schema=False)
@app.get("/terms/", include_in_schema=False)
async def personal_data_consent_page() -> FileResponse:
    index_file = mini_app_dist / "index.html"
    if not index_file.is_file():
        raise HTTPException(status_code=404, detail="Mini App frontend is not built")
    return FileResponse(index_file)


if mini_app_dist.is_dir():
    app.mount("/mini-app", StaticFiles(directory=mini_app_dist, html=True), name="mini-app")


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
