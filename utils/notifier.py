import asyncio
import logging
from aiogram import Bot
from aiogram.exceptions import TelegramRetryAfter, TelegramForbiddenError, TelegramBadRequest

log = logging.getLogger(__name__)

MSG_LIMIT = 4096


def _chunk(text: str, limit: int = MSG_LIMIT) -> list[str]:
    """Uzun xabarni Telegram limiti bo'yicha bo'laklaydi."""
    if len(text) <= limit:
        return [text]
    parts = []
    while text:
        if len(text) <= limit:
            parts.append(text)
            break
        # So'z o'rtasida kesmaslik uchun bo'sh joy qidirish
        cut = text.rfind(" ", 0, limit)
        if cut == -1:
            cut = limit
        parts.append(text[:cut])
        text = text[cut:].lstrip()
    return parts


async def notify(bot: Bot, telegram_id: int, text: str, parse_mode: str = "HTML") -> bool:
    chunks = _chunk(text)
    success = True
    for chunk in chunks:
        sent = await _send_one(bot, telegram_id, chunk, parse_mode)
        if not sent:
            success = False
            break
    return success


async def _send_one(bot: Bot, telegram_id: int, text: str, parse_mode: str) -> bool:
    try:
        await bot.send_message(telegram_id, text, parse_mode=parse_mode)
        return True
    except TelegramRetryAfter as e:
        log.warning("FloodWait user=%s: %ss kutilmoqda", telegram_id, e.retry_after)
        await asyncio.sleep(e.retry_after)
        try:
            await bot.send_message(telegram_id, text, parse_mode=parse_mode)
            return True
        except Exception as e2:
            log.error("notify retry muvaffaqiyatsiz user=%s: %s", telegram_id, e2)
            return False
    except TelegramForbiddenError:
        log.info("notify skip user=%s: bot bloklangan", telegram_id)
        return False
    except TelegramBadRequest as e:
        log.warning("notify bad request user=%s: %s", telegram_id, e)
        return False
    except Exception as e:
        log.warning("notify xato user=%s: %s", telegram_id, e)
        return False


async def notify_many(bot: Bot, telegram_ids: list[int], text: str) -> None:
    for tid in telegram_ids:
        await notify(bot, tid, text)
        await asyncio.sleep(0.05)


async def notify_managers(bot: Bot, text: str) -> None:
    from database.queries.users import get_managers
    managers = await get_managers()
    for m in managers:
        await notify(bot, m["telegram_id"], text)
        await asyncio.sleep(0.05)
