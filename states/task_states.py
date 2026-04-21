from aiogram.fsm.state import State, StatesGroup


class CreateTask(StatesGroup):
    title = State()
    description = State()
    assignee = State()
    priority = State()
    task_type = State()
    deadline = State()
    confirm = State()


class CommentState(StatesGroup):
    waiting_comment = State()
    waiting_return_reason = State()
