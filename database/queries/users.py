from database.connection import get_pool


async def get_user_by_telegram_id(telegram_id: int) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT *, role::text as role, position::text as position "
            "FROM users WHERE telegram_id = $1",
            telegram_id
        )
    return dict(row) if row else None


async def get_user(user_id: int) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT *, role::text as role, position::text as position "
            "FROM users WHERE id = $1",
            user_id
        )
    return dict(row) if row else None


async def create_user(
    telegram_id: int,
    username: str | None,
    full_name: str,
    role: str = "member",
    is_active: bool = False
) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO users (telegram_id, username, full_name, role, is_active) "
            "VALUES ($1, $2, $3, $4::user_role, $5) "
            "ON CONFLICT (telegram_id) DO UPDATE "
            "SET username=$2, full_name=$3, role=$4::user_role, is_active=$5, last_active=NOW() "
            "RETURNING *",
            telegram_id, username, full_name, role, is_active
        )
    return dict(row)


async def approve_user(telegram_id: int, role: str) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET is_active=TRUE, role=$2::user_role WHERE telegram_id=$1",
            telegram_id, role
        )


async def reject_user(telegram_id: int) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM users WHERE telegram_id=$1 AND is_active=FALSE",
            telegram_id
        )


async def get_all_active_members() -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, telegram_id, full_name, role::text as role, position::text as position "
            "FROM users WHERE is_active=TRUE ORDER BY full_name"
        )
    return [dict(r) for r in rows]


async def get_all_managers() -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, telegram_id, full_name, role::text as role "
            "FROM users WHERE is_active=TRUE AND role IN ('super_admin','pm','ad')"
        )
    return [dict(r) for r in rows]


async def get_managers() -> list[dict]:
    return await get_all_managers()


async def get_content_managers() -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, telegram_id, full_name FROM users "
            "WHERE is_active=TRUE AND position='kontent_menejer'"
        )
    return [dict(r) for r in rows]


async def get_user_task_load(user_id: int) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT COUNT(*) as load FROM tasks "
            "WHERE assigned_to=$1 AND status NOT IN ('bajarildi','bekor_qilindi')",
            user_id
        )
    return row["load"] if row else 0


async def get_idle_members() -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT u.id, u.telegram_id, u.full_name, u.position::text as position "
            "FROM users u "
            "WHERE u.is_active=TRUE AND u.role='member' "
            "AND NOT EXISTS ("
            "  SELECT 1 FROM tasks t "
            "  WHERE t.assigned_to=u.id AND t.status NOT IN ('bajarildi','bekor_qilindi')"
            ")"
        )
    return [dict(r) for r in rows]


async def save_google_token(
    user_id: int,
    access_token: str,
    refresh_token: str,
    expiry,
    calendar_id: str = "primary"
) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """UPDATE users
               SET gcal_access_token=$2, gcal_refresh_token=$3,
                   gcal_token_expiry=$4, gcal_calendar_id=$5, gcal_connected=TRUE
               WHERE id=$1""",
            user_id, access_token, refresh_token, expiry, calendar_id
        )


async def get_google_token(user_id: int) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT gcal_access_token  AS access_token,
                      gcal_refresh_token AS refresh_token,
                      gcal_token_expiry  AS expiry,
                      gcal_calendar_id   AS calendar_id
               FROM users WHERE id=$1 AND gcal_connected=TRUE""",
            user_id
        )
    return dict(row) if row else None


async def disconnect_google(user_id: int) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """UPDATE users
               SET gcal_access_token=NULL, gcal_refresh_token=NULL,
                   gcal_token_expiry=NULL, gcal_connected=FALSE
               WHERE id=$1""",
            user_id
        )
