import time
import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery

log = logging.getLogger(__name__)

# Module-level TTL cache: telegram_id → (db_user, expire_time)
_cache: dict[int, tuple[dict | None, float]] = {}
TTL = 60  # sekund


def invalidate_user_cache(telegram_id: int) -> None:
    """Role o'zgarganda yoki deactivate qilinganda chaqiriladi."""
    _cache.pop(telegram_id, None)


class AuthMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        from database.queries.users import get_user_by_telegram_id

        if isinstance(event, (Message, CallbackQuery)):
            user_id = event.from_user.id if event.from_user else None
            if user_id:
                now = time.monotonic()
                cached = _cache.get(user_id)
                if cached and now < cached[1]:
                    data["db_user"] = cached[0]
                else:
                    try:
                        db_user = await get_user_by_telegram_id(user_id)
                    except Exception as e:
                        log.error("AuthMiddleware DB xato user=%s: %s", user_id, e)
                        db_user = None
                    _cache[user_id] = (db_user, now + TTL)
                    data["db_user"] = db_user

        return await handler(event, data)
