#!/usr/bin/env python3
"""
Teste automatizado: mocka checkin.py com datas fixas
e verifica que toda action tem campo "message".
"""
import json, os, sys, tempfile, shutil
from datetime import datetime, timezone, timedelta

TEST_DIR = tempfile.mkdtemp(prefix="hermes-checkin-test-")
FAILURES = 0

# ── Patch environment ───────────────────────────────────────────────────
TZ = timezone(timedelta(hours=-3))
FIXED_NOW = datetime(2026, 7, 15, 18, 30, 0, tzinfo=TZ)  # Wednesday 18:30 BRT
FIXED_EPOCH = int(FIXED_NOW.timestamp())

def brt_now():
    return FIXED_NOW, FIXED_EPOCH

def fake_git_backup(*a, **kw):
    pass

# ── Setup CHECKIN_DATA_DIR ──────────────────────────────────────────────
os.environ["CHECKIN_DATA_DIR"] = TEST_DIR

# Write empty state + focus_sessions
state = {
    "date": "2026-07-14",
    "windows": {
        "1": {"scheduled_epoch": 0, "checkin_emitted_at": None, "checkin_sent_at": None,
              "user_responded_at": None, "followup_emitted_at": None,
              "followup_action": None, "followup_sent_at": None,
              "escalation_sent": None, "marker": "RESP-W1-2026-07-15-9999"},
        "2": {"scheduled_epoch": 0, "checkin_emitted_at": None, "checkin_sent_at": None,
              "user_responded_at": None, "followup_emitted_at": None,
              "followup_action": None, "followup_sent_at": None,
              "escalation_sent": None, "marker": "RESP-W2-2026-07-15-9999"},
        "3": {"scheduled_epoch": 0, "checkin_emitted_at": None, "checkin_sent_at": None,
              "user_responded_at": None, "followup_emitted_at": None,
              "followup_action": None, "followup_sent_at": None,
              "escalation_sent": None, "marker": "RESP-W3-2026-07-15-9999"},
    }
}
os.makedirs(TEST_DIR, exist_ok=True)
with open(os.path.join(TEST_DIR, "state.json"), "w") as f:
    json.dump(state, f)

fs = {"active_sessions": [], "completed_today": [], "stats": {"total_sessions": 0, "total_minutes": 0, "current_streak": 0}}
with open(os.path.join(TEST_DIR, "focus_sessions.json"), "w") as f:
    json.dump(fs, f)

# ── Import and monkey-patch ─────────────────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import checkin

checkin.brt_now = brt_now
checkin.git_backup_commit = fake_git_backup

# ── Run the script ──────────────────────────────────────────────────────
from io import StringIO
old_stdout = sys.stdout
sys.stdout = StringIO()
checkin.main()
output = sys.stdout.getvalue()
sys.stdout = old_stdout

# ── Validate ────────────────────────────────────────────────────────────
lines = output.strip().split("\n")
actions = [json.loads(line) for line in lines if line.strip() and not line.startswith("{")]

# Actions that MUST have a "message" field
MUST_HAVE_MESSAGE = {"send_checkin", "send_followup", "send_escalation",
                      "send_reengagement", "suggest_focus", "generate_daily_summary"}
MUST_HAVE_NONE = {"none"}  # no message needed

print("=== checkin.py action validation ===")
actions_seen = set()
for action in actions:
    act = action.get("action", "?")
    actions_seen.add(act)
    has_message = "message" in action

    if act in MUST_HAVE_MESSAGE:
        if not has_message:
            print(f"FAIL: action='{act}' missing 'message' field")
            FAILURES += 1
        else:
            print(f"  OK: {act} -> message={str(action['message'])[:80]}...")
    elif act in MUST_HAVE_NONE:
        print(f"  OK: {act} (no message needed)")
    else:
        print(f"  WARN: unknown action '{act}'")

print(f"\nValidated {len(actions)} actions, {FAILURES} failures")

# ── Cleanup ─────────────────────────────────────────────────────────────
shutil.rmtree(TEST_DIR, ignore_errors=True)

if FAILURES:
    sys.exit(1)
else:
    print("checkin_actions: PASSED")
