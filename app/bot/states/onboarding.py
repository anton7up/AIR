from aiogram.fsm.state import State, StatesGroup


class OnboardingStates(StatesGroup):
    awaiting_consent = State()
    consent_declined = State()
    answering = State()
