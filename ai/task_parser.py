import os
import json
import re
from groq import AsyncGroq
from dotenv import load_dotenv
from datetime import datetime
import pytz

load_dotenv()

_client = None


def _get_client() -> AsyncGroq:
    global _client
    if _client is None:
        _client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))
    return _client
TZ = pytz.timezone(os.getenv("TIMEZONE", "Asia/Tashkent"))


# ── SYSTEM PROMPT ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """Sen media jamoa uchun vazifa tahlil qiluvchi AI yordamchisisаn.

Senga xom audio transkripsiya matni beriladi. Bu matnda:
- Musor so'zlar ko'p bo'ladi ("hmm", "ну", "значит", "yani" va h.k.)
- O'zbek va rus tili aralash bo'lishi mumkin
- Bir nechta odam uchun bir vaqtda vazifalar berilishi mumkin

SENING VAZIFANG:
1. Matndan barcha vazifalarni aniqlab chiqish
2. Har bir vazifa uchun quyidagilarni ajratib olish:
   - assignee: Kim bajarishi kerak (ism yoki lavozim)
   - task: Nima qilish kerak (aniq, qisqa)
   - deadline: Qachon bajarish kerak (ISO format yoki tavsif)
   - priority: "yuqori" | "orta" | "past"
   - task_type: "loyiha" | "birmartalik" | "rutiniy"

QOIDALAR:
- Faqat aniq vazifalarni ajrat, suhbat va musor so'zlarni o'tkazib yubor
- Deadline aniq aytilmagan bo'lsa → null
- Prioritet aytilmagan bo'lsa → "orta"
- "Tez", "zudlik bilan", "urgent" → "yuqori" prioritet
- "Ertaga" → ertangi sana
- "Bugun" → bugungi sana 23:59
- "Bu hafta" → joriy hafta juma 23:59
- Ism yoki lavozim aniqlanmasa → assignee: "aniqlanmagan"

JAVOB FORMATI — faqat sof JSON, hech qanday izoh yoki markdown yo'q:
{
  "tasks": [
    {
      "assignee": "Jasur",
      "task": "Syemka — Chilonzor lokatsiyasi",
      "deadline": "ertaga 15:00",
      "deadline_iso": null,
      "priority": "yuqori",
      "task_type": "birmartalik",
      "notes": ""
    }
  ],
  "unresolved": "Aniqlab bo'lmagan qismlar (ixtiyoriy)"
}"""


# ── MAIN PARSER ──────────────────────────────────────────────────────────────

async def parse_tasks_from_text(
    raw_text: str,
    team_members: list[dict] = None,
    current_date: str = None
) -> dict:
    """
    Xom transkripsiya matnidan vazifalarni ajratib oladi.

    Args:
        raw_text: Whisper dan kelgan xom matn
        team_members: Jamoa a'zolari ro'yxati [{id, full_name, position}]
        current_date: Bugungi sana (YYYY-MM-DD)

    Returns:
        {"tasks": [...], "unresolved": "..."}
    """

    if not current_date:
        current_date = datetime.now(TZ).strftime("%Y-%m-%d")

    # Jamoa a'zolarini prompt ga qo'shamiz
    members_info = ""
    if team_members:
        members_list = "\n".join(
            "  - " + (m['full_name'] or '?') + " (" + (m.get('position') or 'noma\'lum') + ")"
            for m in team_members
        )
        members_info = f"\n\nJAMOA A'ZOLARI (ismlar shu ro'yxatdan mos keltirilsin):\n{members_list}"

    user_message = f"""Bugungi sana: {current_date}
{members_info}

TRANSKRIPSIYA MATNI:
\"\"\"{raw_text}\"\"\"

Ushbu matndan barcha vazifalarni ajratib, JSON formatida qaytir."""

    response = await _get_client().chat.completions.create(
        model="llama-3.3-70b-versatile",
        max_tokens=2000,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message}
        ]
    )

    raw_json = response.choices[0].message.content.strip()

    # JSON ni tozalash
    raw_json = re.sub(r"```json|```", "", raw_json).strip()

    try:
        result = json.loads(raw_json)
    except json.JSONDecodeError:
        # Agar JSON noto'g'ri bo'lsa — xavfsiz qaytarish
        result = {
            "tasks": [],
            "unresolved": raw_text,
            "error": "JSON parse xatosi"
        }

    return result


# ── MEETING PROTOCOL PARSER ──────────────────────────────────────────────────

MEETING_SYSTEM_PROMPT = """Sen yig'ilish protokol yozuvchisisаn.

Senga yig'ilish audio transkripsiyasi beriladi.
Sening vazifang:
1. Aniq protokol yozish
2. Qarorlarni ajratib olish
3. Kim nima qilishi kerakligini aniqlash

JAVOB FORMATI — faqat sof JSON:
{
  "protocol": "Yig'ilish qisqacha mazmuni",
  "decisions": [
    {"decision": "Qaror matni", "responsible": "Kim javobgar"}
  ],
  "tasks": [
    {
      "assignee": "Ism",
      "task": "Nima qilish kerak",
      "deadline": "Qachon",
      "priority": "yuqori|orta|past"
    }
  ]
}"""


async def parse_meeting_protocol(
    raw_text: str,
    team_members: list[dict] = None,
    current_date: str = None
) -> dict:
    """Yig'ilish transkripsiyasidan protokol va vazifalar yaratadi."""

    if not current_date:
        current_date = datetime.now(TZ).strftime("%Y-%m-%d")

    members_info = ""
    if team_members:
        members_list = "\n".join(
            "  - " + (m['full_name'] or '?') + " (" + (m.get('position') or 'noma\'lum') + ")"
            for m in team_members
        )
        members_info = f"\nJAMOA A'ZOLARI:\n{members_list}"

    user_message = f"""Bugungi sana: {current_date}
{members_info}

YIGʻILISH TRANSKRIPSIYASI:
\"\"\"{raw_text}\"\"\"

Protokol va vazifalarni JSON formatida qaytir."""

    response = await _get_client().chat.completions.create(
        model="llama-3.3-70b-versatile",
        max_tokens=2000,
        messages=[
            {"role": "system", "content": MEETING_SYSTEM_PROMPT},
            {"role": "user", "content": user_message}
        ]
    )

    raw_json = response.choices[0].message.content.strip()
    raw_json = re.sub(r"```json|```", "", raw_json).strip()

    try:
        result = json.loads(raw_json)
    except json.JSONDecodeError:
        result = {
            "protocol": raw_text,
            "decisions": [],
            "tasks": [],
            "error": "JSON parse xatosi"
        }

    return result


# ── COMMENT PARSER ───────────────────────────────────────────────────────────

COMMENT_SYSTEM_PROMPT = """Sen vazifa izohi tahlil qiluvchisisаn.

Senga hodimning audio izohi transkripsiyasi beriladi.
Izoh turini aniqla va matni tozala.

IZOH TURLARI:
- "bajardim"   → Vazifa bajarildi
- "kechikadi"  → Vazifa kechikadi (sabab bilan)
- "savol"      → Savol bor
- "muammo"     → Jiddiy muammo (urgent)
- "oddiy"      → Oddiy izoh / yangilik

JAVOB FORMATI — faqat sof JSON:
{
  "comment_type": "bajardim|kechikadi|savol|muammo|oddiy",
  "clean_text": "Tozalangan izoh matni",
  "is_urgent": false
}"""


async def parse_comment(raw_text: str) -> dict:
    """Audio izohni tahlil qiladi va turini aniqlaydi."""

    response = await _get_client().chat.completions.create(
        model="llama-3.3-70b-versatile",
        max_tokens=500,
        messages=[
            {"role": "system", "content": COMMENT_SYSTEM_PROMPT},
            {"role": "user", "content": raw_text}
        ]
    )

    raw_json = response.choices[0].message.content.strip()
    raw_json = re.sub(r"```json|```", "", raw_json).strip()

    try:
        result = json.loads(raw_json)
    except json.JSONDecodeError:
        result = {
            "comment_type": "oddiy",
            "clean_text": raw_text,
            "is_urgent": False
        }

    return result
