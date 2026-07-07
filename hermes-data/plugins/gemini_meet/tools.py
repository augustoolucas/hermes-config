"""Agent-facing tools for gemini_meet plugin.

Mirrors the bundled google_meet plugin's tools but uses our own
process_manager and Gemini Live realtime backend.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


# ── Tool schemas ────────────────────────────────────────────────────────

GEMINI_MEET_JOIN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "url": {
            "type": "string",
            "description": "Google Meet URL (https://meet.google.com/xxx-xxxx-xxx)",
        },
        "guest_name": {
            "type": "string",
            "description": "Display name for the bot in the meeting",
            "default": "Hermes",
        },
        "duration": {
            "type": "string",
            "description": "Maximum meeting duration (e.g. '30m', '1h')",
            "default": "30m",
        },
        "auth_state": {
            "type": "string",
            "description": "Path to a Playwright storageState JSON file with Google auth session. "
            "When set, the bot joins authenticated (avoids guest-admission blocks). "
            "Generate once via `hermes meet auth` or by logging into Google in a headed browser "
            "and exporting context.storage_state().",
        },
    },
    "required": ["url"],
}

GEMINI_MEET_STATUS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {},
}

GEMINI_MEET_TRANSCRIPT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "last": {
            "type": "integer",
            "description": "Number of last transcript lines to return (0 = all)",
            "default": 0,
        },
    },
}

GEMINI_MEET_SAY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "text": {
            "type": "string",
            "description": "Text to speak in the meeting",
        },
    },
    "required": ["text"],
}

GEMINI_MEET_LEAVE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {},
}

GEMINI_MEET_CREATE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "description": "Meeting title / summary",
            "default": "Reunião Hermes",
        },
        "duration": {
            "type": "string",
            "description": "Meeting duration (e.g. '30m', '1h')",
            "default": "30m",
        },
    },
}


# ── Helpers ─────────────────────────────────────────────────────────────

def _out_dir() -> Path:
    """Return the meetings output directory."""
    home = os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))
    return Path(home) / "workspace" / "meetings"


def _active_meeting() -> Path | None:
    """Return the path to the active meeting directory, if any."""
    meetings = _out_dir()
    if not meetings.exists():
        return None
    for d in sorted(meetings.iterdir(), reverse=True):
        if d.is_dir():
            status_file = d / "status.json"
            if status_file.exists():
                try:
                    status = json.loads(status_file.read_text())
                    if status.get("in_call") or status.get("inCall"):
                        return d
                except (json.JSONDecodeError, OSError):
                    continue
    return None


# ── Handlers ────────────────────────────────────────────────────────────

def handle_gemini_meet_join(args: dict, **_kw: Any) -> str:
    url = args.get("url", "")
    if not url or "meet.google.com" not in url:
        return json.dumps({"error": "Invalid Google Meet URL"})

    from hermes_plugins.gemini_meet import process_manager as pm
    guest_name = args.get("guest_name", "Hermes")
    duration = args.get("duration", "30m")

    api_key = os.environ.get("GEMINI_API_KEY", "")
    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-native-audio-preview-12-2025")
    voice = os.environ.get("GEMINI_VOICE", "Puck")

    auth_state = args.get("auth_state", "")
    if auth_state and not os.path.isfile(auth_state):
        return json.dumps({"error": f"auth_state file not found: {auth_state}"})

    try:
        result = pm.start(
            url,
            guest_name=guest_name,
            duration=duration,
            mode="realtime",
            realtime_api_key=api_key,
            realtime_model=model,
            realtime_voice=voice,
            auth_state=auth_state or None,
        )
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"error": str(e)})


def handle_gemini_meet_status(_args: dict, **_kw: Any) -> str:
    meeting = _active_meeting()
    if not meeting:
        return json.dumps({"in_call": False, "message": "No active meeting"})

    status_file = meeting / "status.json"
    try:
        status = json.loads(status_file.read_text())
        return json.dumps(status)
    except (json.JSONDecodeError, OSError) as e:
        return json.dumps({"error": str(e)})


def handle_gemini_meet_transcript(args: dict, **_kw: Any) -> str:
    meeting = _active_meeting()
    if not meeting:
        return json.dumps({"error": "No active meeting"})

    transcript_file = meeting / "transcript.txt"
    if not transcript_file.exists():
        return json.dumps({"transcript": "", "message": "No transcript yet"})

    try:
        lines = transcript_file.read_text().splitlines()
        last = args.get("last", 0)
        if last > 0:
            lines = lines[-last:]
        return json.dumps({"transcript": "\n".join(lines), "lines": len(lines)})
    except OSError as e:
        return json.dumps({"error": str(e)})


def handle_gemini_meet_say(args: dict, **_kw: Any) -> str:
    text = args.get("text", "").strip()
    if not text:
        return json.dumps({"error": "No text provided"})

    meeting = _active_meeting()
    if not meeting:
        return json.dumps({"error": "No active meeting"})

    say_queue = meeting / "say_queue.jsonl"
    try:
        import uuid
        entry = {"id": str(uuid.uuid4()), "text": text}
        with open(say_queue, "a") as f:
            f.write(json.dumps(entry) + "\n")
        return json.dumps({"ok": True, "queued": text})
    except OSError as e:
        return json.dumps({"error": str(e)})


def handle_gemini_meet_create(args: dict, **_kw: Any) -> str:
    """Create a Google Calendar event with a Google Meet conference link.

    Uses the OAuth token from the google-workspace skill (already
    configured on this profile). Returns the Meet URL.
    """
    from datetime import datetime, timedelta, timezone as dt_timezone

    summary = args.get("summary", "Reunião Hermes").strip()
    duration_raw = args.get("duration", "30m").strip().lower()

    # Parse duration.
    duration_s = 1800  # 30 min default
    try:
        if duration_raw.endswith("h"):
            duration_s = int(float(duration_raw[:-1]) * 3600)
        elif duration_raw.endswith("m"):
            duration_s = int(float(duration_raw[:-1]) * 60)
        else:
            duration_s = int(float(duration_raw))
    except (ValueError, TypeError):
        pass

    # Resolve the token path — check both profile and root.
    token_path = None
    candidates = [
        os.path.join(os.environ.get("HERMES_HOME", "/opt/data"), "google_token.json"),
        "/opt/data/google_token.json",
    ]
    for p in candidates:
        if os.path.isfile(p):
            token_path = p
            break
    if not token_path:
        return json.dumps({"error": "Google OAuth token not found — run hermes meet auth first"})

    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError as e:
        return json.dumps({"error": f"google-auth / google-api-python-client not installed: {e}"})

    try:
        with open(token_path) as f:
            token_data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        return json.dumps({"error": f"Failed to read token: {e}"})

    try:
        creds = Credentials(
            token=token_data.get("token"),
            refresh_token=token_data.get("refresh_token"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=token_data.get("client_id"),
            client_secret=token_data.get("client_secret"),
            scopes=token_data.get("scopes", ["https://www.googleapis.com/auth/calendar"]),
        )
        service = build("calendar", "v3", credentials=creds, cache_discovery=False)

        now = datetime.now(dt_timezone.utc)
        end = now + timedelta(seconds=duration_s)

        request_id = f"gemini-meet-{now.strftime('%Y%m%d%H%M%S')}"
        event = {
            "summary": summary,
            "start": {
                "dateTime": now.isoformat(),
                "timeZone": "America/Recife",
            },
            "end": {
                "dateTime": end.isoformat(),
                "timeZone": "America/Recife",
            },
            "conferenceData": {
                "createRequest": {
                    "requestId": request_id,
                    "conferenceSolutionKey": {"type": "hangoutsMeet"},
                },
            },
        }

        created = service.events().insert(
            calendarId="primary",
            conferenceDataVersion=1,
            body=event,
        ).execute()

        meet_url = None
        if created.get("conferenceData"):
            for ep in created["conferenceData"].get("entryPoints", []):
                if ep.get("entryPointType") == "video":
                    meet_url = ep["uri"]
                    break

        if not meet_url:
            meet_url = created.get("hangoutLink", "")

        return json.dumps({
            "ok": True,
            "meetUrl": meet_url,
            "eventId": created.get("id"),
            "summary": created.get("summary"),
            "htmlLink": created.get("htmlLink"),
        })
    except Exception as e:
        return json.dumps({"error": f"Failed to create Meet: {e}"})


def handle_gemini_meet_leave(_args: dict, **_kw: Any) -> str:
    meeting = _active_meeting()
    if not meeting:
        return json.dumps({"error": "No active meeting"})

    stop_file = meeting / "stop"
    try:
        stop_file.write_text("stop")
        return json.dumps({"ok": True, "message": "Stop signal sent"})
    except OSError as e:
        return json.dumps({"error": str(e)})
