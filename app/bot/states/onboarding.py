from aiogram.fsm.state import State, StatesGroup


class OnboardingStates(StatesGroup):
    awaiting_consent = State()
    consent_declined = State()
    resume_choice = State()
    restart_confirmation = State()
    returning = State()
    repeat_confirmation = State()
    answering = State()
