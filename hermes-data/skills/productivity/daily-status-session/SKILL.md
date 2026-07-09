---
name: daily-status-session
description: "Optimized flow for handling Lucas's daily status updates in live conversations — parallel tool calls, no wasted round trips."
version: 2.1.0
---

# Daily Status Session Handler

## When to use

When Lucas starts a conversation with a status update (e.g., "bom dia", planos do dia, progresso em tasks). This skill optimizes the tool-calling flow to minimize latency.

Also use when:
- Lucas declares a focus session ("vou focar em X por Y")
- Lucas reports task progress during or after a focus session
- Lucas asks about his current status or streak

## Optimized flow

### First turn — do everything in ONE round

When Lucas gives a status update or says "bom dia", do these in parallel:

```
read_file(/opt/data/profiles/accountability/.cron/responsibility_partner/daily_summary_YYYY-MM-DD.md)  # último disponível (até 7 dias)
read_file(/opt/data/profiles/accountability/.cron/responsibility_partner/focus_sessions.json)           # focus sessions ativas
read_file(/opt/data/profiles/accountability/wiki/index.md)                                              # LLM Wiki — fatos duráveis
session_search(query="...", limit=3)                                                                    # contexto cross-session
```

The daily summary file path is deterministic: `daily_summary_YYYY-MM-DD.md`. Do NOT run `search_files` to discover it — the path is known. Just `read_file` directly.

**On Mondays (or after holidays), "yesterday" may not exist.** Start with yesterday's date, but if that file is missing, try the previous day, and so on up to 7 days back. The same `load_last_available_summary` pattern used in `checkin.py` applies — find the most recent daily_summary with content.

If today's summary already exists (Lucas coming back mid-day), read BOTH the last available and today's in parallel:
```
read_file(/opt/data/profiles/accountability/.cron/responsibility_partner/daily_summary_YYYY-MM-DD.md)  # último disponível
read_file(/opt/data/profiles/accountability/.cron/responsibility_partner/daily_summary_YYYY-MM-DD.md)  # hoje
read_file(/opt/data/profiles/accountability/.cron/responsibility_partner/focus_sessions.json)           # focus sessions
read_file(/opt/data/profiles/accountability/wiki/index.md)                                              # LLM Wiki
session_search(query="...", limit=3)
```

### Detect focus session intent

If Lucas's message contains focus-related keywords ("foco", "focar", "vou trabalhar em", "concentrar"), trigger the focus-session-handler skill instead of the normal status flow. The focus-session-handler will:
1. Parse task and duration
2. Create cron one-shot jobs
3. Save state to focus_sessions.json
4. Update daily_summary

### Detect unblock / stuck intent

If Lucas's message contains stuck-related keywords ("não tô conseguindo começar", "tô travado", "procrastinando", "não saiu", "empacado"), trigger the unblock-helper skill instead. The unblock-helper will:
1. Ask one question to reduce barrier to entry
2. Offer optional 10min check-in

### Extract intention of the day (W1 response)

When Lucas responds to the W1 check-in (which now asks "qual a coisa mais importante" and "algo burocrático"):
- Extract the main intention from his response
- Save it as `intention: "..."` in the daily_summary YAML frontmatter
- One short, factual sentence. Not paragraphs.
- Example: "Terminar o PR da API de batimetria" or "Foco no relatório mensal"

### Extract plans for tomorrow (W3 response)

When Lucas responds to the W3 check-in (which now asks "qual vai ser sua primeira tarefa amanhã"):
- Save `plans_for_next_day` to **tomorrow's** daily_summary file
- Create the file if it doesn't exist (minimal YAML frontmatter with `date` and `plans_for_next_day`)
- One short sentence. If Lucas doesn't specify or says "não sei", skip — don't force it.

### Save status IMMEDIATELY

When Lucas shares task progress, save `daily_summary_YYYY-MM-DD.md` with YAML frontmatter right after responding — don't defer to end of conversation. This ensures the cron check-in system sees updated context.

Format:
```yaml
---
date: 'YYYY-MM-DD'
summary_text: '...'
context: '...'
intention: '...'  # extracted from W1 response — one short sentence
plans_for_next_day: '...'  # extracted from W3 response — one short sentence
tasks:
- id: ...
  name: ...
  status: em andamento|pendente|em espera|concluído
  notes: ...
  since: 'YYYY-MM-DD'  # or completed: 'YYYY-MM-DD'
metrics:
  tasks_completed_today: 2
  focus_sessions_completed: 1
  focus_minutes_total: 120
  checkins_responded: 3
  checkins_total: 3
---
```

### Track gamification metrics

After every status update, calculate and include the `metrics` section in the daily_summary:
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

Do NOT mention:
- Streak breaks or negative trends
- Every milestone every time — only the first time it's reached
- Milestones if Lucas seems stressed or busy — read the room

### Task statuses

Use 3 active categories:
- `em andamento` — actively working
- `pendente` — planned but not started
- `em espera` — blocked, waiting on external factor

Plus `concluído` for done tasks.

## Pitfalls

- **Do NOT use `~` in paths.** Always use `/opt/data/profiles/accountability/.cron/responsibility_partner/`. `~` resolves differently for the cron agent vs main agent, causing split-brain. The accountability profile data directory is `/opt/data/profiles/accountability/.cron/responsibility_partner/` — aligned with `CHECKIN_DATA_DIR` in docker-compose.
- **Do NOT use `search_files` to find the daily summary path.** The path is deterministic — go straight to `read_file`. Using search_files adds an unnecessary round trip.
- **Do NOT do a second round of tool calls** if you already have the daily summary content from the first parallel batch. Parse and respond.
- **Save the daily summary after EVERY status update**, not just at end of conversation. The cron system depends on it for reply detection.
- **Keep task status in daily_summary files, NOT in the wiki.** The wiki is for durable facts only (preferences, config, conventions, projects).
- **Tasks concluídas stay in daily_summary** — they don't get promoted to the wiki.
- **Confirm what was saved.** After writing the daily_summary, tell Lucas what you registered (one line). This lets him catch mismatches immediately instead of discovering later that the cron job has stale data.
- **Don't let infrastructure debugging derail the conversation.** Cron errors, rate limits, skill config — these are YOUR problems, not his. Handle them without losing focus on his task status. Circle back to his tasks before the conversation ends.
- **When interrupted mid-status, resume.** If Lucas reported a task status and the conversation got sidetracked (by meta-discussion or error reports), explicitly circle back: "Só pra confirmar, teu status ficou X. Alguma atualização desde então?"
- **Sync checkin.py after any edit.** Three copies exist and ALL must stay identical:
  1. `/opt/data/profiles/accountability/.cron/responsibility_partner/checkin.py` — profile scripts dir (used by cron)
  2. `/opt/data/scripts/checkin.py` (used by cron via `script:` parameter, resolved from HERMES_HOME)
  3. `/opt/data/home/scripts/checkin.py` (legacy mirror, also synced)
  After patching the canonical, cp it to the other two. Verify with `md5sum` on all three.
- **Cron sessions may not be immediately searchable.** Very recent cron runs (<10 min) might not appear in `session_search`. Fall back to reading `state.json` directly to determine what the cron actually did.
- **W1: busca o último daily_summary disponível (até 7 dias).** O `checkin.py` usa `load_last_available_summary(days_back=7, start_offset=1)` — não apenas o dia anterior. Isso cobre o gap de fim de semana e feriados. Se encontrar um registro de 3 dias atrás (ex: sexta-feira), a mensagem mostra "📋 Último registro (sexta-feira, 22/05):". O cron agent entrega essa mensagem; você NUNCA deve rebaixá-la para "não tenho registro de ontem" quando o script produziu contexto. Nas conversas ao vivo (Lucas dizendo "bom dia"), siga o mesmo padrão: tente ontem primeiro, mas se não existir, busque até 7 dias atrás. A regra "não misturar contexto de dias anteriores" só se aplica ao MEMORY (não salve tasks stale lá), não aos daily_summary files.
- **Fim de semana NO conversational flow (sem cron):** O daily_summary só existe em dias úteis. Se Lucas diz "bom dia" numa segunda-feira e o resumo de ontem (domingo) não existe, NÃO pergunte "o que rolou ontem?" — você já sabe que ontem foi domingo. Busque diretamente o último dia útil (sexta-feira ou anterior) com `load_last_available_summary`. Se não encontrar nada em 7 dias, ENTÃO pergunte ao usuário o que ele tem para compartilhar. Regra: tentar primeiro, perguntar depois. Semana passada é contexto, não surpresa.
- **State.json com scheduled_epoch null = check-ins do dia vão falhar.** Se state.json tem scheduled_epoch: null nas janelas, o rollover não preencheu os horários. Forçar rollover: setar state["date"] para ontem e deixar o próximo tick do cron (<1 min) recriar as janelas. Fazer backup antes (state.json.bak). Sintoma: check-in não chega no horário esperado e o state mostra campos null.
- **PyYAML é dependência obrigatória do checkin.py.** Sem ele, o script quebra no import yaml e TODOS os check-ins falham silenciosamente. Se um python3 -c "import yaml" falhar, instalar PyYAML imediatamente — não escrever fallback manual. A preferência do Lucas é clara: use soluções prontas, não implementações próprias.
- **`m in summary.lower()` é bug silencioso.** Strings com maiúsculas (ex: `"Sem atividade"`) NUNCA casam com `summary.lower()` porque o `in` do Python é case-sensitive. Sempre usar `m.lower() in summary.lower()`. Esse bug fez a função `load_last_active_date` tratar summaries genéricos de "Sem atividade" como conteúdo real por meses, exibindo "último registro: ontem" quando na verdade eram só mensagens automáticas vazias.
- **CHECKIN_WINDOW_SEC deve ser ≥ 2× o intervalo do cron.** Com cron a cada 5 min e janela de 5 min, um erro 503 do provider mata o check-in do dia. Com janela de 10 min (600s), há 2 chances de execução. Regra: `CHECKIN_WINDOW_SEC ≥ cron_interval * 2`.
- **Provider 503 no cron é ponto único de falha.** Se o model do cron job falhar durante a janela de check-in, a mensagem é perdida. Mitigações: (a) janela maior (item acima), (b) model estável (evitar modelos beta/flash em cron jobs críticos), (c) considerar `no_agent=True` com o script gerando a mensagem completa, eliminando dependência de LLM no runtime.
