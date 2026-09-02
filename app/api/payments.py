from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import TelegramIdentity, get_rate_limited_telegram_identity
from app.api.mini_app import access_status, load_user
from app.core.config import Settings, get_settings
from app.core.security import payment_call_limiter
from app.db.models import PaymentOrder, PaymentOrderStatus
from app.db.session import get_session
from app.services.payments import (
    PAYMENT_PLANS,
    apply_verified_payment,
    find_reusable_pending_order,
    payment_return_url,
)
from app.services.yookassa import SdkYooKassaGateway, YooKassaGateway

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/payments", tags=["payments"])


class CreatePaymentRequest(BaseModel):
    plan_id: str = Field(min_length=1, max_length=50)
    email: EmailStr


class YooKassaWebhook(BaseModel):
    type: str | None = Field(default=None, max_length=100)
    event: str | None = Field(default=None, max_length=100)
    object: dict[str, Any]


def get_yookassa_gateway(
    settings: Settings = Depends(get_settings),
) -> YooKassaGateway:
    if not settings.yookassa_configured:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Оплата временно недоступна",
        )
    assert settings.yookassa_shop_id is not None
    assert settings.yookassa_secret_key is not None
    return SdkYooKassaGateway(
        settings.yookassa_shop_id,
        settings.yookassa_secret_key.get_secret_value(),
    )


@router.post("/create")
async def create_payment(
    payload: CreatePaymentRequest,
    identity: TelegramIdentity = Depends(get_rate_limited_telegram_identity),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    gateway: YooKassaGateway = Depends(get_yookassa_gateway),
) -> dict[str, object]:
    user, _ = await load_user(session, identity.telegram_id)
    plan = PAYMENT_PLANS.get(payload.plan_id)
    if plan is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Неизвестный тариф AIR")
    assert settings.yookassa_return_url is not None

    now = datetime.now(timezone.utc)
    email = str(payload.email).lower()
    user.receipt_email = email
    order = await find_reusable_pending_order(
        session, user=user, plan_id=plan.id, now=now
    )
    if order is None:
        order = PaymentOrder(
            user_id=user.id,
            plan_id=plan.id,
            amount=plan.amount,
            currency="RUB",
            status=PaymentOrderStatus.PENDING,
            idempotency_key=str(uuid4()),
            receipt_email=email,
        )
        session.add(order)
    else:
        order.receipt_email = email
    await session.commit()
    await session.refresh(order)

    if order.yookassa_payment_id and order.confirmation_url:
        return {
            "order_id": order.id,
            "payment_id": order.yookassa_payment_id,
            "confirmation_url": order.confirmation_url,
        }

    try:
        async with payment_call_limiter.slot():
            payment = await gateway.create_payment(
                amount=order.amount,
                currency=order.currency,
                description=plan.title,
                return_url=payment_return_url(settings.yookassa_return_url, order.id),
                metadata={
                    "air_order_id": str(order.id),
                    "air_user_id": str(user.id),
                    "plan_id": plan.id,
                },
                idempotency_key=order.idempotency_key,
            )
    except Exception as exc:
        logger.exception("YooKassa payment creation failed for order %s", order.id)
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "Не удалось открыть оплату. Попробуй ещё раз позже.",
        ) from exc

    order.yookassa_payment_id = payment.payment_id
    order.confirmation_url = payment.confirmation_url
    await session.commit()
    return {
        "order_id": order.id,
        "payment_id": payment.payment_id,
        "confirmation_url": payment.confirmation_url,
    }


@router.get("/{order_id}/status")
async def payment_status(
    order_id: int,
    identity: TelegramIdentity = Depends(get_rate_limited_telegram_identity),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    gateway: YooKassaGateway = Depends(get_yookassa_gateway),
) -> dict[str, object]:
    user, _ = await load_user(session, identity.telegram_id)
    order = await session.scalar(
        select(PaymentOrder).where(
            PaymentOrder.id == order_id,
            PaymentOrder.user_id == user.id,
        )
    )
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Платёж не найден")

    if order.status == PaymentOrderStatus.PENDING and order.yookassa_payment_id:
        current_order_id = order.id
        await session.commit()
        async with payment_call_limiter.slot(current_order_id):
            order = await session.scalar(
                select(PaymentOrder)
                .where(PaymentOrder.id == current_order_id)
                .execution_options(populate_existing=True)
            )
            assert order is not None
            if order.status == PaymentOrderStatus.PENDING and order.yookassa_payment_id:
                payment_id = order.yookassa_payment_id
                await session.commit()
                try:
                    verified = await gateway.get_payment(payment_id)
                except Exception:
                    logger.exception(
                        "YooKassa status refresh failed for order %s", current_order_id
                    )
                else:
                    await apply_verified_payment(
                        session,
                        order_id=current_order_id,
                        payment=verified,
                    )
        order = await session.scalar(
            select(PaymentOrder)
            .where(PaymentOrder.id == order_id)
            .execution_options(populate_existing=True)
        )
        assert order is not None
    access, _ = await access_status(session, user, settings)
    return {
        "order_id": order.id,
        "status": order.status.value,
        "access_active": access == "active",
    }


@router.post("/yookassa/webhook")
async def yookassa_webhook(
    payload: YooKassaWebhook,
    session: AsyncSession = Depends(get_session),
    gateway: YooKassaGateway = Depends(get_yookassa_gateway),
) -> dict[str, str]:
    if payload.event not in {"payment.succeeded", "payment.canceled"}:
        return {"status": "ignored"}
    payment_id = payload.object.get("id")
    if not isinstance(payment_id, str) or not payment_id:
        return {"status": "ignored"}

    order = await session.scalar(
        select(PaymentOrder).where(PaymentOrder.yookassa_payment_id == payment_id)
    )
    if order is None:
        logger.warning("Ignoring YooKassa webhook for unknown payment %s", payment_id)
        return {"status": "ignored"}
    if order.status == PaymentOrderStatus.SUCCEEDED:
        return {"status": "already_processed"}

    order_id = order.id
    await session.commit()
    async with payment_call_limiter.slot(order_id):
        order = await session.scalar(
            select(PaymentOrder)
            .where(PaymentOrder.id == order_id)
            .execution_options(populate_existing=True)
        )
        assert order is not None
        if order.status == PaymentOrderStatus.SUCCEEDED:
            return {"status": "already_processed"}
        await session.commit()
        try:
            verified = await gateway.get_payment(payment_id)
        except Exception as exc:
            logger.exception("Could not verify YooKassa webhook for order %s", order_id)
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "Не удалось проверить платёж",
            ) from exc
        result = await apply_verified_payment(
            session,
            order_id=order_id,
            payment=verified,
        )
    if result == "invalid":
        logger.error("Rejected inconsistent YooKassa payment for order %s", order_id)
        return {"status": "ignored"}
    return {"status": result}
