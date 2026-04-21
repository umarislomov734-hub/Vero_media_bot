from datetime import datetime

PRIORITY_ICON = {"yuqori": "🔴", "orta": "🟡", "past": "🟢"}
STATUS_ICON = {
    "yangi": "🆕", "jarayonda": "▶️", "bajarildi": "✅",
    "kechikdi": "⚠️", "qaytarildi": "↩️", "bekor_qilindi": "❌"
}


def format_task(task: dict) -> str:
    priority = PRIORITY_ICON.get(task.get("priority", ""), "")
    status = STATUS_ICON.get(task.get("status", ""), "")
    deadline = ""
    if task.get("deadline"):
        dl = task["deadline"]
        if isinstance(dl, datetime):
            deadline = f" | {dl.strftime('%d.%m %H:%M')}"
        else:
            deadline = f" | {dl}"
    assignee = f"\n👤 {task['assignee_name']}" if task.get("assignee_name") else ""
    return (
        f"{priority} {status} <b>{task['title']}</b>{deadline}"
        f"{assignee}"
    )


def format_deadline(dt: datetime | None) -> str:
    if not dt:
        return "—"
    return dt.strftime("%d.%m.%Y %H:%M")


def format_user_load(load: int) -> str:
    if load == 0:
        return "🟢 Bo'sh"
    if load <= 3:
        return f"🟡 {load} ta vazifa (o'rta)"
    return f"🔴 {load} ta vazifa (band)"
