import pytz
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command

from database.queries.users import get_user_by_telegram_id
from database.queries.tasks import (
    get_tasks_by_user, get_all_tasks,
    count_tasks_by_user, count_all_tasks,
    get_task, get_task_comments,
)
from keyboards.inline import tasks_list_kb, task_detail_kb, PAGE_SIZE

router = Router()

TZ            = pytz.timezone("Asia/Tashkent")
PRIORITY_ICON = {"yuqori": "🔴", "orta": "🟡", "past": "🟢"}
STATUS_ICON   = {
    "yangi":         "🆕",
    "jarayonda":     "🔄",
    "tekshiruvda":   "👀",
    "qaytarildi":    "↩️",
    "bajarildi":     "✅",
    "kechikdi":      "⚠️",
    "bekor_qilindi": "❌",
}
COMMENT_ICON = {
    "bajardim":  "✅",
    "kechikadi": "⏳",
    "savol":     "❓",
    "muammo":    "🚨",
    "oddiy":     "💬",
}


# ── MENING VAZIFALARIM ───────────────────────────────────────────────────────

@router.message(F.text == "📋 Vazifalarim")
@router.message(Command("my"))
async def my_tasks(message: Message, db_user: dict | None = None):
    user = db_user or await get_user_by_telegram_id(message.from_user.id)
    if not user:
        return
    await _send_task_list(message, user, scope="my", page=0)


# ── BARCHA VAZIFALAR (Admin / PM / AD) ───────────────────────────────────────

@router.message(F.text == "📊 Barcha vazifalar")
@router.message(Command("all"))
async def all_tasks(message: Message, db_user: dict | None = None):
    user = db_user or await get_user_by_telegram_id(message.from_user.id)
    if not user or user["role"] not in ("super_admin", "pm", "ad"):
        await message.answer("❌ Ruxsat yo'q.")
        return
    await _send_task_list(message, user, scope="all", page=0)


# ── SAHIFALAR ARASI O'TISH ───────────────────────────────────────────────────

@router.callback_query(F.data.startswith("page:"))
async def paginate_tasks(call: CallbackQuery, db_user: dict | None = None):
    parts = call.data.split(":")
    if len(parts) < 3:
        await call.answer()
        return
    _, scope, page_str = parts[0], parts[1], parts[2]
    try:
        page = int(page_str)
    except ValueError:
        await call.answer()
        return

    user = db_user or await get_user_by_telegram_id(call.from_user.id)
    if not user:
        return
    await _edit_task_list(call, user, scope=scope, page=page)


@router.callback_query(F.data == "noop")
async def noop(call: CallbackQuery):
    await call.answer()


# ── VAZIFA TAFSILOTI ─────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("task:"))
async def task_detail(call: CallbackQuery, db_user: dict | None = None):
    try:
        task_id = int(call.data.split(":")[1])
    except (IndexError, ValueError):
        await call.answer("Noto'g'ri ma'lumot", show_alert=True)
        return

    task     = await get_task(task_id)
    comments = await get_task_comments(task_id)

    if not task:
        await call.answer("Vazifa topilmadi!", show_alert=True)
        return

    user        = db_user or await get_user_by_telegram_id(call.from_user.id)
    is_manager  = bool(user and user["role"] in ("super_admin", "pm", "ad"))
    is_assigned = bool(user and user["id"] == task["assigned_to"])

    text = _format_task_detail(task, comments)
    await call.message.edit_text(
        text,
        reply_markup=task_detail_kb(
            task_id=task_id,
            is_manager=is_manager,
            is_assigned=is_assigned,
            status=task["status"],
        ),
        parse_mode="HTML",
    )


# ── ORQAGA ───────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "back_to_list")
async def back_to_list(call: CallbackQuery, db_user: dict | None = None):
    user = db_user or await get_user_by_telegram_id(call.from_user.id)
    if not user:
        return
    await _edit_task_list(call, user, scope="my", page=0)


# ── FILTER ───────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("filter:"))
async def filter_tasks(call: CallbackQuery, db_user: dict | None = None):
    parts = call.data.split(":")
    if len(parts) < 3:
        await call.answer()
        return
    scope, filter_type = parts[1], parts[2]

    user = db_user or await get_user_by_telegram_id(call.from_user.id)
    if not user:
        return

    await _edit_task_list(call, user, scope=scope, page=0, status_filter=filter_type)


# ── HELPERS ──────────────────────────────────────────────────────────────────

async def _send_task_list(
    message: Message,
    user: dict,
    scope: str,
    page: int,
    status_filter: str = "active",
) -> None:
    tasks, total, title = await _fetch_tasks(user, scope, page, status_filter)
    if not tasks and page == 0:
        await message.answer(
            "📭 <b>Hozircha faol vazifalar yo'q.</b>",
            parse_mode="HTML",
        )
        return
    text = _format_task_list(tasks, title=title, show_assignee=(scope == "all"), total=total)
    await message.answer(
        text,
        reply_markup=tasks_list_kb(tasks, prefix=scope, page=page, total=total),
        parse_mode="HTML",
    )


async def _edit_task_list(
    call: CallbackQuery,
    user: dict,
    scope: str,
    page: int,
    status_filter: str = "active",
) -> None:
    tasks, total, title = await _fetch_tasks(user, scope, page, status_filter)
    if not tasks and page == 0:
        await call.message.edit_text(
            "📭 <b>Hozircha faol vazifalar yo'q.</b>",
            parse_mode="HTML",
        )
        return
    text = _format_task_list(tasks, title=title, show_assignee=(scope == "all"), total=total)
    await call.message.edit_text(
        text,
        reply_markup=tasks_list_kb(tasks, prefix=scope, page=page, total=total),
        parse_mode="HTML",
    )


async def _fetch_tasks(
    user: dict,
    scope: str,
    page: int,
    status_filter: str,
) -> tuple[list, int, str]:
    offset = page * PAGE_SIZE
    if scope == "my":
        tasks = await get_tasks_by_user(user["id"], status_filter=status_filter, offset=offset, limit=PAGE_SIZE)
        total = await count_tasks_by_user(user["id"], status_filter=status_filter)
        title = "📋 Mening vazifalarim"
    else:
        tasks = await get_all_tasks(status_filter=status_filter, offset=offset, limit=PAGE_SIZE)
        total = await count_all_tasks(status_filter=status_filter)
        title = "📊 Barcha faol vazifalar"
    return tasks, total, title


def _fmt_deadline(dl) -> str:
    if not dl:
        return ""
    if hasattr(dl, "astimezone"):
        dl = dl.astimezone(TZ)
    return f" | ⏰ {dl.strftime('%d.%m %H:%M')}"


def _format_task_list(tasks: list, title: str, show_assignee: bool = False, total: int = 0) -> str:
    lines = [f"<b>{title}</b>", f"Jami: {total} ta", "─" * 28, ""]
    for task in tasks:
        p_icon   = PRIORITY_ICON.get(task.get("priority", "orta"), "🟡")
        s_icon   = STATUS_ICON.get(task.get("status", "yangi"), "🔄")
        deadline = _fmt_deadline(task.get("deadline"))
        assignee = f" → {task['assignee_name']}" if show_assignee and task.get("assignee_name") else ""
        lines.append(f"{p_icon}{s_icon} <b>{task.get('title', '—')[:40]}</b>{assignee}{deadline}")
    return "\n".join(lines)


def _format_task_detail(task: dict, comments: list) -> str:
    p_icon = PRIORITY_ICON.get(task.get("priority", "orta"), "🟡")
    s_icon = STATUS_ICON.get(task.get("status", "yangi"), "🔄")

    lines = [
        f"{p_icon} <b>{task.get('title', '—')}</b>",
        f"Holat: {s_icon} {task.get('status', '—')}",
        "",
    ]
    if task.get("description"):
        lines += [f"📝 {task['description']}", ""]
    if task.get("assignee_name"):
        lines.append(f"👤 Mas'ul: <b>{task['assignee_name']}</b>")
    if task.get("creator_name"):
        lines.append(f"✍️ Berdi: {task['creator_name']}")
    if task.get("deadline"):
        dl = task["deadline"].astimezone(TZ)
        lines.append(f"⏰ Deadline: <b>{dl.strftime('%d.%m.%Y %H:%M')}</b>")
    if task.get("return_count", 0) > 0:
        lines.append(f"↩️ Qaytarildi: {task['return_count']} marta")
        if task.get("return_reason"):
            lines.append(f"   Sabab: <i>{task['return_reason']}</i>")
    if comments:
        lines += ["", f"💬 <b>Izohlar ({len(comments)}):</b>"]
        for c in comments[-5:]:
            c_icon = COMMENT_ICON.get(c.get("comment_type", "oddiy"), "💬")
            lines.append(f"{c_icon} <b>{c.get('user_name', '?')}:</b> {c.get('text', '')}")
    return "\n".join(lines)
