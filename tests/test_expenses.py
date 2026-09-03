from decimal import Decimal

import pytest

from app.services.expenses import ExpenseCalculator


def test_cigarette_expenses() -> None:
    result = ExpenseCalculator().calculate({
        "nicotine_type": "cigarettes",
        "cig_daily": 20,
        "cig_years": 10,
        "cig_pack_size": 20,
        "cig_pack_price": 200,
    })

    assert result.yearly == Decimal("73050.00")
    assert result.monthly == Decimal("6087.50")
    assert result.lifetime == Decimal("730500.00")
    assert result.five_year_projection == Decimal("365250.00")


def test_vape_uses_replaceable_ml_strategy() -> None:
    result = ExpenseCalculator().calculate({
        "nicotine_type": "vape",
        "vape_daily_ml": 2,
        "vape_years": 3,
        "vape_bottle_ml": 30,
        "vape_bottle_price": 600,
    })

    assert result.yearly == Decimal("14610.00")
    assert result.lifetime == Decimal("43830.00")
    assert result.consumption_parameters["unit"] == "ml"


def test_disposable_e_cigarette_uses_days_and_device_price() -> None:
    result = ExpenseCalculator().calculate(
        {
            "nicotine_type": "disposable_e_cigarette",
            "disposable_days_per_device": 4,
            "disposable_puffs_per_device": 1600,
            "disposable_device_price": 800,
            "disposable_years": 3,
        }
    )

    assert result.daily_units == Decimal("0.25")
    assert result.monthly == Decimal("6087.50")
    assert result.yearly == Decimal("73050.00")
    assert result.lifetime == Decimal("219150.00")
    assert result.five_year_projection == Decimal("365250.00")
    assert result.consumption_parameters == {
        "days_per_device": 4.0,
        "puffs_per_device": 1600.0,
        "daily_units": 0.25,
        "unit": "disposable_e_cigarette",
    }
    assert result.cost_parameters == {"device_price_rub": 800.0}


def test_disposable_daily_cost_and_historical_spending_regression() -> None:
    result = ExpenseCalculator().calculate(
        {
            "nicotine_type": "disposable_e_cigarette",
            "disposable_days_per_device": 3,
            "disposable_puffs_per_device": 2000,
            "disposable_device_price": 1000,
            "disposable_years": 4,
        }
    )

    assert result.yearly == Decimal("121750.00")
    assert result.monthly == Decimal("10145.83")
    assert result.lifetime == Decimal("487000.00")
    assert result.lifetime > 0


def test_disposable_rejects_zero_days_per_device() -> None:
    with pytest.raises(ValueError, match="greater than zero"):
        ExpenseCalculator().calculate(
            {
                "nicotine_type": "disposable_e_cigarette",
                "disposable_days_per_device": 0,
                "disposable_puffs_per_device": 2000,
                "disposable_device_price": 1000,
                "disposable_years": 4,
            }
        )


def test_hookah_calculation_is_weekly() -> None:
    result = ExpenseCalculator().calculate({
        "nicotine_type": "hookah",
        "hookah_weekly_sessions": 2,
        "hookah_years": 4,
        "hookah_session_price": 1500,
    })

    assert result.yearly == Decimal("156532.50")
    assert result.lifetime == Decimal("626130.00")


def test_unknown_nicotine_type_is_rejected() -> None:
    with pytest.raises(ValueError):
        ExpenseCalculator().calculate({"nicotine_type": "unknown"})
