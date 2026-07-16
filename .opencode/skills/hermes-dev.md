---
name: hermes-dev
description: "Workflows for developing and debugging the Hermes accountability partner system."
version: 1.0.0
metadata:
  tags: [hermes, dev, debug]
---

# Hermes Dev Skill

Workflows for developing and debugging the Hermes accountability partner system.

## Workflow 1: Debug cron failure

1. Read cron state:
   ```
   docker exec hermes cat /opt/data/profiles/accountability/.cron/responsibility_partner/state.json
   ```
   Check: windows, `sent_at`, `responded_at` (null means pending/failed), `followup_action`.

2. Find latest request dump:
   ```
   docker exec hermes ls -lt /opt/data/profiles/accountability/sessions/request_dump_cron_c9e31c8f7b6a*
   ```

3. Inspect the dump:
   - Count messages: 4 = turn 2 failed, 2 = turn 1.
   - Check model field (should be null for checkin → inherits config default).
   - Check finish_reason — stop vs length/tool_calls.

4. Check cron status:
   ```
   docker exec hermes hermes -p accountability cron list
   ```
   Verify `last_status` = ok, `next_run` is in the future.

5. Read container jobs.json:
   ```
   docker exec hermes cat /opt/data/cron/jobs.json
   ```
   Verify model, enabled_toolsets (should include `accountability-tools`), and prompt.

## Workflow 2: Safe deploy

1. Run validation:
   ```
   cd hermes-data && bash tests/validate.sh
   ```
   Abort deploy if any check fails.

2. Deploy:
   ```
   ./deploy.sh
   ```

3. Wait 5 seconds for container restart, then verify checksums:
   ```
   md5sum hermes-data/SOUL.md
   docker exec hermes md5sum /opt/data/profiles/accountability/SOUL.md

   md5sum hermes-data/scripts/checkin.py
   docker exec hermes md5sum /opt/data/scripts/checkin.py

   md5sum hermes-data/plugins/accountability-tools/tools.py
   docker exec hermes md5sum /opt/data/plugins/accountability-tools/tools.py
   ```

4. Verify cron:
   ```
   docker exec hermes hermes -p accountability cron list
   ```
   All jobs should show `last_status` = ok.

5. Check no error request dumps were generated post-deploy:
   ```
   docker exec hermes ls -lt /opt/data/profiles/accountability/sessions/request_dump_cron_*
   ```

## Workflow 3: Commit preparation

1. Review staged changes:
   ```
   git diff --cached --stat
   ```

2. Audit for sensitive data:
   ```
   hermes-data/tests/test_sensitive_data.sh
   ```
   Verify: no real chat IDs, no `sk-...` API keys, no emails. TELEGRAM_CHAT_ID placeholder must be present if config references it.

3. If clean, commit and push.

## Consumer cross-reference map

Critical — tools.py outputs must match checkin.py expectations.

| checkin.py reference | What it expects | tools.py counterpart |
|---|---|---|
| `is_in_focus_session()` (~line 370) | `end_epoch` in focus_sessions.json | `focus_session_start` (tools.py:96) must set `end_epoch = started_at + duration*60` |
| checkin.py:336 | `task` field in focus session record | tools.py:108 writes `task` (NOT `task_name`) |
| checkin.py reads focus sessions | `completed_date` (string YYYY-MM-DD) | tools.py:159 writes `completed_date` as string |
| checkin.py reads state.json | `checkin_sent_at`, `user_responded_at`, `followup_action` | `checkin_state_update` writes these fields |

## Troubleshooting patterns

| Pattern | Root cause | Fix |
|---|---|---|
| Duplicate check-ins | `sent_at` never set on first tick | checkin.py must mark `sent_at` immediately after emission, before any yielding |
| HTTP 400 on cron run | Model does not support single-turn/tool-less prompt | Verify model for checkin job is `null` (inherits default). Check `sessions/request_dump_cron_*` — 593 chars, no tools expected. |
| Wrong date in daily_summary | Summary content date != today | tools.py:54 rejects `date` field that doesn't match today. Fix the summary content or adjust validation. |
| Follow-up after response | `checkin_state_update` not called by live agent | Live agent must call `checkin_state_update` when user responds. Check `responded_at` in state.json — if null, agent did not mark it. Also check auto-fill mtime check on state file. |
| Focus session not detected | `end_epoch` missing or miscalculated | `is_in_focus_session()` checks `current_time < end_epoch`. Verify `focus_session_start` sets `end_epoch = started_at + (duration * 60)`. |
