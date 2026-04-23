import asyncio
import logging
import os
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web

from database.connection import create_pool, get_pool
from handlers import common, audio, admin, calendar, shablon
from handlers.tasks import list as task_list
from handlers.tasks import create as task_create
from handlers.tasks import complete as task_complete
from handlers import projects, stats, growth, meeting, archive, publish
from middlewares.auth import AuthMiddleware
from middlewares.logger import LoggerMiddleware
from middlewares.error import ErrorMiddleware
from utils.scheduler import start_scheduler

load_dotenv()
logging.basicConfig(level=logging.INFO)

log = logging.getLogger(__name__)


async def _oauth_callback(request: web.Request) -> web.Response:
    code  = request.rel_url.query.get("code")
    state = request.rel_url.query.get("state")

    if not code or not state:
        return web.Response(text="Xato: code yoki state yo'q", status=400)

    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT telegram_id FROM gcal_oauth_states "
            "WHERE state=$1 AND expires_at > NOW()",
            state
        )
        if not row:
            return web.Response(text="Xato: muddati o'tgan yoki noto'g'ri havola.", status=400)
        telegram_id = row["telegram_id"]
        await conn.execute("DELETE FROM gcal_oauth_states WHERE state=$1", state)

    bot: Bot = request.app["bot"]

    try:
        from utils.google_calendar import exchange_code
        from database.queries.users import get_user_by_telegram_id, save_google_token

        client_id     = os.getenv("GOOGLE_CLIENT_ID")
        client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
        redirect_uri  = os.getenv("GOOGLE_REDIRECT_URI")

        token_data = await exchange_code(client_id, client_secret, redirect_uri, code)
        if not token_data:
            await bot.send_message(telegram_id, "❌ Google bilan ulanishda xato. Qayta urinib ko'ring.")
            return web.Response(text="Xato: tokenni olishda muammo.", status=500)

        user = await get_user_by_telegram_id(telegram_id)
        if user:
            await save_google_token(
                user["id"],
                token_data["access_token"],
                token_data["refresh_token"],
                token_data["expiry"],
                token_data.get("calendar_id", "primary")
            )
            await bot.send_message(
                telegram_id,
                "✅ <b>Google Calendar ulandi!</b>\n\n"
                "Endi deadline berilgan har bir vazifa avtomatik "
                "kalendaringizga qo'shiladi.",
                parse_mode="HTML"
            )
    except Exception as e:
        log.error(f"OAuth callback xatosi: {e}")
        return web.Response(text="Ichki xato.", status=500)

    html = (
        "<html><body style='font-family:sans-serif;text-align:center;padding:60px'>"
        "<h2>✅ Ulandi!</h2>"
        "<p>Botga qayting va vazifalarni boshqaring.</p>"
        "</body></html>"
    )
    return web.Response(text=html, content_type="text/html")


async def main():
    bot = Bot(token=os.getenv("BOT_TOKEN"), default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp  = Dispatcher(storage=MemoryStorage())

    await create_pool()

    dp.message.middleware(ErrorMiddleware())
    dp.callback_query.middleware(ErrorMiddleware())
    dp.message.middleware(LoggerMiddleware())
    dp.message.middleware(AuthMiddleware())
    dp.callback_query.middleware(AuthMiddleware())

    dp.include_router(common.router)
    dp.include_router(audio.router)
    dp.include_router(task_list.router)
    dp.include_router(task_create.router)
    dp.include_router(task_complete.router)
    dp.include_router(admin.router)
    dp.include_router(projects.router)
    dp.include_router(stats.router)
    dp.include_router(growth.router)
    dp.include_router(meeting.router)
    dp.include_router(archive.router)
    dp.include_router(publish.router)
    dp.include_router(calendar.router)
    dp.include_router(shablon.router)

    await start_scheduler(bot)

    # OAuth callback server
    oauth_port = int(os.getenv("GOOGLE_OAUTH_PORT", 8080))
    app = web.Application()
    app["bot"] = bot
    app.router.add_get("/oauth/callback", _oauth_callback)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", oauth_port)
    await site.start()
    log.info(f"OAuth server port {oauth_port} da ishga tushdi")

    logging.info("Bot ishga tushdi!")
    try:
        await dp.start_polling(bot)
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
