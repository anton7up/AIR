from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.db.models import NicotineType, SmokingProfile, User
from app.services.progress import ProgressCalculator


def test_progress_is_calculated_from_quit_time_and_profile() -> None:
    now = datetime(2026, 1, 4, 12, tzinfo=timezone.utc)
    user = User(
        telegram_id=1,
        telegram_first_name="Alex",
        quit_started_at=now - timedelta(days=3, hours=4),
        program_started_at=now - timedelta(days=3, hours=4),
    )
    profile = SmokingProfile(
        user_id=1,
        nicotine_type=NicotineType.CIGARETTES,
        years_of_use=Decimal("5"),
        daily_units=Decimal("15"),
        consumption_parameters={"unit": "cigarette"},
        cost_parameters={},
        monthly_expense=Decimal("4500"),
        yearly_expense=Decimal("54000"),
        lifetime_expense=Decimal("270000"),
        projected_five_year_expense=Decimal("270000"),
    )
    result = ProgressCalculator().calculate(user, profile, user.quit_started_at, now)
    assert result.days == 3
    assert result.hours == 4
    assert result.program_day == 4
    assert result.units_avoided == 47.5


def test_program_day_does_not_reset_with_quit_streak() -> None:
    now = datetime(2026, 1, 9, 12, tzinfo=timezone.utc)
    user = User(
        telegram_id=1,
        telegram_first_name="Alex",
        program_started_at=now - timedelta(days=8),
        quit_started_at=now - timedelta(days=3, hours=11),
    )
    profile = SmokingProfile(
        user_id=1,
        nicotine_type=NicotineType.CIGARETTES,
        years_of_use=Decimal("5"),
        daily_units=Decimal("15"),
        consumption_parameters={"unit": "cigarette"},
        cost_parameters={},
        monthly_expense=Decimal("4500"),
        yearly_expense=Decimal("54000"),
        lifetime_expense=Decimal("270000"),
        projected_five_year_expense=Decimal("270000"),
    )
    result = ProgressCalculator().calculate(user, profile, user.quit_started_at, now)
    assert result.program_day == 9
    assert result.days == 3


def test_streak_uses_explicit_active_attempt_start_instead_of_legacy_field() -> None:
    now = datetime(2026, 1, 9, 12, tzinfo=timezone.utc)
    user = User(
        telegram_id=1,
        telegram_first_name="Alex",
        program_started_at=now - timedelta(days=8),
        quit_started_at=now - timedelta(days=100),
    )
    profile = SmokingProfile(
        user_id=1,
        nicotine_type=NicotineType.CIGARETTES,
        years_of_use=Decimal("5"),
        daily_units=Decimal("15"),
        consumption_parameters={"unit": "cigarette"},
        cost_parameters={},
        monthly_expense=Decimal("4500"),
        yearly_expense=Decimal("54000"),
        lifetime_expense=Decimal("270000"),
        projected_five_year_expense=Decimal("270000"),
    )
    result = ProgressCalculator().calculate(
        user, profile, now - timedelta(minutes=7), now
    )
    assert result.elapsed_seconds == 420
    assert result.days == 0
    assert result.hours == 0
    assert result.program_day == 9


@pytest.mark.parametrize(
    ("days", "expected_units", "expected_money"),
    [
        (1, 0.25, 200),
        (2, 0.5, 400),
        (3, 0.75, 600),
        (4, 1.0, 800),
        (10, 2.5, 2000),
    ],
)
def test_disposable_progress_keeps_fractional_devices(
    days: int, expected_units: float, expected_money: int
) -> None:
    now = datetime(2026, 1, 11, 12, tzinfo=timezone.utc)
    user = User(telegram_id=2, telegram_first_name="Alex")
    profile = SmokingProfile(
        user_id=2,
        nicotine_type=NicotineType.DISPOSABLE,
        years_of_use=Decimal("0"),
        daily_units=Decimal("0.25"),
        package_price=Decimal("800"),
        consumption_parameters={
            "days_per_device": 4,
            "puffs_per_device": 1600,
            "unit": "disposable_e_cigarette",
        },
        cost_parameters={"device_price_rub": 800},
        monthly_expense=Decimal("6087.50"),
        yearly_expense=Decimal("73050"),
        lifetime_expense=Decimal("0"),
        projected_five_year_expense=Decimal("365250"),
    )

    result = ProgressCalculator().calculate(
        user, profile, now - timedelta(days=days), now
    )

    assert result.units_avoided == expected_units
    assert result.money_saved == expected_money
    assert result.unit_label == "электронки"
