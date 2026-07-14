---
name: focus-session-handler
description: "Manages Lucas's focus sessions — declares, schedules check-ins, escalates, and tracks completion."
version: 2.0.0
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

## Tool reference

| Task | Tool to use |
|---|---|
| Start session | `focus_session_start(task_name=..., duration_minutes=...)` |
| Complete session | `focus_session_complete(session_id=..., result=...)` |
| Check active sessions | `focus_session_status()` → `{active: true, task: "...", remaining_minutes: ...}` |
| Check specific session | `focus_session_status(session_id="fs-...")` |

These tools manage `focus_sessions.json` automatically — you never need to know the file path.

## Procedure: Declaring a Focus Session

### Step 1: Parse the intent
Extract:
- **Task:** what he's focusing on (free text or match to existing task in daily_summary)
- **Duration:** parse from natural language ("2h" → 120min, "1h30" → 90min, "meia hora" → 30min)
- If no duration specified, ask: "Quanto tempo pretende dedicar?"

### Step 2: Save state via tool
```
focus_session_start(task_name="Nome da task", duration_minutes=90)
```

Returns: `{ok: true, session_id: "fs-...", task_name: "...", duration_minutes: 90}`

### Step 3: Create cron jobs

**End-of-session cron (always):**
```
cronjob(
  action="create",
  schedule="<duration_minutes>m",
  name="focus-end-<id>",
  prompt="[FOCUS SESSION END] Session: <task> (<duration>min). Use focus_session_complete to finalize. If no response after 20min, escalate. Respond [SILENT] if user hasn't interacted.",
  deliver="telegram:${TELEGRAM_CHAT_ID}",
  enabled_toolsets=["file", "send_message", "accountability-tools"]
)
```

**Mid-point cron (only if duration > 60min):**
```
cronjob(
  action="create",
  schedule="<duration_minutes/2>m",
  name="focus-mid-<id>",
  prompt="[FOCUS SESSION MIDPOINT] Session: <task>. Ask Lucas if he's still working on it. One question, no pressure. Respond [SILENT] if no answer.",
  deliver="telegram:${TELEGRAM_CHAT_ID}",
  enabled_toolsets=["file", "send_message", "accountability-tools"]
)
```

### Step 4: Update daily summary
After starting, save via `daily_summary_save` with the updated tasks list — add a focus entry:
```json
{"id": "fs-...", "name": "Foco: <task>", "status": "em andamento", "notes": "Focus session: <duration>min, started now", "since": "YYYY-MM-DD"}
```

### Step 5: Confirm to Lucas
Natural response, one line:
- "Focado em [task] até ~[hora]. Te cobro lá."
- "Beleza, [task] por [duração]. Te aviso quando acabar."

## Procedure: Mid-Point Check-In (Cron fires)

1. Call `focus_session_status()` to get current state
2. If user already responded or session is no longer active → `[SILENT]`
3. Otherwise, send a light check-in: "Faz 1h. Ainda em [task]?"

## Procedure: End-of-Session Check-In (Cron fires)

1. Call `focus_session_status()` to get current state
2. If user already responded or session is no longer active → `[SILENT]`
3. Otherwise: "Tempo de [task] acabou. Como foi?"
4. **Do NOT update status yet** — wait for Lucas's response

## Procedure: Escalation (No response to end check-in)

If Lucas doesn't respond within 20 minutes:
1. Send: "Ei, a sessão de [task] acabou. Conseguiu avançar?"
2. After another 20 min: mark expired via `focus_session_complete(session_id=..., result="sem resposta")`
3. Update daily_summary with `daily_summary_save`

## Procedure: Early Completion

When Lucas says he's done ("terminei", "parei", "concluí", "acabei"):

1. Cancel pending cron jobs: `cronjob(action="remove", job_id="...")`
2. Complete via tool: `focus_session_complete(session_id="...", result="Concluído")`
3. Update daily_summary with `daily_summary_save` — change task status
4. Respond: "Boa. [task] finalizada."

## Procedure: Cancellation

When Lucas says to cancel ("deixa pra lá", "não vou mais", "cancela"):

1. Same as early completion but pass empty result
2. Respond: "OK, [task] cancelada."

## Pitfalls

- **Do NOT read/write focus_sessions.json directly.** Use `focus_session_start` / `focus_session_complete`.
- **Do NOT create focus sessions without duration.** Always ask if not specified.
- **Do NOT interrupt focus sessions with regular check-ins.** The SOUL.md marks focus sessions as "do not interrupt" periods.
- **Cancel cron jobs on early completion.** Stale cron jobs firing after Lucas already finished is confusing.
- **One focus session at a time.** If Lucas declares a new one while one is active, ask if he wants to cancel the current one first.
- **Sync focus_sessions.json with daily_summary.** Every focus session should appear in the daily summary.
