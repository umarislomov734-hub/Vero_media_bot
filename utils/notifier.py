import logging
from aiogram import Bot

log = logging.getLogger(__name__)


async def notify(bot: Bot, telegram_id: int, text: str, parse_mode: str = "HTML") -> bool:
    try:
        await bot.send_message(telegram_id, text, parse_mode=parse_mode)
        return True
    except Exception as e:
        log.warning("notify failed user=%s: %s", telegram_id, e)
        return False


async def notify_many(bot: Bot, telegram_ids: list[int], text: str) -> None:
    for tid in telegram_ids:
        await notify(bot, tid, text)


async def notify_managers(bot: Bot, text: str) -> None:
    from database.queries.users import get_managers
    managers = await get_managers()
    for m in managers:
        await notify(bot, m["telegram_id"], text)
