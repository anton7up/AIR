from __future__ import annotations

import asyncio
import ipaddress
import logging
import math
import time
from collections import OrderedDict, deque
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import HTTPException, status
from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RateLimitPolicy:
    name: str
    requests: int
    window_seconds: int

    @property
    def refill_per_second(self) -> float:
        return self.requests / self.window_seconds


@dataclass
class _TokenBucket:
    tokens: float
    updated_at: float
    last_seen: float
    idle_ttl: float


class BoundedRateLimiter:
    def __init__(self, max_buckets: int = 10_000) -> None:
        self.max_buckets = max_buckets
        self._buckets: OrderedDict[tuple[str, str], _TokenBucket] = OrderedDict()
        self._lock = asyncio.Lock()
        self._operations = 0

    async def consume(
        self,
        policy: RateLimitPolicy,
        identifier: str,
        *,
        now: float | None = None,
    ) -> int | None:
        current = time.monotonic() if now is None else now
        key = (policy.name, identifier)
        async with self._lock:
            self._operations += 1
            if self._operations % 128 == 0:
                self._remove_expired(current)
            bucket = self._buckets.get(key)
            if bucket is None:
                if len(self._buckets) >= self.max_buckets:
                    self._buckets.popitem(last=False)
                bucket = _TokenBucket(
                    tokens=float(policy.requests),
                    updated_at=current,
                    last_seen=current,
                    idle_ttl=max(float(policy.window_seconds * 2), 60.0),
                )
                self._buckets[key] = bucket
            else:
                elapsed = max(0.0, current - bucket.updated_at)
                bucket.tokens = min(
                    float(policy.requests),
                    bucket.tokens + elapsed * policy.refill_per_second,
                )
                bucket.updated_at = current
                bucket.last_seen = current
                self._buckets.move_to_end(key)
            if bucket.tokens >= 1.0:
                bucket.tokens -= 1.0
                return None
            retry_after = math.ceil((1.0 - bucket.tokens) / policy.refill_per_second)
            return max(1, retry_after)

    def _remove_expired(self, now: float) -> None:
        expired = [
            key
            for key, bucket in self._buckets.items()
            if now - bucket.last_seen > bucket.idle_ttl
        ]
        for key in expired:
            self._buckets.pop(key, None)

    async def reset(self) -> None:
        async with self._lock:
            self._buckets.clear()
            self._operations = 0

    @property
    def bucket_count(self) -> int:
        return len(self._buckets)


class AdminLoginGuard:
    def __init__(
        self,
        *,
        attempts: int = 5,
        window_seconds: int = 600,
        max_clients: int = 2_048,
    ) -> None:
        self.attempts = attempts
        self.window_seconds = window_seconds
        self.max_clients = max_clients
        self._failures: OrderedDict[str, deque[float]] = OrderedDict()
        self._lock = asyncio.Lock()

    async def retry_after(self, client_ip: str, *, now: float | None = None) -> int | None:
        current = time.monotonic() if now is None else now
        async with self._lock:
            failures = self._failures.get(client_ip)
            if failures is None:
                return None
            self._trim(failures, current)
            if not failures:
                self._failures.pop(client_ip, None)
                return None
            self._failures.move_to_end(client_ip)
            if len(failures) < self.attempts:
                return None
            return max(1, math.ceil(self.window_seconds - (current - failures[0])))

    async def record_failure(self, client_ip: str, *, now: float | None = None) -> None:
        current = time.monotonic() if now is None else now
        async with self._lock:
            failures = self._failures.get(client_ip)
            if failures is None:
                if len(self._failures) >= self.max_clients:
                    self._failures.popitem(last=False)
                failures = deque()
                self._failures[client_ip] = failures
            self._trim(failures, current)
            failures.append(current)
            self._failures.move_to_end(client_ip)

    def _trim(self, failures: deque[float], now: float) -> None:
        threshold = now - self.window_seconds
        while failures and failures[0] <= threshold:
            failures.popleft()

    async def reset(self) -> None:
        async with self._lock:
            self._failures.clear()


class ExternalPaymentCallLimiter:
    def __init__(self, concurrency: int = 4) -> None:
        self.concurrency = concurrency
        self._global = asyncio.Semaphore(concurrency)
        self._registry_lock = asyncio.Lock()
        self._order_locks: dict[int, tuple[asyncio.Lock, int]] = {}

    @asynccontextmanager
    async def slot(self, order_id: int | None = None) -> AsyncIterator[None]:
        async with self._global:
            if order_id is None:
                yield
                return
            async with self._registry_lock:
                lock, references = self._order_locks.get(
                    order_id, (asyncio.Lock(), 0)
                )
                self._order_locks[order_id] = (lock, references + 1)
            await lock.acquire()
            try:
                yield
            finally:
                lock.release()
                async with self._registry_lock:
                    current_lock, references = self._order_locks[order_id]
                    if references == 1:
                        self._order_locks.pop(order_id, None)
                    else:
                        self._order_locks[order_id] = (
                            current_lock,
                            references - 1,
                        )


GLOBAL_IP_POLICY = RateLimitPolicy("global_ip", 600, 60)
WEBHOOK_IP_POLICY = RateLimitPolicy("yookassa_webhook_ip", 60, 60)
NORMAL_READ_POLICY = RateLimitPolicy("normal_read", 120, 60)
PROGRAM_WRITE_POLICY = RateLimitPolicy("program_write", 30, 60)
USER_EVENT_POLICY = RateLimitPolicy("user_event", 10, 60)
SUPPORT_POLICY = RateLimitPolicy("support_message", 5, 600)
PAYMENT_CREATE_POLICY = RateLimitPolicy("payment_create", 3, 600)
PAYMENT_STATUS_POLICY = RateLimitPolicy("payment_status", 30, 300)

rate_limiter = BoundedRateLimiter()
admin_login_guard = AdminLoginGuard()
payment_call_limiter = ExternalPaymentCallLimiter()


class ProductionTrustedHostMiddleware:
    def __init__(self, app: ASGIApp, allowed_hosts: tuple[str, ...]) -> None:
        self.app = app
        self.allowed_hosts = {host.casefold() for host in allowed_hosts}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return
        raw_host = Headers(scope=scope).get("host", "")
        host = (
            raw_host.partition("]")[0] + "]"
            if raw_host.startswith("[")
            else raw_host.partition(":")[0]
        )
        if host.casefold() not in self.allowed_hosts:
            logger.warning("Rejected untrusted HTTP Host header")
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1008})
                return
            response = PlainTextResponse("Invalid host header", status_code=400)
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp, *, production: bool) -> None:
        self.app = app
        self.production = production

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-Content-Type-Options"] = "nosniff"
                headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
                headers["Permissions-Policy"] = (
                    "camera=(), microphone=(), geolocation=()"
                )
                if self.production:
                    headers["Strict-Transport-Security"] = (
                        "max-age=31536000; includeSubDomains"
                    )
            await send(message)

        await self.app(scope, receive, send_with_headers)


def raise_rate_limit(retry_after: int) -> None:
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Too many requests",
        headers={"Retry-After": str(retry_after)},
    )


def rate_limit_response(retry_after: int) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        headers={"Retry-After": str(retry_after)},
        content={"detail": "Too many requests", "retry_after": retry_after},
    )


class TrustedProxyResolver:
    def __init__(self, trusted_proxy_cidrs: str) -> None:
        self.networks = tuple(
            ipaddress.ip_network(value.strip(), strict=False)
            for value in trusted_proxy_cidrs.split(",")
            if value.strip()
        )

    def is_trusted(self, peer_ip: str) -> bool:
        try:
            peer = ipaddress.ip_address(peer_ip)
        except ValueError:
            return False
        return any(peer in network for network in self.networks)

    def resolve(self, peer_ip: str, forwarded_for: str | None) -> str:
        if not forwarded_for or not self.is_trusted(peer_ip):
            return peer_ip
        addresses: list[str] = []
        for raw_value in forwarded_for.split(","):
            value = raw_value.strip()
            try:
                addresses.append(str(ipaddress.ip_address(value)))
            except ValueError:
                continue
        for address in reversed(addresses):
            if not self.is_trusted(address):
                return address
        return addresses[0] if addresses else peer_ip


class PayloadTooLarge(Exception):
    pass


class SecurityMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        trusted_proxy_cidrs: str,
        max_request_body_bytes: int,
        limiter: BoundedRateLimiter = rate_limiter,
        global_ip_policy: RateLimitPolicy = GLOBAL_IP_POLICY,
        webhook_ip_policy: RateLimitPolicy = WEBHOOK_IP_POLICY,
    ) -> None:
        self.app = app
        self.proxy_resolver = TrustedProxyResolver(trusted_proxy_cidrs)
        self.max_request_body_bytes = max_request_body_bytes
        self.limiter = limiter
        self.global_ip_policy = global_ip_policy
        self.webhook_ip_policy = webhook_ip_policy

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = self._headers(scope)
        peer = scope.get("client")
        peer_ip = peer[0] if peer else "unknown"
        client_ip = self.proxy_resolver.resolve(peer_ip, headers.get("x-forwarded-for"))
        scope["client"] = (client_ip, peer[1] if peer else 0)
        state = scope.setdefault("state", {})
        state["peer_ip"] = peer_ip
        state["client_ip"] = client_ip

        if self.proxy_resolver.is_trusted(peer_ip):
            forwarded_proto = headers.get("x-forwarded-proto", "").strip().lower()
            if forwarded_proto in {"http", "https"}:
                scope["scheme"] = forwarded_proto

        path = str(scope.get("path", ""))
        if path.startswith("/api/"):
            retry_after = await self.limiter.consume(
                self.global_ip_policy, client_ip
            )
            if retry_after is not None:
                logger.warning("Security rate limit triggered: bucket=global_ip path=%s", path)
                await rate_limit_response(retry_after)(scope, receive, send)
                return
            if path == "/api/v1/payments/yookassa/webhook":
                retry_after = await self.limiter.consume(
                    self.webhook_ip_policy, client_ip
                )
                if retry_after is not None:
                    logger.warning("Security rate limit triggered: bucket=webhook path=%s", path)
                    await rate_limit_response(retry_after)(scope, receive, send)
                    return

        body_limit = self._body_limit(path)
        content_length = headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > body_limit:
                    await self._payload_too_large(scope, receive, send)
                    return
            except ValueError:
                pass

        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > body_limit:
                    raise PayloadTooLarge
            return message

        try:
            await self.app(scope, limited_receive, send)
        except PayloadTooLarge:
            await self._payload_too_large(scope, receive, send)

    @staticmethod
    def _headers(scope: Scope) -> dict[str, str]:
        return {
            key.decode("latin1").lower(): value.decode("latin1")
            for key, value in scope.get("headers", [])
        }

    def _body_limit(self, path: str) -> int:
        if path == "/api/v1/admin/login":
            return min(self.max_request_body_bytes, 8 * 1024)
        if path == "/api/v1/payments/yookassa/webhook":
            return min(self.max_request_body_bytes, 64 * 1024)
        if path == "/api/v1/payments/create":
            return min(self.max_request_body_bytes, 16 * 1024)
        if (
            path.endswith("/nicotine-desire")
            or path.endswith("/lapse")
            or path.endswith("/quit-attempt/restart")
        ):
            return min(self.max_request_body_bytes, 32 * 1024)
        if path.startswith("/api/v1/mini-app/sos") or path.startswith(
            "/api/v1/mini-app/program"
        ):
            return min(self.max_request_body_bytes, 64 * 1024)
        return self.max_request_body_bytes

    @staticmethod
    async def _payload_too_large(scope: Scope, receive: Receive, send: Send) -> None:
        response = JSONResponse(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            content={"detail": "Payload too large"},
        )
        await response(scope, receive, send)
