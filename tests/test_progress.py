from datetime import datetime, timedelta, timezone
from decimal import Decimal

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
