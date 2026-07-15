#!/usr/bin/env python3
"""
Teste de compatibilidade: chama cada handler de accountability-tools
com entrada real e verifica formato de saida contra consumidores.
"""
import json, os, sys, tempfile, shutil
from datetime import datetime, timezone, timedelta

TZ = timezone(timedelta(hours=-3))
TEST_DIR = tempfile.mkdtemp(prefix="hermes-toolfmt-test-")
os.environ["CHECKIN_DATA_DIR"] = TEST_DIR
os.makedirs(TEST_DIR, exist_ok=True)

FAILURES = [0]


def assert_ok(condition, msg):
    if not condition:
        print("  FAIL: {}".format(msg))
        FAILURES[0] += 1


# ── Import tools ────────────────────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "plugins",
                                "accountability-tools"))
from tools import (
    handle_focus_session_start,
    handle_focus_session_complete,
    handle_focus_session_status,
    handle_daily_summary_save,
    handle_checkin_state_update,
)


def _now_epoch():
    return int(datetime.now(timezone.utc).astimezone(TZ).timestamp())


TODAY = datetime.now(timezone.utc).astimezone(TZ).strftime("%Y-%m-%d")

# ── focus_session_start ─────────────────────────────────────────
print("=== focus_session_start ===")
r = handle_focus_session_start({"task_name": "Benchmark SQL", "duration_minutes": 60})
assert_ok(r.get("ok"), "expected ok=True, got {}".format(r))
assert_ok("task" not in r, "output should NOT have 'task' field (it's task_name)")
assert_ok(r.get("task_name") == "Benchmark SQL", "task_name mismatch")
assert_ok(r.get("duration_minutes") == 60, "duration_minutes mismatch")
sid = r.get("session_id")
assert_ok(sid is not None, "session_id missing")

# Check focus_sessions.json has end_epoch correctly
with open(os.path.join(TEST_DIR, "focus_sessions.json")) as f:
    fs_data = json.load(f)
session = fs_data["active_sessions"][0]
assert_ok(session["task"] == "Benchmark SQL", "saved 'task' field mismatch")
assert_ok(session["end_epoch"] is not None, "end_epoch missing (was critical bug)")
assert_ok(session["end_epoch"] == session["started_at"] + 3600,
          "end_epoch must be started_at + duration*60")
assert_ok(session["status"] == "active", "initial status should be 'active'")
print("  OK: task='{}' end_epoch={} session_id={}".format(
    session["task"], session["end_epoch"], sid))
print()

# ── focus_session_complete ──────────────────────────────────────
print("=== focus_session_complete ===")
r2 = handle_focus_session_complete({"session_id": sid, "result": "np.concatenate venceu"})
assert_ok(r2.get("ok"), "expected ok=True, got {}".format(r2))
assert_ok(r2.get("session_id") == sid, "session_id mismatch")
assert_ok(r2.get("result") == "np.concatenate venceu", "result mismatch")

with open(os.path.join(TEST_DIR, "focus_sessions.json")) as f:
    fs_data = json.load(f)
assert_ok(len(fs_data["active_sessions"]) == 0, "active_sessions should be empty after complete")
assert_ok(len(fs_data["completed_today"]) == 1, "completed_today should have 1 entry")
completed = fs_data["completed_today"][0]
assert_ok(completed["status"] == "completed", "status should be 'completed'")
assert_ok(isinstance(completed["completed_date"], str), "completed_date must be string YYYY-MM-DD")
assert_ok(completed["completed_date"] == TODAY,
          "completed_date should be today ({}), got {}".format(TODAY, completed["completed_date"]))
assert_ok(completed["completed_at"] is not None, "completed_at epoch missing")
print("  OK: completed_date={} status={}".format(completed["completed_date"], completed["status"]))
print()

# ── focus_session_status (no active session) ────────────────────
print("=== focus_session_status (idle) ===")
r3 = handle_focus_session_status({})
assert_ok(r3.get("active") is False, "should be inactive after complete")
print("  OK: active=False completed_today={}".format(r3.get("completed_today", 0)))
print()

# ── focus_session_status (with active session) ──────────────────
print("=== focus_session_status (active) ===")
r_start = handle_focus_session_start({"task_name": "Refactor", "duration_minutes": 90})
r4 = handle_focus_session_status({})
assert_ok(r4.get("active") is True, "should be active")
assert_ok(r4.get("task") == "Refactor", "task mismatch in status")
assert_ok(r4.get("duration_minutes") == 90, "duration mismatch")
assert_ok(r4.get("remaining_seconds") > 0, "remaining_seconds should be >0")
print("  OK: active=True task={} remaining_minutes={}".format(r4["task"], r4["remaining_minutes"]))
print()

# Clean up the test session
handle_focus_session_complete({"session_id": r_start["session_id"]})

# ── daily_summary_save rejects wrong date ───────────────────────
print("=== daily_summary_save (wrong date) ===")
r5 = handle_daily_summary_save({"date": "2026-07-09", "summary_text": "wrong"})
assert_ok(r5.get("ok") is False, "should reject date != today")
assert_ok("must be today" in r5.get("error", ""),
          "error message should mention 'today', got {}".format(r5.get("error")))
print("  OK: rejected date=2026-07-09")
print()

# ── daily_summary_save accepts today ────────────────────────────
print("=== daily_summary_save (today) ===")
r6 = handle_daily_summary_save({"summary_text": "Test summary", "intention": "Write tests"})
assert_ok(r6.get("ok"), "should accept today's date")
assert_ok(r6.get("date") == TODAY, "date should be today")
print("  OK: saved to {}".format(r6.get("path", "?")))

# Cleanup test file
if r6.get("path"):
    try:
        os.remove(r6["path"])
    except OSError:
        pass
print()

# ── checkin_state_update validation ─────────────────────────────
print("=== checkin_state_update ===")

# Pre-create state.json
state_path = os.path.join(TEST_DIR, "state.json")
state = {
    "date": TODAY,
    "windows": {
        "1": {"scheduled_epoch": 1, "checkin_sent_at": None, "user_responded_at": None,
              "followup_action": None, "followup_sent_at": None, "escalation_sent": None,
              "checkin_emitted_at": None, "followup_emitted_at": None, "marker": "T1"},
        "2": {"scheduled_epoch": 2, "checkin_sent_at": None, "user_responded_at": None,
              "followup_action": None, "followup_sent_at": None, "escalation_sent": None,
              "checkin_emitted_at": None, "followup_emitted_at": None, "marker": "T2"},
        "3": {"scheduled_epoch": 3, "checkin_sent_at": None, "user_responded_at": None,
              "followup_action": None, "followup_sent_at": None, "escalation_sent": None,
              "checkin_emitted_at": None, "followup_emitted_at": None, "marker": "T3"},
    },
}
with open(state_path, "w") as f:
    json.dump(state, f)

# Invalid window
r7 = handle_checkin_state_update({"window": "99", "field": "checkin_sent_at", "value": 123})
assert_ok(r7.get("ok") is False, "should reject invalid window 99")

# Invalid field
r8 = handle_checkin_state_update({"window": "1", "field": "banana", "value": 123})
assert_ok(r8.get("ok") is False, "should reject invalid field 'banana'")

# Successful update
ts = _now_epoch()
r9 = handle_checkin_state_update({"window": "1", "field": "checkin_sent_at", "value": ts})
assert_ok(r9.get("ok") is True, "expected ok=True, got {}".format(r9))

with open(state_path) as f:
    updated = json.load(f)
assert_ok(updated["windows"]["1"]["checkin_sent_at"] == ts,
          "checkin_sent_at should persist in state.json")
print("  OK: window=1 field=checkin_sent_at persisted")
print()

# ── Cleanup ────────────────────────────────────────────────────
shutil.rmtree(TEST_DIR, ignore_errors=True)

if FAILURES[0]:
    print("\n{} FAILURE(S)".format(FAILURES[0]))
    sys.exit(1)
else:
    print("tool_format: PASSED")
