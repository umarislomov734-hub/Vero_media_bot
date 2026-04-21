import asyncio

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, Document, PhotoSize, Video
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database.queries.users import get_user_by_telegram_id, get_managers
from database.queries.tasks import (
    get_task, complete_task, return_task,
    add_comment, add_task_file
)
from database.connection import get_pool

router = Router()


async def _maybe_delete_gcal_event(task_id: int, user_internal_id: int) -> None:
    try:
        from database.queries.tasks import get_gcal_event, delete_gcal_event_record
        from database.queries.users import get_google_token
        from utils.google_calendar import delete_event as gcal_delete

        event_id = await get_gcal_event(task_id, user_internal_id)
        if not event_id:
            return
        token_data = await get_google_token(user_internal_id)
        if not token_data:
            return
        await gcal_delete(token_data, event_id)
        await delete_gcal_event_record(task_id, user_internal_id)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"_maybe_delete_gcal_event xatosi: {e}")


async def _maybe_update_gcal_event(
    task_id: int, assignee_internal_id: int, task_title: str, new_deadline_dt
) -> None:
    try:
        from database.queries.tasks import get_gcal_event
        from database.queries.users import get_google_token, save_google_token
        from utils.google_calendar import update_event as gcal_update, refresh_token_if_needed

        event_id = await get_gcal_event(task_id, assignee_internal_id)
        if not event_id:
            return
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
        await gcal_update(fresh, event_id, task_title, new_deadline_dt)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"_maybe_update_gcal_event xatosi: {e}")


class CommentState(StatesGroup):
    waiting_comment  = State()
    waiting_return   = State()
    waiting_file     = State()


# ── BAJARILDI ────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("complete:"))
async def start_complete(call: CallbackQuery, state: FSMContext):
    task_id = int(call.data.split(":")[1])
    task = await get_task(task_id)

    if not task:
        await call.answer("Vazifa topilmadi!", show_alert=True)
        return

    await state.set_state(CommentState.waiting_comment)
    await state.update_data(commenting_task_id=task_id, action="complete")

    await call.message.edit_text(
        f"✅ <b>{task['title']}</b>\n\n"
        "🎙️ Audio yoki matn bilan izoh qoldiring:\n"
        "<i>Nima qildingiz? Natija qanday?</i>\n\n"
        "Faylni ham biriktirish mumkin (/skip — o'tkazib yuborish)",
        parse_mode="HTML"
    )


@router.message(CommentState.waiting_comment, F.text.startswith("/skip"))
async def skip_comment_complete(message: Message, state: FSMContext):
    data = await state.get_data()
    task_id = data["commenting_task_id"]
    user = await get_user_by_telegram_id(message.from_user.id)

    await complete_task(task_id)
    asyncio.create_task(_maybe_delete_gcal_event(task_id, user["id"]))
    await state.set_state(CommentState.waiting_file)

    await message.answer(
        "✅ Vazifa bajarildi deb belgilandi!\n\n"
        "📎 Natija faylini yuboring yoki /skip:",
    )


@router.message(CommentState.waiting_comment, F.text)
async def text_comment_complete(message: Message, state: FSMContext):
    data = await state.get_data()
    task_id = data["commenting_task_id"]
    user = await get_user_by_telegram_id(message.from_user.id)

    await add_comment(
        task_id=task_id,
        user_id=user["id"],
        text=message.text,
        comment_type="bajardim"
    )
    await complete_task(task_id)
    asyncio.create_task(_maybe_delete_gcal_event(task_id, user["id"]))
    await state.set_state(CommentState.waiting_file)

    await message.answer(
        "✅ Izoh saqlandi, vazifa bajarildi!\n\n"
        "📎 Natija faylini yuboring yoki /skip:",
    )

    # Pipeline keyingi etapga
    from handlers.audio import _check_pipeline_advance
    await _check_pipeline_advance(task_id, message.bot)


# ── FAYL YUKLASH ─────────────────────────────────────────────────────────────

@router.message(CommentState.waiting_file, F.document | F.photo | F.video)
async def upload_result_file(message: Message, state: FSMContext):
    data = await state.get_data()
    task_id = data["commenting_task_id"]
    user = await get_user_by_telegram_id(message.from_user.id)

    # Fayl turini aniqlash
    if message.document:
        file_id   = message.document.file_id
        file_type = "document"
        file_name = message.document.file_name
    elif message.photo:
        file_id   = message.photo[-1].file_id
        file_type = "photo"
        file_name = "photo.jpg"
    elif message.video:
        file_id   = message.video.file_id
        file_type = "video"
        file_name = message.video.file_name or "video.mp4"
    else:
        await message.answer("❌ Fayl turi qo'llab-quvvatlanmaydi.")
        return

    # Vazifaning loyihasini olish
    task = await get_task(task_id)

    await add_task_file(
        task_id=task_id,
        project_id=task.get("project_id"),
        uploaded_by=user["id"],
        file_id=file_id,
        file_type=file_type,
    )

    await state.clear()
    await message.answer(
        f"📎 Fayl arxivga saqlandi!\n"
        f"<code>{file_name}</code>",
        parse_mode="HTML"
    )


@router.message(CommentState.waiting_file, F.text.startswith("/skip"))
async def skip_file(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("✅ Tugadi. Fayl saqlanmadi.")


# ── VAZIFA QAYTARISH (PM / AD) ────────────────────────────────────────────────

@router.callback_query(F.data.startswith("return:"))
async def start_return(call: CallbackQuery, state: FSMContext):
    task_id = int(call.data.split(":")[1])
    task = await get_task(task_id)

    if not task:
        await call.answer("Vazifa topilmadi!", show_alert=True)
        return

    await state.set_state(CommentState.waiting_return)
    await state.update_data(returning_task_id=task_id)

    await call.message.edit_text(
        f"↩️ <b>{task['title']}</b>\n\n"
        "Qaytarish sababini yozing yoki audio yuboring:\n"
        "<i>Nima yetishmadi? Nima qayta qilinsin?</i>",
        parse_mode="HTML"
    )


@router.message(CommentState.waiting_return, F.text | F.voice)
async def process_return(message: Message, state: FSMContext):
    data = await state.get_data()
    task_id = data["returning_task_id"]
    user = await get_user_by_telegram_id(message.from_user.id)

    # Matn yoki audio
    if message.voice:
        from ai.transcriber import transcribe_from_telegram
        from ai.task_parser import parse_comment
        raw_text = await transcribe_from_telegram(message.bot, message.voice.file_id)
        result = await parse_comment(raw_text)
        reason = result.get("clean_text", raw_text)
        audio_id = message.voice.file_id
    else:
        reason = message.text
        audio_id = None

    task = await get_task(task_id)

    # Qaytarish
    await return_task(task_id, reason)

    # Izoh qo'shish
    await add_comment(
        task_id=task_id,
        user_id=user["id"],
        text=f"↩️ Qaytarildi: {reason}",
        comment_type="oddiy",
        audio_file_id=audio_id
    )

    await state.clear()

    await message.answer(
        f"↩️ Vazifa qaytarildi!\n\n"
        f"📌 {task['title']}\n"
        f"Sabab: <i>{reason}</i>",
        parse_mode="HTML"
    )

    # Mas'ulga xabar
    from database.queries.users import get_user
    if task.get("assigned_to"):
        assignee = await get_user(task["assigned_to"])
        if assignee:
            await message.bot.send_message(
                assignee["telegram_id"],
                f"↩️ <b>Vazifa qaytarildi!</b>\n\n"
                f"📌 {task['title']}\n\n"
                f"Sabab: <i>{reason}</i>\n\n"
                "Qayta bajarib, 'Bajardim' deb yuboring.",
                parse_mode="HTML"
            )


# ── IZOH QOLDIRISH ────────────────────────────────────────────────────────────

class IzohState(StatesGroup):
    waiting = State()


@router.callback_query(F.data.startswith("comment:"))
async def start_comment(call: CallbackQuery, state: FSMContext):
    task_id = int(call.data.split(":")[1])
    task = await get_task(task_id)
    if not task:
        await call.answer("Vazifa topilmadi!", show_alert=True)
        return

    await state.set_state(IzohState.waiting)
    await state.update_data(comment_task_id=task_id)

    await call.message.edit_text(
        f"💬 <b>{task['title']}</b>\n\n"
        "Izohingizni yozing (matn yoki audio):\n"
        "<i>Savol, muammo yoki holat haqida</i>",
        parse_mode="HTML"
    )


@router.message(IzohState.waiting, F.text | F.voice)
async def save_comment(message: Message, state: FSMContext):
    data = await state.get_data()
    task_id = data["comment_task_id"]
    user = await get_user_by_telegram_id(message.from_user.id)

    if message.voice:
        from ai.transcriber import transcribe_from_telegram
        text = await transcribe_from_telegram(message.bot, message.voice.file_id)
        audio_id = message.voice.file_id
        comment_type = "oddiy"
    else:
        text = message.text
        audio_id = None
        t = text.lower()
        if any(w in t for w in ["muammo", "xato", "ishlamaydi"]):
            comment_type = "muammo"
        elif any(w in t for w in ["savol", "?"]):
            comment_type = "savol"
        elif any(w in t for w in ["kechikadi", "kechikaman", "ulgurmayman"]):
            comment_type = "kechikadi"
        else:
            comment_type = "oddiy"

    await add_comment(
        task_id=task_id,
        user_id=user["id"],
        text=text,
        comment_type=comment_type,
        audio_file_id=audio_id
    )
    await state.clear()
    await message.answer("💬 Izoh saqlandi!")


# ── VAZIFA TAHRIRLASH ─────────────────────────────────────────────────────────

class EditTaskState(StatesGroup):
    field   = State()
    value   = State()


@router.callback_query(F.data.startswith("edit:"))
async def start_edit_task(call: CallbackQuery, state: FSMContext):
    task_id = int(call.data.split(":")[1])
    task = await get_task(task_id)
    if not task:
        await call.answer("Vazifa topilmadi!", show_alert=True)
        return

    await state.set_state(EditTaskState.field)
    await state.update_data(edit_task_id=task_id)

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text="📌 Sarlavha",  callback_data="edit_field:title")
    builder.button(text="⏰ Deadline",  callback_data="edit_field:deadline")
    builder.button(text="❌ Bekor",     callback_data=f"task:{task_id}")
    builder.adjust(2, 1)

    await call.message.edit_text(
        f"✏️ <b>{task['title']}</b>\n\nNimani o'zgartirmoqchisiz?",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("edit_field:"))
async def choose_edit_field(call: CallbackQuery, state: FSMContext):
    field = call.data.split(":")[1]
    await state.update_data(edit_field=field)
    await state.set_state(EditTaskState.value)

    if field == "title":
        await call.message.edit_text("📌 Yangi sarlavhani yozing:")
    else:
        await call.message.edit_text("⏰ Yangi deadline (DD.MM.YYYY HH:MM):")


@router.message(EditTaskState.value, F.text)
async def save_edit_value(message: Message, state: FSMContext):
    data = await state.get_data()
    task_id = data["edit_task_id"]
    field   = data["edit_field"]

    pool = await get_pool()
    async with pool.acquire() as conn:
        if field == "title":
            await conn.execute("UPDATE tasks SET title=$1, updated_at=NOW() WHERE id=$2",
                               message.text.strip(), task_id)
            await message.answer(f"✅ Sarlavha yangilandi: <b>{message.text.strip()}</b>",
                                 parse_mode="HTML")
        else:
            from datetime import datetime
            import pytz
            tz = pytz.timezone("Asia/Tashkent")
            try:
                dl = datetime.strptime(message.text.strip(), "%d.%m.%Y %H:%M")
                dl = tz.localize(dl)
                await conn.execute("UPDATE tasks SET deadline=$1, updated_at=NOW() WHERE id=$2",
                                   dl, task_id)
                await message.answer(f"✅ Deadline yangilandi: <b>{dl.strftime('%d.%m.%Y %H:%M')}</b>",
                                     parse_mode="HTML")
                task = await get_task(task_id)
                if task and task.get("assigned_to"):
                    asyncio.create_task(_maybe_update_gcal_event(
                        task_id, task["assigned_to"], task["title"], dl
                    ))
            except ValueError:
                await message.answer("❌ Format noto'g'ri. Masalan: 25.04.2026 18:00")
                return

    await state.clear()


# ── VAZIFANI BEKOR QILISH ─────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("cancel_task:"))
async def cancel_task_handler(call: CallbackQuery):
    task_id = int(call.data.split(":")[1])
    task = await get_task(task_id)
    if not task:
        await call.answer("Vazifa topilmadi!", show_alert=True)
        return

    user = await get_user_by_telegram_id(call.from_user.id)
    if not user or user["role"] not in ("super_admin", "pm", "ad"):
        await call.answer("❌ Ruxsat yo'q", show_alert=True)
        return

    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE tasks SET status='bekor_qilindi', updated_at=NOW() WHERE id=$1",
            task_id
        )

    await call.answer("❌ Vazifa bekor qilindi", show_alert=True)

    if task.get("assigned_to"):
        asyncio.create_task(_maybe_delete_gcal_event(task_id, task["assigned_to"]))

    from database.queries.users import get_user
    if task.get("assigned_to"):
        assignee = await get_user(task["assigned_to"])
        if assignee:
            try:
                await call.bot.send_message(
                    assignee["telegram_id"],
                    f"❌ <b>Vazifa bekor qilindi:</b>\n\n📌 {task['title']}",
                    parse_mode="HTML"
                )
            except Exception:
                pass

    await call.message.edit_text(
        f"❌ <b>{task['title']}</b>\n\nVazifa bekor qilindi.",
        parse_mode="HTML"
    )
