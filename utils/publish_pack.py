import logging
import os
from aiogram import Bot

from database.queries.tasks import get_project_files, get_publish_pack, update_publish_pack, mark_published
from database.queries.users import get_user, get_content_managers

log = logging.getLogger(__name__)

PLATFORMS = ["youtube", "instagram", "telegram"]

# Har bir platforma uchun kerakli fayllar
REQUIRED_FIELDS = {
    "youtube":   ["yt_video_id", "yt_thumbnail_id", "yt_title", "yt_description"],
    "instagram": ["ig_video_id", "ig_cover_id", "ig_caption"],
    "telegram":  ["tg_video_id", "tg_post_text"],
}


# ── NASHR PAKETI YIG'ISH ────────────────────────────────────────────────────

async def collect_publish_pack(project_id: int, bot: Bot) -> dict:
    """
    Loyiha tugagach barcha fayllarni yig'ib,
    kontent menejyerga nashr paketini yuboradi.
    """
    pack = await get_publish_pack(project_id)
    if not pack:
        log.warning(f"Publish pack topilmadi: project_id={project_id}")
        return {}

    # Yetishmayotgan maydonlarni tekshirish
    missing = _check_missing_fields(pack)

    if missing:
        await _notify_missing_files(project_id, missing, bot)
        return {"status": "incomplete", "missing": missing}

    # Hamma fayl to'liq — kontent menejyerga yuborish
    await _send_to_content_manager(pack, bot)
    await update_publish_pack(project_id, "status", "tayyor")

    return {"status": "ready", "pack": pack}


def _check_missing_fields(pack: dict) -> list:
    """Yetishmayotgan maydonlarni qaytaradi."""
    missing = []
    for platform, fields in REQUIRED_FIELDS.items():
        for field in fields:
            if not pack.get(field):
                missing.append({"platform": platform, "field": field})
    return missing


async def _notify_missing_files(project_id: int, missing: list, bot: Bot):
    """Yetishmayotgan fayllar uchun mas'ul kishiga eslatma."""
    from database.queries.tasks import get_project_milestone_assignees

    assignees = await get_project_milestone_assignees(project_id)

    # Platforma bo'yicha mas'ullarni guruhlash
    platform_responsible = {
        "youtube":   "dizayner",    # Thumbnail uchun
        "instagram": "smm",         # Caption + cover uchun
        "telegram":  "kontent_menejer",
    }

    for item in missing:
        platform  = item["platform"]
        field     = item["field"]
        position  = platform_responsible.get(platform)

        # Mas'ul hodimni topish
        responsible = next(
            (a for a in assignees if a.get("position") == position), None
        )

        field_names = {
            "yt_video_id":      "YouTube video fayli",
            "yt_thumbnail_id":  "YouTube oblozhka (thumbnail)",
            "yt_title":         "YouTube sarlavha",
            "yt_description":   "YouTube tavsif matni",
            "ig_video_id":      "Instagram Reels video",
            "ig_cover_id":      "Instagram cover rasm",
            "ig_caption":       "Instagram caption matni",
            "tg_video_id":      "Telegram video",
            "tg_post_text":     "Telegram post matni",
        }

        field_label = field_names.get(field, field)

        if responsible:
            try:
                await bot.send_message(
                    responsible["telegram_id"],
                    f"⚠️ <b>Nashr paketi to'liq emas!</b>\n\n"
                    f"Yetishmayapti: <b>{field_label}</b>\n"
                    f"Platform: {platform.upper()}\n\n"
                    f"Iltimos, faylni vazifaga biriktiring.",
                    parse_mode="HTML"
                )
            except Exception as e:
                log.error(f"Notify missing file xatosi: {e}")


async def _send_to_content_manager(pack: dict, bot: Bot):
    """To'liq nashr paketini kontent menejyerga yuboradi."""
    managers = await get_content_managers()

    publish_date = (
        pack["publish_date"].strftime("%d.%m.%Y %H:%M")
        if pack.get("publish_date") else "belgilanmagan"
    )

    # Matn xabari
    text = (
        f"📦 <b>Nashr Paketi Tayyor!</b>\n"
        f"{'─' * 30}\n\n"
        f"▸ <b>YouTube:</b>\n"
        f"   📝 {pack.get('yt_title', '—')}\n"
        f"   🏷 {pack.get('yt_tags', '—')}\n\n"
        f"▸ <b>Instagram:</b>\n"
        f"   📝 {(pack.get('ig_caption') or '')[:80]}...\n\n"
        f"▸ <b>Telegram:</b>\n"
        f"   📝 {(pack.get('tg_post_text') or '')[:80]}...\n\n"
        f"{'─' * 30}\n"
        f"📅 Nashr sanasi: <b>{publish_date}</b>\n"
        f"✅ Hamma fayl to'liq — nashrga tayyor!"
    )

    for manager in managers:
        try:
            await bot.send_message(
                manager["telegram_id"],
                text,
                parse_mode="HTML"
            )

            # YouTube video
            if pack.get("yt_video_id"):
                await bot.send_video(
                    manager["telegram_id"],
                    pack["yt_video_id"],
                    caption="🎬 YouTube video"
                )

            # YouTube thumbnail
            if pack.get("yt_thumbnail_id"):
                await bot.send_photo(
                    manager["telegram_id"],
                    pack["yt_thumbnail_id"],
                    caption="🖼 YouTube thumbnail"
                )

            # Instagram video
            if pack.get("ig_video_id") and pack["ig_video_id"] != pack.get("yt_video_id"):
                await bot.send_video(
                    manager["telegram_id"],
                    pack["ig_video_id"],
                    caption="📱 Instagram Reels"
                )

            # Instagram cover
            if pack.get("ig_cover_id"):
                await bot.send_photo(
                    manager["telegram_id"],
                    pack["ig_cover_id"],
                    caption="🖼 Instagram cover"
                )

        except Exception as e:
            log.error(f"Publish pack yuborishda xato [{manager['full_name']}]: {e}")


# ── FAYL BIRIKTIRISH ─────────────────────────────────────────────────────────

async def attach_file_to_pack(
    project_id: int,
    file_id: str,
    file_type: str,
    platform: str,
    field: str,
    bot: Bot
):
    """
    Hodim fayl yuklasa — nashr paketiga biriktiriladi.
    Keyin paket to'liqligini tekshiradi.
    """
    await update_publish_pack(project_id, field, file_id)

    pack = await get_publish_pack(project_id)
    missing = _check_missing_fields(pack)

    if not missing:
        # Hamma fayl to'liq bo'ldi!
        await collect_publish_pack(project_id, bot)
