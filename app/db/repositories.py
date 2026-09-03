from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Gender, NicotineType, SmokingProfile, User
from app.services.consent import require_current_personal_data_consent
from app.services.expenses import ExpenseResult


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def save_onboarding(
        self,
        telegram_id: int,
        first_name: str,
        username: str | None,
        answers: dict[str, Any],
        result: ExpenseResult,
    ) -> User:
        user = await self.session.scalar(
            select(User).where(User.telegram_id == telegram_id)
        )
        if user is None:
            raise ValueError("Сначала необходимо согласие на обработку персональных данных")
        require_current_personal_data_consent(user)

        user.telegram_first_name = first_name
        user.username = username
        user.gender = Gender(answers["gender"])
        user.had_quit_attempts = bool(answers["had_quit_attempts"])
        user.acquisition_source = str(answers["acquisition_source"])

        profile = await self.session.scalar(
            select(SmokingProfile).where(SmokingProfile.user_id == user.id)
        )
        if profile is None:
            profile = SmokingProfile(user_id=user.id)
            self.session.add(profile)

        nicotine_type = NicotineType(answers["nicotine_type"])
        years_key = {
            NicotineType.CIGARETTES: "cig_years",
            NicotineType.HEATED_TOBACCO: "heated_years",
            NicotineType.VAPE: "vape_years",
            NicotineType.DISPOSABLE: "disposable_years",
            NicotineType.SNUS: "snus_years",
            NicotineType.HOOKAH: "hookah_years",
        }[nicotine_type]
        profile.nicotine_type = nicotine_type
        profile.years_of_use = Decimal(str(answers[years_key]))
        profile.daily_units = result.daily_units
        profile.units_per_package = result.units_per_package
        profile.package_price = result.package_price
        profile.consumption_parameters = result.consumption_parameters
        profile.cost_parameters = result.cost_parameters
        profile.monthly_expense = result.monthly
        profile.yearly_expense = result.yearly
        profile.lifetime_expense = result.lifetime
        profile.projected_five_year_expense = result.five_year_projection

        await self.session.commit()
        await self.session.refresh(user)
        return user
