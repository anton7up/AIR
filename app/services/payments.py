from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    PaymentOrder,
    PaymentOrderStatus,
    Subscription,
    SubscriptionStatus,
    User,
)
from app.services.yookassa import VerifiedPayment


@dataclass(frozen=True)
class PaymentPlan:
    id: str
    title: str
    amount: Decimal
    access_days: int | None


PAYMENT_PLANS: dict[str, PaymentPlan] = {
    "air_30_days": PaymentPlan(
        "air_30_days", "AIR — доступ на 30 дней", Decimal("990.00"), 30
    ),
    "air_lifetime": PaymentPlan(
        "air_lifetime", "AIR — бессрочный доступ", Decimal("2450.00"), None
    ),
}


def payment_return_url(base_url: str, order_id: int) -> str:
    parts = urlsplit(base_url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update({"payment": "return", "order_id": str(order_id)})
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def validate_verified_payment(order: PaymentOrder, payment: VerifiedPayment) -> bool:
    return (
        payment.payment_id == order.yookassa_payment_id
        and payment.status in {"succeeded", "canceled"}
        and payment.amount == order.amount
        and payment.currency == order.currency
        and payment.metadata.get("air_order_id") == str(order.id)
        and payment.metadata.get("air_user_id") == str(order.user_id)
        and payment.metadata.get("plan_id") == order.plan_id
    )


def _verified_order_identity(
    payment: VerifiedPayment,
) -> tuple[int, int, str] | None:
    try:
        order_id = int(payment.metadata["air_order_id"])
        user_id = int(payment.metadata["air_user_id"])
        plan_id = payment.metadata["plan_id"]
    except (KeyError, TypeError, ValueError):
        return None
    if order_id <= 0 or user_id <= 0 or not isinstance(plan_id, str):
        return None
    return order_id, user_id, plan_id


async def activate_paid_access(
    session: AsyncSession,
    *,
    user_id: int,
    plan: PaymentPlan,
    now: datetime,
) -> Subscription:
    latest = await session.scalar(
        select(Subscription)
        .where(Subscription.user_id == user_id)
        .order_by(Subscription.id.desc())
    )
    if (
        latest is not None
        and latest.status == SubscriptionStatus.ACTIVE
        and latest.ends_at is None
    ):
        return latest

    if plan.access_days is None:
        subscription = Subscription(
            user_id=user_id,
            plan=plan.id,
            status=SubscriptionStatus.ACTIVE,
            starts_at=now,
            ends_at=None,
        )
        session.add(subscription)
        return subscription

    base = now
    if latest is not None and latest.status == SubscriptionStatus.ACTIVE and latest.ends_at:
        current_end = latest.ends_at
        if current_end.tzinfo is None:
            current_end = current_end.replace(tzinfo=timezone.utc)
        base = max(base, current_end)
    subscription = Subscription(
        user_id=user_id,
        plan=plan.id,
        status=SubscriptionStatus.ACTIVE,
        starts_at=now,
        ends_at=base + timedelta(days=plan.access_days),
    )
    session.add(subscription)
    return subscription


async def apply_verified_payment(
    session: AsyncSession,
    *,
    order_id: int,
    payment: VerifiedPayment,
    now: datetime | None = None,
) -> str:
    identity = _verified_order_identity(payment)
    if identity is None:
        return "invalid"
    metadata_order_id, user_id, plan_id = identity
    if metadata_order_id != order_id or payment.status not in {"succeeded", "canceled"}:
        return "invalid"

    plan = PAYMENT_PLANS.get(plan_id)
    if plan is None:
        return "invalid"
    if payment.status == "succeeded" and not payment.paid:
        return "invalid"

    paid_at = now or datetime.now(timezone.utc)
    target_status = (
        PaymentOrderStatus.SUCCEEDED
        if payment.status == "succeeded"
        else PaymentOrderStatus.CANCELED
    )
    claimed = await session.execute(
        update(PaymentOrder)
        .where(
            PaymentOrder.id == order_id,
            PaymentOrder.status == PaymentOrderStatus.PENDING,
            PaymentOrder.yookassa_payment_id == payment.payment_id,
            PaymentOrder.user_id == user_id,
            PaymentOrder.plan_id == plan_id,
            PaymentOrder.amount == payment.amount,
            PaymentOrder.currency == payment.currency,
        )
        .values(
            status=target_status,
            paid_at=paid_at if target_status == PaymentOrderStatus.SUCCEEDED else None,
        )
        .returning(PaymentOrder.id)
        .execution_options(synchronize_session="fetch")
    )

    if claimed.scalar_one_or_none() is None:
        await session.commit()
        existing = await session.scalar(
            select(PaymentOrder)
            .where(PaymentOrder.id == order_id)
            .execution_options(populate_existing=True)
        )
        if existing is None or not validate_verified_payment(existing, payment):
            return "invalid"
        if existing.status == PaymentOrderStatus.SUCCEEDED:
            return "already_processed"
        if (
            existing.status == PaymentOrderStatus.CANCELED
            and payment.status == "canceled"
        ):
            return "canceled"
        return "invalid"

    try:
        if target_status == PaymentOrderStatus.SUCCEEDED:
            await activate_paid_access(
                session,
                user_id=user_id,
                plan=plan,
                now=paid_at,
            )
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    return "succeeded" if target_status == PaymentOrderStatus.SUCCEEDED else "canceled"


async def find_reusable_pending_order(
    session: AsyncSession,
    *,
    user: User,
    plan_id: str,
    now: datetime,
) -> PaymentOrder | None:
    order = await session.scalar(
        select(PaymentOrder)
        .where(
            PaymentOrder.user_id == user.id,
            PaymentOrder.plan_id == plan_id,
            PaymentOrder.status == PaymentOrderStatus.PENDING,
        )
        .order_by(PaymentOrder.id.desc())
    )
    if order is None:
        return None
    created_at = order.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return order if created_at >= now - timedelta(hours=24) else None
