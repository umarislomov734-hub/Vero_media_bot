import asyncio

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database.queries.users import (
    get_user_by_telegram_id, get_all_active_members
)
from database.queries.tasks import create_task, get_task
from keyboards.inline import (
    members_select_kb, priority_kb,
    task_type_kb, confirm_create_kb
)

router = Router()


# ── FSM STATES ───────────────────────────────────────────────────────────────

class CreateTask(StatesGroup):
    title       = State()
    description = State()
    assignee    = State()
    priority    = State()
    task_type   = State()
    deadline    = State()
    confirm     = State()


# ── GOOGLE CALENDAR HELPER ───────────────────────────────────────────────────

async def _maybe_create_gcal_event(task: dict, assignee_internal_id: int) -> None:
    try:
        if not task or not task.get("deadline"):
            return
        from database.queries.users import get_google_token, save_google_token
        from database.queries.tasks import save_gcal_event
        from utils.google_calendar import create_event as gcal_create, refresh_token_if_needed

        token_data = await get_google_token(assignee_internal_id)
        if not token_data:
            return

        fresh = await refresh_token_if_needed(token_data)
        if not fresh:
            return
        if fresh.get("access_token") != token_data.get("access_token"):
            await save_google_token(
                assignee_internal_id, fresh["access_token"],
                fresh["refresh_token"], fresh["expiry"],
                fresh.get("calendar_id", "primary")
            )

        from datetime import datetime
        dl = task["deadline"]
        if not isinstance(dl, datetime):
            dl = datetime.fromisoformat(str(dl))

        event_id = await gcal_create(fresh, task["title"], dl, task["id"])
        if event_id:
            await save_gcal_event(
                task_id=task["id"],
                user_id=assignee_internal_id,
                event_id=event_id,
                calendar_id=fresh.get("calendar_id", "primary")
            )
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"_maybe_create_gcal_event xatosi: {e}")


# ── BOSHLASH ─────────────────────────────────────────────────────────────────

@router.message(F.text == "➕ Yangi vazifa")
@router.message(Command("task"))
async def start_create_task(message: Message, state: FSMContext):
    user = await get_user_by_telegram_id(message.from_user.id)
    if not user:
        return

    await state.clear()
    await state.set_state(CreateTask.title)
    await state.update_data(creator_id=user["id"])

    await message.answer(
        "➕ <b>Yangi vazifa yaratish</b>\n\n"
        "📌 Vazifa sarlavhasini yozing:\n\n"
        "<i>Bekor qilish uchun /cancel</i>",
        parse_mode="HTML"
    )


# ── 1. SARLAVHA ───────────────────────────────────────────────────────────────

@router.message(CreateTask.title)
async def get_title(message: Message, state: FSMContext):
    title = message.text.strip()

    if len(title) < 3:
        await message.answer("❌ Sarlavha juda qisqa. Kamida 3 ta harf.")
        return

    await state.update_data(title=title)
    await state.set_state(CreateTask.description)

    await message.answer(
        f"✅ Sarlavha: <b>{title}</b>\n\n"
        "📝 Tavsif yozing yoki o'tkazib yuborish uchun /skip bosing:",
        parse_mode="HTML"
    )


# ── 2. TAVSIF ─────────────────────────────────────────────────────────────────

@router.message(CreateTask.description, F.text == "/skip")
@router.message(CreateTask.description, F.text.startswith("/skip"))
async def skip_description(message: Message, state: FSMContext):
    await state.set_state(CreateTask.assignee)
    await state.update_data(description=None)
    await _ask_assignee(message, state)


@router.message(CreateTask.description)
async def get_description(message: Message, state: FSMContext):
    await state.set_state(CreateTask.assignee)
    await state.update_data(description=message.text.strip())
    await _ask_assignee(message, state)


async def _ask_assignee(message: Message, state: FSMContext):
    await state.set_state(CreateTask.assignee)
    members = await get_all_active_members()

    from database.queries.tasks import get_tasks_by_user
    for m in members:
        tasks = await get_tasks_by_user(m["id"], status_filter="active")
        m["active_count"] = len(tasks)

    await message.answer(
        "👤 Kim bajarsin? Tanlang:\n<i>(raqam — faol vazifalar soni)</i>",
        reply_markup=members_select_kb(members, show_load=True),
        parse_mode="HTML"
    )


# ── 3. BAJARUVCHI ─────────────────────────────────────────────────────────────

@router.callback_query(CreateTask.assignee, F.data.startswith("assign:"))
async def get_assignee(call: CallbackQuery, state: FSMContext):
    assignee_id = int(call.data.split(":")[1])
    assignee_name = call.data.split(":")[2]

    await state.update_data(assignee_id=assignee_id, assignee_name=assignee_name)
    await state.set_state(CreateTask.priority)

    await call.message.edit_text(
        f"👤 Mas'ul: <b>{assignee_name}</b>\n\n"
        "🎯 Prioritet tanlang:",
        reply_markup=priority_kb(),
        parse_mode="HTML"
    )


# ── 4. PRIORITET ──────────────────────────────────────────────────────────────

@router.callback_query(CreateTask.priority, F.data.startswith("priority:"))
async def get_priority(call: CallbackQuery, state: FSMContext):
    priority = call.data.split(":")[1]
    icons = {"yuqori": "🔴", "orta": "🟡", "past": "🟢"}

    await state.update_data(priority=priority)
    await state.set_state(CreateTask.task_type)

    await call.message.edit_text(
        f"🎯 Prioritet: <b>{icons[priority]} {priority}</b>\n\n"
        "📦 Vazifa turi:",
        reply_markup=task_type_kb(),
        parse_mode="HTML"
    )


# ── 5. VAZIFA TURI ────────────────────────────────────────────────────────────

@router.callback_query(CreateTask.task_type, F.data.startswith("type:"))
async def get_task_type(call: CallbackQuery, state: FSMContext):
    task_type = call.data.split(":")[1]
    type_icons = {"loyiha": "🎬", "birmartalik": "⚡", "rutiniy": "🔁"}

    await state.update_data(task_type=task_type)
    await state.set_state(CreateTask.deadline)

    await call.message.edit_text(
        f"📦 Tur: <b>{type_icons[task_type]} {task_type}</b>\n\n"
        "⏰ Deadline yozing yoki o'tkazib yuborish uchun /skip:\n\n"
        "<i>Misol: 25.12 18:00 yoki ertaga 15:00</i>",
        parse_mode="HTML"
    )


# ── 6. DEADLINE ───────────────────────────────────────────────────────────────

@router.message(CreateTask.deadline, F.text.startswith("/skip"))
async def skip_deadline(message: Message, state: FSMContext):
    await state.set_state(CreateTask.confirm)
    await state.update_data(deadline=None, deadline_str="belgilanmagan")
    await _show_confirm(message, state)


@router.message(CreateTask.deadline)
async def get_deadline(message: Message, state: FSMContext):
    await state.set_state(CreateTask.confirm)
    deadline_str = message.text.strip()
    deadline_dt = _parse_deadline(deadline_str)

    await state.update_data(
        deadline=deadline_dt.isoformat() if deadline_dt else None,
        deadline_str=deadline_str
    )
    await _show_confirm(message, state)


def _parse_deadline(text: str):
    """Oddiy deadline parseri."""
    import re
    from datetime import datetime, timedelta
    import pytz

    tz = pytz.timezone("Asia/Tashkent")
    now = datetime.now(tz)
    text = text.lower().strip()

    # "bugun HH:MM"
    if "bugun" in text:
        m = re.search(r"(\d{1,2}):(\d{2})", text)
        if m:
            return now.replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0)
        return now.replace(hour=23, minute=59, second=0)

    # "ertaga HH:MM"
    if "ertaga" in text:
        tomorrow = now + timedelta(days=1)
        m = re.search(r"(\d{1,2}):(\d{2})", text)
        if m:
            return tomorrow.replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0)
        return tomorrow.replace(hour=23, minute=59, second=0)

    # "DD.MM HH:MM" yoki "DD.MM.YYYY HH:MM"
    m = re.search(r"(\d{1,2})\.(\d{1,2})(?:\.(\d{4}))?\s*(\d{1,2}):(\d{2})", text)
    if m:
        day, month = int(m.group(1)), int(m.group(2))
        year = int(m.group(3)) if m.group(3) else now.year
        hour, minute = int(m.group(4)), int(m.group(5))
        try:
            return tz.localize(datetime(year, month, day, hour, minute))
        except Exception:
            pass

    return None


# ── 7. TASDIQLASH ─────────────────────────────────────────────────────────────

async def _show_confirm(message: Message, state: FSMContext):
    data = await state.get_data()

    p_icons = {"yuqori": "🔴", "orta": "🟡", "past": "🟢"}
    t_icons = {"loyiha": "🎬", "birmartalik": "⚡", "rutiniy": "🔁"}

    text = (
        "📋 <b>Vazifa ma'lumotlari:</b>\n"
        "─" * 28 + "\n"
        f"📌 Sarlavha: <b>{data['title']}</b>\n"
        f"📝 Tavsif: {data.get('description') or '—'}\n"
        f"👤 Mas'ul: <b>{data['assignee_name']}</b>\n"
        f"🎯 Prioritet: {p_icons[data['priority']]} {data['priority']}\n"
        f"📦 Tur: {t_icons[data['task_type']]} {data['task_type']}\n"
        f"⏰ Deadline: {data.get('deadline_str', '—')}\n"
        "─" * 28
    )

    await message.answer(
        text,
        reply_markup=confirm_create_kb(),
        parse_mode="HTML"
    )


# ── TASDIQLASH CALLBACK ───────────────────────────────────────────────────────

@router.callback_query(CreateTask.confirm, F.data == "create_confirm")
async def confirm_create(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()

    task = await create_task(
        title=data["title"],
        description=data.get("description"),
        assigned_to=data["assignee_id"],
        created_by=data["creator_id"],
        priority=data["priority"],
        task_type=data["task_type"],
        deadline=data.get("deadline"),
        source="manual"
    )

    asyncio.create_task(_maybe_create_gcal_event(task, data["assignee_id"]))

    await state.clear()

    await call.message.edit_text(
        f"✅ <b>Vazifa yaratildi!</b>\n\n"
        f"📌 {data['title']}\n"
        f"👤 {data['assignee_name']} xabardor qilindi.",
        parse_mode="HTML"
    )

    from database.queries.users import get_user, get_user_by_telegram_id, get_managers
    p_icons = {"yuqori": "🔴", "orta": "🟡", "past": "🟢"}

    # Bajaruvchiga notification
    assignee = await get_user(data["assignee_id"])
    if assignee:
        await call.bot.send_message(
            assignee["telegram_id"],
            f"📌 <b>Yangi vazifa!</b>\n\n"
            f"{p_icons[data['priority']]} <b>{data['title']}</b>\n"
            f"✍️ Berdi: {call.from_user.full_name}\n"
            f"⏰ Deadline: {data.get('deadline_str', '—')}",
            parse_mode="HTML"
        )

    # Member → Member bo'lsa PM/AD ga xabar
    creator = await get_user_by_telegram_id(call.from_user.id)
    if creator and creator["role"] == "member" and assignee and assignee["role"] == "member":
        managers = await get_managers()
        for m in managers:
            try:
                await call.bot.send_message(
                    m["telegram_id"],
                    f"👥 <b>Member vazifa berdi</b>\n\n"
                    f"✍️ {creator['full_name']} → {assignee['full_name']}\n"
                    f"{p_icons[data['priority']]} {data['title']}\n"
                    f"⏰ {data.get('deadline_str', '—')}",
                    parse_mode="HTML"
                )
            except Exception:
                pass


@router.callback_query(CreateTask.confirm, F.data == "create_cancel")
async def cancel_create(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("❌ Bekor qilindi.")


# ── AUDIO DAN TASDIQLASH ──────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("audio_confirm:"))
async def confirm_audio_tasks(call: CallbackQuery, state: FSMContext):
    """Audio pipeline dan kelgan vazifalarni tasdiqlaydi."""
    data = await state.get_data()
    tasks = data.get("parsed_tasks", [])
    sender_id = data.get("sender_id")

    if not tasks:
        await call.answer("Vazifalar topilmadi!", show_alert=True)
        return

    # Har bir vazifani DB ga yozish
    members = await get_all_active_members()
    members_map = {m["full_name"].lower(): m["id"] for m in members}
    # Lavozim bo'yicha ham xarita
    position_map = {m.get("position", "").lower(): m["id"] for m in members if m.get("position")}

    created = []
    for t in tasks:
        assignee_name = t.get("assignee", "").lower()
        assignee_id = members_map.get(assignee_name) or position_map.get(assignee_name)

        task = await create_task(
            title=t["task"],
            assigned_to=assignee_id,
            created_by=sender_id,
            priority=t.get("priority", "orta"),
            task_type=t.get("task_type", "birmartalik"),
            deadline=t.get("deadline_iso"),
            source="audio"
        )
        created.append((task, t, assignee_id))
        if assignee_id:
            asyncio.create_task(_maybe_create_gcal_event(task, assignee_id))

    await state.clear()

    await call.message.edit_text(
        f"✅ <b>{len(created)} ta vazifa yaratildi!</b>\n"
        "Barcha mas'ullar xabardor qilindi.",
        parse_mode="HTML"
    )

    # Har bir mas'ulga notification
    from database.queries.users import get_user
    p_icons = {"yuqori": "🔴", "orta": "🟡", "past": "🟢"}

    for task, t, assignee_id in created:
        if not assignee_id:
            continue
        assignee = await get_user(assignee_id)
        if assignee:
            await call.bot.send_message(
                assignee["telegram_id"],
                f"📌 <b>Yangi vazifa!</b>\n\n"
                f"{p_icons.get(t.get('priority','orta'), '🟡')} <b>{t['task']}</b>\n"
                f"⏰ {t.get('deadline') or '—'}\n"
                f"✍️ Audio orqali berildi",
                parse_mode="HTML"
            )


@router.callback_query(F.data == "audio_edit")
async def edit_audio_tasks(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text(
        "✏️ Tahrirlash rejimi.\n\n"
        "Qaysi vazifani o'zgartirmoqchisiz? Raqamini yuboring:",
    )


@router.callback_query(F.data == "audio_cancel")
async def cancel_audio_tasks(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("❌ Bekor qilindi.")


# ── BEKOR QILISH ─────────────────────────────────────────────────────────────

@router.message(Command("cancel"))
async def cancel_any(message: Message, state: FSMContext):
    current = await state.get_state()
    if current:
        await state.clear()
        await message.answer("❌ Bekor qilindi.")
    else:
        await message.answer("Hech qanday aktiv jarayon yo'q.")
