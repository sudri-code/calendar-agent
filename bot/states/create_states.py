from aiogram.fsm.state import State, StatesGroup


class CreateEventStates(StatesGroup):
    choose_mode = State()       # text / step-by-step
    choose_calendar = State()
    choose_date = State()
    choose_time = State()
    choose_duration = State()
    choose_attendees = State()
    enter_title = State()
    enter_description = State()
    choose_recurrence = State()
    recurrence_frequency = State()
    recurrence_interval = State()
    recurrence_days = State()
    recurrence_end_type = State()
    recurrence_end_date = State()
    recurrence_count = State()
    confirm = State()
    completed = State()


class RescheduleStates(StatesGroup):
    choose_event = State()
    choose_recurrence_mode = State()
    choose_date = State()
    choose_time = State()
    confirm = State()


class DeleteStates(StatesGroup):
    choose_event = State()
    choose_recurrence_mode = State()
    confirm = State()
