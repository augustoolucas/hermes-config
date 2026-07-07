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

def handle_gemini_meet_join(args: dict) -> str:
    url = args.get("url", "")
    if not url or "meet.google.com" not in url:
        return json.dumps({"error": "Invalid Google Meet URL"})

    from plugins.gemini_meet.process_manager import ProcessManager

    pm = ProcessManager()
    guest_name = args.get("guest_name", "Hermes")
    duration = args.get("duration", "30m")

    try:
        result = pm.start(url, guest_name=guest_name, duration=duration, realtime=True)
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"error": str(e)})


def handle_gemini_meet_status(_args: dict) -> str:
    meeting = _active_meeting()
    if not meeting:
        return json.dumps({"in_call": False, "message": "No active meeting"})

    status_file = meeting / "status.json"
    try:
        status = json.loads(status_file.read_text())
        return json.dumps(status)
    except (json.JSONDecodeError, OSError) as e:
        return json.dumps({"error": str(e)})


def handle_gemini_meet_transcript(args: dict) -> str:
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


def handle_gemini_meet_say(args: dict) -> str:
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


def handle_gemini_meet_leave(_args: dict) -> str:
    meeting = _active_meeting()
    if not meeting:
        return json.dumps({"error": "No active meeting"})

    stop_file = meeting / "stop"
    try:
        stop_file.write_text("stop")
        return json.dumps({"ok": True, "message": "Stop signal sent"})
    except OSError as e:
        return json.dumps({"error": str(e)})
