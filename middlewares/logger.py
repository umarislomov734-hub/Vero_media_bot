import logging
from typing import Any, Awaitable, Callable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery

log = logging.getLogger("mediabot")


class LoggerMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any]
    ) -> Any:
        if isinstance(event, Message):
            user = event.from_user
            log.info(
                "MSG user_id=%s username=%s text=%s",
                user.id if user else "?",
                user.username if user else "?",
                (event.text or "")[:50]
            )
        elif isinstance(event, CallbackQuery):
            user = event.from_user
            log.info(
                "CBQ user_id=%s data=%s",
                user.id if user else "?",
                event.data
            )
        return await handler(event, data)
