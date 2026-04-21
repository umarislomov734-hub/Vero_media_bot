import logging
import os
import uuid

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database.connection import get_pool
from database.queries.users import (
    get_user_by_telegram_id,
    get_google_token,
    disconnect_google,
)
from utils.google_calendar import get_auth_url

router = Router()
log    = logging.getLogger(__name__)


@router.message(Command("calendar"))
async def cmd_calendar(message: Message):
    user = await get_user_by_telegram_id(message.from_user.id)
    if not user:
        return

    token = await get_google_token(user["id"])

    if token:
        builder = InlineKeyboardBuilder()
        builder.button(text="❌ Google Calendar uzish", callback_data="gcal_disconnect")
        await message.answer(
            "✅ <b>Google Calendar ulangan!</b>\n\n"
            "Deadline berilgan vazifalar avtomatik kalendaringizga qo'shiladi.\n\n"
            "Uzmoqchimisiz?",
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
        return

    client_id     = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    redirect_uri  = os.getenv("GOOGLE_REDIRECT_URI")

    if not all([client_id, client_secret, redirect_uri]):
        await message.answer(
            "⚠️ Google Calendar hali sozlanmagan.\n"
            "Admin bilan bog'laning."
        )
        return

    state = str(uuid.uuid4())
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO gcal_oauth_states (telegram_id, state) VALUES ($1,$2) "
            "ON CONFLICT (state) DO NOTHING",
            message.from_user.id, state
        )

    auth_url = get_auth_url(client_id, client_secret, redirect_uri, state)

    builder = InlineKeyboardBuilder()
    builder.button(text="🔗 Google Calendar ga ulash", url=auth_url)

    await message.answer(
        "📅 <b>Google Calendar ulanishi</b>\n\n"
        "Quyidagi tugmani bosib Google hisobingizga ruxsat bering.\n\n"
        "<i>Ruxsat bergandan so'ng deadline berilgan barcha vazifalar "
        "avtomatik kalendaringizga qo'shiladi.</i>",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "gcal_disconnect")
async def gcal_disconnect(call: CallbackQuery):
    user = await get_user_by_telegram_id(call.from_user.id)
    if not user:
        return
    await disconnect_google(user["id"])
    await call.message.edit_text(
        "❌ <b>Google Calendar uzildi.</b>\n\n"
        "Qayta ulash uchun /calendar yuboring.",
        parse_mode="HTML"
    )
