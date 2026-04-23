import asyncio
import logging
import os

import asyncpg
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None

_MAX_RETRY = 5
_RETRY_DELAY = 2


async def create_pool() -> None:
    global _pool
    delay = _RETRY_DELAY
    for attempt in range(1, _MAX_RETRY + 1):
        try:
            db_url = os.getenv("DATABASE_URL", "")
            ssl = "disable" if "localhost" in db_url or "127.0.0.1" in db_url else True
            _pool = await asyncpg.create_pool(
                dsn=db_url,
                ssl=ssl,
                min_size=2,
                max_size=10,
                command_timeout=30,
                timeout=10,
            )
            log.info("DB pool yaratildi (urinish %d)", attempt)
            break
        except (asyncpg.PostgresConnectionError, OSError) as exc:
            if attempt == _MAX_RETRY:
                log.critical("DB ulanishda %d urinish muvaffaqiyatsiz: %s", _MAX_RETRY, exc)
                raise
            log.warning("DB ulanish urinishi %d muvaffaqiyatsiz (%s), %ds kutilmoqda...", attempt, exc, delay)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30)

    await _init_schema()


async def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("DB pool hali yaratilmagan. create_pool() chaqiring.")
    return _pool


async def _init_schema() -> None:
    schema_path = os.path.join(os.path.dirname(__file__), "..", "_docs", "schema.sql")
    try:
        with open(schema_path, "r", encoding="utf-8") as f:
            sql = f.read()
        async with _pool.acquire() as conn:
            await conn.execute(sql)
        log.info("schema.sql qo'llanildi")
    except FileNotFoundError:
        log.warning("schema.sql topilmadi, o'tkazib yuborildi")
    except asyncpg.PostgresError as exc:
        log.debug("schema.sql DB xabari (odatda normal): %s", exc)

    migrations = [
        """CREATE TABLE IF NOT EXISTS gcal_events (
            id            SERIAL PRIMARY KEY,
            task_id       INT REFERENCES tasks(id) ON DELETE CASCADE,
            user_id       INT REFERENCES users(id) ON DELETE CASCADE,
            gcal_event_id TEXT NOT NULL,
            calendar_id   TEXT NOT NULL DEFAULT 'primary',
            synced_at     TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(task_id, user_id)
        )""",
        """CREATE TABLE IF NOT EXISTS gcal_oauth_states (
            id          SERIAL PRIMARY KEY,
            telegram_id BIGINT NOT NULL,
            state       TEXT UNIQUE NOT NULL,
            created_at  TIMESTAMPTZ DEFAULT NOW(),
            expires_at  TIMESTAMPTZ DEFAULT NOW() + INTERVAL '10 minutes'
        )""",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS gcal_access_token  TEXT",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS gcal_refresh_token  TEXT",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS gcal_token_expiry   TIMESTAMPTZ",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS gcal_calendar_id    TEXT",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS gcal_connected      BOOLEAN DEFAULT FALSE",
    ]
    async with _pool.acquire() as conn:
        for sql in migrations:
            try:
                await conn.execute(sql)
            except asyncpg.PostgresError as exc:
                log.debug("Migration o'tkazib yuborildi (odatda normal): %s", exc)
