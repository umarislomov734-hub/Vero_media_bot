import asyncio
import logging
import os
from datetime import datetime
from pathlib import Path

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot
from aiogram.exceptions import TelegramRetryAfter, TelegramForbiddenError

from database.queries.tasks import (
    get_member_task_summary,
    get_tasks_needing_reminder,
    get_overdue_tasks_with_assignees,
    mark_reminded_bulk,
    get_weekly_stats_per_user,
    get_recurring_tasks,
    clone_recurring_task,
)
from database.queries.users import get_all_active_members, get_managers

TZ  = pytz.timezone(os.getenv("TIMEZONE", "Asia/Tashkent"))
log = logging.getLogger(__name__)

PRIORITY_ICON = {"yuqori": "🔴", "orta": "🟡", "past": "🟢"}


async def _safe_send(bot: Bot, telegram_id: int, text: str) -> None:
    try:
        await bot.send_message(telegram_id, text, parse_mode="HTML")
    except TelegramRetryAfter as e:
        log.warning("FloodWait scheduler user=%s: %ss", telegram_id, e.retry_after)
        await asyncio.sleep(e.retry_after)
        try:
            await bot.send_message(telegram_id, text, parse_mode="HTML")
        except Exception as e2:
            log.error("scheduler retry muvaffaqiyatsiz user=%s: %s", telegram_id, e2)
    except TelegramForbiddenError:
        log.info("scheduler skip user=%s: bot bloklangan", telegram_id)
    except Exception as e:
        log.error("scheduler send xato user=%s: %s", telegram_id, e)


# ════════════════════════════════════════════════════════════════════════════
#  1. KUNDALIK ERTALAB ESLATMA — 09:00
#  N+1 fix: get_member_task_summary() — barcha a'zolar uchun 1 ta query
# ════════════════════════════════════════════════════════════════════════════

async def morning_reminder(bot: Bot):
    log.info("morning_reminder ishga tushdi")
    members = await get_all_active_members()
    if not members:
        return

    member_ids = [m["id"] for m in members]
    summaries = await get_member_task_summary(member_ids)

    weekly_stats = {s["name"]: s for s in await get_weekly_stats_per_user()}

    for member in members:
        data = summaries.get(member["id"], {"today": [], "tomorrow": [], "overdue": []})
        today    = data["today"]
        tomorrow = data["tomorrow"]
        overdue  = data["overdue"]

        if not today and not tomorrow and not overdue:
            continue

        lines = [f"🌅 <b>Xayrli tong, {member['full_name']}!</b>\n"]

        if overdue:
            lines.append("🚨 <b>Kechikkan vazifalar:</b>")
            for t in overdue:
                icon = PRIORITY_ICON.get(t.get("priority", "orta"), "🟡")
                lines.append(f"  {icon} {t['title']}")
            lines.append("")

        if today:
            lines.append("🔴 <b>Bugun tugashi kerak:</b>")
            for t in today:
                icon = PRIORITY_ICON.get(t.get("priority", "orta"), "🟡")
                dl   = t["deadline"].strftime("%H:%M") if t.get("deadline") else "—"
                lines.append(f"  {icon} {t['title']} [{dl}]")
            lines.append("")

        if tomorrow:
            lines.append("🟡 <b>Ertaga:</b>")
            for t in tomorrow:
                icon = PRIORITY_ICON.get(t.get("priority", "orta"), "🟡")
                lines.append(f"  {icon} {t['title']}")
            lines.append("")

        stats = weekly_stats.get(member["full_name"])
        if stats:
            lines.append(f"📊 Bu hafta: {stats['done']}/{stats['total']} ✅")

        try:
            await _safe_send(bot, member["telegram_id"], "\n".join(lines))
            await asyncio.sleep(0.05)
        except Exception as e:
            log.error("morning_reminder xatosi [%s]: %s", member["full_name"], e)


# ════════════════════════════════════════════════════════════════════════════
#  2. DEADLINE ZANJIRI — Har 2 soatda
#  N+1 fix: batch queries, bulk mark_reminded
# ════════════════════════════════════════════════════════════════════════════

async def deadline_chain(bot: Bot):
    log.info("deadline_chain ishga tushdi")
    managers = await get_managers()

    # 3 kun qoldi
    tasks_3d = await get_tasks_needing_reminder(days=3, field="reminded_3d")
    reminded_3d_ids = []
    for t in tasks_3d:
        dl = t["deadline"].strftime("%d.%m %H:%M")
        await _safe_send(
            bot, t["user_telegram_id"],
            f"⏰ <b>3 kun qoldi!</b>\n\n📌 {t['title']}\n🗓 Deadline: {dl}"
        )
        reminded_3d_ids.append(t["id"])
        await asyncio.sleep(0.05)
    if reminded_3d_ids:
        await mark_reminded_bulk(reminded_3d_ids, "reminded_3d")

    # 1 kun qoldi
    tasks_1d = await get_tasks_needing_reminder(days=1, field="reminded_1d")
    reminded_1d_ids = []
    for t in tasks_1d:
        dl = t["deadline"].strftime("%d.%m %H:%M")
        await _safe_send(
            bot, t["user_telegram_id"],
            f"🔔 <b>1 kun qoldi!</b>\n\n📌 {t['title']}\n🗓 Deadline: {dl}"
        )
        reminded_1d_ids.append(t["id"])
        await asyncio.sleep(0.05)
        for m in managers:
            await _safe_send(
                bot, m["telegram_id"],
                f"⚠️ <b>{t['assignee_name']}</b> ning vazifasiga 1 kun qoldi:\n"
                f"📌 {t['title']} | 🗓 {dl}"
            )
            await asyncio.sleep(0.05)
    if reminded_1d_ids:
        await mark_reminded_bulk(reminded_1d_ids, "reminded_1d")

    # Kechikkan vazifalar — PM/AD ga
    await _notify_overdue_to_managers(bot, managers)


async def _notify_overdue_to_managers(bot: Bot, managers: list[dict]):
    overdue_tasks = await get_overdue_tasks_with_assignees()
    if not overdue_tasks:
        return
    for t in overdue_tasks:
        dl = t["deadline"].strftime("%d.%m %H:%M") if t.get("deadline") else "—"
        for m in managers:
            await _safe_send(
                bot, m["telegram_id"],
                f"🚨 <b>Kechikdi!</b>\n\n"
                f"👤 {t['assignee_name']}\n"
                f"📌 {t['title']}\n"
                f"🗓 Deadline o'tdi: {dl}\n\nSabab so'raldi."
            )
            await asyncio.sleep(0.05)


# ════════════════════════════════════════════════════════════════════════════
#  3. HAFTALIK HISOBOT — Har dushanba 09:00
# ════════════════════════════════════════════════════════════════════════════

async def weekly_report(bot: Bot):
    log.info("weekly_report ishga tushdi")
    members  = await get_all_active_members()
    managers = [m for m in members if m["role"] in ("super_admin", "pm", "ad")]

    stats_per_user = await get_weekly_stats_per_user()
    overall = {
        "done":     sum(s["done"]     for s in stats_per_user),
        "overdue":  sum(s["overdue"]  for s in stats_per_user),
        "missed":   sum(s["missed"]   for s in stats_per_user),
        "returned": sum(s["returned"] for s in stats_per_user),
    }
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

    problems = [s for s in stats_per_user if s["missed"] > 0 or s["overdue"] > 0]
    if problems:
        lines += ["", "⚠️ <b>Diqqat talab qiluvchilar:</b>"]
        for p in problems:
            lines.append(f"  • {p['name']}: {p['missed']} bajarilmadi, {p['overdue']} kechikdi")

    text = "\n".join(lines)
    for m in managers:
        await _safe_send(bot, m["telegram_id"], text)
        await asyncio.sleep(0.05)


# ════════════════════════════════════════════════════════════════════════════
#  4. RUTINIY VAZIFALAR — 00:01
# ════════════════════════════════════════════════════════════════════════════

async def refresh_recurring_tasks(bot: Bot):
    log.info("refresh_recurring_tasks ishga tushdi")
    tasks = await get_recurring_tasks()
    for t in tasks:
        try:
            new_task = await clone_recurring_task(t["id"])
            if new_task and t.get("assigned_to"):
                from database.queries.users import get_user
                assignee = await get_user(t["assigned_to"])
                if assignee:
                    await _safe_send(
                        bot, assignee["telegram_id"],
                        f"🔁 <b>Rutiniy vazifa yangilandi:</b>\n📌 {t['title']}"
                    )
        except Exception as e:
            log.error("Rutiniy vazifa klonlashda xato: %s", e)


# ════════════════════════════════════════════════════════════════════════════
#  5. BO'SH VAQT MODULI — Har 2 soatda
# ════════════════════════════════════════════════════════════════════════════

async def idle_check(bot: Bot):
    log.info("idle_check ishga tushdi")
    from database.queries.users import get_idle_members
    idle_members = await get_idle_members()
    if not idle_members:
        return

    names    = ", ".join(i["full_name"] for i in idle_members)
    managers = await get_managers()
    for m in managers:
        await _safe_send(bot, m["telegram_id"], f"💡 <b>Bo'sh hodimlar:</b> {names}\n\nVazifa berasizmi?")
        await asyncio.sleep(0.05)

    for member in idle_members:
        await _safe_send(
            bot, member["telegram_id"],
            "📚 <b>Hozir bo'sh vaqtingiz bor!</b>\n\n"
            "Bugun nima o'rgandingiz yoki yangi nima sinab ko'rdingiz?\n"
            "🎙️ Audio yuboring!"
        )
        await asyncio.sleep(0.05)


# ════════════════════════════════════════════════════════════════════════════
#  6. KUNDALIK DB BACKUP — 02:00 (7 kun saqlanadi)
# ════════════════════════════════════════════════════════════════════════════

async def daily_backup():
    db_url = os.getenv("DATABASE_URL", "")
    if not db_url:
        log.warning("DATABASE_URL topilmadi, backup o'tkazib yuborildi")
        return

    try:
        from urllib.parse import urlparse
        p      = urlparse(db_url)
        host   = p.hostname or "localhost"
        port   = str(p.port or 5432)
        dbname = p.path.lstrip("/")
        user   = p.username or "postgres"
    except Exception as e:
        log.error("DB URL parse xatosi: %s", e)
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
            log.info("✅ Backup saqlandi: %s", filename.name)
        else:
            log.error("pg_dump xatosi: %s", stderr.decode())
            return
    except FileNotFoundError:
        log.warning("pg_dump topilmadi — backup o'tkazib yuborildi")
        return
    except Exception as e:
        log.error("Backup xatosi: %s", e)
        return

    # 7 kundan eski backuplarni o'chirish
    cutoff = datetime.now().timestamp() - 7 * 86400
    for old in backup_dir.glob("backup_*.sql"):
        if old.stat().st_mtime < cutoff:
            old.unlink()
            log.info("Eski backup o'chirildi: %s", old.name)


# ════════════════════════════════════════════════════════════════════════════
#  SCHEDULER ISHGA TUSHIRISH
# ════════════════════════════════════════════════════════════════════════════

async def start_scheduler(bot: Bot):
    scheduler = AsyncIOScheduler(timezone=TZ)

    scheduler.add_job(morning_reminder, "cron", hour=9, minute=0, args=[bot], id="morning_reminder")
    scheduler.add_job(deadline_chain, "interval", hours=2, args=[bot], id="deadline_chain")
    scheduler.add_job(weekly_report, "cron", day_of_week="mon", hour=9, minute=0, args=[bot], id="weekly_report")
    scheduler.add_job(refresh_recurring_tasks, "cron", hour=0, minute=1, args=[bot], id="recurring_refresh")
    scheduler.add_job(idle_check, "cron", hour="10,12,14,16,18", minute=0, args=[bot], id="idle_check")
    scheduler.add_job(daily_backup, "cron", hour=2, minute=0, id="daily_backup")

    scheduler.start()
    log.info("✅ Scheduler ishga tushdi")
    return scheduler
