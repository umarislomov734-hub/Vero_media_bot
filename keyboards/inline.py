from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


# ── VAZIFA RO'YXATI ───────────────────────────────────────────────────────────

def tasks_list_kb(tasks: list, prefix: str = "my") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    for task in tasks[:10]:  # Max 10 ta
        p_icon = {"yuqori": "🔴", "orta": "🟡", "past": "🟢"}.get(task["priority"], "🟡")
        label = f"{p_icon} {task['title'][:30]}"
        builder.button(text=label, callback_data=f"task:{task['id']}")

    builder.button(text="🔴 Yuqori", callback_data=f"filter:{prefix}:yuqori_priority")
    builder.button(text="⚠️ Kechikdi", callback_data=f"filter:{prefix}:kechikdi")
    builder.button(text="✅ Bajarildi", callback_data=f"filter:{prefix}:bajarildi")

    builder.adjust(1, 1, 1, 3)
    return builder.as_markup()


# ── VAZIFA TAFSILOTI ──────────────────────────────────────────────────────────

def task_detail_kb(
    task_id: int,
    is_manager: bool,
    is_assigned: bool,
    status: str
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    if is_assigned and status not in ("bajarildi", "bekor_qilindi"):
        builder.button(text="✅ Bajardim", callback_data=f"complete:{task_id}")
        builder.button(text="💬 Izoh", callback_data=f"comment:{task_id}")

    if is_manager and status not in ("bajarildi", "bekor_qilindi"):
        builder.button(text="↩️ Qaytarish", callback_data=f"return:{task_id}")
        builder.button(text="✏️ Tahrirlash", callback_data=f"edit:{task_id}")
        builder.button(text="❌ Bekor", callback_data=f"cancel_task:{task_id}")

    builder.button(text="« Orqaga", callback_data="back_to_list")
    builder.adjust(2, 3, 1)
    return builder.as_markup()


# ── TASDIQLASH ────────────────────────────────────────────────────────────────

def confirm_tasks_kb(count: int, prefix: str = "audio") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=f"✅ {count} ta vazifani tasdiqlash",
        callback_data=f"{prefix}_confirm:{count}"
    )
    builder.button(text="✏️ Tahrirlash", callback_data=f"{prefix}_edit")
    builder.button(text="❌ Bekor", callback_data=f"{prefix}_cancel")
    builder.adjust(1, 2)
    return builder.as_markup()


def confirm_create_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Tasdiqlash", callback_data="create_confirm")
    builder.button(text="❌ Bekor", callback_data="create_cancel")
    builder.adjust(2)
    return builder.as_markup()


# ── A'ZO TANLASH ──────────────────────────────────────────────────────────────

def members_select_kb(members: list, show_load: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    pos_icons = {
        "operator":       "🎥",
        "montajchi":      "✂️",
        "smm":            "📱",
        "dizayner":       "🎨",
        "ssenarист":      "📝",
        "kontent_menejer":"📋",
    }
    for m in members:
        icon = pos_icons.get(m.get("position", ""), "👤")
        load = f" [{m.get('active_count', 0)}]" if show_load else ""
        label = f"{icon} {m['full_name']}{load}"
        builder.button(text=label, callback_data=f"assign:{m['id']}:{m['full_name']}")

    builder.adjust(2)
    return builder.as_markup()


# ── PRIORITET ─────────────────────────────────────────────────────────────────

def priority_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🔴 Yuqori", callback_data="priority:yuqori")
    builder.button(text="🟡 O'rta",  callback_data="priority:orta")
    builder.button(text="🟢 Past",   callback_data="priority:past")
    builder.adjust(3)
    return builder.as_markup()


# ── VAZIFA TURI ───────────────────────────────────────────────────────────────

def task_type_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🎬 Loyiha",     callback_data="type:loyiha")
    builder.button(text="⚡ Birmartalik", callback_data="type:birmartalik")
    builder.button(text="🔁 Rutiniy",    callback_data="type:rutiniy")
    builder.adjust(3)
    return builder.as_markup()


# ── YANGI A'ZO ────────────────────────────────────────────────────────────────

def confirm_join_kb(telegram_id: int, full_name: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for role, label in [
        ("member", "🟢 Member"),
        ("pm",     "🟠 PM"),
        ("ad",     "🟠 AD"),
    ]:
        builder.button(
            text=label,
            callback_data=f"join_accept:{telegram_id}:{role}"
        )
    builder.button(text="❌ Rad etish", callback_data=f"join_reject:{telegram_id}")
    builder.adjust(3, 1)
    return builder.as_markup()


# ── FILTER ────────────────────────────────────────────────────────────────────

def archive_search_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🎬 Loyiha fayllar", callback_data="archive_files")
    builder.button(text="📋 Izohlar",        callback_data="archive_comments")
    builder.button(text="🎙️ Yig'ilishlar",   callback_data="archive_meetings")
    builder.adjust(1)
    return builder.as_markup()


def tasks_filter_kb(prefix: str = "my") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 Faol",    callback_data=f"filter:{prefix}:active")
    builder.button(text="✅ Bajarildi", callback_data=f"filter:{prefix}:bajarildi")
    builder.button(text="⚠️ Kechikdi", callback_data=f"filter:{prefix}:kechikdi")
    builder.button(text="↩️ Qaytarildi", callback_data=f"filter:{prefix}:qaytarildi")
    builder.adjust(2, 2)
    return builder.as_markup()


def edit_task_kb(task_index: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Tahrirlash", callback_data=f"edit_task:{task_index}")
    builder.button(text="❌ O'chirish",  callback_data=f"drop_task:{task_index}")
    builder.adjust(2)
    return builder.as_markup()


def select_project_kb(projects: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for p in projects:
        builder.button(text=p["title"], callback_data=f"publish_project:{p['id']}")
    builder.adjust(1)
    return builder.as_markup()


def select_platform_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="YouTube",   callback_data="pack_platform:youtube")
    builder.button(text="Instagram", callback_data="pack_platform:instagram")
    builder.button(text="Telegram",  callback_data="pack_platform:telegram")
    builder.adjust(3)
    return builder.as_markup()


def select_pack_field_kb(fields: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for key, label in fields:
        builder.button(text=label, callback_data=f"pack_field:{key}")
    builder.adjust(2)
    return builder.as_markup()


def admin_team_kb(members: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for m in members:
        builder.button(
            text=f"👤 {m['full_name']}",
            callback_data=f"admin_member:{m['id']}"
        )
    builder.button(text="🔙 Orqaga", callback_data="back_admin")
    builder.adjust(1)
    return builder.as_markup()


def admin_member_kb(member_id: int, current_role: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if current_role != "pm":
        builder.button(text="📊 PM qilish",     callback_data=f"change_role:{member_id}:pm")
    if current_role != "ad":
        builder.button(text="🎨 AD qilish",      callback_data=f"change_role:{member_id}:ad")
    if current_role != "member":
        builder.button(text="👤 Member qilish",  callback_data=f"change_role:{member_id}:member")
    builder.button(text="🚫 O'chirish",          callback_data=f"deactivate:{member_id}")
    builder.button(text="🔙 Orqaga",             callback_data="admin_team")
    builder.adjust(2, 1, 1)
    return builder.as_markup()


def publish_confirm_kb(project_id: int, show_publish: bool = True) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📎 Fayl biriktirish", callback_data=f"attach_file:{project_id}")
    if show_publish:
        builder.button(text="🚀 Nashr qilish", callback_data=f"do_publish:{project_id}")
    builder.button(text="❌ Bekor", callback_data="cancel_publish")
    builder.adjust(1)
    return builder.as_markup()
