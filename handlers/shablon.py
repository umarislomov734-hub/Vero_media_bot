from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database.queries.users import get_user_by_telegram_id, get_all_active_members
from database.queries.tasks import create_task
from database.connection import get_pool

router = Router()

YOUTUBE_ETAPLAR = [
    ("Yangi ideya — tasdiqlanmoqda",   "ad"),
    ("Ssenariy yozilmoqda",            "ssenarист"),
    ("Syemkaga tayyorgarlik",          "operator"),
    ("Syemka",                         "operator"),
    ("Montaj",                         "montajchi"),
    ("Dizayn (thumbnail/grafika)",     "dizayner"),
    ("Tekshiruv",                      "ad"),
    ("Nashr",                          "kontent_menejer"),
]

REELS_ETAPLAR = [
    ("Ssenariy",   "ssenarист"),
    ("Syemka",     "operator"),
    ("Montaj",     "montajchi"),
    ("Nashr",      "kontent_menejer"),
]


class ShabState(StatesGroup):
    choose   = State()
    title    = State()
    deadline = State()


@router.message(F.text == "📋 Shablonlar")
async def show_templates(message: Message, state: FSMContext):
    user = await get_user_by_telegram_id(message.from_user.id)
    if not user or user["role"] not in ("super_admin", "pm", "ad"):
        await message.answer("❌ Ruxsat yo'q.")
        return

    await state.set_state(ShabState.choose)
    builder = InlineKeyboardBuilder()
    builder.button(text="🎬 YouTube video (8 etap)", callback_data="shab:youtube")
    builder.button(text="⚡ Reels / Shorts (4 etap)", callback_data="shab:reels")
    builder.button(text="📅 Haftalik reja",           callback_data="shab:hafta")
    builder.adjust(1)

    await message.answer(
        "📋 <b>Tez Shablonlar</b>\n\nQaysi shablon?",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )


@router.callback_query(ShabState.choose, F.data.startswith("shab:"))
async def choose_template(call: CallbackQuery, state: FSMContext):
    shab = call.data.split(":")[1]
    await state.update_data(shab=shab, creator_tg=call.from_user.id)
    await state.set_state(ShabState.title)

    names = {"youtube": "YouTube video", "reels": "Reels/Shorts", "hafta": "Haftalik reja"}
    await call.message.edit_text(
        f"📋 <b>{names[shab]}</b>\n\nLoyiha/mavzu nomini yozing:",
        parse_mode="HTML"
    )


@router.message(ShabState.title)
async def get_shab_title(message: Message, state: FSMContext):
    await state.set_state(ShabState.deadline)
    await state.update_data(shab_title=message.text.strip())
    await message.answer(
        "⏰ Umumiy deadline (DD.MM YYYY HH:MM) yoki /skip:"
    )


@router.message(ShabState.deadline)
async def create_from_template(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()

    shab  = data["shab"]
    title = data["shab_title"]
    creator_tg = data["creator_tg"]

    from database.queries.users import get_user_by_telegram_id as _get
    creator = await _get(creator_tg)
    if not creator:
        await message.answer("❌ Xato: foydalanuvchi topilmadi.")
        return

    deadline = None
    if not message.text.strip().startswith("/skip"):
        from handlers.tasks.create import _parse_deadline
        deadline = _parse_deadline(message.text.strip())

    # Jamoa lavozim xaritasi
    members = await get_all_active_members()
    pos_map = {}
    for m in members:
        pos = (m.get("position") or "").lower()
        if pos and pos not in pos_map:
            pos_map[pos] = m["id"]

    if shab == "youtube":
        etaplar = YOUTUBE_ETAPLAR
    elif shab == "reels":
        etaplar = REELS_ETAPLAR
    else:
        await _create_haftalik(message, creator, members, deadline)
        return

    created = 0
    for etap_title, position in etaplar:
        assignee_id = pos_map.get(position)
        task = await create_task(
            title=f"{title} — {etap_title}",
            assigned_to=assignee_id,
            created_by=creator["id"],
            priority="orta",
            task_type="loyiha",
            deadline=deadline.isoformat() if deadline else None,
            source="manual"
        )
        if task and assignee_id:
            assignee = next((m for m in members if m["id"] == assignee_id), None)
            if assignee:
                try:
                    await message.bot.send_message(
                        assignee["telegram_id"],
                        f"📌 <b>Yangi vazifa ({shab.upper()} shablon):</b>\n\n"
                        f"{title} — {etap_title}",
                        parse_mode="HTML"
                    )
                except Exception:
                    pass
        created += 1

    await message.answer(
        f"✅ <b>{created} ta vazifa yaratildi!</b>\n\n"
        f"📋 {title}\n"
        f"Barcha mas'ullar xabardor qilindi.",
        parse_mode="HTML"
    )


async def _create_haftalik(message, creator, members, deadline):
    lines = ["📅 <b>Haftalik reja yaratildi:</b>\n"]
    for m in members:
        task = await create_task(
            title=f"Haftalik vazifa — {m['full_name']}",
            assigned_to=m["id"],
            created_by=creator["id"],
            priority="orta",
            task_type="rutiniy",
            deadline=deadline.isoformat() if deadline else None,
            source="manual"
        )
        if task:
            try:
                await message.bot.send_message(
                    m["telegram_id"],
                    f"📅 <b>Haftalik reja yangilandi!</b>\n\n"
                    f"Vazifangizni bajarib, izoh qoldiring.",
                    parse_mode="HTML"
                )
            except Exception:
                pass
        lines.append(f"  • {m['full_name']}")

    await message.answer("\n".join(lines), parse_mode="HTML")
