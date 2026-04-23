import logging
import traceback
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import TelegramObject, Message, CallbackQuery

log = logging.getLogger("mediabot.error")


class ErrorMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        try:
            return await handler(event, data)
        except TelegramBadRequest:
            raise
        except Exception as e:
            log.error("Unhandled exception: %s\n%s", e, traceback.format_exc())
            await self._notify_user(event, "Xato yuz berdi. Iltimos, qayta urinib ko'ring.")

    @staticmethod
    async def _notify_user(event: TelegramObject, text: str) -> None:
        try:
            if isinstance(event, Message):
                await event.answer(text)
            elif isinstance(event, CallbackQuery):
                await event.answer(text, show_alert=True)
        except Exception:
            pass
