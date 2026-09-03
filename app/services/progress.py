from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

from app.db.models import SmokingProfile, User
from app.services.program.content import PROGRAM_LENGTH
from app.services.program_content import RECOVERY_MILESTONES


def as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


@dataclass(frozen=True)
class ProgressSnapshot:
    elapsed_seconds: int
    days: int
    hours: int
    program_day: int
    money_saved: int
    units_avoided: float
    unit_label: str


UNIT_LABELS = {
    "cigarette": "сигарет",
    "stick": "стиков",
    "ml": "мл жидкости",
    "disposable_e_cigarette": "электронки",
    "pouch": "пакетиков",
    "session": "кальянных сессий",
}


class ProgressCalculator:
    def calculate(
        self,
        user: User,
        profile: SmokingProfile,
        streak_started_at: datetime | None,
        now: datetime | None = None,
    ) -> ProgressSnapshot:
        current = as_utc(now or datetime.now(timezone.utc))
        elapsed = (
            max(current - as_utc(streak_started_at), current - current)
            if streak_started_at is not None
            else current - current
        )
        seconds = int(elapsed.total_seconds())
        elapsed_days = Decimal(seconds) / Decimal(86400)
        money_saved = (
            Decimal(profile.yearly_expense) * elapsed_days / Decimal("365.25")
        ).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        unit = str(profile.consumption_parameters.get("unit", "unit"))
        if unit == "disposable_e_cigarette":
            days_per_device = Decimal(
                str(profile.consumption_parameters.get("days_per_device", 0))
            )
            units = (
                elapsed_days / days_per_device
                if days_per_device > 0
                else Decimal("0")
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        else:
            daily_units = Decimal(profile.daily_units or 0)
            units = (daily_units * elapsed_days).quantize(
                Decimal("0.1"), rounding=ROUND_HALF_UP
            )
        return ProgressSnapshot(
            elapsed_seconds=seconds,
            days=seconds // 86400,
            hours=(seconds % 86400) // 3600,
            program_day=self.program_day(user, current),
            money_saved=int(money_saved),
            units_avoided=float(units),
            unit_label=UNIT_LABELS.get(unit, "единиц никотина"),
        )

    def program_day(self, user: User, now: datetime | None = None) -> int:
        if user.program_started_at is None:
            return 1
        current = as_utc(now or datetime.now(timezone.utc))
        elapsed = max(current - as_utc(user.program_started_at), current - current)
        return min(PROGRAM_LENGTH, int(elapsed.total_seconds()) // 86400 + 1)


def recovery_timeline(elapsed_hours: int) -> list[dict[str, object]]:
    return [
        {
            "hours": item.hours,
            "title": item.title,
            "description": item.description,
            "reached": elapsed_hours >= item.hours,
        }
        for item in RECOVERY_MILESTONES
    ]


def nearest_recovery(elapsed_hours: int) -> dict[str, object]:
    timeline = recovery_timeline(elapsed_hours)
    return next((item for item in timeline if not item["reached"]), timeline[-1])
