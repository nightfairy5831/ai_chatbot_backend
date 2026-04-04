import httpx
from datetime import datetime, timedelta
from app.core.config import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI

SCOPES = "https://www.googleapis.com/auth/calendar"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
CALENDAR_API = "https://www.googleapis.com/calendar/v3"


def get_auth_url(state: str) -> str:
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPES,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{AUTH_URL}?{query}"


def exchange_code(code: str) -> dict:
    with httpx.Client() as client:
        resp = client.post(TOKEN_URL, data={
            "code": code,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code",
        })
        resp.raise_for_status()
        return resp.json()


def refresh_access_token(refresh_token: str) -> str:
    with httpx.Client() as client:
        resp = client.post(TOKEN_URL, data={
            "refresh_token": refresh_token,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "grant_type": "refresh_token",
        })
        resp.raise_for_status()
        return resp.json()["access_token"]


def get_available_slots(refresh_token: str, date_str: str, calendar_id: str = "primary") -> list[dict]:
    access_token = refresh_access_token(refresh_token)
    date = datetime.strptime(date_str, "%Y-%m-%d")
    time_min = date.isoformat() + "T00:00:00Z"
    time_max = date.isoformat() + "T23:59:59Z"

    with httpx.Client() as client:
        resp = client.get(
            f"{CALENDAR_API}/calendars/{calendar_id}/events",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"timeMin": time_min, "timeMax": time_max, "singleEvents": True, "orderBy": "startTime"},
        )
        resp.raise_for_status()
        events = resp.json().get("items", [])

    busy = []
    for event in events:
        start = event.get("start", {}).get("dateTime")
        end = event.get("end", {}).get("dateTime")
        if start and end:
            busy.append((datetime.fromisoformat(start), datetime.fromisoformat(end)))

    work_start = date.replace(hour=9, minute=0)
    work_end = date.replace(hour=17, minute=0)
    slots = []
    current = work_start

    for busy_start, busy_end in sorted(busy):
        if current < busy_start:
            slots.append({"start": current.strftime("%H:%M"), "end": busy_start.strftime("%H:%M")})
        current = max(current, busy_end)

    if current < work_end:
        slots.append({"start": current.strftime("%H:%M"), "end": work_end.strftime("%H:%M")})

    return slots


def create_event(refresh_token: str, date_str: str, time_str: str, summary: str, description: str = "", calendar_id: str = "primary", duration_minutes: int = 60) -> dict:
    access_token = refresh_access_token(refresh_token)
    start_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    end_dt = start_dt + timedelta(minutes=duration_minutes)

    event_body = {
        "summary": summary,
        "description": description,
        "start": {"dateTime": start_dt.isoformat(), "timeZone": "UTC"},
        "end": {"dateTime": end_dt.isoformat(), "timeZone": "UTC"},
    }

    with httpx.Client() as client:
        resp = client.post(
            f"{CALENDAR_API}/calendars/{calendar_id}/events",
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
            json=event_body,
        )
        resp.raise_for_status()
        return resp.json()


def cancel_event(refresh_token: str, event_id: str, calendar_id: str = "primary") -> bool:
    access_token = refresh_access_token(refresh_token)
    with httpx.Client() as client:
        resp = client.delete(
            f"{CALENDAR_API}/calendars/{calendar_id}/events/{event_id}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        return resp.status_code == 204


def list_events(refresh_token: str, calendar_id: str = "primary", days: int = 30) -> list[dict]:
    access_token = refresh_access_token(refresh_token)
    now = datetime.utcnow()
    time_min = now.isoformat() + "Z"
    time_max = (now + timedelta(days=days)).isoformat() + "Z"

    with httpx.Client() as client:
        resp = client.get(
            f"{CALENDAR_API}/calendars/{calendar_id}/events",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"timeMin": time_min, "timeMax": time_max, "singleEvents": True, "orderBy": "startTime"},
        )
        resp.raise_for_status()
        return resp.json().get("items", [])
