from database.connection import get_pool


async def get_active_projects() -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, title, status, current_stage::text as current_stage, deadline "
            "FROM projects WHERE status='active' ORDER BY deadline NULLS LAST"
        )
    return [dict(r) for r in rows]


async def get_project(project_id: int) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT p.*, p.status::text as status, p.current_stage::text as current_stage, "
            "u.full_name as creator_name "
            "FROM projects p LEFT JOIN users u ON p.created_by=u.id WHERE p.id=$1",
            project_id
        )
    return dict(row) if row else None


async def create_project(title: str, created_by: int, deadline=None) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO projects (title, created_by, deadline) VALUES ($1,$2,$3) RETURNING *",
            title, created_by, deadline
        )
    return dict(row)


async def get_project_milestones(project_id: int) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT m.*, m.status::text as status, u.full_name as assignee_name "
            "FROM milestones m LEFT JOIN users u ON m.assigned_to=u.id "
            "WHERE m.project_id=$1 ORDER BY m.order_num",
            project_id
        )
    return [dict(r) for r in rows]


async def get_milestone(milestone_id: int) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT m.*, m.status::text as status FROM milestones m WHERE m.id=$1",
            milestone_id
        )
    return dict(row) if row else None


async def complete_milestone(milestone_id: int) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE milestones SET status='bajarildi', completed_at=NOW() WHERE id=$1",
            milestone_id
        )


async def create_milestone(
    project_id: int,
    title: str,
    order_num: int,
    assigned_to: int | None = None
) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO milestones (project_id, title, order_num, assigned_to) "
            "VALUES ($1,$2,$3,$4) RETURNING *",
            project_id, title, order_num, assigned_to
        )
    return dict(row)


async def update_project_stage(project_id: int, stage: str) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE projects SET current_stage=$2::text, updated_at=NOW() WHERE id=$1",
            project_id, stage
        )


async def complete_project(project_id: int) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE projects SET status='completed', updated_at=NOW() WHERE id=$1",
            project_id
        )
