from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database.queries.users import get_user_by_telegram_id
from database.queries.stats import save_growth_log, get_growth_logs
from ai.transcriber import transcribe_from_telegram

router = Router()


class GrowthState(StatesGroup):
    waiting_audio = State()


# ── BO'SH VAQT MODULI ─────────────────────────────────────────────────────────

@router.message(F.text == "📚 O'sish")
async def growth_menu(message: Message, state: FSMContext):
    user = await get_user_by_telegram_id(message.from_user.id)
    if not user:
        return

    logs = await get_growth_logs(user["id"], limit=3)

    lines = [
        "📚 <b>O'sish moduli</b>\n",
        "Bugun nima o'rgandingiz? Audio yuboring!\n"
    ]
    if logs:
        lines.append("<b>So'nggi yozuvlar:</b>")
        for log in logs:
            date = log["date"].strftime("%d.%m") if log.get("date") else "—"
            lines.append(f"• {date}: {log['description'][:60]}")

    await message.answer("\n".join(lines), parse_mode="HTML")
    await state.set_state(GrowthState.waiting_audio)


@router.message(GrowthState.waiting_audio, F.voice | F.audio)
async def handle_growth_audio(message: Message, state: FSMContext):
    user = await get_user_by_telegram_id(message.from_user.id)
    if not user:
        await state.clear()
        return

    wait = await message.answer("🎙️ Tahlil qilinmoqda...")

    file_id = message.voice.file_id if message.voice else message.audio.file_id
    text = await transcribe_from_telegram(message.bot, file_id)

    if not text.strip():
        await wait.edit_text("❌ Audio tushunilmadi.")
        await state.clear()
        return

    await save_growth_log(user["id"], "audio_log", text)
    await wait.edit_text(
        f"✅ <b>Yozib qo'yildi!</b>\n\n<i>{text[:200]}</i>",
        parse_mode="HTML"
    )
    await state.clear()


@router.message(GrowthState.waiting_audio, F.text)
async def handle_growth_text(message: Message, state: FSMContext):
    user = await get_user_by_telegram_id(message.from_user.id)
    if not user:
        await state.clear()
        return

    await save_growth_log(user["id"], "text_log", message.text)
    await message.answer("✅ Yozib qo'yildi!", parse_mode="HTML")
    await state.clear()
