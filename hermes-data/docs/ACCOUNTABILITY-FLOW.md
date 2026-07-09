# Accountability Assistant — Flow & Architecture

> Last updated: 2026-07-09 · Version 2.6

This document describes the complete behavior of the Hermes accountability system — the cron-based check-in engine (`checkin.py`), the live agent skills, the state machine per check-in window, follow-up & escalation logic, focus session tracking, and proactive calendar-based suggestions.

---

## 1. Cron Schedule & Check-in Windows

```mermaid
gantt
    title Cron Windows (BRT timezone, Monday–Friday)
    dateFormat  HH:mm
    axisFormat %H:%M

    section Cron active (UTC)
    Cron ticks every 5min :cron, 08:00, 12:00
    Cron ticks every 5min :cron2, 15:00, 18:00

    section Check-in Windows
    W1 Morning    :w1, 09:00, 09:10
    W2 Midday     :w2, 11:30, 11:40
    W3 End of day :w3, 17:00, 17:10

    section Secondary Cron Features
    Proactive Focus (09-18h) :pf, 09:00, 18:00
    Re-engagement (~15h BRT) :re, 15:00, 15:01
    Daily Summary (18:30)    :ds, after w3, 18:30
    Weekly Report (Fri 18:00):wr, after w3, 18:00
```

### Window Timing Constants

| Constant | Value | Meaning |
|---|---|---|
| `CHECKIN_WINDOW_SEC` | 600s (10 min) | How long after `scheduled_epoch` the check-in can be sent |
| `FOLLOWUP_DELAY_SEC` | 1200s (20 min) | Wait time before follow-up fires |
| `FOLLOWUP_WINDOW_SEC` | 300s (5 min) | Window in which follow-up can be sent |
| `ESCALATION_DELAY_SEC` | 1200s (20 min) | Wait after follow-up for escalation |
| `FOCUS_RETRY_WINDOW_SEC` | 900s (15 min) | Retry window for focus session check-ins |
| `PROACTIVE_COOLDOWN_SEC` | 3600s (1h) | Cooldown between proactive focus suggestions |

### Check-in Window Definitions

```python
WINDOWS = {
    1: (9, 0, 9, 30),      # W1: 09:00–09:30 BRT
    2: (11, 30, 12, 0),    # W2: 11:30–12:00 BRT
    3: (17, 0, 17, 45),    # W3: 17:00–17:45 BRT
}
```

Each window has a `scheduled_epoch` randomly picked within this range. The check-in can be sent any time `scheduled <= now < scheduled + CHECKIN_WINDOW_SEC` (10-minute window).

---

## 2. Window State Machine

Each check-in window (W1, W2, W3) goes through a finite state machine. The state is persisted in `state.json`.

```mermaid
stateDiagram-v2
    [*] --> Scheduled : rollover (new day)

    Scheduled --> Sent : scheduled <= now < scheduled + 10min
    note: Emits `send_checkin` action

    Sent --> AutoFilled : daily_summary.mtime > sent_at
    note: Lucas responded → filled respond_at

    Sent --> FollowupSent : now >= sent_at + 20min
    note: Emits `send_followup` action

    FollowupSent --> AutoFilled : daily_summary.mtime > sent_at
    note: Lucas responded after follow-up

    FollowupSent --> FollowupExpired : now >= followup_start + 5min
    note: Follow-up window passed

    FollowupExpired --> Escalation1 : W3 only, now >= followup_expiry + 20min
    note: Emits `send_escalation` action

    Escalation1 --> Escalation2 : now >= escalation1 + 5min
    note: Emits `send_escalation` (tentative summary)

    AutoFilled : [*] No further action (responded)

    state Escalation2 {
        Final --> [*] : No more escalations
    }
```

### State Fields (per window in `state.json`)

| Field | Type | Description |
|---|---|---|
| `scheduled_epoch` | int | When the check-in is randomly scheduled |
| `checkin_sent_at` | int or null | Epoch when the check-in message was delivered |
| `user_responded_at` | int or null | Epoch when the user was detected as having responded |
| `followup_action` | null / "sent" / "skipped" / "expired" | Follow-up status |
| `followup_sent_at` | int or null | Epoch when follow-up was delivered |
| `escalation_sent` | null / "escalation_1" / "escalation_2" | Escalation stage (W3 only) |
| `marker` | string | Unique response token for tracking |

---

## 3. Auto-fill Mechanism (responded_at detection)

The `user_responded_at` field is filled by `checkin.py` **after the fact** — it infers that Lucas responded by checking if `daily_summary.md` for today was modified AFTER the check-in was sent.

```mermaid
sequenceDiagram
    participant cron as Cron (checkin.py)
    participant state as state.json
    participant ds as daily_summary.md
    participant live as Live Agent

    cron->>state: W2: checkin_sent_at = 11:35
    Note over cron: Emits `send_checkin`
    
    live->>ds: Lucas responds at 11:37<br/>Save daily_summary.md (mtime=11:37)
    
    cron->>state: Next tick (11:40): W2 sent_at=11:35, responded_at=null
    cron->>ds: Check daily_summary.md mtime
    Note over cron,ds: mtime 11:37 > sent_at 11:35? → YES
    cron->>state: W2: user_responded_at = 11:40
    Note over cron: Returns `action: none`<br/>Follow-up SUPPRESSED
```

### Anti-pattern (why mtime comparison is needed)

```
Scenario: Lucas responded to W1 at 09:00, but ignored W2
  daily_summary.md mtime = 09:00 (from W1 response)
  
  ❌ Without mtime check: "daily_summary exists → mark W2 as responded"
     → W2 follow-up NEVER fires → Lucas never held accountable for W2
  
  ✅ With mtime check: "mtime 09:00 < W2.sent_at 11:35 → Lucas did NOT respond to W2"
     → Auto-fill skipped → Follow-up fires → Lucas held accountable
```

---

## 4. Follow-up & Escalation Timeline

```mermaid
sequenceDiagram
    participant cron as Cron
    participant state as state.json
    participant tg as Telegram

    Note over cron: Window 3 example
    cron->>tg: W3 check-in sent (17:10)
    cron->>state: W3: checkin_sent_at = 17:10

    Note over cron: +20 minutes (FOLLOWUP_DELAY_SEC)
    cron->>tg: Follow-up sent (17:30)
    cron->>state: W3: followup_action = "sent"

    Note over cron: +5 minutes (FOLLOWUP_WINDOW_SEC)
    cron->>state: W3: followup_action = "expired"

    Note over cron: +20 minutes (ESCALATION_DELAY_SEC)
    cron->>tg: ⚠️ Escalation 1: "Como foi o dia?" (17:55)
    cron->>state: W3: escalation_sent = "escalation_1"

    Note over cron: +5 minutes
    cron->>tg: ⚠️ Escalation 2: tentative summary (18:00)
    cron->>state: W3: escalation_sent = "escalation_2"
```

### Follow-up Window Summary

| Step | Trigger | Action |
|---|---|---|
| Check-in | `scheduled <= now < scheduled + 10min` | `send_checkin` + set `checkin_sent_at` |
| Follow-up | `now >= sent_at + 20min` AND `window < 5min` | `send_followup` + set `followup_action = "sent"` |
| Follow-up expiry | `now >= followup_start + 5min` | Set `followup_action = "expired"` |
| Escalation 1 (W3 only) | `now >= followup_expiry + 20min` | `send_escalation` (polite) |
| Escalation 2 (W3 only) | `now >= escalation1 + 5min` | `send_escalation` (tentative summary) |

---

## 5. Live Agent Interactions

When Lucas responds to a check-in, the **daily-status-session** skill activates.

```mermaid
flowchart TD
    A[Lucas responds to check-in] --> B{Keywords?}
    
    B -->|bom dia, progress, tasks| C[daily-status-session]
    B -->|foco, vou focar| D[focus-session-handler]
    B -->|tô travado, procrastinando| E[unblock-helper]
    
    C --> C1[Read last daily_summary<br/>+ focus_sessions.json<br/>+ LLM Wiki index.md]
    C1 --> C2[Extract intention<br/>from W1 response]
    C2 --> C3[Save daily_summary_YMD.md<br/>with YAML frontmatter]
    C3 --> C4[Respond with context]
    
    D --> D1[Parse task + duration]
    D1 --> D2[Create focus session in<br/>focus_sessions.json]
    D2 --> D3[Schedule midpoint + end<br/>cron one-shot jobs]
    D3 --> D4[Respond with session<br/>started confirmation]
    
    E --> E1[Ask: Qual o menor<br/>passo possível?]
    E1 --> E2[Offer 10-min check-in]
```

### What the skill saves in `daily_summary`

```yaml
---
date: '2026-07-09'
summary_text: 'Atuando na otimização de queries do Oracle'
intention: 'Concluir remoção de duplicação de memória nos fetchs'
tasks:
  - name: 'Remover duplicação de memória nos fetchs do oracle'
    status: em andamento
  - name: 'Executar benchmarks comparativos'
    status: pendente
plans_for_next_day: 'Primeira task: analisar resultados do benchmark'
---
```

---

## 6. Focus Sessions

```mermaid
stateDiagram-v2
    [*] --> Active : Lucas declares focus

    state Active {
        [*] --> InProgress : started_at
        InProgress --> MidpointSent : midpoint cron fires
        MidpointSent --> EndSent : end cron fires
    }

    Active --> Completed : Lucas reports done early<br/>(user_responded_end = true)
    
    MidpointSent --> MidpointRetry : 15min after midpoint<br/>user did not respond
    MidpointRetry --> MidpointExpired : 15min after retry<br/>still no response
    
    EndSent --> EndRetry : 15min after end<br/>user did not respond  
    EndRetry --> EndExpired : 15min after retry<br/>still no response
    
    Active --> Cancelled : Lucas says "parei"
    EndExpired --> [*] : Session logged as expired
    Completed --> [*] : Session logged as completed
```

### Focus Session Lifecycle

| Phase | Trigger | Action |
|---|---|---|
| **Declare** | Lucas: "vou focar em X por 2h" | Create entry in `focus_sessions.json` |
| **Midpoint** | Cron job at start + duration/2 | Ask: "Ainda focado? Como está?" |
| **End** | Cron job at start + duration | Ask: "Terminou? Quer marcar como concluído?" |
| **Retry** | No response + 15min | Re-send check-in |
| **Expire** | No response + 30min | Mark session expired, escalate |
| **Complete early** | Lucas: "terminei" | Mark completed, update daily_summary |

---

## 7. Proactive Focus Suggestions

```mermaid
flowchart TD
    A[Cron tick during 09-18h BRT] --> B{Is Lucas in<br/>focus session?}
    B -->|Yes| Z[action: none]
    B -->|No| C{Has Lucas responded<br/>to any check-in today?}
    C -->|Yes| Z
    C -->|No| D{Cooldown > 1h<br/>since last suggestion?}
    D -->|No| Z
    D -->|Yes| E[Query Google Calendar<br/>all calendars]
    E --> F{Free window<br/>>= 60min between<br/>09-18h?}
    F -->|No| Z
    F -->|Yes| G[Find first non-stale<br/>window starting soon]
    G --> H[suggest_focus:<br/>'Tem X min livres até Yh.<br/>Sugestão: task pendente']
    H --> I[save cooldown timestamp<br/>in state.json]
```

### Re-engagement (~15h BRT)

```mermaid
flowchart TD
    A[Cron tick at ~15h BRT] --> B{Any window has<br/>user_responded_at?}
    B -->|Yes| Z[action: none]
    B -->|No| C{Last activity<br/>less than 30min ago?}
    C -->|Yes| Z
    C -->|No| D[Check if daily_summary<br/>exists for today]
    D -->|Exists with content| E[action: none<br/>Lucas interacted but<br/>outside check-in]
    D -->|No content| F[send_reengagement:<br/>'Lucas, ainda não<br/>registramos nada hoje.']
```

---

## 8. Data Architecture

### Files and their roles

| File | Path | Writer | Reader | Contents |
|---|---|---|---|---|
| `state.json` | `{BASE_DIR}/state.json` | `checkin.py` | `checkin.py`, cron agent, live agent | Check-in window states, cooldowns, weekly report flags |
| `daily_summary_YYYY-MM-DD.md` | `{BASE_DIR}/daily_summary_*.md` | `checkin.py`, live agent | `checkin.py`, live agent | YAML frontmatter + Markdown: tasks, intentions, plans, metrics |
| `focus_sessions.json` | `{BASE_DIR}/focus_sessions.json` | live agent, `checkin.py` | `checkin.py`, live agent | Active/completed sessions, stats, streaks |
| `jobs.json` | `{BASE_DIR}/../cron/jobs.json` | deploy.sh | Hermes cron scheduler | Cron job definitions + agent prompts |
| `SKILL.md` | Skills directory | deploy.sh | Live agent | Behavior instructions for agent |
| `SOUL.md` | Profile root | deploy.sh | Live agent | Agent personality + guardrails |
| `config.yaml` | Profile root | Admin | Hermes gateway | Model, plugins, platform configs |
| `LLM Wiki` | `{WIKI_PATH}/` | Live agent | Live agent | Durable facts (user profile, projects) |

### Write flow

```mermaid
flowchart LR
    subgraph "Every 5 minutes"
        cron[checkin.py] -->|W + save| state.json
        cron -->|metrics| daily_summary
        cron -->|generate_daily_summary| agent[Cron Agent]
    end

    subgraph "On Lucas response"
        live[Live Agent] -->|tasks, intention, summary| daily_summary
        live -->|focus declare| focus_sessions.json
        live -->|facts| wiki[LLM Wiki]
        live -->|streak, metrics| state.json
    end
```

### Read flow

```mermaid
flowchart LR
    subgraph "checkin.py"
        cron[checkin.py] --> state.json
        cron --> daily_summary
        cron --> focus_sessions.json
        cron --> gc[Google Calendar API]
    end

    subgraph "Live Agent"
        live[Live Agent] --> daily_summary
        live --> state.json
        live --> focus_sessions.json
        live --> wiki[LLM Wiki]
        live --> sessions[session_search]
    end
```

---

## 9. Complete Day Timeline

```mermaid
gantt
    title Example Day with Full Interaction
    dateFormat HH:mm
    axisFormat %H:%M

    section Cron System
    W1 check-in        :w1, 09:05, 09:06
    Proactive Focus    :pf1, 09:15, 1min
    W2 check-in        :w2, 11:35, 11:36
    Re-engagement skip :re1, after pf1, 15:00
    Proactive Focus    :pf2, 15:10, 1min
    W3 check-in        :w3, 17:10, 17:11
    Daily Summary gen  :ds1, 18:30, 1min

    section Lucas
    Bom dia (W1 resp)  :r1, 09:10, 2min
    Declara foco       :f1, 09:15, 2min
    Focus midpoint resp:fm1, 10:15, 1min
    W2 response        :r2, 11:37, 2min
    Termina foco       :f2, 11:50, 1min
    W3 response        :r3, 17:15, 2min

    section Focus Session
    Active: 09:15-11:50 :fs, 09:15, 11:50
    Midpoint cron       :fm2, 10:15, 1min
    End cron            :fe1, 11:15, 1min
```

---

## 10. Key Design Decisions

| Decision | Why |
|---|---|
| **Randomized check-in times** | Prevents pattern predictability; feels more natural |
| **Daily summary as response proof** | No need for explicit "I responded" API call; file mtime is the evidence |
| **mtime > sent_at for auto-fill** | Prevents false positives from earlier-day interactions |
| **followup_action = "sent"** | Prevents duplicate follow-ups in 5-min cron window |
| **Multi-calendar support** | `GOOGLE_CALENDAR_ID=email1,email2` — queries all for free windows |
| **Stale windows >30min are skipped** | Prevent suggesting focus in windows that already started long ago |
| **Re-engagement only if NO responded** | Only nudge when truly no interaction today |
| **Escalation W3-only** | Morning and midday windows end with follow-up; only end-of-day escalates |
| **Streak from responded check-ins** | `checkins_responded` in `calculate_metrics()` determines streak |
| **Cron runs even during focus** | `is_in_focus_session()` check skips check-in, not cron — focus retries still fire |

---

## 11. Environment Variables

| Variable | Used by | Default |
|---|---|---|
| `CHECKIN_DATA_DIR` | checkin.py | `~/.cron/responsibility_partner` |
| `GOOGLE_SERVICE_ACCOUNT_PATH` | checkin.py | `/opt/data/google-service-account.json` |
| `GOOGLE_CALENDAR_ID` | checkin.py | Comma-separated list of calendar IDs |
| `GEMINI_API_KEY` | (removed — was gemini_meet) | — |
| `PULSE_RUNTIME_PATH` | (removed — was gemini_meet) | — |

---

## 12. Files Modified by This System

| File | Description |
|---|---|
| `hermes-data/scripts/checkin.py` | Main cron script (~1120 lines) |
| `hermes-data/cron/jobs.json` | Cron job definitions + agent prompts |
| `hermes-data/skills/productivity/daily-status-session/SKILL.md` | Live agent skill |
| `hermes-data/skills/productivity/focus-session-handler/SKILL.md` | Focus session skill |
| `hermes-data/skills/productivity/unblock-helper/SKILL.md` | Unblock / task initiation skill |
| `hermes-data/SOUL.md` | Agent personality (accountability tone, rules) |
| `deploy.sh` | Deployment script |
| `docker-compose.yaml` | Container orchestration |
| `.env.example` | Environment template |

