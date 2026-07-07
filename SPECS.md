# Hermes — Accountability Partner v2.5 Spec

---

## Section 1: Functional Specification

### Overview

Hermes is an accountability partner for a developer (Lucas). It operates in two layers:

1. **Live sessions** — on-demand interaction when Lucas initiates a conversation
2. **Scheduled check-ins** — automated prompts at 3 windows during workdays

Version 2 adds six major capabilities on top of v1:

1. **Focus Sessions** — declared periods of concentrated work with dedicated check-ins
2. **Escalation** — mandatory end-of-day status capture with multi-level follow-up
3. **Gamification** — subtle streak and milestone tracking for motivation
4. **ADHD-Specific Features** (v2.3) — re-engagement nudges, intention-of-the-day, unblock helper for task paralysis, nightly preparation
5. **Calendar-Aware Proactive Suggestions** (v2.4) — Google Calendar integration detects free blocks and suggests focus sessions
6. **LLM Wiki Memory** (v2.5) — inspectable Markdown-based long-term memory replacing Hindsight; free web search via SearXNG and web extraction via fastCRW

The assistant does not execute tasks. It monitors, tracks, reminds, and maintains cross-session memory.

---

### 1. User Onboarding

When a new session starts (first interaction of the day), the assistant:

1. Checks for any existing status record from previous days
2. If a record exists, briefly summarizes what was last discussed or worked on
3. If no record exists (e.g., Monday or after a holiday), attempts to find the most recent available record (up to 7 days back) and references it
4. Waits for the user's status update before proceeding

---

### 2. Daily Status Updates

When the user provides a status update (e.g., "I finished task X", "I'm working on Y", "I'm blocked on Z"), the assistant:

1. **Immediately** saves the update to persistent storage

2. Classifies the task into one of four statuses:
   - `em andamento` — actively working
   - `pendente` — planned but not started
   - `em espera` — blocked, dependent on external factor
   - `concluído` — completed
3. Records metadata: task name, status, notes, start date (and completion date if done)
4. Confirms back to the user what was registered (one-line summary)
5. Calculates and includes gamification metrics in the daily summary

The assistant never defers saving. Updates are recorded right away, not at the end of the conversation.

---

### 3. Check-in System (Scheduled Prompts)

Three times per workday (weekdays only), a scheduled job prompts the user:

**Window 1 (morning, 08:30–09:30 BRT):** References the previous day's summary if available. Asks about progress and intent for the day. User uses this summary to remember everything was done the day before to report it on his daily meeting.

**Window 2 (midday, 11:00–12:00 BRT):** References today's summary if it exists. Follows up on stated plans or asks about pending items.

**Window 3 (evening, 16:30–17:30 BRT):** Asks for end-of-day status. If no response was recorded, summarizes what is known and prompts for confirmation.

If the user does not respond to a check-in within the scheduled window, a follow-up is sent after a delay.

#### 3.1 Focus Session Suppression

Regular check-ins (W1, W2, W3) are automatically suppressed when the user is in an active focus session. The focus session's own dedicated check-ins (mid-point and end-of-session) replace them.

---

### 4. Focus Sessions (NEW in v2)

#### 4.1 Declaration

The user declares a focus session using natural language:
- "vou focar em X por 2h"
- "foco na API agora"
- "vou trabalhar na batimetria por 1h30"

If no duration is specified, the assistant asks: "Quanto tempo pretende dedicar?"

#### 4.2 Scheduling

Upon declaration, the assistant:
1. Registers the session in `focus_sessions.json`
2. Creates a cron one-shot for the end-of-session check-in
3. For sessions >60 minutes, creates an additional cron one-shot for a mid-point check-in
4. Confirms naturally: "Focado em [task] até ~[hora]. Te cobro lá."

#### 4.3 Mid-Point Check-In

For sessions >60 minutes, a check-in fires at the halfway mark:
- "Faz 1h. Ainda em [task]?"
- One question, no pressure
- If the user responds, the session continues normally
- If no response, the system does not insist — waits for the end-of-session

#### 4.4 End-of-Session Check-In

When the declared duration expires:
- "Tempo de [task] acabou. Como foi?"
- Opens space for the user to report progress

#### 4.5 Escalation (No Response)

If the user does not respond to the end-of-session check-in:
1. After 20 minutes: "Ei, a sessão de [task] acabou. Conseguiu avançar?"
2. After another 20 minutes: "Preciso fechar o status. [task] estava em andamento. Correto?"
3. Session is marked as `expired` in state

#### 4.6 Early Completion

When the user says "terminei", "parei", "concluí", "acabei":
1. Pending cron jobs (mid-point and end) are cancelled
2. Session is marked as `completed`
3. Daily summary is updated with the result
4. Response: "Boa. [task] finalizada."

#### 4.7 Cancellation

When the user says "deixa pra lá", "não vou mais", "cancela":
1. Same as early completion but status = `cancelled`
2. Daily summary is updated with the cancellation
3. Response: "OK, [task] cancelada."

#### 4.8 Rules

- One focus session active at a time. Declaring a new one while one is active requires confirming cancellation of the current one.
- Regular check-ins are suppressed during active focus sessions.
- The assistant does not interrupt focus sessions proactively — only at scheduled check-in points.
- If the user sends a message during a focus session (voluntarily), the assistant responds normally — the user broke focus by choice.

#### 4.9 Focus Session Retry (NEW in v2.1)

Cron one-shot jobs are fire-and-forget — if the LLM provider returns an error (e.g., 503) at the exact moment the check-in fires, the message is lost. The retry mechanism ensures focus session check-ins are never permanently missed.

**How it works:**
1. The `checkin.py` script (which runs every 5 minutes) monitors active focus sessions
2. For each active session, it checks if mid-point or end check-ins were sent (`midpoint_sent`, `end_sent`)
3. If the scheduled time has passed but the check-in was not sent, it triggers the check-in immediately
4. Retry window: 15 minutes (`FOCUS_RETRY_WINDOW_SEC = 900`) after the scheduled time
5. If after 15 minutes the check-in still wasn't sent, the session is marked as `expired`

**Escalation after retry:**
- If the end-of-session check-in was sent but the user didn't respond, escalation follows the same pattern as W3:
  1. After 15 minutes: "Ei, a sessão de [task] acabou. Conseguiu avançar?"
  2. After another 15 minutes: session marked as `expired`, daily summary updated

**State fields involved:**
- `midpoint_sent: boolean` — whether mid-point check-in was delivered
- `end_sent: boolean` — whether end-of-session check-in was delivered
- `user_responded_midpoint: boolean` — whether user responded to mid-point
- `user_responded_end: boolean` — whether user responded to end
- `escalation_sent: string|null` — escalation level sent ("escalation_1", "escalation_2")

---

### 5. Wake Agent Gate — Silent Skip for `action: "none"` (NEW in v2.2)

#### 5.1 Problem

When `checkin.py` returns `{"action": "none"}` (weekend, holiday, or nothing to do), the cron job still invokes the LLM agent. The agent is supposed to respond `[SILENT]`, but this requires an LLM API call. If the API call fails (e.g., `httpx.ReadError`, network blip, rate limit), the user receives a Telegram notification about the cron job failure — even though nothing was actually wrong with the system. This is noise that erodes trust in the accountability system.

#### 5.2 Solution

The `checkin.py` script now appends `{"wakeAgent": false}` as the last line of stdout whenever action is `"none"`. The Hermes scheduler's `_parse_wake_gate` function checks the last non-empty stdout line: if it parses as JSON with `wakeAgent: false`, the agent invocation is skipped entirely (no LLM call, no Telegram delivery, no error notification).

**Cases that trigger `wakeAgent: false`:**
- `action: "none", reason: "weekend"` — Saturday/Sunday
- `action: "none", reason: "holiday"` — date in `HOLIDAYS` list
- `action: "none", reason: "user_in_focus_session"` — check-in suppressed by active focus session
- `action: "none"` — default (nothing to do this tick)

**Cases that still invoke the agent (no wake gate):**
- `action: "send_checkin"` — LLM delivers the check-in message
- `action: "send_followup"` — LLM delivers follow-up
- `action: "send_escalation"` — LLM delivers escalation
- `action: "generate_daily_summary"` — LLM generates the daily summary
- `action: "generate_weekly_report"` — LLM generates the weekly report
- `action: focus_session_retry` — LLM delivers the retry check-in

#### 5.3 Impact

- **Eliminates all Telegram error notifications** for weekend/holiday/no-op ticks (was 24+ per day on weekends)
- **Reduces LLM API calls** by ~70% on non-working days (no more "[SILENT]" calls)
- **Reduces cron job execution time** from ~2-5s (LLM round-trip) to <100ms (script-only)
- **No behavior change** for active check-ins — they still go through the agent as before

#### 5.4 Example output

When `checkin.py` detects a holiday:
```json
{"action": "none", "reason": "holiday"}
{"wakeAgent": false}
```

The scheduler reads the last line → `{"wakeAgent": false}` → skips agent → no Telegram notification.

---

### 6. Re-engagement Check-in (NEW in v2.3)

#### 6.1 Problem

If Lucas doesn't respond to any check-in all morning, he may go the entire day without reporting. In v2, the first nudge only happened at end-of-day escalation (~17:00 BRT). For someone with ADHD, that's too late — by 15:00, momentum may already be lost.

#### 6.2 Solution

A new re-engagement check-in fires at ~15:00 BRT (18:00 UTC) when NO check-in (W1 or W2) has been responded to during the day. This is checked by the `checkin.py` script.

**Conditions:**
- Time is between 15:00–15:55 BRT
- No window has `user_responded_at` set
- No focus session active
- W3 hasn't fired yet (still in the future)

**Message:**
```
Lucas, ainda não registramos nada hoje. 2 minutos, status rápido? 📝
```

**Tone:** practical, no guilt. Low-friction entry point to get back on track.

**Cron schedule extended:** `*/5 11-15,18-21 * * 1-5` (added 18:00 UTC = 15:00 BRT)

#### 6.3 Suppression

If Lucas has already responded to any check-in or is in an active focus session, re-engagement is suppressed — no need to double-tap.

---

### 7. Intention of the Day (NEW in v2.3)

#### 7.1 Problem

The W1 check-in previously only recapped yesterday. It didn't generate a forward-looking commitment that the system could reference later.

#### 7.2 Solution

The W1 check-in now asks two targeted questions:
1. "Qual a coisa mais importante pra entregar hoje?"
2. "Tem algo burocrático que quer tirar do caminho cedo?"

When Lucas responds, the live agent extracts the main intention and saves it as `intention` in the daily_summary YAML frontmatter. W2 and W3 automatically reference this intention, creating a light accountability thread throughout the day:

W2: "📌 Intenção do dia: Terminar o PR da API"
W3: "📌 Intenção do dia: Terminar o PR da API"

**Rules:**
- One short sentence. Not paragraphs.
- If Lucas doesn't answer the question directly, don't force it — skip.
- The intention is referenced, not weaponized. "Você disse que ia fazer X e não fez" is never the tone.

---

### 8. Unblock Helper — "Só Começa" Mode (NEW in v2.3)

#### 8.1 Problem

ADHD task initiation paralysis: Lucas knows what to do but can't start. The barrier to entry feels overwhelming. Task decomposition requires too much context and effort.

#### 8.2 Solution

A new skill (`unblock-helper`) triggered by natural language:
- "não tô conseguindo começar X"
- "tô travado em Y"
- "procrastinando Z"

**Flow:**
1. Hermes asks ONE question: "Qual o menor passo possível? Só abrir o arquivo? Só ler o ticket?"
2. Lucas names the micro-step
3. Hermes confirms: "Beleza, então o plano é [micro-passo]. Vou te perguntar em 10min como foi. Quer?"
4. If accepted, creates a cron one-shot 10min check-in

This is NOT task decomposition. It's barrier reduction. Lucas already knows the full task — he just needs the first step to feel trivial.

**Rules:**
- One question. No analysis, no suggestions, no "have you tried..."
- Don't prescribe the micro-step. Lucas decides.
- Don't use during active focus sessions.
- Accept "no" gracefully.

---

### 9. Nightly Preparation (NEW in v2.3)

#### 9.1 Problem

Morning decision fatigue hits ADHD hard. If Lucas already knows what to start with when he wakes up, the inertia barrier is lower.

#### 9.2 Solution

The W3 check-in now includes: "Qual vai ser sua primeira tarefa amanhã?"

When Lucas responds, the live agent saves `plans_for_next_day` to **tomorrow's** daily_summary file (creating it if it doesn't exist, with minimal YAML frontmatter).

The next day's W1 automatically references it:
"Ontem você planejou começar com: Revisar o PR da batimetria. Ainda faz sentido?"

**Rules:**
- One short sentence. Not a full task breakdown.
- If Lucas doesn't specify or says "não sei", skip — don't force it.
- The W1 reference is a question, not an obligation. "Ainda faz sentido?" not "Você disse que ia fazer."

---

### 10. Updated Cron Schedule (NEW in v2.3)

The cron schedule was extended to support the re-engagement check-in at 15:00 BRT:

**Old:** `*/5 11-15,19-21 * * 1-5` (UTC)
**New:** `*/5 11-15,18-21 * * 1-5` (UTC)

The 18:00 UTC hour covers 15:00–15:55 BRT, enabling the re-engagement window. All existing check-in windows (W1, W2, W3) remain unchanged.

---

### 11. Task Stale Detection (NEW in v2.1)

#### 11.1 Problem

Tasks can stay in `em andamento` (in progress) for days without updates. The user may forget about them or lose momentum. In v1, stale tasks were only surfaced when the check-in system happened to reference them — there was no proactive detection.

#### 11.2 Solution

The `checkin.py` script now automatically detects tasks that have been in `em andamento` for more than 3 days without an update to the `since` field.

**When it triggers:**
- During the W1 (morning) check-in generation
- Only for tasks with `status: "em andamento"` and `since` older than 3 days

**What it does:**
- Appends a warning section to the W1 check-in message:
  ```
  ⚠️ *Tasks em andamento há mais de 3 dias:*
  • [task name] — desde [date] (N dias)
  Alguma atualização sobre essas?
  ```

**Rules:**
- Only appears in W1 (morning) — not W2 or W3, to avoid nagging
- Subtle, contextual — part of the natural check-in flow
- No negative framing — just a factual reminder
- Threshold configurable via `STALE_THRESHOLD_DAYS` constant (default: 3)

---

### 12. Escalation — End-of-Day Mandatory Capture (NEW in v2)

#### 12.1 Problem

In v1, if the user did not respond to the W3 check-in (16:30–17:30), the system marked `followup_action: "expired"` and generated a summary at 18:30 with whatever it had. There was no escalation — the user could go the entire day without reporting.

#### 12.2 Solution

A multi-level escalation ensures every day has a status capture:

1. **W3 check-in** fires normally (16:30–17:30)
2. **Follow-up** after 20 minutes if no response
3. **Escalation Level 1** after 20 more minutes: "Fim do dia passou. Status rápido?"
4. **Escalation Level 2** after 20 more minutes: generates a tentative summary based on what is known and asks "Baseado no que registrei, seu dia foi: [resumo]. Correto?"

The daily summary at 18:30 always captures whatever was collected — with or without user confirmation.

#### 12.3 Suppression

If the user has already interacted during the day (daily summary exists with real content), escalation is suppressed. The system only escalates when there is genuinely no status for the day.

---

### 13. Cross-Session Memory

The assistant maintains two types of memory:

**Short-term (daily summaries):**
- One file per day, structured as YAML frontmatter + markdown
- Contains: date, free-text summary, task list with status and notes, gamification metrics
- Files are used to reconstruct context for check-ins and future sessions

**Long-term (LLM Wiki):**
- Stores durable facts about the user: preferences, communication style, environment details, projects, recurring conventions
- Persists as Markdown files in `/opt/data/wiki/`
- Agent reads wiki pages at session start for orientation; edits them when new facts emerge
- Fully inspectable and editable by the user
- NOT used for task status or progress (those live in daily summaries)

When the user references something from the past, the assistant retrieves relevant sessions or memory and connects the new conversation to that context — without asking the user to repeat information.

---

### 14. Git Backup for Daily Summaries (NEW in v2.1)

All daily summary files are version-controlled in a local git repository at `/opt/data/.cron/responsibility_partner/.git/`.

**How it works:**
- After every `save_daily_summary_md()` call, the script runs `git add` + `git commit` automatically
- Commit message format: `auto: daily summary YYYY-MM-DD`
- Best-effort: git failures never break the check-in system
- `.gitignore` excludes transient state files (`state.json`, `focus_sessions.json`, `history.jsonl`, `*.tmp`)

**What it provides:**
- Full edit history for every daily summary
- `git diff` to see what changed between versions
- `git checkout` to recover from corruption or accidental edits
- `git log` to review the evolution of task tracking over time

**What is NOT versioned:**
- `state.json` — transient check-in state, changes every 5 minutes
- `focus_sessions.json` — transient focus session state
- `history.jsonl` — append-only log, not useful for versioning

---

### 15. Gamification (NEW in v2)

#### 15.1 Metrics Tracked

Each daily summary includes a `metrics` section in the YAML frontmatter:

```yaml
metrics:
  tasks_completed_today: 2
  focus_sessions_completed: 1
  focus_minutes_total: 120
  checkins_responded: 3
  checkins_total: 3
  current_streak: 5
```

#### 15.2 Streak Calculation

**Streak of days:** consecutive days with a daily summary containing at least 1 task or real summary text. Generic entries like "Sem atividade" do not count.

**Focus streak:** consecutive days with at least 1 focus session completed.

#### 15.3 Milestones

Milestones are commented on subtly (1 line) by the assistant when relevant:

| Milestone | When to comment |
|-----------|-----------------|
| 3 consecutive days | Next morning check-in |
| 5 consecutive days | Next morning check-in |
| 1 week | Weekly report |
| 10 tasks completed (total) | When the 10th is marked done |
| First focus session ever | At declaration time |

#### 15.4 Rules

- Only mention milestones once (first time reached)
- Never mention streak breaks or negative trends
- Read the room — if the user seems stressed, skip the comment
- One line, no fanfare: "3 dias seguidos de atualização. Consistência."
- No emojis in milestone messages

---

### 16. Communication Style

The assistant communicates in Portuguese (Brazil), with the following characteristics:

- **Concise:** Short, direct responses. One-line answers when possible.
- **Warm but dry:** Sincere acknowledgment without being effusive. One genuine "good work" is worth more than three paragraphs of cheerleading.
- **Direct:** If something is blocked, it says so. If a plan is vague, it asks for clarification.
- **Contextual:** Always connects to what was previously discussed. Never asks the user to repeat something already shared.

**What it does NOT do:**
- Execute tasks on behalf of the user
- Give moral advice or self-help
- Suggest actions — it monitors and follows up, does not prescribe
- Use generic questions like "how can I help?" — it asks specific, contextual questions
- Spam emojis

---

### 17. Session Close

When a conversation ends (or the user goes silent), the assistant:

1. Saves any status updates that were shared during the session
2. Summarizes in one line what was recorded and confirms it with the user
3. If the conversation was interrupted (e.g., by an error or side discussion), explicitly asks for a status update before closing: "To confirm, your status is X. Any updates since then?"

---

### 18. Handling Infrastructure Issues

When the assistant encounters its own infrastructure issues (cron failures, memory provider errors, rate limits), it handles them without involving the user. These are internal problems. The user is never told about backend failures unless they directly impact the user's experience (e.g., a check-in not arriving).

Before closing the conversation, the assistant ensures it has an accurate, up-to-date record of the user's status. Infrastructure issues never take priority over capturing the user's state.

---

### 19. Accountability Logic

The assistant operates on a simple principle: **nothing falls through the cracks**.

- Tasks that are started are tracked until they are done or explicitly cancelled
- If a task has been in `em andamento` for multiple days without update, the check-in system flags it
- If the user mentions a blocker, it is recorded and followed up on in the next check-in
- If the user goes quiet, the system detects the silence and prompts for a status check
- Focus sessions are tracked until completion, cancellation, or expiry
- End-of-day escalation ensures no day goes without a status capture

---

### 20. Proactive Focus Suggestions via Google Calendar (NEW in v2.4)

#### 20.1 Problem

With ADHD, Lucas often has free time blocks between meetings but doesn't realize it — or doesn't think to declare a focus session proactively. The system had no awareness of his calendar availability.

#### 20.2 Solution

The `checkin.py` script now integrates with Google Calendar via a service account (read-only). It detects free blocks ≥ 60 minutes between 09h–18h BRT and proactively suggests focus sessions.

**How it works:**
1. `checkin.py` calls Google Calendar API every 5 minutes
2. `get_free_windows()` calculates unoccupied blocks between 09h–18h BRT
3. `check_proactive_suggestion()` triggers if:
   - A free window starts in the next 15 minutes
   - No active focus session
   - User hasn't responded to any check-in today
   - Cooldown of 1 hour since last suggestion
4. Output: `action: "suggest_focus"` with message like: "Tem 90min livres até 15h. Sugestão: [tarefa pendente]. Quer focar?"

**Dependencies:**
- `google-auth` and `google-api-python-client` libraries in the container
- Service account JSON at `/opt/data/google-service-account.json`
- Environment variables: `GOOGLE_SERVICE_ACCOUNT_PATH`, `GOOGLE_CALENDAR_ID`

**Fallback:** If Google libs are not installed or service account is missing, integration fails silently — regular check-ins continue normally.

**Rules:**
- Suggests max 1x per hour (cooldown)
- Does not suggest during active focus sessions
- Does not suggest if user already responded to any check-in today
- Only between 09h–18h BRT
- Minimum free block: 60 minutes
- The suggestion is an invitation, not a demand. If Lucas says no, life goes on.

**New state field:** `proactive_suggestion_last` (epoch) — tracks cooldown between suggestions.

**New cron action:** `suggest_focus` — delivers the proactive message to Telegram, suppressed if user already interacted today.

**New environment variables:**
| Variable | Purpose |
|---|---|
| `GOOGLE_SERVICE_ACCOUNT_PATH` | Path to service account JSON key (default: `/opt/data/google-service-account.json`) |
| `GOOGLE_CALENDAR_ID` | Email of the calendar to query (e.g., `lucasaugusto096@gmail.com`) |

---

### 21. LLM Wiki — Inspectable Long-Term Memory (NEW in v2.5)

#### 21.1 Problem

In v2.4, the system used Hindsight for long-term memory — durable facts about the user, preferences, environment, and projects. Hindsight is an agent memory API backed by embedded PostgreSQL with its own LLM costs per operation. For ~30 durable facts, it was overkill: each retention, recall, and consolidation operation cost LLM API credits, the daemon had an idle timeout (300s) that shutdown the service, and rate limits on the LLM model broke the entire memory layer. The facts were not inspectable — only accessible via API.

#### 21.2 Solution

The Hermes built-in `llm-wiki` skill replaces Hindsight as the long-term memory system.

**What it is:** A directory of interlinked Markdown files (`/opt/data/wiki/`) following the Karpathy LLM Wiki pattern. The wiki stores durable facts about Lucas — preferences, environment, projects, conventions — in human-readable, git-backable files.

**How it works:**
1. `WIKI_PATH=/opt/data/wiki` is set as an environment variable in docker-compose
2. The wiki is initialized with `SCHEMA.md`, `index.md`, `log.md`, and entity/concept pages
3. At session start, the agent reads `SCHEMA.md`, `index.md`, and `entities/lucas.md` to orient itself
4. When new durable facts are discovered, the agent edits or creates wiki pages using `edit_file`/`write_file`
5. `session_search` and the wiki together provide cross-session context

**Wiki structure:**
```
/opt/data/wiki/
├── SCHEMA.md                     # conventions, tag taxonomy, page thresholds
├── index.md                      # catalog of all pages
├── log.md                        # append-only action log
├── entities/
│   └── lucas.md                  # profile, ADHD, work context
├── concepts/
│   ├── communication-preferences.md
│   ├── environment.md            # providers, models, tools
│   └── projects.md               # work projects, repositories
├── comparisons/
├── queries/
└── raw/                          # immutable source material
```

**Advantages over Hindsight:**
- Zero LLM cost for memory operations — the wiki IS the memory
- No idle timeout, no daemon to manage, no PostgreSQL
- Fully inspectable and editable by Lucas in any text editor
- Survives restarts without re-initialization
- Git-backable (can be added to the hermes-config repo)

**What does NOT change:**
- Daily summaries continue as the task/progress record
- Focus sessions continue in `focus_sessions.json`
- The accountability check-in system is unchanged

---

## Section 2: Technical Implementation

### Architecture Overview

Hermes is implemented as a containerized agent (Hermes Agent) running on Docker. It operates in two modes:

1. **Live agent** — handles on-demand conversations with the user
2. **Cron agent** — runs scheduled jobs (check-ins, focus session check-ins) in isolated sessions

The system relies on seven core components working together.

---

### Component 1: Daily Summary Storage

**What it is:** A folder of daily files, one per day, stored on the host filesystem. Each file is a structured document (YAML frontmatter + markdown) containing date, free-text summary, task list with status and notes, and gamification metrics.

**How it works:**
- File naming follows a deterministic pattern: `daily_summary_YYYY-MM-DD.md`
- The cron agent writes to these files at end-of-day; the live agent writes during conversation
- Files are the source of truth for task status and daily progress
- They are also read by the check-in system to personalize prompts
- Search across files is done by direct file access (no database)

**YAML Frontmatter Schema:**
```yaml
---
date: 'YYYY-MM-DD'
summary_text: 'Free-text summary of the day'
context: 'Project or context notes'
plans_for_next_day: 'Plans for tomorrow'
tasks:
- id: task-id
  name: Task description
  status: em andamento|pendente|em espera|concluído
  notes: 'Latest notes'
  since: 'YYYY-MM-DD'
  completed: 'YYYY-MM-DD'  # only for concluído
metrics:
  tasks_completed_today: 0
  focus_sessions_completed: 0
  focus_minutes_total: 0
  checkins_responded: 0
  checkins_total: 0
  current_streak: 0
---
```

**Paths:**
- Canonical: `/opt/data/.cron/responsibility_partner/daily_summary_YYYY-MM-DD.md`
- Note: `~` resolves differently for cron agent (`/opt/data`) vs main agent (`/opt/data/home`). Always use absolute paths.

---

### Component 2: Check-in Scheduler

**What it is:** A Python script (`checkin.py`, v5) that runs every 5 minutes via cron. It determines whether a check-in, follow-up, escalation, or summary should be sent.

**How it works:**
- Three fixed windows per weekday (morning, midday, evening) in BRT timezone
- State is tracked in a `state.json` file
- The script outputs a structured action that the cron agent processes

**Actions:**
- `send_checkin` — deliver check-in message (immutable, from script)
- `send_followup` — deliver follow-up for unanswered check-in
- `send_escalation` — deliver escalation for unanswered W3 (NEW in v2)
- `send_reengagement` — deliver re-engagement message at ~15h BRT (NEW in v2.3)
- `suggest_focus` — suggest focus session based on calendar free blocks (NEW in v2.4)
- `generate_daily_summary` — generate end-of-day summary with metrics
- `generate_weekly_report` — generate weekly report
- `focus_session_checkin` — deliver focus session retry check-in
- `none` — silent, no action needed

**Windows (BRT):**
| Window | Time Range | Purpose |
|--------|-----------|---------|
| W1 | 08:30–09:30 | Morning: recap of yesterday, plans for today |
| W2 | 11:00–12:00 | Midday: progress check on stated plans |
| W3 | 16:30–17:30 | Evening: end-of-day status capture |

**Timing Constants:**
- `CHECKIN_WINDOW_SEC = 600` (10 min) — at least 2x the cron interval
- `FOLLOWUP_DELAY_SEC = 1200` (20 min) — wait before follow-up
- `FOLLOWUP_WINDOW_SEC = 300` (5 min) — window to send follow-up
- `ESCALATION_DELAY_SEC = 1200` (20 min) — wait before next escalation level

**Escalation Flow (W3 only):**
```
W3 check-in → no response → 20min → follow-up → no response → 20min → escalation_1 → no response → 20min → escalation_2 (tentative summary)
```

**Focus Session Awareness:**
- Before sending a regular check-in, the script checks if the user is in an active focus session
- If yes, the check-in is suppressed (`action: "none"`, `reason: "user_in_focus_session"`)
- Focus sessions have their own dedicated check-ins via cron one-shot jobs

**State File (`state.json`):**
```json
{
  "date": "YYYY-MM-DD",
  "windows": {
    "1": {
      "scheduled_epoch": 1717514400,
      "checkin_sent_at": null,
      "user_responded_at": null,
      "followup_action": null,
      "followup_sent_at": null,
      "escalation_sent": null,
      "marker": "RESP-W1-YYYY-MM-DD-NNNN"
    }
  },
  "weekly_report_sent": {},
  "proactive_suggestion_last": null
}
```

**Copies (must stay synchronized):**
1. `/opt/data/scripts/checkin.py` — used by cron via `script:` parameter
2. `/opt/data/home/scripts/checkin.py` — legacy mirror
3. `/opt/data/home/.cron/responsibility_partner/checkin.py` — legacy mirror

Verify synchronization with `md5sum` after any edit.

---

### Component 3: Focus Session Manager

**What it is:** A JSON-based state file plus a Hermes skill that manages focus sessions — declared periods of concentrated work with dedicated check-ins.

**State File (`focus_sessions.json`):**
Located at `/opt/data/.cron/responsibility_partner/focus_sessions.json`.

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

**How it works:**
1. Live agent detects focus intent from natural language
2. Creates entry in `focus_sessions.json`
3. Creates cron one-shot job(s) via `cronjob(action="create", schedule="<duration>m")`
4. For sessions >60min: mid-point cron at half duration + end cron at full duration
5. For sessions ≤60min: end cron only
6. Cron job fires → delivers check-in to Telegram
7. Escalation if no response (same pattern as W3)

**Skill:** `focus-session-handler` at `/opt/data/skills/productivity/focus-session-handler/SKILL.md`

**Rules:**
- One focus session active at a time
- Regular check-ins suppressed during active focus session
- Early completion cancels pending cron jobs
- Focus sessions are recorded in the daily summary

---

### Component 4: Long-Term Memory (LLM Wiki)

**What it is:** An LLM Wiki — a directory of interlinked Markdown files at `/opt/data/wiki/` following the Karpathy LLM Wiki pattern. Replaces Hindsight as of v2.5.

**How it works:**
- The wiki stores durable facts about the user: preferences, communication style, environment details, project information, recurring conventions
- At session start, the agent reads `SCHEMA.md`, `index.md`, and relevant entity/concept pages to orient itself
- New facts are stored by creating or editing Markdown pages via `edit_file`/`write_file`
- The wiki is powered by the Hermes built-in `llm-wiki` skill (v2.1.0)
- Path: `/opt/data/wiki/` (configurable via `WIKI_PATH` env var)

**Advantages over Hindsight (removed in v2.5):**
- Zero LLM cost for memory operations
- No daemon to manage (no idle timeout, no PostgreSQL)
- Fully inspectable and editable by the user
- Survives restarts without re-initialization
- Git-backable

**Note:** Hindsight was previously configured in `local_embedded` mode with PostgreSQL. All hindsight data (profiles, logs, config, embedded PostgreSQL) was removed in v2.5.

---

### Component 5: Live Session Handler

**What it is:** The primary interface — a stateless LLM agent that receives user messages, reads relevant context from daily summaries and memory, updates records, and responds.

**How it works:**
- At the start of a conversation, the agent reads the daily summary for today (if it exists) and the previous day, plus `focus_sessions.json`
- During the conversation, it updates the daily summary immediately when the user provides status information
- Focus session declarations are handled by the `focus-session-handler` skill
- At the end, it confirms what was recorded
- Task status uses four categories (em andamento, pendente, em espera, concluído)

**Skills used:**
- `daily-status-session` (v2.1.0) — optimized flow for status updates, parallel tool calls
- `focus-session-handler` (v1.0.0) — focus session lifecycle management
- `unblock-helper` (v1.0.0) — task initiation paralysis micro-step reduction (NEW in v2.3)
- `llm-wiki` (v2.1.0) — inspectable Markdown-based long-term memory (NEW in v2.5)

---

### Component 6: Web Search (SearXNG)

**What it is:** A self-hosted, privacy-respecting metasearch engine that aggregates results from 70+ search engines. Free, no API key required.

**Container:** `searxng-core` (docker.io/searxng/searxng:latest)
**Port:** 8080 (internal, on hermes-net)
**Config:** `./searxng/core-config/settings.yml` — JSON format enabled for Hermes compatibility
**Cache:** `searxng-valkey` (valkey/valkey:9-alpine) — Redis-compatible cache

Hermes accesses SearXNG via `SEARXNG_URL=http://searxng-core:8080`. The `web_search` tool is configured with `web.search_backend: "searxng"` in config.yaml.

Added in v2.4, fully operational in v2.5.

---

### Component 7: Web Extract & Crawl (fastCRW)

**What it is:** A Rust-native, single-binary web scraper and crawler (`us/crw`) that implements a Firecrawl-compatible API at `/firecrawl/v2/*`. ~50 MB RAM, sub-second cold start.

**Container:** `crw` (ghcr.io/us/crw:latest)
**Port:** 3000 (internal, on hermes-net)
**JS Renderer:** `lightpanda` (lightpanda/browser:latest) — lightweight headless browser for JavaScript-heavy pages, ~64 MB RAM

Hermes accesses fastCRW via `FIRECRAWL_API_URL=http://crw:3000`. The `web_extract` and `web_crawl` tools are configured with `web.extract_backend: "firecrawl"` in config.yaml.

fastCRW handles scraping and crawling. Web search is handled by SearXNG (Component 6). Together they provide a complete, free, self-hosted web toolkit for Hermes.

Added in v2.5.

---

### Data Flow

```
[USER] ──message──> [LIVE AGENT]
                       │
                       ├── reads ──> [DAILY SUMMARY (today + previous)]
                       │
                       ├── reads ──> [FOCUS SESSIONS JSON]
                       │
                       ├── reads ──> [HINDSIGHT (user profile, long-term facts)]
                       │
                       ├── writes ──> [DAILY SUMMARY]
                       │
                       ├── writes ──> [FOCUS SESSIONS JSON]
                       │
                       ├── creates ──> [CRON ONE-SHOT (focus session)]
                       │
                       └── response ──> [USER]

[CRON SCHEDULER] ──fires──> [CHECKIN.PY]
                                │
                                ├── reads ──> [STATE.JSON]
                                │
                                ├── reads ──> [DAILY SUMMARY (today)]
                                │
                                ├── reads ──> [FOCUS SESSIONS JSON]
                                │
                                └── action: [SEND CHECKIN | FOLLOW-UP | ESCALATION | SILENT | GENERATE SUMMARY]
                                              │
                                              └──> [CRON AGENT] ──delivers──> [USER]

[CRON SCHEDULER] ──fires──> [FOCUS SESSION ONE-SHOT]
                                │
                                └──> [CRON AGENT] ──delivers──> [USER]
```

---

### Key Technical Characteristics

1. **Two-agent model** — live agent (user-initiated) and cron agent (scheduled, isolated). Cron runs in clean sessions with no prior context except what's injected by the check-in script.

2. **File-based state** — no database for daily summaries or focus sessions. Plain files with structured format. Simple, durable, human-readable.

3. **Stateless live agent** — each conversation starts fresh, reading from daily summaries, focus sessions, and memory to reconstruct context. No session state persisted between conversations.

4. **Deterministic context retrieval** — daily summary path is always derived from the date, never searched. Session search is used for historical context retrieval only.

5. **Immutable check-in messages** — the check-in script generates the message; the cron agent delivers it verbatim. The live agent does not modify or rewrite check-in content.

6. **Fail-safe suppression** — the system defaults to silence (no message) when uncertain. If the user has updated today, no check-in is sent. Duplicate prompts are more disruptive than missed prompts.

7. **Focus session isolation** — regular check-ins are suppressed during active focus sessions. Focus sessions have their own dedicated check-in mechanism via cron one-shot jobs.

8. **Mandatory end-of-day capture** — escalation ensures no workday goes without a status capture, even if the user does not respond to any check-in.

---

### Hermes Agent Configuration

**Container:** `hermes` (nousresearch/hermes-agent)
**Volume mount:** `~/.hermes` → `/opt/data`
**Model:** minimax-m2.7 via opencode-go
**Platform:** Telegram only
**Cron schedule:** `*/5 11-15,18-21 * * 1-5` (UTC) = `*/5 08-12,16-18 * * 1-5` (BRT)
**Memory provider:** Hindsight (local_embedded)
**SOUL.md:** `/opt/data/SOUL.md`

**Cron Jobs:**
| Job | Schedule | Purpose |
|-----|----------|---------|
| `c9e31c8f7b6a` | `*/5 11-15,18-21 * * 1-5` | Daily check-ins (W1, W2, W3) + escalation + re-engagement + proactive focus suggestions |
| `c102a47935ce` | `0 21 * * 5` | Weekly report (Friday 18h BRT) |
| Focus session one-shots | Dynamic | Created per focus session declaration |

**Toolsets enabled for cron:**
- `file` — read/write daily summaries and state files
- `session_search` — search past sessions for context
- `send_message` — deliver messages to Telegram
- `web` — web search if needed

**Additional containers (docker-compose):**
| Container | Image | Purpose |
|-----------|-------|---------|
| `searxng-core` | searxng/searxng:latest | Web search engine (SearXNG) |
| `searxng-valkey` | valkey/valkey:9-alpine | Cache for SearXNG |
| `crw` | ghcr.io/us/crw:latest | Web extract & crawl (fastCRW) |
| `lightpanda` | lightpanda/browser:latest | JS renderer for fastCRW |

---

### What's Working (v2.5)

- Daily status capture with immediate persistence
- 3x/day scheduled check-ins with follow-up logic
- Re-engagement check-in (~15h BRT) when no check-in was responded to during the day
- W1 turbo with intention-of-the-day capture and forward referencing in W2/W3
- Unblock helper skill for ADHD task initiation paralysis
- Nightly preparation — save first task for tomorrow, reference in next day's W1
- Proactive focus suggestions via Google Calendar — detects free blocks ≥60 min and suggests focus sessions
- **LLM Wiki — inspectable Markdown-based long-term memory (replaces Hindsight)**
- **Self-hosted web search via SearXNG (free, no API keys)**
- **Self-hosted web extraction via fastCRW / crw (free, Firecrawl-compatible, ~50 MB RAM)**
- Cross-session memory via session_search + LLM Wiki
- Suppression of duplicate check-ins when user has already provided status
- File-based state that survives restarts
- Focus sessions with mid-point and end-of-session check-ins
- Focus session retry via checkin.py polling (5min guarantee)
- Escalation for end-of-day mandatory status capture
- Task stale detection (>3 days without update)
- Gamification metrics in daily summaries
- Focus session awareness in regular check-ins
- Git backup for daily summary versioning
- Wake Agent gate — silent skip for `action: "none"` (no LLM call on weekends/holidays/no-op)
- Extended cron schedule for re-engagement and proactive suggestions

### Known Limitations

- Long-term memory (LLM Wiki) depends on the agent following the `llm-wiki` skill conventions — quality varies with the model's adherence to skill instructions
- Cron sessions take ~10 minutes to become searchable after execution
- Check-in suppression logic depends on a daily summary file existing for today — if the user provides a status verbally in the check-in window (without opening the app), it may not be captured
- The check-in system does not track task-level progress — only status categories and free-text notes
- Focus sessions are limited to one active session at a time
- Gamification streaks are basic (consecutive days) — no weighted scoring or category-specific streaks
- Git backup is best-effort — if git fails silently, no alert is raised
- fastCRW (crw) uses LightPanda for JS rendering; complex anti-bot pages may require the optional Chrome tier (not included due to resource constraints)

---

### Files Modified

| File | Action | Description |
|------|--------|-------------|
| `/opt/data/SOUL.md` | Updated | v2.3 — Re-engagement, Intention, Unblock Helper, Nightly Prep. v2.4 — Sugestões Proativas. v2.5 — LLM Wiki substitui Hindsight |
| `/opt/data/skills/productivity/focus-session-handler/SKILL.md` | Created | Focus session lifecycle management skill |
| `/opt/data/skills/productivity/daily-status-session/SKILL.md` | Updated | v2.3 — intention extraction, nightly prep, unblock detection. v2.5 — LLM Wiki orientation on session start |
| `/opt/data/skills/productivity/unblock-helper/SKILL.md` | Created (v2.3) | Task initiation paralysis — micro-step barrier reduction |
| `/opt/data/skills/research/llm-wiki/SKILL.md` | Enabled (v2.5) | Inspectable Markdown long-term memory (built-in Hermes skill) |
| `/opt/data/wiki/` | Created (v2.5) | LLM Wiki directory — entities, concepts, schema |
| `/opt/data/.hindsight/` | Removed (v2.5) | Hindsight data, config, and embedded PostgreSQL deleted |
| `/opt/data/scripts/checkin.py` | Updated | v5 — retry, stale detection, git backup, escalation. v2.2 — wakeAgent gate. v2.3 — re-engagement, W1 intention, W2/W3 context, nightly prep. v2.4 — Google Calendar proactive suggestions |
| `/opt/data/cron/jobs.json` | Updated | v2.3 — send_reengagement. v2.4 — suggest_focus, extended schedule |
| `/opt/data/config.yaml` | Updated (v2.4-v2.5) | Web backends (searxng + firecrawl), auxiliary vision model, WIKI_PATH |
| `docker-compose.yaml` | Updated | v2.4 — GOOGLE env vars. v2.5 — searxng-core, searxng-valkey, crw, lightpanda, WIKI_PATH, SEARXNG_URL, FIRECRAWL_API_URL |
| `deploy.sh` | Created (v2.3) | Automated deployment script |
| `searxng/core-config/settings.yml` | Created (v2.5) | SearXNG configuration with JSON format enabled |
| `.env.example` | Updated (v2.5) | Added GOOGLE_SERVICE_ACCOUNT_PATH, GOOGLE_CALENDAR_ID, FIRECRAWL_API_URL |

---

## Future Improvements

The following improvements were identified during the v2 design process. They are not yet implemented but represent potential areas for future development.

### High Priority

1. **Streak with Trend Analysis** — Beyond the current streak counter, calculate whether the user's engagement is improving, stable, or declining (comparison with previous week's average). Useful for the weekly report.

2. **Weekly Pattern Report** — Analyze daily summaries from the past week and identify:
   - Most productive hours (based on when tasks are marked done)
   - Distraction frequency (tasks started but not completed)
   - Tasks that never get started (always "pendente")
   - Average focus session duration and completion rate

### Medium Priority

3. **Multiple Focus Sessions** — Support more than one active focus session at a time, with naming to differentiate. Useful for days with distinct work blocks.

4. **Automatic Daily Summary Backup Verification** — Periodic check that git repo is healthy and all daily summaries are committed. Alert if backup is stale.

5. **Task Progress Tracking** — Beyond status categories, track percentage completion or subtask breakdown. Useful for large tasks that span multiple days.

### Low Priority

6. **Voice Check-in** — Use Hermes TTS (Edge TTS, free) to deliver check-ins as voice messages on Telegram. More natural for quick status updates.

7. **Dashboard Web** — Visual dashboard with streaks, productivity graphs, focus session history. Hermes has a built-in web dashboard feature.

8. **Jira Integration** — Sync work tasks from Jira with daily summaries. Requires Jira API access (not currently available).

9. **ML-based Distraction Prediction** — Use historical patterns to predict when the user is likely to get distracted and intervene proactively. Requires significant data accumulation first.

---

*Document version: 2.5 — based on Hermes Accountability Partner v2.5 implementation for Lucas Alcantara.*
*Date: 2026-07-07*
