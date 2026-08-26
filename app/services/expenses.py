from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.db.models import NicotineType

DAYS_PER_MONTH = Decimal("30.4375")
DAYS_PER_YEAR = Decimal("365.25")
WEEKS_PER_YEAR = Decimal("52.1775")
MONEY = Decimal("0.01")


def decimal(value: Any) -> Decimal:
    return Decimal(str(value))


def money(value: Decimal) -> Decimal:
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class ExpenseResult:
    monthly: Decimal
    yearly: Decimal
    lifetime: Decimal
    five_year_projection: Decimal
    daily_units: Decimal | None = None
    units_per_package: Decimal | None = None
    package_price: Decimal | None = None
    consumption_parameters: dict[str, Any] = field(default_factory=dict)
    cost_parameters: dict[str, Any] = field(default_factory=dict)


class ExpenseStrategy(ABC):
    @abstractmethod
    def calculate(self, answers: dict[str, Any]) -> ExpenseResult:
        raise NotImplementedError

    def result(
        self,
        yearly: Decimal,
        years: Decimal,
        **kwargs: Any,
    ) -> ExpenseResult:
        return ExpenseResult(
            monthly=money(yearly / Decimal("12")),
            yearly=money(yearly),
            lifetime=money(yearly * years),
            five_year_projection=money(yearly * Decimal("5")),
            **kwargs,
        )


class PackagedDailyStrategy(ExpenseStrategy):
    def __init__(self, daily_key: str, years_key: str, size_key: str, price_key: str, unit: str) -> None:
        self.daily_key = daily_key
        self.years_key = years_key
        self.size_key = size_key
        self.price_key = price_key
        self.unit = unit

    def calculate(self, answers: dict[str, Any]) -> ExpenseResult:
        daily = decimal(answers[self.daily_key])
        years = decimal(answers[self.years_key])
        size = decimal(answers[self.size_key])
        price = decimal(answers[self.price_key])
        yearly = daily / size * price * DAYS_PER_YEAR
        return self.result(
            yearly,
            years,
            daily_units=daily,
            units_per_package=size,
            package_price=price,
            consumption_parameters={"daily_units": float(daily), "unit": self.unit},
            cost_parameters={"units_per_package": float(size), "package_price_rub": float(price)},
        )


class HookahExpenseStrategy(ExpenseStrategy):
    def calculate(self, answers: dict[str, Any]) -> ExpenseResult:
        weekly_sessions = decimal(answers["hookah_weekly_sessions"])
        years = decimal(answers["hookah_years"])
        session_price = decimal(answers["hookah_session_price"])
        yearly = weekly_sessions * session_price * WEEKS_PER_YEAR
        return self.result(
            yearly,
            years,
            daily_units=weekly_sessions / Decimal("7"),
            package_price=session_price,
            consumption_parameters={"weekly_sessions": float(weekly_sessions), "unit": "session"},
            cost_parameters={"session_price_rub": float(session_price)},
        )


STRATEGIES: dict[NicotineType, ExpenseStrategy] = {
    NicotineType.CIGARETTES: PackagedDailyStrategy("cig_daily", "cig_years", "cig_pack_size", "cig_pack_price", "cigarette"),
    NicotineType.HEATED_TOBACCO: PackagedDailyStrategy("heated_daily", "heated_years", "heated_pack_size", "heated_pack_price", "stick"),
    NicotineType.VAPE: PackagedDailyStrategy("vape_daily_ml", "vape_years", "vape_bottle_ml", "vape_bottle_price", "ml"),
    NicotineType.SNUS: PackagedDailyStrategy("snus_daily_pouches", "snus_years", "snus_can_size", "snus_can_price", "pouch"),
    NicotineType.HOOKAH: HookahExpenseStrategy(),
}


class ExpenseCalculator:
    def calculate(self, answers: dict[str, Any]) -> ExpenseResult:
        nicotine_type = NicotineType(answers["nicotine_type"])
        return STRATEGIES[nicotine_type].calculate(answers)

