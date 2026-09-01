from __future__ import annotations

import asyncio
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from yookassa import Configuration, Payment  # type: ignore[import-untyped]


@dataclass(frozen=True)
class CreatedPayment:
    payment_id: str
    status: str
    confirmation_url: str


@dataclass(frozen=True)
class VerifiedPayment:
    payment_id: str
    status: str
    paid: bool
    amount: Decimal
    currency: str
    metadata: dict[str, str]


class YooKassaGateway(Protocol):
    async def create_payment(
        self,
        *,
        amount: Decimal,
        currency: str,
        description: str,
        return_url: str,
        metadata: dict[str, str],
        idempotency_key: str,
    ) -> CreatedPayment: ...

    async def get_payment(self, payment_id: str) -> VerifiedPayment: ...


class SdkYooKassaGateway:
    """Small async adapter around YooKassa's official synchronous Python SDK."""

    def __init__(self, shop_id: str, secret_key: str) -> None:
        Configuration.configure(shop_id, secret_key)

    async def create_payment(
        self,
        *,
        amount: Decimal,
        currency: str,
        description: str,
        return_url: str,
        metadata: dict[str, str],
        idempotency_key: str,
    ) -> CreatedPayment:
        response = await asyncio.to_thread(
            Payment.create,
            {
                "amount": {"value": f"{amount:.2f}", "currency": currency},
                "capture": True,
                "confirmation": {"type": "redirect", "return_url": return_url},
                "description": description,
                "metadata": metadata,
            },
            idempotency_key,
        )
        confirmation_url = getattr(response.confirmation, "confirmation_url", None)
        if not confirmation_url:
            raise RuntimeError("YooKassa did not return a confirmation URL")
        return CreatedPayment(
            payment_id=str(response.id),
            status=str(response.status),
            confirmation_url=str(confirmation_url),
        )

    async def get_payment(self, payment_id: str) -> VerifiedPayment:
        response = await asyncio.to_thread(Payment.find_one, payment_id)
        raw_metadata = getattr(response, "metadata", None) or {}
        metadata = {
            str(key): str(value)
            for key, value in dict(raw_metadata).items()
        }
        return VerifiedPayment(
            payment_id=str(response.id),
            status=str(response.status),
            paid=bool(response.paid),
            amount=Decimal(str(response.amount.value)),
            currency=str(response.amount.currency),
            metadata=metadata,
        )
