from aiogram.fsm.state import State, StatesGroup


class SupportStates(StatesGroup):
    waiting_user_message = State()
    waiting_admin_reply = State()
