from app.bot.keyboards.onboarding import consent_declined_keyboard, consent_keyboard
from app.bot.texts.messages import (
    PERSONAL_DATA_CONSENT,
    PERSONAL_DATA_CONSENT_DECLINED,
)
from app.services.consent import personal_data_consent_url


def test_bot_consent_copy_and_choices() -> None:
    assert "в моменты тяги к никотину" in PERSONAL_DATA_CONSENT
    assert "Подробнее: Согласие на обработку персональных данных" in PERSONAL_DATA_CONSENT
    keyboard = consent_keyboard("https://airtgbot.ru/personal-data-consent")
    assert keyboard.inline_keyboard[0][0].url == "https://airtgbot.ru/personal-data-consent"
    assert keyboard.inline_keyboard[1][0].callback_data == "consent:accept"
    assert keyboard.inline_keyboard[2][0].callback_data == "consent:decline"


def test_decline_copy_can_return_or_close() -> None:
    assert "AIR не сможет персонализировать программу" in PERSONAL_DATA_CONSENT_DECLINED
    callbacks = [row[0].callback_data for row in consent_declined_keyboard().inline_keyboard]
    assert callbacks == ["consent:return", "consent:close"]


def test_legal_url_uses_existing_mini_app_origin() -> None:
    assert personal_data_consent_url("https://airtgbot.ru/mini-app/") == (
        "https://airtgbot.ru/personal-data-consent"
    )
