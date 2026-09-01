from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import validate_init_data
from app.core.config import Settings, get_settings
from app.db.models import PaymentOrder, PaymentOrderStatus, ReceiptStatus, User
from app.db.session import get_session

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])
ADMIN_COOKIE_NAME = "air_admin_session"
ADMIN_PLAN_TITLES = {
    "air_30_days": "30 дней",
    "air_lifetime": "Навсегда",
}


class AdminLoginRequest(BaseModel):
    password: str = Field(min_length=1, max_length=1000)


class ReceiptStatusRequest(BaseModel):
    status: Literal["pending", "sent"]


def create_admin_session(password: str, ttl_seconds: int, now: int | None = None) -> str:
    issued_at = int(time.time()) if now is None else now
    expires_at = issued_at + ttl_seconds
    payload = str(expires_at)
    key = hashlib.sha256(password.encode()).digest()
    signature = hmac.new(key, f"air-admin:{payload}".encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{signature}"


def validate_admin_session(
    value: str,
    password: str,
    ttl_seconds: int,
    now: int | None = None,
) -> bool:
    try:
        raw_expiry, received_signature = value.split(".", maxsplit=1)
        expires_at = int(raw_expiry)
    except (ValueError, TypeError):
        return False
    current_time = int(time.time()) if now is None else now
    if expires_at <= current_time or expires_at > current_time + ttl_seconds + 60:
        return False
    key = hashlib.sha256(password.encode()).digest()
    expected = hmac.new(
        key, f"air-admin:{expires_at}".encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, received_signature)


def configured_admin_password(settings: Settings) -> str:
    if settings.admin_panel_password is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Админ-панель временно недоступна",
        )
    password = settings.admin_panel_password.get_secret_value()
    if not password:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Админ-панель временно недоступна",
        )
    return password


async def require_admin(
    init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
    admin_session: str | None = Cookie(default=None, alias=ADMIN_COOKIE_NAME),
    settings: Settings = Depends(get_settings),
) -> str:
    if init_data:
        if settings.bot_token is None:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Авторизация недоступна")
        try:
            identity = validate_init_data(
                init_data,
                settings.bot_token.get_secret_value(),
                settings.telegram_init_data_max_age_seconds,
            )
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Требуется авторизация") from exc
        if not settings.is_admin(identity.telegram_id):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Доступ запрещён")
        return "telegram"

    if admin_session:
        password = configured_admin_password(settings)
        if validate_admin_session(
            admin_session, password, settings.admin_session_ttl_seconds
        ):
            return "session"
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Требуется авторизация")


@router.post("/login")
async def admin_login(
    payload: AdminLoginRequest,
    response: Response,
    settings: Settings = Depends(get_settings),
) -> dict[str, bool]:
    password = configured_admin_password(settings)
    if not hmac.compare_digest(payload.password, password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный пароль")
    session_value = create_admin_session(
        password, settings.admin_session_ttl_seconds
    )
    response.set_cookie(
        ADMIN_COOKIE_NAME,
        session_value,
        max_age=settings.admin_session_ttl_seconds,
        httponly=True,
        secure=True,
        samesite="strict",
        path="/api/v1/admin",
    )
    return {"authenticated": True}


@router.post("/logout")
async def admin_logout(
    response: Response,
    _: str = Depends(require_admin),
) -> dict[str, bool]:
    response.delete_cookie(
        ADMIN_COOKIE_NAME,
        secure=True,
        httponly=True,
        samesite="strict",
        path="/api/v1/admin",
    )
    return {"authenticated": False}


@router.get("/access")
async def admin_access(_: str = Depends(require_admin)) -> dict[str, bool]:
    return {"is_admin": True}


def _enum_value(value: object) -> str:
    return str(getattr(value, "value", value))


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


@router.get("/payments")
async def admin_payments(
    _: str = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    rows = (
        await session.execute(
            select(PaymentOrder, User.telegram_id)
            .join(User, User.id == PaymentOrder.user_id)
            .order_by(PaymentOrder.created_at.desc(), PaymentOrder.id.desc())
        )
    ).all()
    orders: list[dict[str, object]] = []
    successful_count = 0
    revenue = Decimal("0")
    receipts_pending = 0
    receipts_sent = 0
    for order, telegram_id in rows:
        payment_status = _enum_value(order.status)
        receipt_status = _enum_value(order.receipt_status)
        if payment_status == PaymentOrderStatus.SUCCEEDED.value:
            successful_count += 1
            revenue += order.amount
            if receipt_status == ReceiptStatus.SENT.value:
                receipts_sent += 1
            else:
                receipts_pending += 1
        orders.append(
            {
                "id": order.id,
                "created_at": _iso(order.created_at),
                "telegram_user_id": telegram_id,
                "email": order.receipt_email,
                "plan_id": order.plan_id,
                "plan_title": ADMIN_PLAN_TITLES.get(order.plan_id, order.plan_id),
                "amount": str(order.amount),
                "currency": order.currency,
                "status": payment_status,
                "yookassa_payment_id": order.yookassa_payment_id,
                "paid_at": _iso(order.paid_at),
                "receipt_status": receipt_status,
                "receipt_sent_at": _iso(order.receipt_sent_at),
            }
        )
    return {
        "stats": {
            "successful_count": successful_count,
            "revenue": str(revenue),
            "receipts_pending": receipts_pending,
            "receipts_sent": receipts_sent,
        },
        "orders": orders,
    }


@router.patch("/payments/{order_id}/receipt")
async def update_receipt_status(
    order_id: int,
    payload: ReceiptStatusRequest,
    _: str = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    order = await session.get(PaymentOrder, order_id)
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Платёж не найден")
    if order.status != PaymentOrderStatus.SUCCEEDED:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Чек можно отметить только для успешного платежа",
        )
    requested = ReceiptStatus(payload.status)
    if requested == ReceiptStatus.SENT:
        if order.receipt_status != ReceiptStatus.SENT:
            order.receipt_status = ReceiptStatus.SENT
            order.receipt_sent_at = datetime.now(timezone.utc)
    else:
        order.receipt_status = ReceiptStatus.PENDING
        order.receipt_sent_at = None
    await session.commit()
    await session.refresh(order)
    return {
        "id": order.id,
        "receipt_status": _enum_value(order.receipt_status),
        "receipt_sent_at": _iso(order.receipt_sent_at),
    }
