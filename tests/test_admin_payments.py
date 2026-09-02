import hashlib
import hmac
import json
from datetime import datetime, timezone
from decimal import Decimal
from http.cookies import SimpleCookie
from urllib.parse import urlencode

import pytest
from fastapi import FastAPI, HTTPException, Response
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.admin import (
    ADMIN_COOKIE_NAME,
    AdminLoginRequest,
    ReceiptStatusRequest,
    admin_login,
    admin_payments,
    require_admin,
    update_receipt_status,
)
from app.api.admin import (
    router as admin_router,
)
from app.core.config import Settings, get_settings
from app.core.security import admin_login_guard
from app.db.base import Base
from app.db.models import (
    PaymentOrder,
    PaymentOrderStatus,
    ReceiptStatus,
    User,
)
from app.db.session import get_session

ADMIN_ID = 700001
TESTER_ID = 700002
USER_ID = 700003
BOT_TOKEN = "test-bot-token"


def settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="production",
        bot_token=BOT_TOKEN,
        admin_telegram_ids=str(ADMIN_ID),
        admin_panel_password="strong-admin-password",
        tester_access_enabled=True,
        tester_telegram_ids=str(TESTER_ID),
        telegram_init_data_max_age_seconds=999_999_999,
    )


def signed_init_data(telegram_id: int, now: int) -> str:
    values = {
        "auth_date": str(now),
        "query_id": "admin-test",
        "user": json.dumps(
            {"id": telegram_id, "first_name": "Admin"}, separators=(",", ":")
        ),
    }
    check = "\n".join(f"{key}={values[key]}" for key in sorted(values))
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    values["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(values)


async def make_session(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'admin.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False)(), engine


async def make_existing_order(session) -> tuple[User, PaymentOrder]:
    user = User(
        telegram_id=USER_ID,
        telegram_first_name="Buyer",
        receipt_email="buyer@example.com",
    )
    session.add(user)
    await session.flush()
    order = PaymentOrder(
        user_id=user.id,
        plan_id="air_30_days",
        amount=Decimal("990.00"),
        currency="RUB",
        status=PaymentOrderStatus.SUCCEEDED,
        yookassa_payment_id="yk-existing-payment",
        idempotency_key="11111111-1111-1111-1111-111111111111",
        receipt_email="buyer@example.com",
        paid_at=datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc),
    )
    session.add(order)
    await session.commit()
    await session.refresh(order)
    return user, order


@pytest.mark.asyncio
@pytest.mark.parametrize("telegram_id", [USER_ID, TESTER_ID])
async def test_regular_user_and_tester_cannot_access_admin(telegram_id: int) -> None:
    now = 1_700_000_000
    with pytest.raises(HTTPException) as exc_info:
        await require_admin(
            init_data=signed_init_data(telegram_id, now),
            admin_session=None,
            settings=settings(),
        )
    # initData is valid; access is rejected solely by the separate admin allowlist.
    assert exc_info.value.status_code in {401, 403}


@pytest.mark.asyncio
async def test_admin_telegram_init_data_gets_access(monkeypatch) -> None:
    now = 1_700_000_000
    monkeypatch.setattr("app.api.auth.time.time", lambda: now)
    monkeypatch.setattr("app.api.admin.time.time", lambda: now)
    assert await require_admin(
        init_data=signed_init_data(ADMIN_ID, now),
        admin_session=None,
        settings=settings(),
    ) == "telegram"


@pytest.mark.asyncio
async def test_wrong_password_is_rejected_and_correct_password_sets_secure_cookie() -> None:
    await admin_login_guard.reset()
    response = Response()
    with pytest.raises(HTTPException) as exc_info:
        await admin_login(
            AdminLoginRequest(password="wrong"),
            response,
            settings(),
            "198.51.100.100",
        )
    assert exc_info.value.status_code == 401

    response = Response()
    assert await admin_login(
        AdminLoginRequest(password="strong-admin-password"),
        response,
        settings(),
        "198.51.100.100",
    ) == {"authenticated": True}
    header = response.headers["set-cookie"]
    assert "HttpOnly" in header
    assert "Secure" in header
    assert "SameSite=strict" in header
    assert "Path=/api/v1/admin" in header
    cookies = SimpleCookie()
    cookies.load(header)
    session_value = cookies[ADMIN_COOKIE_NAME].value
    assert await require_admin(
        init_data=None,
        admin_session=session_value,
        settings=settings(),
    ) == "session"


@pytest.mark.asyncio
async def test_pc_login_cookie_access_and_legacy_payment_flow(tmp_path) -> None:
    session, engine = await make_session(tmp_path)
    async with session:
        user, order = await make_existing_order(session)
        telegram_id = user.telegram_id
        # This is the exact value written by the additive production migration.
        # receipt_sent_at intentionally remains NULL, as it is for an old order.
        await session.execute(
            text("UPDATE payment_orders SET receipt_status = 'pending' WHERE id = :id"),
            {"id": order.id},
        )
        await session.commit()
        session.expire_all()

        test_app = FastAPI()
        test_app.include_router(admin_router)
        test_app.dependency_overrides[get_settings] = settings

        async def override_session():
            yield session

        test_app.dependency_overrides[get_session] = override_session
        transport = ASGITransport(app=test_app)
        async with AsyncClient(
            transport=transport,
            base_url="https://testserver",
        ) as client:
            assert (await client.get("/api/v1/admin/access")).status_code == 401
            assert (await client.get("/api/v1/admin/payments")).status_code == 401
            assert (
                await client.post(
                    "/api/v1/admin/login", json={"password": "wrong"}
                )
            ).status_code == 401

            login = await client.post(
                "/api/v1/admin/login",
                json={"password": "strong-admin-password"},
            )
            assert login.status_code == 200
            assert ADMIN_COOKIE_NAME in client.cookies
            assert "Path=/api/v1/admin" in login.headers["set-cookie"]
            assert "Secure" in login.headers["set-cookie"]
            assert "HttpOnly" in login.headers["set-cookie"]

            access = await client.get("/api/v1/admin/access")
            assert access.status_code == 200
            assert access.json() == {"is_admin": True}

            payments = await client.get("/api/v1/admin/payments")
            assert payments.status_code == 200
            payload = payments.json()
            assert payload["orders"][0]["telegram_user_id"] == telegram_id
            assert payload["orders"][0]["status"] == "succeeded"
            assert payload["orders"][0]["receipt_status"] == "pending"
            assert payload["orders"][0]["receipt_sent_at"] is None
    await engine.dispose()


@pytest.mark.asyncio
async def test_admin_lists_existing_succeeded_payment_and_receipt_is_idempotent(tmp_path) -> None:
    session, engine = await make_session(tmp_path)
    async with session:
        user, order = await make_existing_order(session)
        payload = await admin_payments("telegram", session)
        assert payload["stats"] == {
            "successful_count": 1,
            "revenue": "990.00",
            "receipts_pending": 1,
            "receipts_sent": 0,
        }
        listed = payload["orders"][0]
        assert listed["telegram_user_id"] == user.telegram_id
        assert listed["email"] == "buyer@example.com"
        assert listed["plan_title"] == "30 дней"
        assert listed["status"] == "succeeded"
        assert listed["receipt_status"] == "pending"

        first = await update_receipt_status(
            order.id, ReceiptStatusRequest(status="sent"), "telegram", session
        )
        first_sent_at = first["receipt_sent_at"]
        assert first["receipt_status"] == "sent"
        assert first_sent_at is not None
        repeated = await update_receipt_status(
            order.id, ReceiptStatusRequest(status="sent"), "telegram", session
        )
        assert repeated["receipt_sent_at"] == first_sent_at
        reverted = await update_receipt_status(
            order.id, ReceiptStatusRequest(status="pending"), "telegram", session
        )
        assert reverted == {
            "id": order.id,
            "receipt_status": ReceiptStatus.PENDING.value,
            "receipt_sent_at": None,
        }
    await engine.dispose()


@pytest.mark.asyncio
async def test_regular_user_cannot_authorize_receipt_change() -> None:
    now = 1_700_000_000
    with pytest.raises(HTTPException) as exc_info:
        await require_admin(
            init_data=signed_init_data(USER_ID, now),
            admin_session=None,
            settings=settings(),
        )
    assert exc_info.value.status_code in {401, 403}
