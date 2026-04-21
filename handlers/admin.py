from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database.queries.users import (
    get_user_by_telegram_id, get_all_active_members,
    approve_user, reject_user, get_user_task_load, get_user
)
from keyboards.inline import admin_team_kb, admin_member_kb

router = Router()


class AssignRoleState(StatesGroup):
    waiting_user_id = State()
    waiting_role = State()


ROLES = ["member", "pm", "ad", "super_admin"]
ROLE_LABELS = {
    "member":      "🟢 Member",
    "pm":          "🟠 PM",
    "ad":          "🟠 AD",
    "super_admin": "👑 Super Admin",
}


# ── JAMOA ────────────────────────────────────────────────────────────────────

@router.message(F.text == "👥 Jamoa")
async def team_view(message: Message):
    user = await get_user_by_telegram_id(message.from_user.id)
    if not user or user["role"] not in ("super_admin", "pm", "ad"):
        await message.answer("❌ Ruxsat yo'q.")
        return

    members = await get_all_active_members()
    if not members:
        await message.answer("Hodimlar yo'q.")
        return

    lines = ["👥 <b>Jamoa yuklanishi:</b>\n"]
    for m in members:
        load = await get_user_task_load(m["id"])
        if load == 0:
            icon = "🟢"
        elif load <= 3:
            icon = "🟡"
        else:
            icon = "🔴"
        role = ROLE_LABELS.get(m["role"], "👤")
        lines.append(f"{icon} <b>{m['full_name']}</b> — {load} ta vazifa | {role}")

    await message.answer("\n".join(lines), parse_mode="HTML")


# ── ADMIN PANEL ──────────────────────────────────────────────────────────────

@router.message(F.text == "⚙️ Admin panel")
@router.message(Command("admin"))
async def admin_panel(message: Message):
    user = await get_user_by_telegram_id(message.from_user.id)
    if not user or user["role"] not in ("super_admin", "pm", "ad"):
        await message.answer("❌ Ruxsat yo'q.")
        return

    await message.answer(
        "⚙️ <b>Admin panel</b>\n\n"
        "/members — barcha hodimlar ro'yxati\n"
        "/setrole — hodimga rol berish\n"
        "/stats — haftalik hisobot",
        parse_mode="HTML"
    )


# ── HODIMLAR RO'YXATI ─────────────────────────────────────────────────────────

@router.message(Command("members"))
async def list_members(message: Message):
    user = await get_user_by_telegram_id(message.from_user.id)
    if not user or user["role"] not in ("super_admin", "pm", "ad"):
        await message.answer("❌ Ruxsat yo'q.")
        return

    members = await get_all_active_members()
    if not members:
        await message.answer("Hodimlar yo'q.")
        return

    lines = ["👥 <b>Barcha hodimlar:</b>\n"]
    for m in members:
        icon = ROLE_LABELS.get(m["role"], "👤")
        pos = f" | {m['position']}" if m.get("position") else ""
        lines.append(f"{icon} <b>{m['full_name']}</b>{pos}")

    await message.answer("\n".join(lines), parse_mode="HTML")


# ── ADMIN → HODIM BOSHQARUVI (inline) ───────────────────────────────────────

@router.callback_query(F.data == "back_admin")
async def cb_back_admin(call: CallbackQuery):
    user = await get_user_by_telegram_id(call.from_user.id)
    if not user or user["role"] not in ("super_admin", "pm", "ad"):
        return await call.answer("❌ Ruxsat yo'q", show_alert=True)
    await call.message.edit_text(
        "⚙️ <b>Admin panel</b>\n\n"
        "/members — barcha hodimlar\n"
        "/setrole — rol berish\n"
        "/stats — hisobot",
        parse_mode="HTML"
    )


@router.callback_query(F.data == "admin_team")
async def cb_admin_team(call: CallbackQuery):
    user = await get_user_by_telegram_id(call.from_user.id)
    if not user or user["role"] not in ("super_admin", "pm", "ad"):
        return await call.answer("❌ Ruxsat yo'q", show_alert=True)

    members = await get_all_active_members()
    await call.message.edit_text(
        "👥 <b>Hodimni tanlang:</b>",
        reply_markup=admin_team_kb(members),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("admin_member:"))
async def cb_admin_member(call: CallbackQuery):
    member_id = int(call.data.split(":")[1])
    member = await get_user(member_id)
    if not member:
        return await call.answer("Topilmadi", show_alert=True)

    load = await get_user_task_load(member_id)
    icon = ROLE_LABELS.get(member["role"], "👤")
    await call.message.edit_text(
        f"👤 <b>{member['full_name']}</b>\n"
        f"Rol: {icon}\n"
        f"Yuklanish: {load} ta faol vazifa",
        reply_markup=admin_member_kb(member_id, member["role"]),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("change_role:"))
async def cb_change_role(call: CallbackQuery):
    _, member_id, new_role = call.data.split(":")
    member = await get_user(int(member_id))
    if not member:
        return await call.answer("Topilmadi", show_alert=True)

    await approve_user(member["telegram_id"], new_role)
    await call.answer(f"✅ {ROLE_LABELS.get(new_role, new_role)} roli berildi", show_alert=True)

    try:
        await call.bot.send_message(
            member["telegram_id"],
            f"✅ Rolingiz yangilandi: <b>{ROLE_LABELS.get(new_role, new_role)}</b>",
            parse_mode="HTML"
        )
    except Exception:
        pass
    await cb_admin_member(call)


@router.callback_query(F.data.startswith("deactivate:"))
async def cb_deactivate(call: CallbackQuery):
    member_id = int(call.data.split(":")[1])
    member = await get_user(member_id)
    if not member:
        return await call.answer("Topilmadi", show_alert=True)

    from database.connection import get_pool
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET is_active=FALSE WHERE id=$1", member_id)

    await call.answer(f"🚫 {member['full_name']} o'chirildi", show_alert=True)
    members = await get_all_active_members()
    await call.message.edit_text(
        "👥 <b>Hodimni tanlang:</b>",
        reply_markup=admin_team_kb(members),
        parse_mode="HTML"
    )


# ── ROL BERISH ────────────────────────────────────────────────────────────────

@router.message(Command("setrole"))
async def set_role_start(message: Message, state: FSMContext):
    user = await get_user_by_telegram_id(message.from_user.id)
    if not user or user["role"] != "super_admin":
        await message.answer("❌ Faqat Super Admin rol bera oladi.")
        return

    members = await get_all_active_members()
    lines = ["👤 <b>Hodim Telegram ID sini yozing:</b>\n"]
    for m in members:
        lines.append(f"• {m['full_name']} — <code>{m['telegram_id']}</code>")

    await message.answer("\n".join(lines), parse_mode="HTML")
    await state.set_state(AssignRoleState.waiting_user_id)


@router.message(AssignRoleState.waiting_user_id)
async def get_user_id_for_role(message: Message, state: FSMContext):
    try:
        telegram_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Raqam kiriting.")
        return

    target = await get_user_by_telegram_id(telegram_id)
    if not target:
        await message.answer("❌ Foydalanuvchi topilmadi.")
        return

    await state.update_data(target_telegram_id=telegram_id, target_name=target["full_name"])

    role_list = "\n".join(f"{i+1}. {ROLE_LABELS[r]}" for i, r in enumerate(ROLES))
    await message.answer(
        f"👤 <b>{target['full_name']}</b> uchun rol tanlang:\n\n{role_list}\n\nRaqam yozing:",
        parse_mode="HTML"
    )
    await state.set_state(AssignRoleState.waiting_role)


@router.message(AssignRoleState.waiting_role)
async def assign_role(message: Message, state: FSMContext):
    try:
        idx = int(message.text.strip()) - 1
        role = ROLES[idx]
    except (ValueError, IndexError):
        await message.answer("❌ 1–4 orasida raqam kiriting.")
        return

    data = await state.get_data()
    telegram_id = data["target_telegram_id"]
    name = data["target_name"]

    await approve_user(telegram_id, role)
    await state.clear()

    await message.answer(
        f"✅ <b>{name}</b> ga <b>{ROLE_LABELS[role]}</b> roli berildi.",
        parse_mode="HTML"
    )

    try:
        await message.bot.send_message(
            telegram_id,
            f"✅ Rolingiz yangilandi: <b>{ROLE_LABELS[role]}</b>\n/start bosing.",
            parse_mode="HTML"
        )
    except Exception:
        pass
