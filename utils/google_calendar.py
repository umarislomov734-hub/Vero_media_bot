import logging
import os
import urllib.parse
from datetime import datetime, timezone, timedelta
from typing import Optional

import aiohttp

log = logging.getLogger(__name__)

SCOPES    = ["https://www.googleapis.com/auth/calendar.events"]
AUTH_URI  = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URI = "https://oauth2.googleapis.com/token"
EVENTS_BASE = "https://www.googleapis.com/calendar/v3/calendars/{cal}/events"


def get_auth_url(client_id: str, client_secret: str, redirect_uri: str, state: str) -> str:
    params = {
        "client_id":     client_id,
        "redirect_uri":  redirect_uri,
        "response_type": "code",
        "scope":         " ".join(SCOPES),
        "access_type":   "offline",
        "prompt":        "consent",
        "state":         state,
    }
    return AUTH_URI + "?" + urllib.parse.urlencode(params)


async def exchange_code(
    client_id: str, client_secret: str, redirect_uri: str, code: str
) -> Optional[dict]:
    payload = {
        "code":          code,
        "client_id":     client_id,
        "client_secret": client_secret,
        "redirect_uri":  redirect_uri,
        "grant_type":    "authorization_code",
    }
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(TOKEN_URI, data=payload, timeout=aiohttp.ClientTimeout(total=15)) as r:
                data = await r.json()
                if "access_token" not in data:
                    log.error(f"exchange_code xatosi: {data}")
                    return None
                expiry = datetime.now(timezone.utc) + timedelta(seconds=data.get("expires_in", 3600))
                return {
                    "access_token":  data["access_token"],
                    "refresh_token": data.get("refresh_token"),
                    "expiry":        expiry,
                    "calendar_id":   "primary",
                }
    except Exception as e:
        log.error(f"exchange_code exception: {e}")
        return None


async def refresh_token_if_needed(token_data: dict) -> Optional[dict]:
    try:
        expiry = token_data.get("expiry")
        if expiry:
            if isinstance(expiry, str):
                expiry = datetime.fromisoformat(expiry)
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) < expiry - timedelta(minutes=5):
                return token_data

        refresh_token = token_data.get("refresh_token")
        if not refresh_token:
            return None

        payload = {
            "client_id":     os.getenv("GOOGLE_CLIENT_ID"),
            "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
            "refresh_token": refresh_token,
            "grant_type":    "refresh_token",
        }
        async with aiohttp.ClientSession() as s:
            async with s.post(TOKEN_URI, data=payload, timeout=aiohttp.ClientTimeout(total=15)) as r:
                data = await r.json()
                if "access_token" not in data:
                    log.error(f"Token yangilashda xato: {data}")
                    return None
                new_expiry = datetime.now(timezone.utc) + timedelta(seconds=data.get("expires_in", 3600))
                return {
                    "access_token":  data["access_token"],
                    "refresh_token": refresh_token,
                    "expiry":        new_expiry,
                    "calendar_id":   token_data.get("calendar_id", "primary"),
                }
    except Exception as e:
        log.error(f"refresh_token_if_needed exception: {e}")
        return None


def _headers(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}


def _event_body(title: str, deadline_dt: datetime) -> dict:
    import pytz
    tz_name = os.getenv("TIMEZONE", "Asia/Tashkent")
    if deadline_dt.tzinfo is None:
        tz = pytz.timezone(tz_name)
        deadline_dt = tz.localize(deadline_dt)
    end_dt = deadline_dt + timedelta(hours=1)
    return {
        "summary": f"📌 {title}",
        "start":   {"dateTime": deadline_dt.isoformat(), "timeZone": tz_name},
        "end":     {"dateTime": end_dt.isoformat(),      "timeZone": tz_name},
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "popup", "minutes": 30},
                {"method": "popup", "minutes": 1440},
                {"method": "email",  "minutes": 1440},
            ],
        },
    }


async def create_event(
    token_data: dict, task_title: str, deadline_dt: datetime, task_id: int
) -> Optional[str]:
    try:
        token_data = await refresh_token_if_needed(token_data)
        if not token_data:
            return None
        cal = token_data.get("calendar_id", "primary")
        url = EVENTS_BASE.format(cal=cal)
        body = _event_body(task_title, deadline_dt)
        body["description"] = f"Vazifa #{task_id} — Bot orqali yaratildi"
        async with aiohttp.ClientSession() as s:
            async with s.post(url, json=body, headers=_headers(token_data["access_token"]),
                              timeout=aiohttp.ClientTimeout(total=15)) as r:
                result = await r.json()
                if r.status in (200, 201):
                    return result.get("id")
                log.error(f"create_event HTTP {r.status}: {result}")
                return None
    except Exception as e:
        log.error(f"create_event exception (task_id={task_id}): {e}")
        return None


async def update_event(
    token_data: dict, event_id: str, task_title: str, new_deadline_dt: datetime
) -> bool:
    try:
        token_data = await refresh_token_if_needed(token_data)
        if not token_data:
            return False
        cal = token_data.get("calendar_id", "primary")
        url = EVENTS_BASE.format(cal=cal) + f"/{event_id}"
        body = _event_body(task_title, new_deadline_dt)
        async with aiohttp.ClientSession() as s:
            async with s.patch(url, json=body, headers=_headers(token_data["access_token"]),
                               timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status in (200, 201):
                    return True
                log.error(f"update_event HTTP {r.status}: {await r.json()}")
                return False
    except Exception as e:
        log.error(f"update_event exception: {e}")
        return False


async def delete_event(token_data: dict, event_id: str) -> bool:
    try:
        token_data = await refresh_token_if_needed(token_data)
        if not token_data:
            return False
        cal = token_data.get("calendar_id", "primary")
        url = EVENTS_BASE.format(cal=cal) + f"/{event_id}"
        async with aiohttp.ClientSession() as s:
            async with s.delete(url, headers={"Authorization": f"Bearer {token_data['access_token']}"},
                                timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status in (200, 204):
                    return True
                log.error(f"delete_event HTTP {r.status}")
                return False
    except Exception as e:
        log.error(f"delete_event exception: {e}")
        return False
