from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.auth import TelegramIdentity
from app.api.payments import (
    CreatePaymentRequest,
    YooKassaWebhook,
    create_payment,
    payment_status,
    yookassa_webhook,
)
from app.core.config import Settings
from app.db.base import Base
from app.db.models import (
    NicotineType,
    PaymentOrder,
    PaymentOrderStatus,
    SmokingProfile,
    Subscription,
    SubscriptionStatus,
    User,
)
from app.services.payments import PAYMENT_PLANS, activate_paid_access, payment_return_url
from app.services.yookassa import CreatedPayment, VerifiedPayment


class FakeGateway:
    def __init__(self) -> None:
        self.created: list[dict[str, object]] = []
        self.verified: VerifiedPayment | None = None

    async def create_payment(self, **kwargs) -> CreatedPayment:
        self.created.append(kwargs)
        return CreatedPayment("yk-payment-1", "pending", "https://yookassa.test/pay/1")

    async def get_payment(self, payment_id: str) -> VerifiedPayment:
        assert self.verified is not None
        assert payment_id == self.verified.payment_id
        return self.verified


def payment_settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="production",
        yookassa_shop_id="test-shop",
        yookassa_secret_key="test-secret",
        yookassa_return_url="https://air.example/mini-app/?payment=return",
    )


async def make_session(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'payments.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False)(), engine


async def make_user(session, telegram_id: int = 1001) -> User:
    user = User(telegram_id=telegram_id, telegram_first_name="Payment tester")
    session.add(user)
    await session.flush()
    session.add(
        SmokingProfile(
            user_id=user.id,
            nicotine_type=NicotineType.CIGARETTES,
            years_of_use=Decimal("2"),
            daily_units=Decimal("10"),
            consumption_parameters={},
            cost_parameters={},
            monthly_expense=Decimal("3000"),
            yearly_expense=Decimal("36000"),
            lifetime_expense=Decimal("72000"),
            projected_five_year_expense=Decimal("180000"),
        )
    )
    await session.commit()
    return user


@pytest.mark.asyncio
async def test_create_payment_uses_backend_price_and_saves_email(tmp_path: Path) -> None:
    session, engine = await make_session(tmp_path)
    gateway = FakeGateway()
    async with session:
        user = await make_user(session)
        result = await create_payment(
            CreatePaymentRequest(plan_id="air_30_days", email="Buyer@Example.com"),
            TelegramIdentity(user.telegram_id, "Buyer"),
            session,
            payment_settings(),
            gateway,
        )
        order = await session.get(PaymentOrder, result["order_id"])
        assert order is not None
        assert order.amount == Decimal("990.00")
        assert order.currency == "RUB"
        assert order.status == PaymentOrderStatus.PENDING
        assert order.receipt_email == "buyer@example.com"
        assert user.receipt_email == "buyer@example.com"
        assert gateway.created[0]["amount"] == Decimal("990.00")
        assert gateway.created[0]["metadata"] == {
            "air_order_id": str(order.id),
            "air_user_id": str(user.id),
            "plan_id": "air_30_days",
        }
        assert f"order_id={order.id}" in str(gateway.created[0]["return_url"])
    await engine.dispose()


@pytest.mark.asyncio
async def test_lifetime_price_is_backend_owned_and_unknown_plan_is_rejected(tmp_path: Path) -> None:
    session, engine = await make_session(tmp_path)
    gateway = FakeGateway()
    async with session:
        user = await make_user(session)
        payload = CreatePaymentRequest.model_validate(
            {"plan_id": "air_lifetime", "email": "buyer@example.com", "amount": "1.00"}
        )
        result = await create_payment(
            payload,
            TelegramIdentity(user.telegram_id, "Buyer"),
            session,
            payment_settings(),
            gateway,
        )
        order = await session.get(PaymentOrder, result["order_id"])
        assert order is not None
        assert order.amount == Decimal("2450.00")
        with pytest.raises(HTTPException) as exc_info:
            await create_payment(
                CreatePaymentRequest(plan_id="air_week", email="buyer@example.com"),
                TelegramIdentity(user.telegram_id, "Buyer"),
                session,
                payment_settings(),
                gateway,
            )
        assert exc_info.value.status_code == 422
    await engine.dispose()


@pytest.mark.asyncio
async def test_repeated_create_reuses_pending_payment(tmp_path: Path) -> None:
    session, engine = await make_session(tmp_path)
    gateway = FakeGateway()
    async with session:
        user = await make_user(session)
        request = CreatePaymentRequest(plan_id="air_30_days", email="buyer@example.com")
        first = await create_payment(
            request, TelegramIdentity(user.telegram_id, "Buyer"), session, payment_settings(), gateway
        )
        second = await create_payment(
            request, TelegramIdentity(user.telegram_id, "Buyer"), session, payment_settings(), gateway
        )
        assert second == first
        assert len(gateway.created) == 1
    await engine.dispose()


@pytest.mark.asyncio
async def test_succeeded_webhook_is_verified_and_idempotent(tmp_path: Path) -> None:
    session, engine = await make_session(tmp_path)
    gateway = FakeGateway()
    current_settings = payment_settings()
    async with session:
        user = await make_user(session)
        created = await create_payment(
            CreatePaymentRequest(plan_id="air_30_days", email="buyer@example.com"),
            TelegramIdentity(user.telegram_id, "Buyer"),
            session,
            current_settings,
            gateway,
        )
        order = await session.get(PaymentOrder, created["order_id"])
        assert order is not None
        gateway.verified = VerifiedPayment(
            payment_id="yk-payment-1",
            status="succeeded",
            paid=True,
            amount=Decimal("990.00"),
            currency="RUB",
            metadata={
                "air_order_id": str(order.id),
                "air_user_id": str(user.id),
                "plan_id": "air_30_days",
            },
        )
        event = YooKassaWebhook(event="payment.succeeded", object={"id": "yk-payment-1"})
        assert await yookassa_webhook(event, session, gateway) == {"status": "succeeded"}
        assert await yookassa_webhook(event, session, gateway) == {
            "status": "already_processed"
        }
        assert await session.scalar(
            select(func.count(Subscription.id)).where(Subscription.user_id == user.id)
        ) == 1
        await session.refresh(order)
        assert order.status == PaymentOrderStatus.SUCCEEDED
        assert order.paid_at is not None
    await engine.dispose()


@pytest.mark.asyncio
async def test_succeeded_lifetime_webhook_grants_access_without_end(tmp_path: Path) -> None:
    session, engine = await make_session(tmp_path)
    gateway = FakeGateway()
    async with session:
        user = await make_user(session)
        created = await create_payment(
            CreatePaymentRequest(plan_id="air_lifetime", email="buyer@example.com"),
            TelegramIdentity(user.telegram_id, "Buyer"),
            session,
            payment_settings(),
            gateway,
        )
        order = await session.get(PaymentOrder, created["order_id"])
        assert order is not None
        gateway.verified = VerifiedPayment(
            "yk-payment-1",
            "succeeded",
            True,
            Decimal("2450.00"),
            "RUB",
            {
                "air_order_id": str(order.id),
                "air_user_id": str(user.id),
                "plan_id": "air_lifetime",
            },
        )
        result = await yookassa_webhook(
            YooKassaWebhook(event="payment.succeeded", object={"id": "yk-payment-1"}),
            session,
            gateway,
        )
        subscription = await session.scalar(
            select(Subscription).where(Subscription.user_id == user.id)
        )
        assert result == {"status": "succeeded"}
        assert subscription is not None
        assert subscription.plan == "air_lifetime"
        assert subscription.ends_at is None
    await engine.dispose()


@pytest.mark.asyncio
async def test_inconsistent_payment_never_activates_access(tmp_path: Path) -> None:
    session, engine = await make_session(tmp_path)
    gateway = FakeGateway()
    async with session:
        user = await make_user(session)
        created = await create_payment(
            CreatePaymentRequest(plan_id="air_lifetime", email="buyer@example.com"),
            TelegramIdentity(user.telegram_id, "Buyer"),
            session,
            payment_settings(),
            gateway,
        )
        order = await session.get(PaymentOrder, created["order_id"])
        assert order is not None
        gateway.verified = VerifiedPayment(
            payment_id="yk-payment-1",
            status="succeeded",
            paid=True,
            amount=Decimal("1.00"),
            currency="RUB",
            metadata={"air_order_id": str(order.id), "air_user_id": str(user.id), "plan_id": order.plan_id},
        )
        event = YooKassaWebhook(event="payment.succeeded", object={"id": "yk-payment-1"})
        assert await yookassa_webhook(event, session, gateway) == {"status": "ignored"}
        assert await session.scalar(
            select(func.count(Subscription.id)).where(Subscription.user_id == user.id)
        ) == 0
        assert order.status == PaymentOrderStatus.PENDING
    await engine.dispose()


@pytest.mark.parametrize(
    ("amount", "currency", "plan_id"),
    [
        (Decimal("1.00"), "RUB", "air_lifetime"),
        (Decimal("2450.00"), "USD", "air_lifetime"),
        (Decimal("2450.00"), "RUB", "air_30_days"),
    ],
)
@pytest.mark.asyncio
async def test_wrong_amount_currency_or_metadata_is_rejected(
    tmp_path: Path, amount: Decimal, currency: str, plan_id: str
) -> None:
    session, engine = await make_session(tmp_path)
    gateway = FakeGateway()
    async with session:
        user = await make_user(session)
        created = await create_payment(
            CreatePaymentRequest(plan_id="air_lifetime", email="buyer@example.com"),
            TelegramIdentity(user.telegram_id, "Buyer"),
            session,
            payment_settings(),
            gateway,
        )
        order = await session.get(PaymentOrder, created["order_id"])
        assert order is not None
        gateway.verified = VerifiedPayment(
            "yk-payment-1",
            "succeeded",
            True,
            amount,
            currency,
            {"air_order_id": str(order.id), "air_user_id": str(user.id), "plan_id": plan_id},
        )
        result = await yookassa_webhook(
            YooKassaWebhook(event="payment.succeeded", object={"id": "yk-payment-1"}),
            session,
            gateway,
        )
        assert result == {"status": "ignored"}
        assert await session.scalar(select(func.count(Subscription.id))) == 0
    await engine.dispose()


@pytest.mark.asyncio
async def test_canceled_payment_never_activates_access(tmp_path: Path) -> None:
    session, engine = await make_session(tmp_path)
    gateway = FakeGateway()
    async with session:
        user = await make_user(session)
        created = await create_payment(
            CreatePaymentRequest(plan_id="air_30_days", email="buyer@example.com"),
            TelegramIdentity(user.telegram_id, "Buyer"),
            session,
            payment_settings(),
            gateway,
        )
        order = await session.get(PaymentOrder, created["order_id"])
        assert order is not None
        gateway.verified = VerifiedPayment(
            "yk-payment-1",
            "canceled",
            False,
            Decimal("990.00"),
            "RUB",
            {"air_order_id": str(order.id), "air_user_id": str(user.id), "plan_id": order.plan_id},
        )
        result = await yookassa_webhook(
            YooKassaWebhook(event="payment.canceled", object={"id": "yk-payment-1"}),
            session,
            gateway,
        )
        assert result == {"status": "canceled"}
        assert order.status == PaymentOrderStatus.CANCELED
        assert await session.scalar(select(func.count(Subscription.id))) == 0
    await engine.dispose()


@pytest.mark.asyncio
async def test_30_day_purchase_extends_current_access_and_lifetime_has_no_end(tmp_path: Path) -> None:
    session, engine = await make_session(tmp_path)
    now = datetime(2026, 9, 1, tzinfo=timezone.utc)
    async with session:
        user = await make_user(session)
        existing_end = now + timedelta(days=10)
        session.add(
            Subscription(
                user_id=user.id,
                plan="air_30_days",
                status=SubscriptionStatus.ACTIVE,
                starts_at=now - timedelta(days=20),
                ends_at=existing_end,
            )
        )
        await session.flush()
        extended = await activate_paid_access(
            session, user_id=user.id, plan=PAYMENT_PLANS["air_30_days"], now=now
        )
        lifetime = await activate_paid_access(
            session, user_id=user.id, plan=PAYMENT_PLANS["air_lifetime"], now=now
        )
        assert extended.ends_at == existing_end + timedelta(days=30)
        assert lifetime.ends_at is None
        assert lifetime.plan == "air_lifetime"
    await engine.dispose()


@pytest.mark.asyncio
async def test_user_cannot_read_another_users_order(tmp_path: Path) -> None:
    session, engine = await make_session(tmp_path)
    gateway = FakeGateway()
    async with session:
        owner = await make_user(session, 1001)
        created = await create_payment(
            CreatePaymentRequest(plan_id="air_30_days", email="owner@example.com"),
            TelegramIdentity(owner.telegram_id, "Owner"),
            session,
            payment_settings(),
            gateway,
        )
        stranger = await make_user(session, 2002)
        with pytest.raises(HTTPException) as exc_info:
            await payment_status(
                int(created["order_id"]),
                TelegramIdentity(stranger.telegram_id, "Stranger"),
                session,
                payment_settings(),
                gateway,
            )
        assert exc_info.value.status_code == 404
    await engine.dispose()


def test_return_url_preserves_configured_query() -> None:
    assert payment_return_url("https://air.example/mini-app/?source=paywall", 42) == (
        "https://air.example/mini-app/?source=paywall&payment=return&order_id=42"
    )
