---
name: focus-session-handler
description: "Manages Lucas's focus sessions — declares, schedules check-ins, escalates, and tracks completion."
version: 1.0.0
metadata:
  hermes:
    tags: [productivity, focus, accountability]
    category: productivity
---

# Focus Session Handler

## When to use

When Lucas declares he's going to focus on something:
- "vou focar em X por 2h"
- "foco na API agora"
- "vou trabalhar na batimetria por 1h30"
- "quero focar em X"

Also use when:
- Lucas says he's done early ("terminei", "parei", "concluí")
- A focus session cron fires (mid-point or end)
- Lucas asks about his current focus session

## State File

All focus sessions are tracked in:
```
/opt/data/.cron/responsibility_partner/focus_sessions.json
```

Structure:
```json
{
  "active_sessions": [
    {
      "id": "focus-YYYYMMDD-N",
      "task": "Task name or description",
      "task_id": "optional-task-id-from-daily-summary",
      "started_at": "ISO-8601 with timezone",
      "duration_minutes": 120,
      "end_epoch": 1717514400,
      "midpoint_epoch": 1717510800,
      "midpoint_cron_id": "hermes-cron-job-id",
      "end_cron_id": "hermes-cron-job-id",
      "midpoint_sent": false,
      "end_sent": false,
      "user_responded_midpoint": false,
      "user_responded_end": false,
      "status": "active|completed|cancelled|expired"
    }
  ],
  "completed_today": [],
  "stats": {
    "total_sessions": 0,
    "total_minutes": 0,
    "current_streak": 0
  }
}
```

## Procedure: Declaring a Focus Session

When Lucas declares a focus session:

### Step 1: Parse the intent
Extract:
- **Task:** what he's focusing on (free text or match to existing task in daily_summary)
- **Duration:** parse from natural language ("2h" → 120min, "1h30" → 90min, "meia hora" → 30min)
- If no duration specified, ask: "Quanto tempo pretende dedicar?"

### Step 2: Save state
Write to `focus_sessions.json`. If the file doesn't exist, create it with the full structure.

Calculate epochs:
- `end_epoch` = now + duration_minutes
- `midpoint_epoch` = now + (duration_minutes / 2) — only if duration > 60min

### Step 3: Create cron jobs

**End-of-session cron (always):**
```
cronjob(
  action="create",
  schedule="<duration_minutes>m",
  name="focus-end-<id>",
  prompt="[FOCUS SESSION END] Session: <task> (<duration>min). Check focus_sessions.json for this session. If user hasn't responded yet, ask how it went. If no response after 20min, escalate. Update focus_sessions.json status to completed/expired.",
  deliver="telegram:TELEGRAM_CHAT_ID",
  enabled_toolsets=["file", "send_message"]
)
```

**Mid-point cron (only if duration > 60min):**
```
cronjob(
  action="create",
  schedule="<duration_minutes/2>m",
  name="focus-mid-<id>",
  prompt="[FOCUS SESSION MIDPOINT] Session: <task>. Check focus_sessions.json. Ask Lucas if he's still working on it. One question, no pressure. Update midpoint_sent to true.",
  deliver="telegram:TELEGRAM_CHAT_ID",
  enabled_toolsets=["file", "send_message"]
)
```

Save the cron job IDs in the focus session state.

### Step 4: Confirm to Lucas
Natural response, one line:
- "Focado em [task] até ~[hora]. Te cobro lá."
- "Beleza, [task] por [duração]. Te aviso quando acabar."

### Step 5: Update daily summary
Add a "focus_session" entry to the daily summary's tasks (or update existing task with focus info):
```yaml
- id: focus-<task-id>
  name: "Foco: <task>"
  status: em andamento
  notes: "Focus session: <duration>min, started at <time>"
  since: 'YYYY-MM-DD'
```

## Procedure: Mid-Point Check-In (Cron fires)

When the mid-point cron fires:

1. Read `focus_sessions.json`, find the active session
2. If `user_responded_midpoint` is already true → respond `[SILENT]`
3. If session is no longer active → respond `[SILENT]`
4. Otherwise, send a light check-in:
   - "Faz 1h. Ainda em [task]?"
   - "Checkpoint rápido — ainda focando em [task]?"
5. Update `midpoint_sent` to true in state

## Procedure: End-of-Session Check-In (Cron fires)

When the end-of-session cron fires:

1. Read `focus_sessions.json`, find the active session
2. If `user_responded_end` is already true → respond `[SILENT]`
3. If session is no longer active → respond `[SILENT]`
4. Otherwise, send the check-in:
   - "Tempo de [task] acabou. Como foi?"
   - "[duration] de [task] — conseguiu avançar?"
5. Update `end_sent` to true in state
6. **Do NOT update status yet** — wait for Lucas's response or escalation timeout

## Procedure: Escalation (No response to end check-in)

If Lucas doesn't respond within 20 minutes of the end check-in:

1. Read `focus_sessions.json`
2. If `user_responded_end` is still false:
   - Send: "Ei, a sessão de [task] acabou. Conseguiu avançar?"
3. If still no response after another 20 minutes:
   - Send: "Preciso fechar o status. [task] estava em andamento. Correto?"
   - Mark session as `expired` in state
   - Update daily_summary with status "sem resposta"

## Procedure: Early Completion

When Lucas says he's done ("terminei", "parei", "concluí", "acabei"):

1. Read `focus_sessions.json`, find active session
2. Cancel pending cron jobs:
   ```
   cronjob(action="remove", job_id="<midpoint_cron_id>")
   cronjob(action="remove", job_id="<end_cron_id>")
   ```
3. Update session status to `completed`
4. Update daily_summary — change task status to "concluído" if appropriate, or add notes about progress
5. Respond naturally: "Boa. [task] finalizada."

## Procedure: Cancellation

When Lucas says to cancel ("deixa pra lá", "não vou mais", "cancela"):

1. Same as early completion but status = `cancelled`
2. Update daily_summary — note the cancellation
3. Respond: "OK, [task] cancelada."

## Pitfalls

- **Do NOT use `~` in paths.** Always use `/opt/data/.cron/responsibility_partner/`
- **Do NOT create focus sessions without duration.** Always ask if not specified.
- **Do NOT interrupt focus sessions with regular check-ins.** The SOUL.md marks focus sessions as "do not interrupt" periods.
- **Cancel cron jobs on early completion.** Stale cron jobs firing after Lucas already finished is confusing.
- **One focus session at a time.** If Lucas declares a new one while one is active, ask if he wants to cancel the current one first.
- **Sync focus_sessions.json with daily_summary.** Every focus session should appear in the daily summary.
