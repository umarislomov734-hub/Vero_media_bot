import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database.queries.users import get_user_by_telegram_id
from database.queries.tasks import (
    get_active_projects, get_publish_pack,
    create_publish_pack, update_publish_pack
)
from keyboards.inline import (
    select_project_kb, select_platform_kb,
    select_pack_field_kb, publish_confirm_kb
)
from utils.publish_pack import collect_publish_pack, attach_file_to_pack

router = Router()
log = logging.getLogger(__name__)


class AttachFile(StatesGroup):
    select_project  = State()
    select_platform = State()
    select_field    = State()
    waiting_file    = State()


# ── NASHR PANELI ─────────────────────────────────────────────────────────────

@router.message(F.text == "🚀 Nashr paneli")
async def publish_panel(message: Message):
    user = await get_user_by_telegram_id(message.from_user.id)
    if not user:
        return

    projects = await get_active_projects()
    if not projects:
        await message.answer("📭 Hozirda faol loyihalar yo'q.")
        return

    await message.answer(
        "🚀 <b>Nashr Paneli</b>\n\nQaysi loyiha?",
        reply_markup=select_project_kb(projects),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("publish_project:"))
async def publish_project_detail(callback: CallbackQuery):
    project_id = int(callback.data.split(":")[1])
    pack = await get_publish_pack(project_id)

    if not pack:
        pack = await create_publish_pack(project_id)

    # To'liqlik tekshirish
    from utils.publish_pack import REQUIRED_FIELDS, _check_missing_fields
    missing = _check_missing_fields(pack)

    field_names = {
        "yt_video_id":     "YouTube video",
        "yt_thumbnail_id": "YouTube thumbnail",
        "yt_title":        "YouTube sarlavha",
        "yt_description":  "YouTube tavsif",
        "ig_video_id":     "Instagram video",
        "ig_cover_id":     "Instagram cover",
        "ig_caption":      "Instagram caption",
        "tg_video_id":     "Telegram video",
        "tg_post_text":    "Telegram post",
    }

    if missing:
        missing_list = "\n".join(
            f"  ❌ {field_names.get(m['field'], m['field'])} ({m['platform'].upper()})"
            for m in missing
        )
        text = (
            f"📦 <b>Nashr paketi holati:</b>\n\n"
            f"Yetishmayapti:\n{missing_list}\n\n"
            f"Fayl biriktirish uchun tugmani bosing."
        )
    else:
        text = (
            f"📦 <b>Nashr paketi to'liq!</b>\n\n"
            f"✅ YouTube: tayyor\n"
            f"✅ Instagram: tayyor\n"
            f"✅ Telegram: tayyor\n\n"
            f"Nashr qilishga tayormisiz?"
        )

    await callback.message.edit_text(
        text,
        reply_markup=publish_confirm_kb(project_id, bool(not missing)),
        parse_mode="HTML"
    )


# ── FAYL BIRIKTIRISH ─────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("attach_file:"))
async def attach_file_start(callback: CallbackQuery, state: FSMContext):
    project_id = int(callback.data.split(":")[1])
    await state.update_data(project_id=project_id)
    await state.set_state(AttachFile.select_platform)

    await callback.message.edit_text(
        "Qaysi platforma uchun fayl?",
        reply_markup=select_platform_kb(),
    )


@router.callback_query(F.data == "cancel_publish")
async def cancel_publish(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Nashr bekor qilindi.")


@router.callback_query(F.data.startswith("pack_platform:"), AttachFile.select_platform)
async def select_platform(callback: CallbackQuery, state: FSMContext):
    platform = callback.data.split(":")[1]
    await state.update_data(platform=platform)
    await state.set_state(AttachFile.select_field)

    platform_fields = {
        "youtube":   [("yt_video_id","🎬 Video"), ("yt_thumbnail_id","🖼 Thumbnail"),
                      ("yt_title","📝 Sarlavha"), ("yt_description","📄 Tavsif"), ("yt_tags","🏷 Teglar")],
        "instagram": [("ig_video_id","🎬 Reels video"), ("ig_cover_id","🖼 Cover"),
                      ("ig_caption","📝 Caption"), ("ig_hashtags","#️⃣ Hashtaglar")],
        "telegram":  [("tg_video_id","🎬 Video"), ("tg_post_text","📝 Post matni")],
    }

    fields = platform_fields.get(platform, [])
    await callback.message.edit_text(
        f"Qaysi maydon uchun?",
        reply_markup=select_pack_field_kb(fields)
    )


@router.callback_query(F.data.startswith("pack_field:"), AttachFile.select_field)
async def select_field(callback: CallbackQuery, state: FSMContext):
    field = callback.data.split(":")[1]
    await state.update_data(field=field)

    # Matn maydonlari
    text_fields = {"yt_title", "yt_description", "yt_tags", "ig_caption", "ig_hashtags", "tg_post_text"}
    if field in text_fields:
        await state.set_state(AttachFile.waiting_file)
        await callback.message.edit_text("📝 Matnni yozing:")
    else:
        await state.set_state(AttachFile.waiting_file)
        await callback.message.edit_text("📎 Faylni yuboring (video yoki rasm):")


@router.message(AttachFile.waiting_file, F.video | F.photo | F.document | F.text)
async def receive_file(message: Message, state: FSMContext):
    data = await state.get_data()
    project_id = data["project_id"]
    platform   = data["platform"]
    field      = data["field"]

    text_fields = {"yt_title", "yt_description", "yt_tags", "ig_caption", "ig_hashtags", "tg_post_text"}

    if field in text_fields:
        value     = message.text
        file_type = "text"
    elif message.video:
        value     = message.video.file_id
        file_type = "video"
    elif message.photo:
        value     = message.photo[-1].file_id
        file_type = "photo"
    elif message.document:
        value     = message.document.file_id
        file_type = "document"
    else:
        await message.answer("❌ Noto'g'ri format.")
        return

    await state.clear()

    await attach_file_to_pack(
        project_id=project_id,
        file_id=value,
        file_type=file_type,
        platform=platform,
        field=field,
        bot=message.bot
    )

    await message.answer(
        f"✅ Saqlandi!\n\n"
        f"Platform: {platform.upper()}\n"
        f"Maydon: {field}"
    )


# ── NASHR QILISH ─────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("do_publish:"))
async def do_publish(callback: CallbackQuery):
    project_id = int(callback.data.split(":")[1])
    user = await get_user_by_telegram_id(callback.from_user.id)

    result = await collect_publish_pack(project_id, callback.bot)

    if result.get("status") == "ready":
        await callback.message.edit_text(
            "🚀 <b>Nashr paketi kontent menejyerga yuborildi!</b>\n\n"
            "✅ YouTube\n✅ Instagram\n✅ Telegram",
            parse_mode="HTML"
        )
        from database.queries.tasks import mark_project_published
        await mark_project_published(project_id, user["id"])
    else:
        missing = result.get("missing", [])
        missing_text = ", ".join(m["field"] for m in missing)
        await callback.message.edit_text(
            f"⚠️ Nashr paketi hali to'liq emas!\n\nYetishmayapti: {missing_text}",
            parse_mode="HTML"
        )
