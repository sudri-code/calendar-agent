from aiogram.fsm.state import State, StatesGroup


class SlotStates(StatesGroup):
    enter_people = State()
    enter_range = State()
    enter_duration = State()
    review_options = State()
    confirm_create = State()
