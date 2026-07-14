---
name: daily-status-session
description: "Optimized flow for handling Lucas's daily status updates in live conversations — parallel tool calls, no wasted round trips."
version: 3.0.0
---

# Daily Status Session Handler

## When to use

When Lucas starts a conversation with a status update (e.g., "bom dia", planos do dia, progresso em tasks). This skill optimizes the tool-calling flow to minimize latency.

Also use when:
- Lucas declares a focus session ("vou focar em X por Y") → delegate to focus-session-handler
- Lucas reports task progress during or after a focus session
- Lucas asks about his current status or streak

## Optimized flow

### First turn — do everything in ONE round

When Lucas gives a status update or says "bom dia", do these in parallel:

```
daily_summary_load()                        # today (no date param = today)
daily_summary_load(date="YYYY-MM-DD")       # yesterday (or last available up to 7 days back)
read_file(/opt/data/profiles/accountability/wiki/index.md)  # LLM Wiki — fatos duráveis
session_search(query="...", limit=3)        # contexto cross-session
```

**On Mondays (or after holidays), "yesterday" may not exist.** Start with yesterday's date, but if `daily_summary_load` returns `exists: false`, try the previous day, and so on up to 7 days back. The same `load_last_available_summary` pattern used in `checkin.py` applies — find the most recent daily_summary with content.

### Save status with tools

When Lucas shares task progress, use `daily_summary_save` immediately — don't defer to end of conversation. This ensures the cron check-in system sees updated context.

**CRITICAL: `daily_summary_save` creates/overwrites the file for the given date.** Always pass `date` as today's date. The tool handles YAML formatting and path resolution — you never need to know where the file lives.

Example:
```
daily_summary_save(
    date="2026-07-14",
    summary_text="Lucas está trabalhando na task X.",
    context="Segunda-feira pós-feriado.",
    tasks=[{"id": "task-01", "name": "X", "status": "em andamento", "notes": "...", "since": "2026-07-10"}],
    metrics={"tasks_completed_today": 0, "checkins_responded": 1, "checkins_total": 3}
)
```

### Extract intention of the day (W1 response)

When Lucas responds to the W1 check-in, extract the main intention and save it via `daily_summary_save` with the `intention` field:
- One short, factual sentence. Not paragraphs.
- Example: "Terminar o PR da API de batimetria" or "Foco no relatório mensal"

### Extract plans for tomorrow (W3 response)

When Lucas responds to the W3 check-in, save `plans_for_next_day` to **tomorrow's** daily_summary via `daily_summary_save(date="YYYY-MM-DD+1", plans_for_next_day="...")`. If Lucas doesn't specify, skip.

### Detect focus session intent

If Lucas's message contains focus-related keywords ("foco", "focar", "vou trabalhar em", "concentrar"), delegate to the focus-session-handler skill. That skill uses `focus_session_start` and `focus_session_complete` for state management.

### Detect unblock / stuck intent

If Lucas's message contains stuck-related keywords ("não tô conseguindo começar", "tô travado", "procrastinando", "não saiu", "empacado"), trigger the unblock-helper skill.

### Track gamification metrics

After every status update, calculate and include the `metrics` in `daily_summary_save`:
- `tasks_completed_today`: count of tasks with status "concluído" and completed=today
- `focus_sessions_completed`: from focus_sessions.json completed_today
- `focus_minutes_total`: sum of completed focus session durations today
- `checkins_responded`: from state.json (windows where user_responded_at is not null)
- `checkins_total`: from state.json (windows where checkin_sent_at is not null)

### Report milestones (when relevant)

If a milestone is reached, mention it subtly (1 line):
- 3+ consecutive days with updates: "3 dias seguidos de atualização. Consistência."
- 5+ consecutive days: "5 dias. Bom ritmo."
- 10+ tasks completed (total): "10 tarefas concluídas desde [data]."
- First focus session ever: "Primeira focus session registrada."

Do NOT mention streak breaks, negative trends, or over-celebrate. Read the room.

### Task statuses

- `em andamento` — actively working
- `pendente` — planned but not started
- `em espera` — blocked, waiting on external factor
- `concluído` — done

## Tool reference

| Task | Tool to use |
|---|---|
| Load daily summary | `daily_summary_load(date="YYYY-MM-DD")` — omit date for today |
| Save daily summary | `daily_summary_save(date=..., summary_text=..., tasks=..., metrics=...)` |
| Start focus session | `focus_session_start(task_name=..., duration_minutes=...)` (via focus-session-handler) |
| Complete focus session | `focus_session_complete(session_id=..., result=...)` (via focus-session-handler) |

## Pitfalls

- **Do NOT read or write files directly in /opt/data/.cron/.** Use the tools. They encapsulate all path logic.
- **Do NOT use `search_files` to find the daily summary path.** Use `daily_summary_load`.
- **Do NOT do a second round of tool calls** if you already have the daily summary content from the first parallel batch. Parse and respond.
- **Save the daily summary after EVERY status update**, not just at end of conversation. The cron system depends on it for reply detection.
- **Keep task status in daily_summary files, NOT in the wiki.** The wiki is for durable facts only (preferences, config, conventions, projects).
- **Tasks concluídas stay in daily_summary** — they don't get promoted to the wiki.
- **Confirm what was saved.** After calling `daily_summary_save`, tell Lucas what you registered (one line).
- **Don't let infrastructure debugging derail the conversation.** Cron errors, rate limits, skill config — these are YOUR problems, not his.
- **When interrupted mid-status, resume.** Circle back: "Só pra confirmar, teu status ficou X. Alguma atualização desde então?"
- **Sync checkin.py after any edit.** Three copies exist and ALL must stay identical. After patching the canonical in `/opt/data/scripts/checkin.py`, cp it to the other two. Verify with `md5sum` on all three.
- **Cron sessions may not be immediately searchable.** Very recent cron runs (<10 min) might not appear in `session_search`. Fall back to reading `state.json` directly.
- **W1: busca o último daily_summary disponível (até 7 dias).** O `checkin.py` usa `load_last_available_summary(days_back=7, start_offset=1)`. Siga o mesmo padrão.
- **Fim de semana NO conversational flow (sem cron).** Se Lucas diz "bom dia" numa segunda-feira e o resumo de ontem (domingo) não existe, NÃO pergunte "o que rolou ontem?" — busque o último dia útil. Regra: tentar primeiro, perguntar depois.
- **State.json com scheduled_epoch null = check-ins do dia vão falhar.** Forçar rollover: setar state["date"] para ontem.
- **PyYAML é dependência obrigatória do checkin.py.** Sem ele, o script quebra silenciosamente.
- **`m in summary.lower()` é bug silencioso.** Sempre usar `m.lower() in summary.lower()`.
- **CHECKIN_WINDOW_SEC deve ser ≥ 2× o intervalo do cron.** 10 min = 2 chances.
- **Provider 503 no cron é ponto único de falha.** Use model estável em cron jobs críticos.
- **daily_summary_save replaces the ENTIRE file.** Every call is a full rewrite — you MUST include ALL tasks, not just the one being updated. If you omit a task, it is deleted. Load first with `daily_summary_load()`, merge, then save.
