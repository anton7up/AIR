import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl

from fastapi import Depends, Header, HTTPException, status

from app.core.config import Settings, get_settings


@dataclass(frozen=True)
class TelegramIdentity:
    telegram_id: int
    first_name: str
    username: str | None = None
    is_development: bool = False


def validate_init_data(
    init_data: str,
    bot_token: str,
    max_age_seconds: int,
    now: int | None = None,
) -> TelegramIdentity:
    values = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = values.pop("hash", None)
    if not received_hash:
        raise ValueError("В Telegram initData отсутствует подпись")
    data_check_string = "\n".join(f"{key}={values[key]}" for key in sorted(values))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_hash, received_hash):
        raise ValueError("Подпись Telegram initData недействительна")

    auth_date = int(values.get("auth_date", "0"))
    current_time = now if now is not None else int(time.time())
    if auth_date <= 0 or current_time - auth_date > max_age_seconds or auth_date > current_time + 30:
        raise ValueError("Срок действия Telegram initData истёк")
    user_data = json.loads(values.get("user", "{}"))
    if "id" not in user_data:
        raise ValueError("В Telegram initData отсутствует пользователь")
    return TelegramIdentity(
        telegram_id=int(user_data["id"]),
        first_name=str(user_data.get("first_name", "Пользователь")),
        username=user_data.get("username"),
    )


async def get_telegram_identity(
    init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
    dev_telegram_id: int | None = Header(default=None, alias="X-Dev-Telegram-Id"),
    settings: Settings = Depends(get_settings),
) -> TelegramIdentity:
    if init_data:
        if settings.bot_token is None:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Авторизация Telegram временно недоступна")
        try:
            return validate_init_data(
                init_data,
                settings.bot_token.get_secret_value(),
                settings.telegram_init_data_max_age_seconds,
            )
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Не удалось подтвердить данные Telegram") from exc
    if settings.development_access_enabled and dev_telegram_id is not None:
        return TelegramIdentity(dev_telegram_id, "Dev", is_development=True)
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Открой AIR из Telegram")
