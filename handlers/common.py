from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext

from database.queries.users import get_user_by_telegram_id, get_all_managers
from keyboards.reply import main_menu_kb, admin_menu_kb
from keyboards.inline import confirm_join_kb

router = Router()


# ── /start ───────────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()

    user = await get_user_by_telegram_id(message.from_user.id)

    # Yangi foydalanuvchi
    if not user:
        await message.answer(
            "👋 <b>Salom!</b>\n\n"
            "Siz hali ro'yxatda yo'qsiz.\n"
            "Admin tasdiqlashini kuting...",
            parse_mode="HTML"
        )
        # PM va AD ga xabar
        await _notify_new_member(message)
        return

    # Aktiv emas
    if not user["is_active"]:
        await message.answer("⏳ Hisobingiz hali tasdiqlanmagan. Admin bilan bog'laning.")
        return

    # Xush kelibsiz
    role_icons = {
        "super_admin": "👑",
        "pm":          "🟠",
        "ad":          "🟠",
        "member":      "🟢",
    }
    icon = role_icons.get(user["role"], "👤")

    await message.answer(
        f"{icon} <b>Xush kelibsiz, {user['full_name']}!</b>\n\n"
        f"Rol: <b>{user['role'].upper()}</b>\n\n"
        "Pastdagi menyudan foydalaning 👇",
        reply_markup=_get_menu(user["role"]),
        parse_mode="HTML"
    )


def _get_menu(role: str):
    if role in ("super_admin", "pm", "ad"):
        return admin_menu_kb()
    return main_menu_kb()


async def _notify_new_member(message: Message):
    """PM va AD ga yangi a'zo haqida xabar beradi."""
    managers = await get_all_managers()
    user = message.from_user

    for manager in managers:
        try:
            await message.bot.send_message(
                manager["telegram_id"],
                f"👤 <b>Yangi a'zo qo'shilmoqchi!</b>\n\n"
                f"Ism: <b>{user.full_name}</b>\n"
                f"Username: @{user.username or 'yo\'q'}\n"
                f"ID: <code>{user.id}</code>",
                reply_markup=confirm_join_kb(user.id, user.full_name),
                parse_mode="HTML"
            )
        except Exception:
            pass


# ── YANGI A'ZO TASDIQLASH ─────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("join_accept:"))
async def accept_new_member(call: CallbackQuery):
    _, telegram_id, role = call.data.split(":")
    telegram_id = int(telegram_id)

    from database.queries.users import create_user
    from aiogram.types import User

    # Foydalanuvchi ma'lumotlarini olish
    try:
        chat = await call.bot.get_chat(telegram_id)
        full_name = chat.full_name
        username = chat.username
    except Exception:
        full_name = f"User {telegram_id}"
        username = None

    await create_user(
        telegram_id=telegram_id,
        username=username,
        full_name=full_name,
        role=role,
        is_active=True
    )

    await call.message.edit_text(
        f"✅ <b>{full_name}</b> qabul qilindi!\nRol: <b>{role}</b>",
        parse_mode="HTML"
    )

    # Hodimga xabar
    await call.bot.send_message(
        telegram_id,
        f"✅ <b>Hisobingiz tasdiqlandi!</b>\n"
        f"Rol: <b>{role}</b>\n\n"
        "/start bosib boshlang.",
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("join_reject:"))
async def reject_new_member(call: CallbackQuery):
    _, telegram_id = call.data.split(":")
    telegram_id = int(telegram_id)

    await call.message.edit_text("❌ Rad etildi.")

    try:
        await call.bot.send_message(
            telegram_id,
            "❌ Afsus, so'rovingiz rad etildi. Admin bilan bog'laning."
        )
    except Exception:
        pass


# ── /help ────────────────────────────────────────────────────────────────────

@router.message(F.text == "📖 Yordam")
@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "📖 <b>Yordam</b>\n\n"
        "🎙️ <b>Audio</b> — vazifa berish yoki izoh qoldirish\n"
        "📋 <b>Vazifalarim</b> — mening vazifalarim\n"
        "➕ <b>Yangi vazifa</b> — qo'lda vazifa yaratish\n"
        "📊 <b>Statistika</b> — hisobot\n\n"
        "<i>Istalgan vaqt audio yuboring — bot tushunadi!</i>",
        parse_mode="HTML"
    )
