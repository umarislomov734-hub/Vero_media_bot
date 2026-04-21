import asyncio
import logging
import os
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot

from database.queries.tasks import (
    get_tasks_due_today,
    get_tasks_due_in_days,
    get_overdue_tasks,
    mark_reminded,
    get_weekly_stats_per_user,
    get_recurring_tasks,
    clone_recurring_task,
    get_idle_members,
)
from database.queries.users import get_all_active_members, get_managers

TZ  = pytz.timezone(os.getenv("TIMEZONE", "Asia/Tashkent"))
log = logging.getLogger(__name__)

PRIORITY_ICON = {"yuqori": "🔴", "orta": "🟡", "past": "🟢"}


# ════════════════════════════════════════════════════════════════════════════
#  1. KUNDALIK ERTALAB ESLATMA — 09:00
# ════════════════════════════════════════════════════════════════════════════

async def morning_reminder(bot: Bot):
    """Har kuni 09:00 — har bir hodimga bugungi vazifalar."""
    log.info("morning_reminder ishga tushdi")
    members = await get_all_active_members()

    for member in members:
        try:
            tasks_today    = await get_tasks_due_today(member["id"])
            tasks_tomorrow = await get_tasks_due_in_days(member["id"], days=1)
            overdue        = await get_overdue_tasks(member["id"])

            # Agar hech narsa yo'q — yubormaslik
            if not tasks_today and not tasks_tomorrow and not overdue:
                continue

            lines = [f"🌅 <b>Xayrli tong, {member['full_name']}!</b>\n"]

            if overdue:
                lines.append("🚨 <b>Kechikkan vazifalar:</b>")
                for t in overdue:
                    icon = PRIORITY_ICON.get(t["priority"], "🟡")
                    lines.append(f"  {icon} {t['title']}")
                lines.append("")

            if tasks_today:
                lines.append("🔴 <b>Bugun tugashi kerak:</b>")
                for t in tasks_today:
                    icon = PRIORITY_ICON.get(t["priority"], "🟡")
                    dl   = t["deadline"].strftime("%H:%M") if t["deadline"] else "—"
                    lines.append(f"  {icon} {t['title']} [{dl}]")
                lines.append("")

            if tasks_tomorrow:
                lines.append("🟡 <b>Ertaga:</b>")
                for t in tasks_tomorrow:
                    icon = PRIORITY_ICON.get(t["priority"], "🟡")
                    lines.append(f"  {icon} {t['title']}")
                lines.append("")

            # Haftalik statistika
            from database.queries.stats import get_week_stats_for_user
            stats = await get_week_stats_for_user(member["id"])
            if stats:
                lines.append(
                    f"📊 Bu hafta: {stats['done']}/{stats['total']} ✅"
                )

            await bot.send_message(
                member["telegram_id"],
                "\n".join(lines),
                parse_mode="HTML"
            )

        except Exception as e:
            log.error(f"morning_reminder xatosi [{member['full_name']}]: {e}")


# ════════════════════════════════════════════════════════════════════════════
#  2. DEADLINE ZANJIRI — Har 2 soatda tekshirish
# ════════════════════════════════════════════════════════════════════════════

async def deadline_chain(bot: Bot):
    """3 kun va 1 kun qolganda eslatma. Kechiksa — PM/AD ga."""
    log.info("deadline_chain ishga tushdi")
    members = await get_all_active_members()

    for member in members:
        try:
            # 3 kun qoldi
            tasks_3d = await get_tasks_due_in_days(member["id"], days=3, remind_field="reminded_3d")
            for t in tasks_3d:
                dl = t["deadline"].strftime("%d.%m %H:%M")
                await bot.send_message(
                    member["telegram_id"],
                    f"⏰ <b>3 kun qoldi!</b>\n\n"
                    f"📌 {t['title']}\n"
                    f"🗓 Deadline: {dl}",
                    parse_mode="HTML"
                )
                await mark_reminded(t["id"], "reminded_3d")

            # 1 kun qoldi
            tasks_1d = await get_tasks_due_in_days(member["id"], days=1, remind_field="reminded_1d")
            for t in tasks_1d:
                dl = t["deadline"].strftime("%d.%m %H:%M")
                await bot.send_message(
                    member["telegram_id"],
                    f"🔔 <b>1 kun qoldi!</b>\n\n"
                    f"📌 {t['title']}\n"
                    f"🗓 Deadline: {dl}",
                    parse_mode="HTML"
                )
                await mark_reminded(t["id"], "reminded_1d")

                # PM + AD ga ham xabar
                managers = await get_managers()
                for m in managers:
                    try:
                        await bot.send_message(
                            m["telegram_id"],
                            f"⚠️ <b>{member['full_name']}</b> ning vazifasiga 1 kun qoldi:\n"
                            f"📌 {t['title']} | 🗓 {dl}",
                            parse_mode="HTML"
                        )
                    except Exception:
                        pass

        except Exception as e:
            log.error(f"deadline_chain xatosi: {e}")

    # Kechikkan vazifalar — PM/AD ga urgent
    await _notify_overdue_to_managers(bot)


async def _notify_overdue_to_managers(bot: Bot):
    """Kechikkan vazifalar haqida PM/AD ga xabar."""
    managers = await get_managers()
    members  = await get_all_active_members()

    for member in members:
        overdue = await get_overdue_tasks(member["id"])
        if not overdue:
            continue
        for t in overdue:
            dl = t["deadline"].strftime("%d.%m %H:%M") if t["deadline"] else "—"
            for m in managers:
                try:
                    await bot.send_message(
                        m["telegram_id"],
                        f"🚨 <b>Kechikdi!</b>\n\n"
                        f"👤 {member['full_name']}\n"
                        f"📌 {t['title']}\n"
                        f"🗓 Deadline o'tdi: {dl}\n\n"
                        f"Sabab so'raldi.",
                        parse_mode="HTML"
                    )
                except Exception:
                    pass


# ════════════════════════════════════════════════════════════════════════════
#  3. HAFTALIK HISOBOT — Har dushanba 09:00
# ════════════════════════════════════════════════════════════════════════════

async def weekly_report(bot: Bot):
    """Har dushanba — PM va AD ga haftalik hisobot."""
    log.info("weekly_report ishga tushdi")
    managers = await get_all_active_members()
    managers = [m for m in managers if m["role"] in ("super_admin", "pm", "ad")]

    stats_per_user = await get_weekly_stats_per_user()
    overall        = await _calc_overall(stats_per_user)

    # Top hodim
    top = max(stats_per_user, key=lambda x: x["done"] / max(x["total"], 1), default=None)

    lines = [
        "📊 <b>Haftalik Hisobot</b>",
        f"{'─' * 28}",
        f"✅ Bajarildi:    {overall['done']}",
        f"⚠️ Kechikdi:    {overall['overdue']}",
        f"❌ Bajarilmadi: {overall['missed']}",
        f"↩️ Qaytarildi:  {overall['returned']}",
        "",
        "<b>👤 Shaxsiy natijalar:</b>",
    ]

    for s in stats_per_user:
        pct = int(s["done"] / max(s["total"], 1) * 100)
        bar = "█" * (pct // 10) + "░" * (10 - pct // 10)
        lines.append(f"{s['name']}: {bar} {s['done']}/{s['total']}")

    if top:
        lines += ["", f"🏆 <b>Eng faol: {top['name']} ({top['done']}/{top['total']})</b>"]

    # Muammo bormi?
    problems = [s for s in stats_per_user if s["missed"] > 0 or s["overdue"] > 0]
    if problems:
        lines += ["", "⚠️ <b>Diqqat talab qiluvchilar:</b>"]
        for p in problems:
            lines.append(f"  • {p['name']}: {p['missed']} bajarilmadi, {p['overdue']} kechikdi")

    text = "\n".join(lines)

    for m in managers:
        try:
            await bot.send_message(m["telegram_id"], text, parse_mode="HTML")
        except Exception as e:
            log.error(f"weekly_report yuborishda xato: {e}")


async def _calc_overall(stats_per_user: list) -> dict:
    return {
        "done":     sum(s["done"]     for s in stats_per_user),
        "overdue":  sum(s["overdue"]  for s in stats_per_user),
        "missed":   sum(s["missed"]   for s in stats_per_user),
        "returned": sum(s["returned"] for s in stats_per_user),
    }


# ════════════════════════════════════════════════════════════════════════════
#  4. RUTINIY VAZIFALAR — Har kuni 00:01 yangilash
# ════════════════════════════════════════════════════════════════════════════

async def refresh_recurring_tasks(bot: Bot):
    """Rutiniy vazifalarni yangi kun uchun klonlaydi."""
    log.info("refresh_recurring_tasks ishga tushdi")
    tasks = await get_recurring_tasks()
    for t in tasks:
        try:
            new_task = await clone_recurring_task(t["id"])
            if new_task and t.get("assigned_to"):
                from database.queries.users import get_user
                assignee = await get_user(t["assigned_to"])
                if assignee:
                    await bot.send_message(
                        assignee["telegram_id"],
                        f"🔁 <b>Rutiniy vazifa yangilandi:</b>\n📌 {t['title']}",
                        parse_mode="HTML"
                    )
        except Exception as e:
            log.error(f"Rutiniy vazifa klonlashda xato: {e}")


# ════════════════════════════════════════════════════════════════════════════
#  5. BO'SH VAQT MODULI — Har 2 soatda tekshirish
# ════════════════════════════════════════════════════════════════════════════

async def idle_check(bot: Bot):
    """Bo'sh hodimlarni aniqlaydi va PM/AD ga xabar beradi."""
    log.info("idle_check ishga tushdi")
    idle_members = await get_idle_members()

    if not idle_members:
        return

    managers = await get_managers()
    for m in managers:
        try:
            names = ", ".join(i["full_name"] for i in idle_members)
            await bot.send_message(
                m["telegram_id"],
                f"💡 <b>Bo'sh hodimlar:</b> {names}\n\n"
                f"Vazifa berasizmi?",
                parse_mode="HTML"
            )
        except Exception:
            pass

    # Bo'sh hodimlarning o'ziga ham
    for member in idle_members:
        try:
            await bot.send_message(
                member["telegram_id"],
                f"📚 <b>Hozir bo'sh vaqtingiz bor!</b>\n\n"
                f"Bugun nima o'rgandingiz yoki yangi nima sinab ko'rdingiz?\n"
                f"🎙️ Audio yuboring!",
                parse_mode="HTML"
            )
        except Exception:
            pass


# ════════════════════════════════════════════════════════════════════════════
#  SCHEDULER ISHGA TUSHIRISH
# ════════════════════════════════════════════════════════════════════════════

async def start_scheduler(bot: Bot):
    scheduler = AsyncIOScheduler(timezone=TZ)

    # 1. Kundalik ertalab — 09:00
    scheduler.add_job(
        morning_reminder, "cron",
        hour=9, minute=0,
        args=[bot],
        id="morning_reminder"
    )

    # 2. Deadline zanjiri — har 2 soatda
    scheduler.add_job(
        deadline_chain, "interval",
        hours=2,
        args=[bot],
        id="deadline_chain"
    )

    # 3. Haftalik hisobot — har dushanba 09:00
    scheduler.add_job(
        weekly_report, "cron",
        day_of_week="mon", hour=9, minute=0,
        args=[bot],
        id="weekly_report"
    )

    # 4. Rutiniy vazifalar yangilash — har kuni 00:01
    scheduler.add_job(
        refresh_recurring_tasks, "cron",
        hour=0, minute=1,
        args=[bot],
        id="recurring_refresh"
    )

    # 5. Bo'sh vaqt tekshirish — ish soatlarida har 2 soatda (10:00 - 18:00)
    scheduler.add_job(
        idle_check, "cron",
        hour="10,12,14,16,18", minute=0,
        args=[bot],
        id="idle_check"
    )

    # 6. Kundalik backup — har kuni 02:00
    scheduler.add_job(
        daily_backup, "cron",
        hour=2, minute=0,
        id="daily_backup"
    )

    scheduler.start()
    log.info("✅ Scheduler ishga tushdi")
    return scheduler


# ════════════════════════════════════════════════════════════════════════════
#  6. KUNDALIK DB BACKUP — 02:00
# ════════════════════════════════════════════════════════════════════════════

async def daily_backup():
    """Har kuni DB ni fayl sifatida saqlaydi, 7 kundan eski backup o'chiriladi."""
    db_url = os.getenv("DATABASE_URL", "")
    if not db_url:
        log.warning("DATABASE_URL topilmadi, backup o'tkazib yuborildi")
        return

    # postgresql://user@host:port/dbname dan qismlarni ajratish
    try:
        from urllib.parse import urlparse
        p = urlparse(db_url)
        host   = p.hostname or "localhost"
        port   = str(p.port or 5432)
        dbname = p.path.lstrip("/")
        user   = p.username or "postgres"
    except Exception as e:
        log.error(f"DB URL parse xatosi: {e}")
        return

    backup_dir = Path(__file__).parent.parent / "backups"
    backup_dir.mkdir(exist_ok=True)

    filename = backup_dir / f"backup_{datetime.now().strftime('%Y%m%d_%H%M')}.sql"

    env = os.environ.copy()
    if p.password:
        env["PGPASSWORD"] = p.password

    try:
        proc = await asyncio.create_subprocess_exec(
            "pg_dump", "-h", host, "-p", port, "-U", user, dbname,
            "-f", str(filename),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()

        if proc.returncode == 0:
            log.info(f"✅ Backup saqlandi: {filename.name}")
        else:
            log.error(f"pg_dump xatosi: {stderr.decode()}")
            return
    except FileNotFoundError:
        log.warning("pg_dump topilmadi — backup o'tkazib yuborildi")
        return
    except Exception as e:
        log.error(f"Backup xatosi: {e}")
        return

    # 7 kundan eski fayllarni o'chirish
    cutoff = datetime.now().timestamp() - 365 * 86400
    for old in backup_dir.glob("backup_*.sql"):
        if old.stat().st_mtime < cutoff:
            old.unlink()
            log.info(f"Eski backup o'chirildi: {old.name}")
