from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from ai.transcriber import transcribe_from_telegram
from ai.task_parser import parse_tasks_from_text, parse_comment, parse_meeting_protocol
from database.queries.users import get_all_active_members
from database.queries.tasks import create_task_bulk
from keyboards.inline import confirm_tasks_kb, edit_task_kb

router = Router()


# ── AUDIO QABUL QILISH ───────────────────────────────────────────────────────

@router.message(F.voice | F.audio)
async def handle_audio(message: Message, state: FSMContext):
    """
    Har qanday audio xabarni qabul qiladi.
    Kim yuborgan va qayerdan (guruh/PM) ekaniga qarab yo'naltiriladi.
    """

    # Yuklanmoqda xabari
    wait_msg = await message.answer("🎙️ Audio tahlil qilinmoqda...")

    try:
        # 1. Audio → Matn (Whisper)
        file_id = message.voice.file_id if message.voice else message.audio.file_id
        raw_text = await transcribe_from_telegram(message.bot, file_id)

        if not raw_text.strip():
            await wait_msg.edit_text("❌ Audio tushunilmadi. Qayta urinib ko'ring.")
            return

        # 2. Kim yubordi?
        from database.queries.users import get_user_by_telegram_id
        sender = await get_user_by_telegram_id(message.from_user.id)

        if not sender:
            await wait_msg.edit_text("❌ Siz ro'yxatda yo'qsiz. /start bosing.")
            return

        # 3. Agar member → izoh sifatida qabul qilinadi (vazifa kontekstida)
        current_state = await state.get_state()
        if current_state and "waiting_comment" in current_state:
            await handle_audio_comment(message, state, raw_text, wait_msg)
            return

        # 4. Agar yig'ilish rejimida
        if current_state and "meeting" in current_state:
            await handle_meeting_audio(message, state, raw_text, wait_msg)
            return

        # 5. Vazifa berish rejimi (admin/pm/ad/member → member)
        await handle_task_audio(message, state, raw_text, wait_msg, sender)

    except Exception as e:
        log.error(f"Audio handler xatosi: {e}", exc_info=True)
        err = str(e).lower()
        if "openai" in err or "whisper" in err or "transcri" in err:
            msg = "🎙️ Audio matn shaklga keltirilib bo'lmadi. Ovozingiz aniqroq bo'lishi kerak."
        elif "anthropic" in err or "claude" in err or "parse" in err:
            msg = "🤖 Vazifani tahlil qilishda muammo. Qayta urinib ko'ring."
        elif "connection" in err or "pool" in err or "database" in err:
            msg = "🗄 Serverga ulanishda muammo. Bir daqiqadan so'ng urinib ko'ring."
        else:
            msg = "⚠️ Noma'lum xatolik yuz berdi. Qayta urinib ko'ring."
        await wait_msg.edit_text(msg)


# ── VAZIFA BERISH ────────────────────────────────────────────────────────────

async def handle_task_audio(message, state, raw_text, wait_msg, sender):
    """Audio dan vazifalarni ajratib, tasdiqlash uchun ko'rsatadi."""

    # Jamoa a'zolarini olish (ism moslashtirish uchun)
    team_members = await get_all_active_members()

    # Claude API → Vazifalar
    result = await parse_tasks_from_text(
        raw_text=raw_text,
        team_members=team_members
    )

    tasks = result.get("tasks", [])
    unresolved = result.get("unresolved", "")

    if not tasks:
        await wait_msg.edit_text(
            f"🎙️ <b>Transkripsiya:</b>\n<i>{raw_text}</i>\n\n"
            "❓ Vazifa aniqlanmadi. Aniqroq gapirib ko'ring.",
            parse_mode="HTML"
        )
        return

    # Tasdiqlash uchun ko'rsatish
    text = _format_tasks_preview(tasks, raw_text, unresolved)

    # State ga saqlash
    await state.update_data(
        parsed_tasks=tasks,
        raw_text=raw_text,
        sender_id=sender["id"]
    )

    await wait_msg.edit_text(
        text,
        reply_markup=confirm_tasks_kb(len(tasks)),
        parse_mode="HTML"
    )


def _format_tasks_preview(tasks: list, raw_text: str, unresolved: str) -> str:
    """Topilgan vazifalarni chiroyli formatda ko'rsatadi."""

    priority_icons = {"yuqori": "🔴", "orta": "🟡", "past": "🟢"}

    lines = [
        f"🎙️ <b>Transkripsiya:</b>",
        f"<i>{raw_text[:200]}{'...' if len(raw_text) > 200 else ''}</i>",
        "",
        f"📋 <b>{len(tasks)} ta vazifa aniqlandi:</b>",
        "─" * 30,
    ]

    for i, task in enumerate(tasks, 1):
        icon = priority_icons.get(task.get("priority", "orta"), "🟡")
        deadline = task.get("deadline") or "belgilanmagan"
        lines += [
            f"<b>{i}. {icon} {task.get('assignee', '?')}</b>",
            f"   📌 {task.get('task', '')}",
            f"   ⏰ {deadline}",
            "",
        ]

    if unresolved:
        lines += ["⚠️ <i>Aniqlanmagan:</i>", f"<i>{unresolved}</i>", ""]

    lines += ["Tasdiqlaysizmi?"]
    return "\n".join(lines)


# ── IZOH ─────────────────────────────────────────────────────────────────────

async def handle_audio_comment(message, state, raw_text, wait_msg):
    """Member tomonidan yuborilgan audio izohni tahlil qiladi."""

    result = await parse_comment(raw_text)

    comment_type = result.get("comment_type", "oddiy")
    clean_text = result.get("clean_text", raw_text)
    is_urgent = result.get("is_urgent", False)

    data = await state.get_data()
    task_id = data.get("commenting_task_id")

    # DB ga saqlash
    from database.queries.tasks import add_comment
    from database.queries.users import get_user_by_telegram_id

    user = await get_user_by_telegram_id(message.from_user.id)
    await add_comment(
        task_id=task_id,
        user_id=user["id"],
        text=clean_text,
        comment_type=comment_type,
        audio_file_id=message.voice.file_id if message.voice else None
    )

    # Status o'zgartirish
    type_icons = {
        "bajardim":  "✅",
        "kechikadi": "⏳",
        "savol":     "❓",
        "muammo":    "🔴",
        "oddiy":     "💬",
    }
    icon = type_icons.get(comment_type, "💬")

    await wait_msg.edit_text(
        f"{icon} <b>Izoh saqlandi:</b>\n<i>{clean_text}</i>",
        parse_mode="HTML"
    )

    # PM/AD ga notification
    if comment_type in ("kechikadi", "muammo") or is_urgent:
        await _notify_managers(message, task_id, comment_type, clean_text, is_urgent)

    # Agar bajardim → status o'zgartirish
    if comment_type == "bajardim":
        from database.queries.tasks import complete_task
        await complete_task(task_id)
        await _check_pipeline_advance(task_id, message.bot)

    await state.clear()


# ── YIG'ILISH PROTOKOLI ───────────────────────────────────────────────────────

async def handle_meeting_audio(message, state, raw_text, wait_msg):
    """Yig'ilish audiosini protokolga aylantiradi va vazifalar yaratadi."""

    team_members = await get_all_active_members()
    result = await parse_meeting_protocol(
        raw_text=raw_text,
        team_members=team_members
    )

    protocol = result.get("protocol", "")
    decisions = result.get("decisions", [])
    tasks = result.get("tasks", [])

    # DB ga saqlash
    from database.queries.tasks import save_meeting_log
    from database.queries.users import get_user_by_telegram_id as _get_user
    data = await state.get_data()
    _sender = await _get_user(message.from_user.id)
    meeting_id = await save_meeting_log(
        chat_id=message.chat.id,
        audio_file_id=message.voice.file_id,
        protocol_text=protocol,
        decisions=decisions,
        recorded_by=_sender["id"] if _sender else 0
    )

    text = _format_meeting_result(protocol, decisions, tasks)

    await state.update_data(
        meeting_id=meeting_id,
        meeting_tasks=tasks,
        raw_text=raw_text
    )

    await wait_msg.edit_text(
        text,
        reply_markup=confirm_tasks_kb(len(tasks), prefix="meeting"),
        parse_mode="HTML"
    )


def _format_meeting_result(protocol, decisions, tasks):
    lines = [
        "📋 <b>Yig'ilish Protokoli</b>",
        "─" * 30,
        f"<i>{protocol}</i>",
        "",
    ]

    if decisions:
        lines.append("⚖️ <b>Qarorlar:</b>")
        for d in decisions:
            lines.append(f"  • {d.get('decision')} — <b>{d.get('responsible', '?')}</b>")
        lines.append("")

    if tasks:
        lines.append(f"📌 <b>{len(tasks)} ta vazifa yaratiladi:</b>")
        for t in tasks:
            lines.append(f"  • {t.get('assignee')} → {t.get('task')}")

    return "\n".join(lines)


# ── YORDAMCHI: Pipeline keyingi etapga o'tish ────────────────────────────────

async def _check_pipeline_advance(task_id: int, bot):
    """Milestone tugagach keyingi etapga o'tadi va mas'ulga xabar beradi."""
    from database.queries.tasks import get_task, get_next_milestone
    from database.queries.users import get_user

    task = await get_task(task_id)
    if not task or not task["milestone_id"]:
        return

    next_ms = await get_next_milestone(task["milestone_id"])
    if not next_ms:
        return

    # Keyingi milestone ni aktivlashtirish
    from database.queries.tasks import activate_milestone
    await activate_milestone(next_ms["id"])

    # Mas'ulga xabar
    if next_ms["assigned_to"]:
        user = await get_user(next_ms["assigned_to"])
        if user:
            await bot.send_message(
                user["telegram_id"],
                f"🔔 <b>Yangi etap boshlandi!</b>\n\n"
                f"📌 {next_ms['title']}\n"
                f"Siz mas'ulsiz. Bajarib, 'Bajardim' deb audio yuboring.",
                parse_mode="HTML"
            )


# ── YORDAMCHI: PM/AD ga xabar ────────────────────────────────────────────────

async def _notify_managers(message, task_id, comment_type, text, is_urgent):
    """PM va AD ga muammo/kechikish haqida xabar beradi."""
    from database.queries.users import get_managers
    from database.queries.tasks import get_task

    managers = await get_managers()
    task = await get_task(task_id)
    task_title = task["title"] if task else "Noma'lum vazifa"

    icons = {"kechikadi": "⏳", "muammo": "🚨"}
    icon = icons.get(comment_type, "⚠️")
    urgent_prefix = "🚨 URGENT!\n" if is_urgent else ""

    for manager in managers:
        try:
            await message.bot.send_message(
                manager["telegram_id"],
                f"{urgent_prefix}{icon} <b>{message.from_user.full_name}</b>\n"
                f"Vazifa: <b>{task_title}</b>\n\n"
                f"<i>{text}</i>",
                parse_mode="HTML"
            )
        except Exception:
            pass
