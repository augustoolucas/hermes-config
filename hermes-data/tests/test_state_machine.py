#!/usr/bin/env python3
"""
Teste de state machine: simula W1/W2/W3 em ticks fixos
e verifica que cada janela tem os campos esperados.
"""
import json, os, sys, tempfile, shutil
from datetime import datetime, timezone, timedelta

TZ = timezone(timedelta(hours=-3))
TEST_DIR = tempfile.mkdtemp(prefix="hermes-sm-test-")
FAILURES = [0]


def make_brt_now(dt):
    def _fn():
        return dt, int(dt.timestamp())
    return _fn


def fake_git_backup(*a, **kw):
    pass


def assert_ok(condition, msg):
    if not condition:
        print("  FAIL: {}".format(msg))
        FAILURES[0] += 1


# ── Setup ───────────────────────────────────────────────────────
os.environ["CHECKIN_DATA_DIR"] = TEST_DIR
os.makedirs(TEST_DIR, exist_ok=True)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import checkin

checkin.git_backup_commit = fake_git_backup

# Override random_epoch_in_window to return deterministic epochs
# at exactly the window start so we know when to tick
WINDOWS = {1: (9, 0, 9, 30), 2: (11, 30, 12, 0), 3: (17, 0, 17, 45)}
orig_random = checkin.random_epoch_in_window

def fake_random_epoch_in_window(window, date_brt):
    sh, sm, eh, em = WINDOWS[window]
    dt = date_brt.replace(hour=sh, minute=sm, second=0, microsecond=0)
    return int(dt.timestamp())

checkin.random_epoch_in_window = fake_random_epoch_in_window

# ── Pre-create state for 2026-07-15 (no rollover) ──────────────
state_path = os.path.join(TEST_DIR, "state.json")
state = {"date": "2026-07-15", "windows": {}}
dt_base = datetime(2026, 7, 15, 0, 0, 0, tzinfo=TZ)
for w in (1, 2, 3):
    epoch = fake_random_epoch_in_window(w, dt_base)
    state["windows"][str(w)] = {
        "scheduled_epoch": epoch,
        "checkin_emitted_at": None,
        "checkin_sent_at": None,
        "user_responded_at": None,
        "followup_emitted_at": None,
        "followup_action": None,
        "followup_sent_at": None,
        "escalation_sent": None,
        "marker": "RESP-W{}-2026-07-15-9999".format(w),
    }
with open(state_path, "w") as f:
    json.dump(state, f)

fs_path = os.path.join(TEST_DIR, "focus_sessions.json")
with open(fs_path, "w") as f:
    json.dump({"active_sessions": [], "completed_today": [],
               "stats": {"total_sessions": 0, "total_minutes": 0, "current_streak": 0}}, f)


def run_tick(dt):
    checkin.brt_now = make_brt_now(dt)
    from io import StringIO
    saved = sys.stdout
    sys.stdout = StringIO()
    checkin.main()
    raw = sys.stdout.getvalue()
    sys.stdout = saved
    return [json.loads(l) for l in raw.strip().split("\n") if l.strip()]


# ── Tick 1: 09:00 (W1) ─────────────────────────────────────────
print("=== Tick 1: 09:00 BRT (W1) ===")
actions = run_tick(datetime(2026, 7, 15, 9, 0, 0, tzinfo=TZ))
act_names = [a.get("action", "?") for a in actions]
assert_ok("send_checkin" in act_names, "expected send_checkin, got {}".format(act_names))
with open(state_path) as f:
    state = json.load(f)
w1 = state["windows"]["1"]
assert_ok(w1["checkin_sent_at"] is not None, "checkin_sent_at not set on first tick")
assert_ok(w1["checkin_emitted_at"] is not None, "checkin_emitted_at not set")
assert_ok(w1["followup_action"] is None, "followup_action should be None on first tick")
print("  W1: sent={} emitted={}".format(w1["checkin_sent_at"], w1["checkin_emitted_at"]))
print()

# ── Tick 2: 09:35 (after W1 closed, before W2) ─────────────────
print("=== Tick 2: 09:35 BRT (after W1) ===")
actions = run_tick(datetime(2026, 7, 15, 9, 35, 0, tzinfo=TZ))
act_names = [a.get("action", "?") for a in actions]
assert_ok("send_checkin" not in act_names, "should not re-emit after window closed, got {}".format(act_names))
print("  Actions: {}".format(act_names))
print()

# ── Tick 3: 11:30 (W2) ─────────────────────────────────────────
print("=== Tick 3: 11:30 BRT (W2) ===")
actions = run_tick(datetime(2026, 7, 15, 11, 30, 0, tzinfo=TZ))
act_names = [a.get("action", "?") for a in actions]
assert_ok("send_checkin" in act_names, "expected send_checkin, got {}".format(act_names))
with open(state_path) as f:
    state = json.load(f)
w2 = state["windows"]["2"]
assert_ok(w2["checkin_sent_at"] is not None, "W2 sent_at not set")
assert_ok(w2["checkin_emitted_at"] is not None, "W2 emitted_at not set")
assert_ok(w2["followup_action"] is None, "W2 followup_action should be None")
print("  W2: sent={} emitted={}".format(w2["checkin_sent_at"], w2["checkin_emitted_at"]))
print()

# ── Tick 4: 17:00 (W3) ─────────────────────────────────────────
print("=== Tick 4: 17:00 BRT (W3) ===")
actions = run_tick(datetime(2026, 7, 15, 17, 0, 0, tzinfo=TZ))
act_names = [a.get("action", "?") for a in actions]
assert_ok("send_checkin" in act_names, "expected send_checkin, got {}".format(act_names))
with open(state_path) as f:
    state = json.load(f)
w3 = state["windows"]["3"]
assert_ok(w3["checkin_sent_at"] is not None, "W3 sent_at not set")
assert_ok(w3["checkin_emitted_at"] is not None, "W3 emitted_at not set")
assert_ok(w3["followup_action"] is None, "W3 followup_action should be None on first tick")
print("  W3: sent={} emitted={}".format(w3["checkin_sent_at"], w3["checkin_emitted_at"]))
print()

# ── Final state ─────────────────────────────────────────────────
print("=== Final state ===")
for k in ("1", "2", "3"):
    w = state["windows"][k]
    print("  W{}: sent={} emitted={} responded={} followup={}".format(
        k,
        "yes" if w["checkin_sent_at"] else "no",
        "yes" if w["checkin_emitted_at"] else "no",
        "yes" if w.get("user_responded_at") else "no",
        "yes" if w.get("followup_action") else "-",
    ))

shutil.rmtree(TEST_DIR, ignore_errors=True)

if FAILURES[0]:
    print("\n{} FAILURE(S)".format(FAILURES[0]))
    sys.exit(1)
else:
    print("\nstate_machine: PASSED")
