from database.connection import get_pool


async def create_task(
    title: str,
    description: str | None,
    assigned_to: int,
    created_by: int,
    project_id: int | None = None,
    milestone_id: int | None = None,
    task_type: str = "birmartalik",
    priority: str = "orta",
    source: str = "manual",
    deadline=None,
    is_recurring: bool = False,
    recur_pattern: str | None = None
) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO tasks "
            "(title, description, assigned_to, created_by, project_id, milestone_id, "
            " task_type, priority, status, source, deadline, is_recurring, recur_pattern) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7::task_type,$8::task_priority,'yangi',$9::task_source,$10,$11,$12) "
            "RETURNING *",
            title, description, assigned_to, created_by, project_id, milestone_id,
            task_type, priority, source, deadline, is_recurring, recur_pattern
        )
    return dict(row)


async def create_task_bulk(tasks: list[dict], created_by: int) -> list[dict]:
    results = []
    for t in tasks:
        row = await create_task(
            title=t.get("title", ""),
            description=t.get("description"),
            assigned_to=t["assigned_to"],
            created_by=created_by,
            task_type=t.get("task_type", "birmartalik"),
            priority=t.get("priority", "orta"),
            source=t.get("source", "audio"),
            deadline=t.get("deadline"),
        )
        results.append(row)
    return results


async def get_task(task_id: int) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT t.*, t.priority::text as priority, t.status::text as status, "
            "t.task_type::text as task_type, t.source::text as source, "
            "u.full_name as assignee_name, c.full_name as creator_name "
            "FROM tasks t "
            "LEFT JOIN users u ON t.assigned_to=u.id "
            "LEFT JOIN users c ON t.created_by=c.id "
            "WHERE t.id=$1",
            task_id
        )
    return dict(row) if row else None


async def get_tasks_by_user(user_id: int, status_filter: str = "active") -> list[dict]:
    pool = await get_pool()
    if status_filter in ("bajarildi", "kechikdi", "qaytarildi", "yangi", "jarayonda"):
        where = f"t.assigned_to=$1 AND t.status='{status_filter}'"
    elif status_filter == "yuqori_priority":
        where = "t.assigned_to=$1 AND t.priority='yuqori' AND t.status NOT IN ('bajarildi','bekor_qilindi')"
    else:
        where = "t.assigned_to=$1 AND t.status NOT IN ('bajarildi','bekor_qilindi')"
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT t.*, t.priority::text as priority, t.status::text as status, "
            "t.task_type::text as task_type, "
            "u.full_name as assignee_name, c.full_name as creator_name "
            "FROM tasks t "
            "LEFT JOIN users u ON t.assigned_to=u.id "
            "LEFT JOIN users c ON t.created_by=c.id "
            f"WHERE {where} "
            "ORDER BY CASE t.priority WHEN 'yuqori' THEN 1 WHEN 'orta' THEN 2 ELSE 3 END, "
            "t.deadline NULLS LAST",
            user_id
        )
    return [dict(r) for r in rows]


async def get_all_tasks(status_filter: str = "active") -> list[dict]:
    pool = await get_pool()
    if status_filter in ("bajarildi", "kechikdi", "qaytarildi", "yangi", "jarayonda"):
        where = f"t.status = '{status_filter}'"
    elif status_filter == "yuqori_priority":
        where = "t.priority='yuqori' AND t.status NOT IN ('bajarildi','bekor_qilindi')"
    else:
        where = "t.status NOT IN ('bajarildi','bekor_qilindi')"
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT t.*, t.priority::text as priority, t.status::text as status, "
            "u.full_name as assignee_name "
            f"FROM tasks t LEFT JOIN users u ON t.assigned_to=u.id "
            f"WHERE {where} ORDER BY t.deadline NULLS LAST"
        )
    return [dict(r) for r in rows]


async def get_task_comments(task_id: int, limit: int = 10) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT tc.*, tc.comment_type::text as comment_type, u.full_name as user_name "
            "FROM task_comments tc LEFT JOIN users u ON tc.user_id=u.id "
            "WHERE tc.task_id=$1 ORDER BY tc.created_at DESC LIMIT $2",
            task_id, limit
        )
    return [dict(r) for r in rows]


async def complete_task(task_id: int) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "UPDATE tasks SET status='bajarildi', completed_at=NOW(), updated_at=NOW() "
            "WHERE id=$1 RETURNING *",
            task_id
        )
    return dict(row)


async def return_task(task_id: int, reason: str) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE tasks SET status='qaytarildi', return_count=return_count+1, "
            "return_reason=$2, updated_at=NOW() WHERE id=$1",
            task_id, reason
        )


async def add_comment(
    task_id: int,
    user_id: int,
    text: str,
    comment_type: str = "izoh",
    audio_file_id: str | None = None
) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO task_comments (task_id, user_id, text, comment_type, audio_file_id) "
            "VALUES ($1,$2,$3,$4::comment_type,$5) RETURNING *",
            task_id, user_id, text, comment_type, audio_file_id
        )
    return dict(row)


async def add_task_file(
    task_id: int,
    file_id: str,
    file_type: str,
    platform: str = "general",
    project_id: int | None = None,
    uploaded_by: int | None = None
) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO task_files (task_id, file_id, file_type, platform, project_id, uploaded_by) "
            "VALUES ($1,$2,$3,$4,$5,$6) RETURNING *",
            task_id, file_id, file_type, platform, project_id, uploaded_by
        )
    return dict(row)


async def get_tasks_due_today(user_id: int) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT t.*, t.priority::text as priority, t.status::text as status "
            "FROM tasks t WHERE t.assigned_to=$1 "
            "AND t.status NOT IN ('bajarildi','bekor_qilindi') "
            "AND t.deadline::date = CURRENT_DATE",
            user_id
        )
    return [dict(r) for r in rows]


async def get_tasks_due_in_days(user_id: int, days: int, remind_field: str) -> list[dict]:
    pool = await get_pool()
    col = "reminded_3d" if remind_field == "reminded_3d" else "reminded_1d"
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"SELECT t.*, t.priority::text as priority FROM tasks t "
            f"WHERE t.assigned_to=$1 "
            f"AND t.status NOT IN ('bajarildi','bekor_qilindi') "
            f"AND t.deadline::date = (CURRENT_DATE + $2 * INTERVAL '1 day')::date "
            f"AND t.{col} = FALSE",
            user_id, days
        )
    return [dict(r) for r in rows]


async def get_overdue_tasks(user_id: int) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT t.*, t.priority::text as priority FROM tasks t "
            "WHERE t.assigned_to=$1 "
            "AND t.status NOT IN ('bajarildi','bekor_qilindi') "
            "AND t.deadline < NOW()",
            user_id
        )
    return [dict(r) for r in rows]


async def mark_reminded(task_id: int, field: str) -> None:
    pool = await get_pool()
    col = "reminded_3d" if field == "reminded_3d" else "reminded_1d"
    async with pool.acquire() as conn:
        await conn.execute(f"UPDATE tasks SET {col}=TRUE WHERE id=$1", task_id)


async def get_recurring_tasks() -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM tasks WHERE is_recurring=TRUE AND status='bajarildi' "
            "AND completed_at::date = CURRENT_DATE - INTERVAL '1 day'"
        )
    return [dict(r) for r in rows]


async def clone_recurring_task(task_id: int) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO tasks "
            "(title, description, assigned_to, created_by, task_type, priority, source, "
            " deadline, is_recurring, recur_pattern) "
            "SELECT title, description, assigned_to, created_by, task_type, priority, source, "
            "CASE recur_pattern WHEN 'daily' THEN NOW()+INTERVAL '1 day' "
            "                   ELSE NOW()+INTERVAL '7 days' END, "
            "TRUE, recur_pattern FROM tasks WHERE id=$1 RETURNING *",
            task_id
        )
    return dict(row)


async def get_active_projects() -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, title, status, current_stage::text as current_stage, deadline "
            "FROM projects WHERE status='active' ORDER BY deadline NULLS LAST"
        )
    return [dict(r) for r in rows]


async def get_publish_pack(project_id: int) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM publish_packs WHERE project_id=$1", project_id
        )
    return dict(row) if row else None


async def create_publish_pack(project_id: int) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO publish_packs (project_id) VALUES ($1) "
            "ON CONFLICT (project_id) DO UPDATE SET updated_at=NOW() RETURNING *",
            project_id
        )
    return dict(row)


async def update_publish_pack(project_id: int, field: str, value) -> None:
    allowed = {
        "youtube_video", "youtube_thumbnail", "youtube_title",
        "youtube_description", "youtube_tags",
        "instagram_video", "instagram_cover", "instagram_caption",
        "telegram_video", "telegram_caption", "publish_date", "status"
    }
    if field not in allowed:
        raise ValueError(f"Unknown field: {field}")
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            f"UPDATE publish_packs SET {field}=$1, updated_at=NOW() WHERE project_id=$2",
            value, project_id
        )


async def mark_project_published(project_id: int, published_by: int) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE projects SET status='completed' WHERE id=$1", project_id)
        await conn.execute(
            "UPDATE publish_packs SET status='nashr_qilindi', published_by=$2, updated_at=NOW() "
            "WHERE project_id=$1",
            project_id, published_by
        )


async def mark_published(project_id: int, published_by: int) -> None:
    await mark_project_published(project_id, published_by)


async def get_project_files(project_id: int) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT tf.*, tf.file_type, u.full_name as uploader_name "
            "FROM task_files tf LEFT JOIN users u ON tf.uploaded_by=u.id "
            "WHERE tf.project_id=$1 ORDER BY tf.created_at DESC",
            project_id
        )
    return [dict(r) for r in rows]


async def get_project_files_by_stage(project_id: int, stage: str) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT tf.*, tf.file_type, u.full_name as uploader_name "
            "FROM task_files tf LEFT JOIN users u ON tf.uploaded_by=u.id "
            "WHERE tf.project_id=$1 AND tf.stage=$2 ORDER BY tf.created_at DESC",
            project_id, stage
        )
    return [dict(r) for r in rows]


async def get_project_milestone_assignees(project_id: int) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT DISTINCT u.telegram_id, u.full_name, u.position::text as position "
            "FROM milestones m JOIN users u ON m.assigned_to=u.id WHERE m.project_id=$1",
            project_id
        )
    return [dict(r) for r in rows]


async def get_next_milestone(milestone_id: int) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT m.* FROM milestones m "
            "WHERE m.project_id=(SELECT project_id FROM milestones WHERE id=$1) "
            "AND m.order_num>(SELECT order_num FROM milestones WHERE id=$1) "
            "ORDER BY m.order_num LIMIT 1",
            milestone_id
        )
    return dict(row) if row else None


async def activate_milestone(milestone_id: int) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE milestones SET status='jarayonda' WHERE id=$1", milestone_id
        )


async def save_meeting_log(
    chat_id: int,
    audio_file_id: str,
    protocol_text: str,
    decisions: dict,
    recorded_by: int
) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        import json
        row = await conn.fetchrow(
            "INSERT INTO meeting_logs (chat_id, audio_file_id, protocol_text, decisions, recorded_by) "
            "VALUES ($1,$2,$3,$4::jsonb,$5) RETURNING id",
            chat_id, audio_file_id, protocol_text, json.dumps(decisions), recorded_by
        )
    return row["id"]


async def save_gcal_event(task_id: int, user_id: int, event_id: str, calendar_id: str) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO gcal_events (task_id, user_id, gcal_event_id, calendar_id)
               VALUES ($1,$2,$3,$4)
               ON CONFLICT (task_id, user_id)
               DO UPDATE SET gcal_event_id=$3, calendar_id=$4, synced_at=NOW()""",
            task_id, user_id, event_id, calendar_id
        )


async def get_gcal_event(task_id: int, user_id: int) -> str | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT gcal_event_id FROM gcal_events WHERE task_id=$1 AND user_id=$2",
            task_id, user_id
        )
    return row["gcal_event_id"] if row else None


async def delete_gcal_event_record(task_id: int, user_id: int) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM gcal_events WHERE task_id=$1 AND user_id=$2",
            task_id, user_id
        )


async def get_meeting_logs(limit: int = 10) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT ml.*, u.full_name as recorder_name "
            "FROM meeting_logs ml LEFT JOIN users u ON ml.recorded_by=u.id "
            "ORDER BY ml.meeting_date DESC LIMIT $1",
            limit
        )
    return [dict(r) for r in rows]


async def search_archive(keyword: str) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT tf.*, tf.file_type, p.title as project_title, u.full_name as uploader_name "
            "FROM task_files tf "
            "LEFT JOIN projects p ON tf.project_id=p.id "
            "LEFT JOIN users u ON tf.uploaded_by=u.id "
            "WHERE p.title ILIKE '%' || $1 || '%' "
            "ORDER BY tf.created_at DESC LIMIT 10",
            keyword
        )
    return [dict(r) for r in rows]


async def search_task_comments(keyword: str) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT tc.*, tc.comment_type::text as comment_type, "
            "t.title as task_title, u.full_name as user_name "
            "FROM task_comments tc "
            "LEFT JOIN tasks t ON tc.task_id=t.id "
            "LEFT JOIN users u ON tc.user_id=u.id "
            "WHERE tc.text ILIKE '%' || $1 || '%' "
            "ORDER BY tc.created_at DESC LIMIT 20",
            keyword
        )
    return [dict(r) for r in rows]


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


async def get_idle_members() -> list[dict]:
    from database.queries.users import get_idle_members as _get_idle
    return await _get_idle()
