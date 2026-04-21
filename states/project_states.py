from aiogram.fsm.state import State, StatesGroup


class CreateProjectState(StatesGroup):
    title = State()
    deadline = State()


class MilestoneState(StatesGroup):
    title = State()
    assignee = State()
