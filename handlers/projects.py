from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database.queries.users import get_user_by_telegram_id
from database.queries.projects import (
    get_active_projects, get_project,
    create_project, get_project_milestones,
    complete_milestone, get_milestone
)
from database.queries.tasks import get_next_milestone, activate_milestone

router = Router()

STAGE_ICONS = {
    "yangi_ideya": "🆕", "ssenariyda": "📝", "syemkaga_tayyor": "🎬",
    "syemka_qilindi": "🎥", "montajda": "✂️", "dizaynda": "🎨",
    "tekshiruvda": "👀", "nashr": "🚀"
}


# ── LOYIHALAR RO'YXATI ────────────────────────────────────────────────────────

@router.message(F.text == "🎬 Loyihalar")
@router.message(Command("projects"))
async def list_projects(message: Message):
    user = await get_user_by_telegram_id(message.from_user.id)
    if not user:
        return

    projects = await get_active_projects()
    if not projects:
        await message.answer("📭 Faol loyihalar yo'q.")
        return

    lines = ["🎬 <b>Faol loyihalar:</b>\n"]
    for p in projects:
        stage = p.get("current_stage") or "—"
        icon = STAGE_ICONS.get(stage, "📋")
        deadline = p["deadline"].strftime("%d.%m") if p.get("deadline") else "—"
        lines.append(f"{icon} <b>{p['title']}</b> | {deadline}")
        lines.append(f"   /project_{p['id']}")

    await message.answer("\n".join(lines), parse_mode="HTML")


# ── LOYIHA TAFSILOTI ──────────────────────────────────────────────────────────

@router.message(F.text.regexp(r"^/project_(\d+)$"))
async def project_detail(message: Message):
    project_id = int(message.text.split("_")[1])
    project = await get_project(project_id)
    if not project:
        await message.answer("❌ Loyiha topilmadi.")
        return

    milestones = await get_project_milestones(project_id)

    lines = [
        f"🎬 <b>{project['title']}</b>\n",
        f"Holat: <b>{project['status']}</b>"
    ]
    if project.get("deadline"):
        lines.append(f"Deadline: {project['deadline'].strftime('%d.%m.%Y')}")

    lines.append("\n<b>Etaplar:</b>")
    for m in milestones:
        st = m["status"]
        icon = "✅" if st == "bajarildi" else ("▶️" if st == "jarayonda" else "⏳")
        assignee = f" → {m['assignee_name']}" if m.get("assignee_name") else ""
        lines.append(f"{icon} {m['order_num']}. {m['title']}{assignee}")

    await message.answer("\n".join(lines), parse_mode="HTML")


# ── YANGI LOYIHA ──────────────────────────────────────────────────────────────

class CreateProjectState(StatesGroup):
    title = State()


@router.message(Command("newproject"))
async def new_project_start(message: Message, state: FSMContext):
    user = await get_user_by_telegram_id(message.from_user.id)
    if not user or user["role"] not in ("super_admin", "pm", "ad"):
        await message.answer("❌ Ruxsat yo'q.")
        return

    await message.answer("📝 Loyiha nomini yozing:")
    await state.set_state(CreateProjectState.title)


@router.message(CreateProjectState.title)
async def create_project_handler(message: Message, state: FSMContext):
    user = await get_user_by_telegram_id(message.from_user.id)
    title = message.text.strip()

    project = await create_project(title=title, created_by=user["id"])
    await state.clear()

    await message.answer(
        f"✅ <b>{project['title']}</b> loyihasi yaratildi!\n"
        f"ID: <code>{project['id']}</code>",
        parse_mode="HTML"
    )
