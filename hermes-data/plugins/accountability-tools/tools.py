import json
import os
from datetime import datetime, timezone, timedelta

import yaml

TZ = timezone(timedelta(hours=-3))  # America/Sao_Paulo (BRT, UTC-3)

BASE_DIR = os.environ.get(
    "CHECKIN_DATA_DIR",
    "/opt/data/profiles/accountability/.cron/responsibility_partner",
)
SUMMARY_PREFIX = os.path.join(BASE_DIR, "daily_summary")
FOCUS_FILE = os.path.join(BASE_DIR, "focus_sessions.json")


def _today():
    return datetime.now(timezone.utc).astimezone(TZ).strftime("%Y-%m-%d")


def _mkpath(date_str):
    return f"{SUMMARY_PREFIX}_{date_str}.md"


# ─── daily_summary_load ─────────────────────────────────────────────────


def handle_daily_summary_load(args, **_kw):
    date = args.get("date") or _today()
    path = _mkpath(date)

    if not os.path.exists(path):
        # Try JSON fallback
        json_path = f"{SUMMARY_PREFIX}_{date}.json"
        if os.path.exists(json_path):
            with open(json_path) as f:
                return json.load(f)
        return {"exists": False, "date": date}

    with open(path) as f:
        data = _parse_frontmatter(f.read())

    data["exists"] = True
    data["date"] = date
    return data


# ─── daily_summary_save ─────────────────────────────────────────────────


def handle_daily_summary_save(args, **_kw):
    date = args.get("date") or _today()
    today_str = _today()
    if date != today_str:
        return {"ok": False, "error": f"date must be today ({today_str}), not {date}. Use daily_summary_save without a date parameter to always write to today's file."}
    path = _mkpath(date)
    tmp = path + ".tmp"

    os.makedirs(BASE_DIR, exist_ok=True)

    frontmatter = {"date": date}

    for field in (
        "summary_text",
        "context",
        "intention",
        "plans_for_next_day",
    ):
        val = args.get(field)
        if val:
            frontmatter[field] = val

    tasks = args.get("tasks")
    if tasks:
        frontmatter["tasks"] = tasks

    metrics = args.get("metrics")
    if metrics:
        frontmatter["metrics"] = metrics

    with open(tmp, "w") as f:
        f.write("---\n")
        yaml.dump(
            frontmatter, f, allow_unicode=True, default_flow_style=False,
            sort_keys=False,
        )
        f.write("---\n\n")
        summary = args.get("summary_text", "")
        if summary:
            f.write(f"# {date}\n\n## Atualizações\n\n{summary}\n\n")

    os.replace(tmp, path)
    return {"ok": True, "date": date, "path": path}


# ─── focus_session_start ────────────────────────────────────────────────


def handle_focus_session_start(args, **_kw):
    task_name = args.get("task_name", "Tarefa")
    duration_minutes = int(args.get("duration_minutes", 25))

    data = _load_focus_sessions()
    started_epoch = _now_epoch()
    end_epoch = started_epoch + duration_minutes * 60

    session_id = f"fs-{started_epoch}"

    session = {
        "id": session_id,
        "task": task_name,
        "task_id": args.get("task_id", None),
        "duration_minutes": duration_minutes,
        "started_at": started_epoch,
        "end_epoch": end_epoch,
        "midpoint_sent": False,
        "end_sent": False,
        "user_responded_midpoint": False,
        "user_responded_end": False,
        "escalation_sent": None,
        "status": "active",
    }

    if duration_minutes > 60:
        session["midpoint_epoch"] = started_epoch + (duration_minutes * 60) // 2

    if "active_sessions" not in data:
        data["active_sessions"] = []
    data["active_sessions"].append(session)

    _save_focus_sessions(data)
    return {
        "ok": True,
        "session_id": session_id,
        "task_name": task_name,
        "duration_minutes": duration_minutes,
    }


# ─── focus_session_complete ─────────────────────────────────────────────


def handle_focus_session_complete(args, **_kw):
    session_id = args.get("session_id")
    result = args.get("result", "")

    data = _load_focus_sessions()
    today_str = _today()

    found = None
    for s in data.get("active_sessions", []):
        if s["id"] == session_id:
            found = s
            break

    if not found:
        return {"ok": False, "error": f"session {session_id} not found"}

    data["active_sessions"].remove(found)
    found["status"] = "completed"
    found["completed_at"] = _now_epoch()
    found["completed_date"] = today_str
    if result:
        found["result"] = result

    if "completed_today" not in data:
        data["completed_today"] = []
    data["completed_today"].append(found)

    stats = data.get("stats", {})
    stats["total_sessions"] = stats.get("total_sessions", 0) + 1
    stats["total_minutes"] = stats.get(
        "total_minutes", 0
    ) + found.get("duration_minutes", 0)
    data["stats"] = stats

    _save_focus_sessions(data)
    return {
        "ok": True,
        "session_id": session_id,
        "duration_minutes": found["duration_minutes"],
        "result": result or None,
    }


STATE_FILE = os.path.join(BASE_DIR, "state.json")


# ─── checkin_state_update ───────────────────────────────────────────────


def handle_checkin_state_update(args, **_kw):
    """Atomically update a field in a specific check-in window of state.json.
    Used by the cron agent after successful delivery of check-ins, follow-ups, etc."""
    window = str(args.get("window", ""))
    field = args.get("field", "")
    value = args.get("value")

    if window not in ("1", "2", "3"):
        return {"ok": False, "error": f"invalid window: {window}"}

    allowed = {
        "checkin_sent_at", "user_responded_at",
        "followup_action", "followup_sent_at",
        "escalation_sent",
    }
    if field not in allowed:
        return {"ok": False, "error": f"invalid field: {field} (allowed: {sorted(allowed)})"}

    if field.endswith("_at") and not isinstance(value, int):
        return {"ok": False, "error": f"field {field} requires integer epoch"}

    data = _load_state()
    ws = data.get("windows", {}).get(window)
    if not ws:
        return {"ok": False, "error": f"window {window} not found in state"}

    ws[field] = value
    _save_state(data)
    return {"ok": True, "window": window, "field": field}


# ─── focus_session_status ───────────────────────────────────────────────


def handle_focus_session_status(args, **_kw):
    """Return active focus session info or status of a specific session.
    If no session_id is given, returns the currently active session (if any)."""
    session_id = args.get("session_id")

    data = _load_focus_sessions()
    now = _now_epoch()

    if session_id:
        for s in data.get("active_sessions", []):
            if s["id"] == session_id:
                remaining = max(0, s.get("end_epoch", 0) - now)
                return {
                    "active": True,
                    "session_id": s["id"],
                    "task": s.get("task", "?"),
                    "duration_minutes": s.get("duration_minutes", 0),
                    "remaining_seconds": remaining,
                    "remaining_minutes": remaining // 60,
                    "midpoint_sent": s.get("midpoint_sent", False),
                    "end_sent": s.get("end_sent", False),
                }
        return {"active": False}

    active = None
    for s in data.get("active_sessions", []):
        if s.get("status") == "active":
            active = s
            break

    if not active:
        return {"active": False, "completed_today": len(data.get("completed_today", [])),
                "stats": data.get("stats", {})}

    remaining = max(0, active.get("end_epoch", 0) - now)
    return {
        "active": True,
        "session_id": active["id"],
        "task": active.get("task", "?"),
        "duration_minutes": active.get("duration_minutes", 0),
        "remaining_seconds": remaining,
        "remaining_minutes": remaining // 60,
        "midpoint_sent": active.get("midpoint_sent", False),
        "end_sent": active.get("end_sent", False),
    }


# ─── Internal helpers ───────────────────────────────────────────────────


def _now_epoch():
    return int(datetime.now(timezone.utc).astimezone(TZ).timestamp())


def _load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}


def _save_state(state):
    os.makedirs(BASE_DIR, exist_ok=True)
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    os.replace(tmp, STATE_FILE)


def _parse_frontmatter(text):
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    data = yaml.safe_load(parts[1])
    return data if isinstance(data, dict) else {}


def _load_focus_sessions():
    if os.path.exists(FOCUS_FILE):
        with open(FOCUS_FILE) as f:
            return json.load(f)
    return {
        "active_sessions": [],
        "completed_today": [],
        "stats": {"total_sessions": 0, "total_minutes": 0, "current_streak": 0},
    }


def _save_focus_sessions(data):
    os.makedirs(BASE_DIR, exist_ok=True)
    tmp = FOCUS_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, FOCUS_FILE)
