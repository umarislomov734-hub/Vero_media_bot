from database.connection import get_pool


async def get_week_stats_for_user(user_id: int) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT "
            "COUNT(*) FILTER (WHERE status='bajarildi') as done, "
            "COUNT(*) as total "
            "FROM tasks WHERE assigned_to=$1 AND created_at >= NOW()-INTERVAL '7 days'",
            user_id
        )
    return dict(row) if row else {"done": 0, "total": 0}


async def get_weekly_stats_per_user() -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT u.full_name as name, "
            "COUNT(*) FILTER (WHERE t.status='bajarildi') as done, "
            "COUNT(*) FILTER (WHERE t.status='kechikdi') as overdue, "
            "COUNT(*) FILTER (WHERE t.status NOT IN ('bajarildi','bekor_qilindi','kechikdi')) as missed, "
            "COUNT(*) FILTER (WHERE t.return_count > 0) as returned, "
            "COUNT(*) as total "
            "FROM users u "
            "LEFT JOIN tasks t ON t.assigned_to=u.id AND t.created_at >= NOW()-INTERVAL '7 days' "
            "WHERE u.is_active=TRUE AND u.role='member' "
            "GROUP BY u.id, u.full_name"
        )
    return [dict(r) for r in rows]


async def get_user_monthly_stats(user_id: int) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT "
            "COUNT(*) FILTER (WHERE status='bajarildi') as done, "
            "COUNT(*) as total, "
            "COUNT(*) FILTER (WHERE return_count > 0) as returned "
            "FROM tasks WHERE assigned_to=$1 AND created_at >= NOW()-INTERVAL '30 days'",
            user_id
        )
    return dict(row) if row else {"done": 0, "total": 0, "returned": 0}


async def get_growth_logs(user_id: int, limit: int = 10) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM growth_logs WHERE user_id=$1 ORDER BY date DESC LIMIT $2",
            user_id, limit
        )
    return [dict(r) for r in rows]


async def save_growth_log(user_id: int, activity_type: str, description: str) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO growth_logs (user_id, activity_type, description) VALUES ($1,$2,$3)",
            user_id, activity_type, description
        )
