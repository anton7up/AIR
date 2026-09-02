import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from httpx import ASGITransport, AsyncClient

from app.api.admin import AdminLoginRequest, admin_login
from app.api.auth import TelegramIdentity, get_rate_limited_telegram_identity
from app.api.main import standardized_http_error
from app.core.config import Settings, get_settings
from app.core.security import (
    BoundedRateLimiter,
    RateLimitPolicy,
    SecurityMiddleware,
    TrustedProxyResolver,
    admin_login_guard,
    rate_limiter,
)

BOT_TOKEN = "security-test-token"


def security_settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="production",
        bot_token=BOT_TOKEN,
        admin_panel_password="strong-admin-password",
        telegram_init_data_max_age_seconds=3600,
    )


def signed_init_data(telegram_id: int) -> str:
    values = {
        "auth_date": str(int(time.time())),
        "query_id": f"security-{telegram_id}",
        "user": json.dumps(
            {"id": telegram_id, "first_name": "Security"},
            separators=(",", ":"),
        ),
    }
    check = "\n".join(f"{key}={values[key]}" for key in sorted(values))
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    values["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(values)


def identity_app(path: str, method: str = "GET") -> FastAPI:
    test_app = FastAPI()
    test_app.add_exception_handler(HTTPException, standardized_http_error)
    test_app.dependency_overrides[get_settings] = security_settings

    async def endpoint(
        identity: TelegramIdentity = Depends(get_rate_limited_telegram_identity),
    ) -> dict[str, int]:
        return {"telegram_id": identity.telegram_id}

    test_app.add_api_route(path, endpoint, methods=[method])
    return test_app


@pytest.mark.asyncio
async def test_user_rate_limit_isolated_by_verified_telegram_user() -> None:
    await rate_limiter.reset()
    test_app = identity_app("/api/v1/mini-app/dashboard")
    transport = ASGITransport(app=test_app, client=("198.51.100.10", 1234))
    async with AsyncClient(transport=transport, base_url="https://test") as client:
        first_headers = {"X-Telegram-Init-Data": signed_init_data(1001)}
        for _ in range(120):
            assert (
                await client.get(
                    "/api/v1/mini-app/dashboard", headers=first_headers
                )
            ).status_code == 200
        blocked = await client.get(
            "/api/v1/mini-app/dashboard", headers=first_headers
        )
        assert blocked.status_code == 429
        assert int(blocked.headers["Retry-After"]) >= 1
        assert blocked.json()["detail"] == "Too many requests"

        other = await client.get(
            "/api/v1/mini-app/dashboard",
            headers={"X-Telegram-Init-Data": signed_init_data(2002)},
        )
        assert other.status_code == 200


@pytest.mark.asyncio
async def test_nat_users_share_ip_without_sharing_user_bucket() -> None:
    await rate_limiter.reset()
    test_app = identity_app("/api/v1/mini-app/dashboard")
    test_app.add_middleware(
        SecurityMiddleware,
        trusted_proxy_cidrs="",
        max_request_body_bytes=262_144,
    )
    transport = ASGITransport(app=test_app, client=("198.51.100.20", 1234))
    async with AsyncClient(transport=transport, base_url="https://test") as client:
        for telegram_id in range(3001, 3011):
            headers = {"X-Telegram-Init-Data": signed_init_data(telegram_id)}
            for _ in range(10):
                response = await client.get(
                    "/api/v1/mini-app/dashboard", headers=headers
                )
                assert response.status_code == 200


@pytest.mark.asyncio
async def test_ip_flood_returns_structured_429() -> None:
    limiter = BoundedRateLimiter(max_buckets=10)
    test_app = FastAPI()

    @test_app.get("/api/test")
    async def endpoint() -> dict[str, bool]:
        return {"ok": True}

    test_app.add_middleware(
        SecurityMiddleware,
        trusted_proxy_cidrs="",
        max_request_body_bytes=1024,
        limiter=limiter,
        global_ip_policy=RateLimitPolicy("test_ip", 3, 60),
        webhook_ip_policy=RateLimitPolicy("test_webhook", 10, 60),
    )
    transport = ASGITransport(app=test_app, client=("203.0.113.5", 1234))
    async with AsyncClient(transport=transport, base_url="https://test") as client:
        for _ in range(3):
            assert (await client.get("/api/test")).status_code == 200
        blocked = await client.get("/api/test")
    assert blocked.status_code == 429
    assert blocked.json()["retry_after"] >= 1
    assert "Retry-After" in blocked.headers


def test_untrusted_peer_cannot_spoof_forwarded_for() -> None:
    resolver = TrustedProxyResolver("10.20.0.0/24")

    assert resolver.resolve("203.0.113.8", "1.2.3.4") == "203.0.113.8"


def test_trusted_caddy_peer_resolves_real_client_ip() -> None:
    resolver = TrustedProxyResolver("10.20.0.0/24")

    assert resolver.resolve("10.20.0.3", "198.51.100.42") == "198.51.100.42"


@pytest.mark.asyncio
async def test_proxy_resolution_is_applied_to_request_client() -> None:
    test_app = FastAPI()

    @test_app.get("/client")
    async def client_ip(request: Request) -> dict[str, str]:
        assert request.client is not None
        return {"client_ip": request.client.host}

    test_app.add_middleware(
        SecurityMiddleware,
        trusted_proxy_cidrs="10.20.0.0/24",
        max_request_body_bytes=1024,
        limiter=BoundedRateLimiter(max_buckets=10),
    )
    trusted_transport = ASGITransport(
        app=test_app, client=("10.20.0.3", 1234)
    )
    async with AsyncClient(
        transport=trusted_transport, base_url="https://test"
    ) as client:
        trusted = await client.get(
            "/client", headers={"X-Forwarded-For": "198.51.100.42"}
        )
    assert trusted.json() == {"client_ip": "198.51.100.42"}

    untrusted_transport = ASGITransport(
        app=test_app, client=("203.0.113.8", 1234)
    )
    async with AsyncClient(
        transport=untrusted_transport, base_url="https://test"
    ) as client:
        untrusted = await client.get(
            "/client", headers={"X-Forwarded-For": "1.2.3.4"}
        )
    assert untrusted.json() == {"client_ip": "203.0.113.8"}


@pytest.mark.asyncio
async def test_admin_login_blocks_bruteforce_per_real_ip() -> None:
    await admin_login_guard.reset()
    current_settings = security_settings()
    for _ in range(5):
        with pytest.raises(HTTPException) as exc_info:
            await admin_login(
                AdminLoginRequest(password="wrong"),
                Response(),
                current_settings,
                "198.51.100.50",
            )
        assert exc_info.value.status_code == 401

    with pytest.raises(HTTPException) as blocked_info:
        await admin_login(
            AdminLoginRequest(password="strong-admin-password"),
            Response(),
            current_settings,
            "198.51.100.50",
        )
    assert blocked_info.value.status_code == 429
    assert int(blocked_info.value.headers["Retry-After"]) >= 1

    assert await admin_login(
        AdminLoginRequest(password="strong-admin-password"),
        Response(),
        current_settings,
        "198.51.100.51",
    ) == {"authenticated": True}
    await admin_login_guard.reset()


@pytest.mark.asyncio
async def test_payment_create_and_status_have_separate_user_buckets() -> None:
    await rate_limiter.reset()
    create_app = identity_app("/api/v1/payments/create", "POST")
    create_transport = ASGITransport(app=create_app)
    headers = {"X-Telegram-Init-Data": signed_init_data(4001)}
    async with AsyncClient(
        transport=create_transport, base_url="https://test"
    ) as client:
        for _ in range(3):
            assert (
                await client.post("/api/v1/payments/create", headers=headers)
            ).status_code == 200
        assert (
            await client.post("/api/v1/payments/create", headers=headers)
        ).status_code == 429

    await rate_limiter.reset()
    status_app = identity_app("/api/v1/payments/{order_id}/status")
    status_transport = ASGITransport(app=status_app)
    async with AsyncClient(
        transport=status_transport, base_url="https://test"
    ) as client:
        for _ in range(30):
            assert (
                await client.get("/api/v1/payments/10/status", headers=headers)
            ).status_code == 200
        assert (
            await client.get("/api/v1/payments/10/status", headers=headers)
        ).status_code == 429
        assert (
            await client.get("/api/v1/payments/11/status", headers=headers)
        ).status_code == 200


@pytest.mark.asyncio
async def test_webhook_has_dedicated_ip_flood_limit() -> None:
    limiter = BoundedRateLimiter(max_buckets=10)
    test_app = FastAPI()

    @test_app.post("/api/v1/payments/yookassa/webhook")
    async def webhook() -> dict[str, str]:
        return {"status": "ok"}

    test_app.add_middleware(
        SecurityMiddleware,
        trusted_proxy_cidrs="",
        max_request_body_bytes=1024,
        limiter=limiter,
        global_ip_policy=RateLimitPolicy("test_global", 100, 60),
        webhook_ip_policy=RateLimitPolicy("test_webhook", 2, 60),
    )
    transport = ASGITransport(app=test_app, client=("203.0.113.9", 1234))
    async with AsyncClient(transport=transport, base_url="https://test") as client:
        assert (
            await client.post(
                "/api/v1/payments/yookassa/webhook", json={"event": "test"}
            )
        ).status_code == 200
        assert (
            await client.post(
                "/api/v1/payments/yookassa/webhook", json={"event": "test"}
            )
        ).status_code == 200
        blocked = await client.post(
            "/api/v1/payments/yookassa/webhook", json={"event": "test"}
        )
    assert blocked.status_code == 429


@pytest.mark.asyncio
async def test_request_body_limit_allows_normal_and_rejects_oversized() -> None:
    test_app = FastAPI()

    @test_app.post("/api/echo")
    async def echo(request: Request) -> dict[str, int]:
        body = await request.body()
        return {"size": len(body)}

    test_app.add_middleware(
        SecurityMiddleware,
        trusted_proxy_cidrs="",
        max_request_body_bytes=256,
        limiter=BoundedRateLimiter(max_buckets=10),
        global_ip_policy=RateLimitPolicy("body_global", 100, 60),
        webhook_ip_policy=RateLimitPolicy("body_webhook", 100, 60),
    )
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="https://test") as client:
        normal = await client.post("/api/echo", content=b"a" * 200)
        oversized = await client.post("/api/echo", content=b"a" * 257)

        async def chunked_body():
            yield b"a" * 200
            yield b"b" * 100

        chunked = await client.post("/api/echo", content=chunked_body())
    assert normal.status_code == 200
    assert oversized.status_code == 413
    assert oversized.json() == {"detail": "Payload too large"}
    assert chunked.status_code == 413


@pytest.mark.asyncio
async def test_limiter_state_is_bounded() -> None:
    limiter = BoundedRateLimiter(max_buckets=3)
    policy = RateLimitPolicy("bounded", 10, 60)
    for identifier in ("one", "two", "three", "four"):
        assert await limiter.consume(policy, identifier, now=1.0) is None
    assert limiter.bucket_count == 3
