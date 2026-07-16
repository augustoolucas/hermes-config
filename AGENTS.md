# AGENTS.md — Hermes Config

**Project:** Hermes Config — Accountability Partner for Lucas Alcantara
**Stack:** Hermes agent via Docker, Telegram delivery, Python checkin scripts, YAML/Markdown config
**User:** Lucas (email in .env) | **Developer:** opencode
**Chat paths:** `TELEGRAM_CHAT_ID` → Lucas, `TELEGRAM_CHAT_ID_GROUP` → Lucas+OpenCode

## Key commands

| Command | What it does |
|---|---|
| `./deploy.sh` | Full deploy: runs validate.sh → copies files to container → restarts |
| `cd hermes-data && bash tests/validate.sh` | Run test suite (9 checks) |
| `tools/hermes-exec <cmd>` | Docker exec hermes wrapper |
| `docker exec hermes hermes -p accountability cron list` | Check cron scheduler status |
| `docker exec -u hermes hermes python3 -c '...'` | Inspect state in container |
| `docker exec hermes hermes -p accountability cron run <uuid>` | Manually trigger a cron job |

## File dependency map

```
checkin.py (cron state machine logic)
  → reads/updates state.json, focus_sessions.json, daily_summary.md
  → executed by cron job defined in jobs.json
jobs.json (cron agent LLM prompt — single turn, 593 chars)
  → uses accountability-tools plugin
tools.py (accountability-tools plugin)
  → daily_summary_load / daily_summary_save
  → focus_session_start / focus_session_complete
  → checkin_state_update / focus_session_status
  → consumed by SOUL.md → SKILL.md files (6 skills)
```

## Key config

| Config | Value |
|---|---|
| `CHECKIN_DATA_DIR` | `/opt/data/profiles/accountability/.cron/responsibility_partner` |
| Cron schedule (checkin) | `*/5 8-12,15-18 * * 1-5` |
| Cron schedule (weekly report) | `0 21 * * 5` |
| Windows (BRT) | W1: 09:00-09:30, W2: 11:30-12:00, W3: 17:00-17:45 |
| Checkin model | `null` (uses default from config) |
| Weekly report model | `deepseek/deepseek-v4-pro` |
| Config dir | `~/.hermes/profiles/accountability/config/` |
| Data dir | `/opt/data/profiles/accountability/` |

## Deploy checklist

1. Run `hermes-data/tests/validate.sh` — abort if any check fails
2. Run `./deploy.sh`
3. Verify checksums match repo ↔ container:
   - `md5sum hermes-data/SOUL.md` vs `docker exec hermes md5sum /opt/data/profiles/accountability/SOUL.md`
   - `md5sum hermes-data/scripts/checkin.py` vs `docker exec hermes md5sum /opt/data/scripts/checkin.py`
   - `md5sum hermes-data/plugins/accountability-tools/tools.py` vs `docker exec hermes md5sum /opt/data/plugins/accountability-tools/tools.py`
4. `docker exec hermes hermes -p accountability cron list` — all jobs show last_status=ok
5. Wait 5s after restart, check no error request dumps generated
6. Audit `git diff --cached` for sensitive data before commit

## Sensitive data patterns (never commit)

- Telegram chat IDs: `TELEGRAM_CHAT_ID`, `TELEGRAM_CHAT_ID_GROUP`
- API keys: `sk-...`, any key-like strings
- Emails (any email address)
- Data files (never in repo): `.env`, `google-service-account.json`, `google_token.json`

## Troubleshooting

| Symptom | Likely cause | Check |
|---|---|---|
| Duplicate check-ins | `sent_at` not set on first tick | state.json: `sent_at` vs `emitted_at` — checkin.py should mark `sent_at` immediately after emission |
| HTTP 400 on cron run | Model mismatch / multi-turn | `ls -lt sessions/request_dump_cron_*` → count messages: 4 = turn 2 failed, 2 = turn 1. Check model. Single-turn prompt (593 chars, no tools) is expected. |
| Live agent uses wrong date | `daily_summary_save` validation | `tools.py:54` rejects date != today in summary content |
| W1/W3 not received | Cron schedule BRT misinterpretation | Verify cron `*/5 8-12,15-18 * * 1-5` aligns with BRT (UTC-3). W3 at 17:00 BRT = 20:00 UTC — still in range. |
| Focus session not recognized | `end_epoch` missing in focus_sessions.json | `checkin.py:370` `is_in_focus_session()` needs `end_epoch`. `tools.py:96` `focus_session_start` must set `end_epoch = started_at + duration*60`. |

## Current health

- 9 validation checks (tests/validate.sh)
- 6 tools (tools.py)
- 6 skills (SKILL.md files)
- Single-turn cron prompt (593 chars)
- 3 checkin windows (W1/W2/W3) with 30-45 min grace periods

## Feature implementation checklist

When adding a new feature, update these files if applicable:

| Change | Files to update |
|---|---|
| New tool | `tools.py` + `__init__.py` + mention in `SOUL.md` + reference in `jobs.json` |
| New skill | `skills/productivity/<name>/SKILL.md` + `SOUL.md` skills table + `deploy.sh` cp block |
| New checkin.py behavior | `jobs.json` (if cron agent needs new instruction) + `ACCOUNTABILITY-FLOW.md` (if flow changes) |
| New validation check | `tests/validate.sh` + reference in `deploy.sh` pre-deploy block + `validate-docs.sh` (if counts change) |
| State field changes (state.json / focus_sessions.json) | `checkin.py` consumers + `tools.py` producers + consumer cross-ref in hermes-dev skill |
| Path / env var changes | `deploy.sh` + `AGENTS.md` config table + `docker-compose.yaml` (if new env var) |

Post-implementation: run `hermes-data/tests/validate.sh` before commit. The `validate-docs.sh` check auto-verifies tool/skill/check counts match AGENTS.md.
