import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

_pool = None


async def create_pool():
    global _pool
    _pool = await asyncpg.create_pool(
        dsn=os.getenv("DATABASE_URL"),
        min_size=2,
        max_size=10,
        command_timeout=30
    )
    await _init_schema()


async def get_pool() -> asyncpg.Pool:
    return _pool


async def _init_schema():
    """schema.sql ni o'qib, jadvallarni yaratadi."""
    schema_path = os.path.join(os.path.dirname(__file__), "..", "_docs", "schema.sql")
    try:
        with open(schema_path, "r", encoding="utf-8") as f:
            sql = f.read()
        async with _pool.acquire() as conn:
            try:
                await conn.execute(sql)
            except Exception:
                pass
    except FileNotFoundError:
        pass

    async with _pool.acquire() as conn:
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
        for sql in migrations:
            try:
                await conn.execute(sql)
            except Exception:
                pass
