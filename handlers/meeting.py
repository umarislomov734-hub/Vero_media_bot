from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database.queries.users import get_user_by_telegram_id, get_all_active_members
from database.queries.tasks import save_meeting_log, get_meeting_logs, create_task_bulk
from ai.transcriber import transcribe_from_telegram
from ai.task_parser import parse_meeting_protocol
from keyboards.inline import confirm_tasks_kb

router = Router()


class MeetingState(StatesGroup):
    recording   = State()
    confirming  = State()


# ── YIGʻILISH BOSHLASH ────────────────────────────────────────────────────────

@router.message(F.text == "🎙️ Yig'ilish")
@router.message(Command("meeting"))
async def start_meeting(message: Message, state: FSMContext):
    user = await get_user_by_telegram_id(message.from_user.id)
    if not user or user["role"] not in ("super_admin", "pm", "ad"):
        await message.answer("❌ Faqat PM/AD yig'ilish protokoli yoza oladi.")
        return

    await state.set_state(MeetingState.recording)
    await message.answer(
        "🎙️ <b>Yig'ilish rejimi</b>\n\n"
        "Audio yuboring — bot protokol yozadi va vazifalar yaratadi.\n\n"
        "<i>Bekor qilish: /cancel</i>",
        parse_mode="HTML"
    )


@router.message(MeetingState.recording, F.voice | F.audio)
async def handle_meeting_audio(message: Message, state: FSMContext):
    user = await get_user_by_telegram_id(message.from_user.id)
    if not user:
        await state.clear()
        return

    wait = await message.answer("🎙️ Yig'ilish tahlil qilinmoqda...")

    file_id = message.voice.file_id if message.voice else message.audio.file_id
    raw_text = await transcribe_from_telegram(message.bot, file_id)

    if not raw_text.strip():
        await wait.edit_text("❌ Audio tushunilmadi.")
        return

    team_members = await get_all_active_members()
    result = await parse_meeting_protocol(raw_text, team_members=team_members)

    protocol  = result.get("protocol", raw_text)
    decisions = result.get("decisions", [])
    tasks     = result.get("tasks", [])

    meeting_id = await save_meeting_log(
        chat_id=message.chat.id,
        audio_file_id=file_id,
        protocol_text=protocol,
        decisions=decisions,
        recorded_by=user["id"]
    )

    await state.update_data(meeting_id=meeting_id, meeting_tasks=tasks)
    await state.set_state(MeetingState.confirming)

    lines = [f"📋 <b>Protokol #{meeting_id}</b>", "", f"<i>{protocol[:500]}</i>", ""]
    if decisions:
        lines.append("⚖️ <b>Qarorlar:</b>")
        for d in decisions:
            lines.append(f"  • {d.get('decision', d)}")
        lines.append("")
    if tasks:
        lines.append(f"📌 <b>{len(tasks)} ta vazifa yaratiladi:</b>")
        for t in tasks:
            lines.append(f"  • {t.get('assignee','?')} → {t.get('task','')}")

    await wait.edit_text(
        "\n".join(lines),
        reply_markup=confirm_tasks_kb(len(tasks), prefix="meeting"),
        parse_mode="HTML"
    )


# ── YIG'ILISH TASDIQLASH ──────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("meeting_confirm:"))
async def meeting_confirm(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    tasks = data.get("meeting_tasks", [])
    user  = await get_user_by_telegram_id(call.from_user.id)

    if tasks:
        team_members = await get_all_active_members()
        member_map = {m["full_name"].lower(): m["id"] for m in team_members}

        task_list = []
        for t in tasks:
            assignee_name = t.get("assignee", "")
            assigned_to = None
            for name, uid in member_map.items():
                if assignee_name.lower() in name or name in assignee_name.lower():
                    assigned_to = uid
                    break
            task_list.append({
                "title":       t.get("task", "Vazifa"),
                "assigned_to": assigned_to,
                "priority":    t.get("priority", "orta"),
                "task_type":   "birmartalik",
                "created_by":  user["id"],
            })

        created = await create_task_bulk(task_list, created_by=user["id"])

        for task in (created or []):
            if task.get("assigned_to"):
                try:
                    assignee_row = next(
                        m for m in team_members if m["id"] == task["assigned_to"]
                    )
                    await call.bot.send_message(
                        assignee_row["telegram_id"],
                        f"📌 <b>Yangi vazifa (yig'ilishdan):</b>\n\n{task['title']}",
                        parse_mode="HTML"
                    )
                except Exception:
                    pass

    await state.clear()
    await call.message.edit_text(
        f"✅ <b>{len(tasks)} ta vazifa yaratildi!</b>\n\nMas'ullarga xabar yuborildi.",
        parse_mode="HTML"
    )


@router.callback_query(F.data == "meeting_edit")
async def meeting_edit(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text(
        "✏️ Tahrirlash uchun qayta audio yuboring yoki /cancel:"
    )
    await state.set_state(MeetingState.recording)


@router.callback_query(F.data == "meeting_cancel")
async def meeting_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("❌ Yig'ilish bekor qilindi.")


# ── SO'NGGI YIGʻILISHLAR ──────────────────────────────────────────────────────

@router.message(Command("meetings"))
async def list_meetings(message: Message):
    user = await get_user_by_telegram_id(message.from_user.id)
    if not user or user["role"] not in ("super_admin", "pm", "ad"):
        await message.answer("❌ Ruxsat yo'q.")
        return

    logs = await get_meeting_logs(limit=5)
    if not logs:
        await message.answer("📭 Yig'ilish yozuvlari yo'q.")
        return

    lines = ["📋 <b>So'nggi yig'ilishlar:</b>\n"]
    for log in logs:
        date = log["meeting_date"].strftime("%d.%m.%Y") if log.get("meeting_date") else "—"
        recorder = log.get("recorder_name", "—")
        lines.append(f"• {date} — {recorder}")
        if log.get("protocol_text"):
            lines.append(f"  <i>{log['protocol_text'][:80]}...</i>")

    await message.answer("\n".join(lines), parse_mode="HTML")
