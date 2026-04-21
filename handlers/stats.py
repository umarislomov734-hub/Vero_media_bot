from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command

from database.queries.users import get_user_by_telegram_id
from database.queries.stats import (
    get_week_stats_for_user, get_weekly_stats_per_user,
    get_user_monthly_stats
)

router = Router()


# ── SHAXSIY STATISTIKA ────────────────────────────────────────────────────────

@router.message(F.text == "📊 Statistika")
@router.message(Command("stats"))
async def my_stats(message: Message):
    user = await get_user_by_telegram_id(message.from_user.id)
    if not user:
        return

    week = await get_week_stats_for_user(user["id"])
    month = await get_user_monthly_stats(user["id"])

    done_w = week["done"]
    total_w = week["total"]
    pct_w = round(done_w / total_w * 100) if total_w else 0

    done_m = month["done"]
    total_m = month["total"]

    await message.answer(
        f"📊 <b>Statistika — {user['full_name']}</b>\n\n"
        f"<b>Bu hafta:</b>\n"
        f"✅ Bajarildi: {done_w}/{total_w} ({pct_w}%)\n\n"
        f"<b>Bu oy (30 kun):</b>\n"
        f"✅ Bajarildi: {done_m}/{total_m}\n"
        f"↩️ Qaytarilgan: {month['returned']}",
        parse_mode="HTML"
    )


# ── JAMOA HISOBOTI (PM/AD uchun) ──────────────────────────────────────────────

@router.message(Command("report"))
async def team_report(message: Message):
    user = await get_user_by_telegram_id(message.from_user.id)
    if not user or user["role"] not in ("super_admin", "pm", "ad"):
        await message.answer("❌ Ruxsat yo'q.")
        return

    stats = await get_weekly_stats_per_user()
    if not stats:
        await message.answer("Ma'lumot yo'q.")
        return

    lines = ["📊 <b>Haftalik hisobot:</b>\n"]
    total_done = total_all = 0

    for s in sorted(stats, key=lambda x: x["done"], reverse=True):
        done = s["done"] or 0
        total = s["total"] or 0
        total_done += done
        total_all += total

        icon = "🏆" if done == total and total > 0 else ("⚠️" if s.get("overdue") else "👤")
        line = f"{icon} <b>{s['name']}</b>: {done}/{total}"
        if s.get("returned"):
            line += f" ↩️{s['returned']}"
        lines.append(line)

    lines.append(f"\n<b>Jami:</b> {total_done}/{total_all}")
    await message.answer("\n".join(lines), parse_mode="HTML")
