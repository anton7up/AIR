from decimal import Decimal

from app.bot.texts.messages import result_message


def test_result_message_says_air_is_cheaper_above_990_monthly() -> None:
    message = result_message(
        Decimal("990.01"), Decimal("11880"), Decimal("100000"), Decimal("59400")
    )

    assert "будет дешевле, чем продолжать курить всего один месяц" in message


def test_result_message_uses_same_cost_wording_at_or_below_990_monthly() -> None:
    for monthly in (Decimal("990"), Decimal("500")):
        message = result_message(
            monthly, Decimal("11880"), Decimal("100000"), Decimal("59400")
        )
        assert "будет стоить примерно столько же" in message
