from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command

from database.queries.users import get_user_by_telegram_id
from database.queries.tasks import (
    get_tasks_by_user, get_all_tasks,
    get_task, get_task_comments
)
from keyboards.inline import tasks_list_kb, task_detail_kb, tasks_filter_kb

router = Router()

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


# ── MENING VAZIFALARIM ───────────────────────────────────────────────────────

@router.message(F.text == "📋 Vazifalarim")
@router.message(Command("my"))
async def my_tasks(message: Message):
    user = await get_user_by_telegram_id(message.from_user.id)
    if not user:
        return

    tasks = await get_tasks_by_user(user["id"], status_filter="active")

    if not tasks:
        await message.answer(
            "📭 <b>Hozircha faol vazifalaringiz yo'q.</b>\n\n"
            "<i>Yangi vazifa kelganda xabardor bo'lasiz.</i>",
            parse_mode="HTML"
        )
        return

    text = _format_task_list(tasks, title="📋 Mening vazifalarim")
    await message.answer(
        text,
        reply_markup=tasks_list_kb(tasks, prefix="my"),
        parse_mode="HTML"
    )


# ── BARCHA VAZIFALAR (Admin / PM / AD) ───────────────────────────────────────

@router.message(F.text == "📊 Barcha vazifalar")
@router.message(Command("all"))
async def all_tasks(message: Message):
    user = await get_user_by_telegram_id(message.from_user.id)
    if not user or user["role"] not in ("super_admin", "pm", "ad"):
        await message.answer("❌ Ruxsat yo'q.")
        return

    tasks = await get_all_tasks(status_filter="active")

    if not tasks:
        await message.answer("📭 Hozircha faol vazifalar yo'q.")
        return

    text = _format_task_list(tasks, title="📊 Barcha faol vazifalar", show_assignee=True)
    await message.answer(
        text,
        reply_markup=tasks_list_kb(tasks, prefix="all"),
        parse_mode="HTML"
    )


# ── VAZIFA TAFSILOTI ─────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("task:"))
async def task_detail(call: CallbackQuery):
    task_id = int(call.data.split(":")[1])

    task    = await get_task(task_id)
    comments = await get_task_comments(task_id)

    if not task:
        await call.answer("Vazifa topilmadi!", show_alert=True)
        return

    user = await get_user_by_telegram_id(call.from_user.id)
    is_manager = user and user["role"] in ("super_admin", "pm", "ad")
    is_assigned = user and user["id"] == task["assigned_to"]

    text = _format_task_detail(task, comments)

    await call.message.edit_text(
        text,
        reply_markup=task_detail_kb(
            task_id=task_id,
            is_manager=is_manager,
            is_assigned=is_assigned,
            status=task["status"]
        ),
        parse_mode="HTML"
    )


# ── ORQAGA ───────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "back_to_list")
async def back_to_list(call: CallbackQuery):
    user = await get_user_by_telegram_id(call.from_user.id)
    if not user:
        return
    tasks = await get_tasks_by_user(user["id"])
    if not tasks:
        await call.message.edit_text("📭 <b>Hozircha faol vazifalaringiz yo'q.</b>", parse_mode="HTML")
        return
    text = _format_task_list(tasks, title="📋 Mening vazifalarim")
    await call.message.edit_text(text, reply_markup=tasks_list_kb(tasks, prefix="my"), parse_mode="HTML")


# ── FILTER ───────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("filter:"))
async def filter_tasks(call: CallbackQuery):
    _, scope, filter_type = call.data.split(":")

    user = await get_user_by_telegram_id(call.from_user.id)
    if not user:
        return

    if scope == "my":
        tasks = await get_tasks_by_user(user["id"], status_filter=filter_type)
        title = f"📋 Mening vazifalarim — {filter_type}"
        prefix = "my"
    else:
        tasks = await get_all_tasks(status_filter=filter_type)
        title = f"📊 Barcha vazifalar — {filter_type}"
        prefix = "all"

    filter_labels = {
        "active": "Faol", "bajarildi": "Bajarildi",
        "kechikdi": "Kechikdi", "yuqori": "Yuqori prioritet",
        "qaytarildi": "Qaytarildi"
    }
    label = filter_labels.get(filter_type, filter_type)

    if not tasks:
        await call.answer()
        await call.message.edit_text(
            f"📭 <b>{label}</b> bo'yicha vazifalar yo'q.",
            reply_markup=tasks_filter_kb(prefix),
            parse_mode="HTML"
        )
        return

    text = _format_task_list(tasks, title=title, show_assignee=(scope == "all"))
    await call.message.edit_text(
        text,
        reply_markup=tasks_list_kb(tasks, prefix=prefix),
        parse_mode="HTML"
    )


# ── FORMATLASH ───────────────────────────────────────────────────────────────

def _format_task_list(tasks: list, title: str, show_assignee: bool = False) -> str:
    lines = [f"<b>{title}</b>", f"Jami: {len(tasks)} ta", "─" * 28, ""]

    for task in tasks:
        p_icon = PRIORITY_ICON.get(task["priority"], "🟡")
        s_icon = STATUS_ICON.get(task["status"], "🔄")
        deadline = ""
        if task.get("deadline"):
            from datetime import datetime
            import pytz
            tz = pytz.timezone("Asia/Tashkent")
            dl = task["deadline"]
            if hasattr(dl, "astimezone"):
                dl = dl.astimezone(tz)
            deadline = f" | ⏰ {dl.strftime('%d.%m %H:%M')}"

        assignee = ""
        if show_assignee and task.get("assignee_name"):
            assignee = f" → {task['assignee_name']}"

        lines.append(f"{p_icon}{s_icon} <b>{task['title'][:40]}</b>{assignee}{deadline}")

    return "\n".join(lines)


def _format_task_detail(task: dict, comments: list) -> str:
    p_icon = PRIORITY_ICON.get(task["priority"], "🟡")
    s_icon = STATUS_ICON.get(task["status"], "🔄")

    lines = [
        f"{p_icon} <b>{task['title']}</b>",
        f"Holat: {s_icon} {task['status']}",
        "",
    ]

    if task.get("description"):
        lines += [f"📝 {task['description']}", ""]

    if task.get("assignee_name"):
        lines.append(f"👤 Mas'ul: <b>{task['assignee_name']}</b>")

    if task.get("creator_name"):
        lines.append(f"✍️ Berdi: {task['creator_name']}")

    if task.get("deadline"):
        import pytz
        from datetime import datetime
        tz = pytz.timezone("Asia/Tashkent")
        dl = task["deadline"].astimezone(tz)
        lines.append(f"⏰ Deadline: <b>{dl.strftime('%d.%m.%Y %H:%M')}</b>")

    if task.get("return_count", 0) > 0:
        lines.append(f"↩️ Qaytarildi: {task['return_count']} marta")
        if task.get("return_reason"):
            lines.append(f"   Sabab: <i>{task['return_reason']}</i>")

    # Izohlar
    if comments:
        lines += ["", f"💬 <b>Izohlar ({len(comments)}):</b>"]
        for c in comments[-5:]:  # Oxirgi 5 ta
            c_icon = {
                "bajardim":  "✅",
                "kechikadi": "⏳",
                "savol":     "❓",
                "muammo":    "🚨",
                "oddiy":     "💬",
            }.get(c["comment_type"], "💬")
            lines.append(f"{c_icon} <b>{c['user_name']}:</b> {c['text']}")

    return "\n".join(lines)
