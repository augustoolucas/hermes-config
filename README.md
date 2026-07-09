# Hermes — Accountability Partner

An ADHD-aware accountability layer built on [Hermes Agent](https://github.com/NousResearch/hermes-agent). Scheduled check-ins, focus session tracking, calendar-aware suggestions, and persistent memory — all self-hosted in a single Docker Compose stack.

---

## Features

- **3 daily check-ins** — morning intention, midday progress, evening wrap-up with future-day planning
- **Follow-up & escalation** — progressively raises attention if you don't respond; auto-detects replies to suppress extraneous nudges
- **Focus sessions** — declared work blocks with midpoint and end check-ins, retry on missed delivery, early completion
- **Google Calendar integration** — multi-calendar support; detects free windows ≥60 min, suggests focus sessions
- **ADHD-aware design** — re-engagement nudges at ~3 PM, micro-step unblock helper for task initiation paralysis, nightly preparation
- **LLM Wiki** — inspectable Markdown-based persistent memory for durable facts (preferences, projects, environment)
- **Self-hosted web tools** — SearXNG metasearch engine + fastCRW web extraction, zero API keys or rate limits
- **Gamification** — streak tracking, focus minutes, subtle milestone acknowledgment
- **Git-backed daily summaries** — every status update is version-controlled

→ Full spec: [SPECS.md](hermes-data/docs/SPECS.md) · Architecture: [ACCOUNTABILITY-FLOW.md](hermes-data/docs/ACCOUNTABILITY-FLOW.md)

---

## How It Works

Two agents share files on disk — they never talk to each other directly.

```
Cron (checkin.py)                    Live Agent (skills)
  │                                     │
  │ runs every 5 minutes                │ triggers when you message
  │ checks state.json + daily_summary   │ reads wiki + summaries
  │ decides: check-in? follow-up?       │ saves tasks, intentions, progress
  │ outputs JSON → cron agent delivers  │ responds with context
  │                                     │
  └────────── Shared files ─────────────┘
       state.json | daily_summary_*.md | focus_sessions.json | LLM Wiki
```

---

## Directory Structure

```
hermes-config/
├── docker-compose.yaml         # Hermes + SearXNG + fastCRW + LightPanda
├── deploy.sh                   # Sync files to container + restart
├── .env.example                # Environment template
├── hermes-data/
│   ├── SOUL.md                 # Agent personality & accountability rules
│   ├── cron/
│   │   └── jobs.json           # Cron job definitions + agent prompts
│   ├── scripts/
│   │   └── checkin.py          # Cron script (~1130 lines, Python)
│   ├── skills/productivity/
│   │   ├── daily-status-session/SKILL.md
│   │   ├── focus-session-handler/SKILL.md
│   │   └── unblock-helper/SKILL.md
│   └── docs/
│       ├── SPECS.md            # Full functional specification
│       └── ACCOUNTABILITY-FLOW.md  # Architecture with Mermaid diagrams
└── searxng/
    └── core-config/settings.yml
```

---

## Quick Start

### 1. Clone

```bash
git clone git@github.com:augustoolucas/hermes-config.git
cd hermes-config
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env: fill TELEGRAM_CHAT_ID, TELEGRAM_BOT_TOKEN, API keys,
# GOOGLE_SERVICE_ACCOUNT_PATH, GOOGLE_CALENDAR_ID (comma-separated)
```

### 3. Set up Google Calendar (optional but recommended)

Create a service account, download the JSON key, place it at the path in `GOOGLE_SERVICE_ACCOUNT_PATH`, and share your calendars with the service account email.

### 4. Start

```bash
docker compose up -d
./deploy.sh
```

---

## Requirements

- **Docker** and **Docker Compose**
- **Google service account** (for Calendar-based focus suggestions — optional but recommended)
- **Telegram bot token** (for message delivery)

Everything else (SearXNG web search, fastCRW web scraping, LLM Wiki memory, Edge TTS) runs in containers with no extra API keys.

---

## Documentation

| Document | What it covers |
|---|---|
| [SPECS.md](hermes-data/docs/SPECS.md) | Functional specification — every feature in detail, state schemas, timing constants, future improvements |
| [ACCOUNTABILITY-FLOW.md](hermes-data/docs/ACCOUNTABILITY-FLOW.md) | Architecture — 11 Mermaid diagrams, state machines, data flow, troubleshooting, glossary |
