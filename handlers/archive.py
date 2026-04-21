import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database.queries.users import get_user_by_telegram_id
from database.queries.tasks import (
    search_archive, get_project_files_by_stage,
    get_meeting_logs, search_task_comments
)
from keyboards.inline import archive_search_kb

router = Router()
log = logging.getLogger(__name__)


class ArchiveSearch(StatesGroup):
    query = State()


# ── ARXIV QIDIRISH ───────────────────────────────────────────────────────────

@router.message(F.text == "🗄 Arxiv")
async def archive_menu(message: Message):
    user = await get_user_by_telegram_id(message.from_user.id)
    if not user:
        return

    await message.answer(
        "🗄 <b>Arxiv</b>\n\n"
        "Nima qidirmoqchisiz?",
        reply_markup=archive_search_kb(),
        parse_mode="HTML"
    )


# ── LOYIHA FAYLLARINI QIDIRISH ───────────────────────────────────────────────

@router.callback_query(F.data == "archive_files")
async def archive_files(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ArchiveSearch.query)
    await state.update_data(search_type="files")
    await callback.message.edit_text(
        "🔍 Loyiha nomini yozing:\n"
        "<i>Misol: Zavod videosi, Yangi Yil reklama...</i>",
        parse_mode="HTML"
    )


# ── YIGʻILISH PROTOKOLLARINI QIDIRISH ────────────────────────────────────────

@router.callback_query(F.data == "archive_meetings")
async def archive_meetings(callback: CallbackQuery):
    logs = await get_meeting_logs(limit=10)
    if not logs:
        await callback.message.edit_text("📭 Yig'ilish protokollari topilmadi.")
        return

    text = "📋 <b>Oxirgi yig'ilishlar:</b>\n\n"
    for log_item in logs:
        date  = log_item["meeting_date"].strftime("%d.%m.%Y")
        tasks = len(log_item.get("tasks_created") or [])
        text += (
            f"📅 {date}\n"
            f"📌 {tasks} ta vazifa yaratilgan\n"
            f"📝 {(log_item.get('protocol_text') or '')[:100]}...\n\n"
        )

    await callback.message.edit_text(text, parse_mode="HTML")


# ── IZOHLARNI QIDIRISH ───────────────────────────────────────────────────────

@router.callback_query(F.data == "archive_comments")
async def archive_comments(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ArchiveSearch.query)
    await state.update_data(search_type="comments")
    await callback.message.edit_text(
        "🔍 Kalit so'z yozing:\n"
        "<i>Misol: Chilonzor, montaj, muammo...</i>",
        parse_mode="HTML"
    )


# ── QIDIRUV NATIJASI ─────────────────────────────────────────────────────────

@router.message(ArchiveSearch.query)
async def process_search(message: Message, state: FSMContext):
    data = await state.get_data()
    search_type = data.get("search_type", "files")
    query = message.text.strip()

    await state.clear()

    if search_type == "files":
        results = await search_archive(query)
        if not results:
            await message.answer(f"📭 '{query}' bo'yicha hech narsa topilmadi.")
            return

        text = f"🗄 <b>'{query}' bo'yicha natijalar:</b>\n\n"
        for r in results[:5]:
            date = r["created_at"].strftime("%d.%m.%Y")
            stage_names = {
                "ideya": "Ideya", "ssenariy": "Ssenariy",
                "montajda": "Montaj", "dizaynda": "Dizayn", "nashr": "Nashr"
            }
            stage = stage_names.get(r.get("stage"), r.get("stage", "—"))
            text += (
                f"📁 <b>{r.get('project_title', '—')}</b>\n"
                f"   Etap: {stage} | 📅 {date}\n"
                f"   Yuklagan: {r.get('uploader_name', '—')}\n\n"
            )

        await message.answer(text, parse_mode="HTML")

        # Fayllarni yuborish
        for r in results[:3]:
            try:
                file_type = r.get("file_type", "document")
                if file_type == "video":
                    await message.answer_video(
                        r["file_id"],
                        caption=f"📁 {r.get('project_title')} — {r.get('stage')}"
                    )
                elif file_type == "photo":
                    await message.answer_photo(
                        r["file_id"],
                        caption=f"🖼 {r.get('project_title')} — {r.get('stage')}"
                    )
                else:
                    await message.answer_document(
                        r["file_id"],
                        caption=f"📄 {r.get('project_title')} — {r.get('stage')}"
                    )
            except Exception as e:
                log.error(f"Arxiv fayl yuborishda xato: {e}")

    elif search_type == "comments":
        results = await search_task_comments(query)
        if not results:
            await message.answer(f"📭 '{query}' bo'yicha izoh topilmadi.")
            return

        text = f"💬 <b>'{query}' bo'yicha izohlar:</b>\n\n"
        for r in results[:8]:
            date  = r["created_at"].strftime("%d.%m.%Y")
            c_icon = {
                "bajardim": "✅", "kechikadi": "⏳",
                "muammo": "🔴", "savol": "❓", "oddiy": "💬"
            }.get(r.get("comment_type"), "💬")
            text += (
                f"{c_icon} <b>{r.get('task_title', '—')}</b>\n"
                f"   👤 {r.get('user_name', '—')} | 📅 {date}\n"
                f"   <i>{r.get('text', '')[:100]}</i>\n\n"
            )

        await message.answer(text, parse_mode="HTML")


# ── JARAYON XOTIRASI (/savol) ────────────────────────────────────────────────

class SavolState(StatesGroup):
    waiting = State()


@router.message(F.text.startswith("/savol"))
async def savol_start(message: Message, state: FSMContext):
    parts = message.text.split(maxsplit=1)
    if len(parts) > 1:
        await _process_savol(message, parts[1].strip())
        return
    await state.set_state(SavolState.waiting)
    await message.answer(
        "🧠 <b>Jarayon Xotirasi</b>\n\nSavolingizni yozing:\n"
        "<i>Misol: Chilonzor syemkasida nima muammo bo'lgan?</i>",
        parse_mode="HTML"
    )


@router.message(SavolState.waiting)
async def savol_answer(message: Message, state: FSMContext):
    await state.clear()
    await _process_savol(message, message.text.strip())


async def _process_savol(message: Message, query: str):
    files = await search_archive(query)
    comments = await search_task_comments(query)
    if not files and not comments:
        await message.answer(
            f"📭 '<i>{query}</i>' bo'yicha hech narsa topilmadi.",
            parse_mode="HTML"
        )
        return

    lines = [f"🧠 <b>'{query}' bo'yicha:</b>\n"]
    if comments:
        lines.append("💬 <b>Izohlar:</b>")
        for r in comments[:5]:
            c_icon = {"muammo": "🔴", "savol": "❓", "bajardim": "✅"}.get(
                r.get("comment_type"), "💬"
            )
            lines.append(
                f"{c_icon} <b>{r.get('task_title', '—')}</b>\n"
                f"   {r.get('user_name', '—')}: <i>{r.get('text', '')[:80]}</i>"
            )
        lines.append("")
    if files:
        lines.append("📁 <b>Fayllar:</b>")
        for r in files[:3]:
            lines.append(f"  • {r.get('project_title', '—')} — {r.get('stage', '—')}")

    await message.answer("\n".join(lines), parse_mode="HTML")
