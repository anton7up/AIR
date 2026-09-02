import hashlib
import hmac
import json
from urllib.parse import urlencode

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.auth import get_telegram_identity, validate_init_data
from app.core.config import Settings


def signed_init_data(token: str, auth_date: int = 1_700_000_000) -> str:
    values = {
        "auth_date": str(auth_date),
        "query_id": "test-query",
        "user": json.dumps({"id": 42, "first_name": "Alex", "username": "alex"}, separators=(",", ":")),
    }
    check = "\n".join(f"{key}={values[key]}" for key in sorted(values))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    values["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(values)


def test_valid_telegram_init_data() -> None:
    identity = validate_init_data(signed_init_data("token"), "token", 3600, now=1_700_000_100)
    assert identity.telegram_id == 42
    assert identity.username == "alex"


def test_tampered_telegram_init_data_is_rejected() -> None:
    with pytest.raises(ValueError):
        validate_init_data(signed_init_data("token").replace("Alex", "Eve"), "token", 3600, now=1_700_000_100)


def test_expired_telegram_init_data_is_rejected() -> None:
    with pytest.raises(ValueError):
        validate_init_data(signed_init_data("token"), "token", 60, now=1_700_001_000)


def test_production_without_dev_auth_is_valid() -> None:
    settings = Settings(_env_file=None, app_env="production", dev_auth_enabled=False)

    assert settings.development_access_enabled is False


def test_production_with_dev_auth_fails_configuration() -> None:
    with pytest.raises(ValidationError, match="DEV_AUTH_ENABLED must be false"):
        Settings(_env_file=None, app_env="production", dev_auth_enabled=True)


@pytest.mark.asyncio
async def test_dev_header_is_rejected_when_disabled_in_development() -> None:
    settings = Settings(_env_file=None, app_env="development", dev_auth_enabled=False)

    with pytest.raises(HTTPException) as exc_info:
        await get_telegram_identity(
            init_data=None,
            dev_telegram_id=749408538,
            settings=settings,
        )

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_dev_header_is_allowed_only_when_enabled_in_development() -> None:
    settings = Settings(_env_file=None, app_env="development", dev_auth_enabled=True)

    identity = await get_telegram_identity(
        init_data=None,
        dev_telegram_id=749408538,
        settings=settings,
    )

    assert identity.telegram_id == 749408538
    assert identity.is_development is True


@pytest.mark.asyncio
async def test_dev_header_cannot_impersonate_in_production() -> None:
    settings = Settings(_env_file=None, app_env="production", dev_auth_enabled=False)

    with pytest.raises(HTTPException) as exc_info:
        await get_telegram_identity(
            init_data=None,
            dev_telegram_id=749408538,
            settings=settings,
        )

    assert exc_info.value.status_code == 401
