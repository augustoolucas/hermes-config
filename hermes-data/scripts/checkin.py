#!/usr/bin/env python3
"""
Responsibility Partner — Check-in Engine (v4)
Executado a cada 5 min (Seg-Sex) pelo cron job.
Determina se é hora de check-in, follow-up, escalação, retry de focus session,
detecção de task stale, resumo diário ou relatório semanal.
Output: JSON no stdout com a ação a ser tomada pelo agente.
"""

import json
import os
import random
import subprocess
import sys

import yaml
from datetime import datetime, timezone, timedelta

try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    HAS_GOOGLE = True
except ImportError:
    HAS_GOOGLE = False

# ─── YAML Frontmatter ──────────────────────────────────────────────────

def parse_frontmatter(text):
    """Parse YAML frontmatter from markdown using PyYAML."""
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    data = yaml.safe_load(parts[1])
    return data if isinstance(data, dict) else {}


def save_daily_summary_md(date_str, data):
    """Write daily_summary as Markdown with YAML frontmatter."""
    path = f"{SUMMARY_PREFIX}_{date_str}.md"
    tmp = path + ".tmp"

    frontmatter = {}
    if data.get("date"):
        frontmatter["date"] = data["date"]
    else:
        frontmatter["date"] = date_str
    if data.get("summary_text"):
        frontmatter["summary_text"] = data["summary_text"]
    if data.get("context"):
        frontmatter["context"] = data["context"]
    if data.get("plans_for_next_day"):
        frontmatter["plans_for_next_day"] = data["plans_for_next_day"]
    if data.get("intention"):
        frontmatter["intention"] = data["intention"]

    tasks = data.get("tasks") or data.get("tasks_discussed")
    if tasks:
        frontmatter["tasks"] = []
        for t in tasks:
            item = {}
            item["name"] = t.get("name", t.get("desc", ""))
            item["status"] = t.get("status", "")
            if t.get("id"):
                item["id"] = t["id"]
            elif t.get("desc"):
                item["id"] = t["desc"][:30].lower().replace(" ", "-")
            if t.get("notes"):
                item["notes"] = t["notes"]
            if t.get("completed"):
                item["completed"] = t["completed"]
            if t.get("since"):
                item["since"] = t["since"]
            frontmatter["tasks"].append(item)

    # Gamificação: métricas do dia
    if data.get("metrics"):
        frontmatter["metrics"] = data["metrics"]

    with open(tmp, "w") as f:
        f.write("---\n")
        yaml.dump(frontmatter, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        f.write("---\n\n")
        f.write(f"# {date_str}\n\n")
        if data.get("summary_text"):
            f.write(f"## Atualizações\n\n{data['summary_text']}\n\n")
        if data.get("plans_for_next_day"):
            f.write(f"## Plano\n\n{data['plans_for_next_day']}\n")

    os.replace(tmp, path)

    # Git backup automático
    git_backup_commit(date_str)


def git_backup_commit(date_str):
    """Faz commit automático do daily summary no repo git local."""
    try:
        git_dir = os.path.join(BASE_DIR, ".git")
        if not os.path.exists(git_dir):
            return  # git não inicializado

        summary_path = f"{SUMMARY_PREFIX}_{date_str}.md"
        if not os.path.exists(summary_path):
            return

        subprocess.run(
            ["git", "add", f"daily_summary_{date_str}.md"],
            cwd=BASE_DIR, capture_output=True, timeout=10
        )
        subprocess.run(
            ["git", "commit", "-m", f"auto: daily summary {date_str}"],
            cwd=BASE_DIR, capture_output=True, timeout=10
        )
    except Exception:
        pass  # git backup é best-effort, nunca deve quebrar o checkin

# ─── Config ───────────────────────────────────────────────────────────
BASE_DIR = os.environ.get("CHECKIN_DATA_DIR", os.path.expanduser("~/.cron/responsibility_partner"))
STATE_FILE = os.path.join(BASE_DIR, "state.json")
SUMMARY_PREFIX = os.path.join(BASE_DIR, "daily_summary")
HISTORY_FILE = os.path.join(BASE_DIR, "history.jsonl")
FOCUS_FILE = os.path.join(BASE_DIR, "focus_sessions.json")
TZ = timezone(timedelta(hours=-3))  # America/Sao_Paulo (BRT, UTC-3)

# Janelas (BRT)
WINDOWS = {
    1: (9, 0, 9, 30),     # 09:00–09:30
    2: (11, 30, 12, 0),    # 11:30–12:00
    3: (17, 0, 17, 45),   # 17:00–17:45
}

CHECKIN_WINDOW_SEC = 600   # 10 min para enviar check-in (margem pra retry em caso de 503)
FOLLOWUP_DELAY_SEC = 1200  # 20 min de espera
FOLLOWUP_WINDOW_SEC = 300  # 5 min para enviar follow-up
ESCALATION_DELAY_SEC = 1200  # 20 min após follow-up para escalação
FOCUS_RETRY_WINDOW_SEC = 900  # 15 min para retry de focus session check-in

# Google Calendar
GOOGLE_SERVICE_ACCOUNT_PATH = os.environ.get("GOOGLE_SERVICE_ACCOUNT_PATH", "/opt/data/google-service-account.json")
GOOGLE_CALENDAR_ID = os.environ.get("GOOGLE_CALENDAR_ID", "")
PROACTIVE_COOLDOWN_SEC = 3600  # 1h entre sugestões proativas de foco
PROACTIVE_WINDOW_START = 9   # 09:00 BRT
PROACTIVE_WINDOW_END = 18    # 18:00 BRT
PROACTIVE_MIN_DURATION = 60  # mínimo 60 min livres para sugerir foco

# Feriados — sem check-in nestas datas (formato YYYY-MM-DD)
HOLIDAYS = {
    # Nacionais
    "2026-01-01",  # Confraternização Universal
    "2026-02-16",  # Carnaval (segunda)
    "2026-02-17",  # Carnaval (terça)
    "2026-04-03",  # Sexta-feira Santa
    "2026-04-21",  # Tiradentes
    "2026-05-01",  # Dia do Trabalhador
    "2026-06-04",  # Corpus Christi
    "2026-09-07",  # Independência
    "2026-10-12",  # Nossa Senhora Aparecida
    "2026-11-02",  # Finados
    "2026-11-15",  # Proclamação da República
    "2026-11-20",  # Consciência Negra
    "2026-12-25",  # Natal
    # Estaduais — Pernambuco
    "2026-03-06",  # Data Magna de Pernambuco
    "2026-06-24",  # São João
    # Municipais — Recife
    "2026-07-16",  # Nossa Senhora do Carmo (padroeira)
}

# ─── Helpers ───────────────────────────────────────────────────────────

def brt_now():
    """Retorna (datetime_brt, epoch)."""
    utc = datetime.now(timezone.utc)
    brt = utc.astimezone(TZ)
    return brt, int(brt.timestamp())


def random_epoch_in_window(window, date_brt):
    """Escolhe um minuto aleatório dentro da janela (epoch)."""
    sh, sm, eh, em = WINDOWS[window]
    start = date_brt.replace(hour=sh, minute=sm, second=0, microsecond=0)
    end = date_brt.replace(hour=eh, minute=em, second=0, microsecond=0)
    s = int(start.timestamp()) // 60
    e = int(end.timestamp()) // 60
    return random.randint(s, e) * 60


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}


def save_state(state):
    os.makedirs(BASE_DIR, exist_ok=True)
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    os.replace(tmp, STATE_FILE)


def load_focus_sessions():
    """Carrega focus sessions do arquivo JSON."""
    if os.path.exists(FOCUS_FILE):
        with open(FOCUS_FILE) as f:
            return json.load(f)
    return {"active_sessions": [], "completed_today": [], "stats": {"total_sessions": 0, "total_minutes": 0, "current_streak": 0}}


def save_focus_sessions(data):
    """Salva focus sessions no arquivo JSON."""
    os.makedirs(BASE_DIR, exist_ok=True)
    tmp = FOCUS_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, FOCUS_FILE)


def load_daily_summary(date_str):
    """Carrega resumo de uma data específica. Tenta .md primeiro, fallback .json."""
    md_path = f"{SUMMARY_PREFIX}_{date_str}.md"
    if os.path.exists(md_path):
        with open(md_path) as f:
            return parse_frontmatter(f.read())
    json_path = f"{SUMMARY_PREFIX}_{date_str}.json"
    if os.path.exists(json_path):
        with open(json_path) as f:
            return json.load(f)
    return None


def save_daily_summary(date_str, data):
    """Salva daily_summary em Markdown com YAML frontmatter."""
    save_daily_summary_md(date_str, data)


def load_last_available_summary(days_back=7, start_offset=1):
    """Busca o daily_summary mais recente nos últimos `days_back` dias,
    começando de `start_offset` dias atrás. Retorna (date_str, data) ou (None, None)."""
    for i in range(start_offset, start_offset + days_back):
        d = (datetime.now(TZ) - timedelta(days=i)).strftime("%Y-%m-%d")
        s = load_daily_summary(d)
        if s:
            return d, s
    return None, None


def load_week_summaries():
    """Carrega resumos dos últimos 7 dias."""
    summaries = []
    for i in range(7):
        d = (datetime.now(TZ) - timedelta(days=i)).strftime("%Y-%m-%d")
        s = load_daily_summary(d)
        if s:
            summaries.append(s)
    return summaries


def load_last_active_date(days_back=14, start_offset=1):
    """Busca o último dia com atividade real (tasks ou summary_text não-genérico).
    Retorna (days_ago, date_str, summary) ou (None, None, None)."""
    for i in range(start_offset, start_offset + days_back):
        d = (datetime.now(TZ) - timedelta(days=i)).strftime("%Y-%m-%d")
        s = load_daily_summary(d)
        if not s:
            continue
        tasks = s.get("tasks") or s.get("tasks_discussed") or []
        summary = s.get("summary_text", "")
        # Considera "ativo" se tem tasks OU summary com conteúdo real
        boring_markers = ["Sem atividade", "não interagiu", "sem interação", "não respondeu"]
        has_real_summary = summary and not any(m.lower() in summary.lower() for m in boring_markers)
        if tasks or has_real_summary:
            return i, d, summary
    return None, None, None


def build_streak_context():
    """Constrói string de contexto sobre dias sem interação."""
    days_ago, last_date, last_summary = load_last_active_date(days_back=14, start_offset=1)
    if days_ago is None:
        return "Nenhum registro de atividade encontrado nos últimos 14 dias."

    last_dt = datetime.strptime(last_date, "%Y-%m-%d").replace(tzinfo=TZ)
    dias_semana = ["segunda-feira", "terça-feira", "quarta-feira",
                   "quinta-feira", "sexta-feira", "sábado", "domingo"]
    date_label = f"{dias_semana[last_dt.weekday()]}, {last_dt.strftime('%d/%m')}"

    if days_ago == 1:
        return f"📋 Último registro: *ontem* ({date_label})."
    elif days_ago <= 7:
        return f"📋 Último registro: *{date_label}* ({days_ago} dias atrás)."
    else:
        return f"⚠️ Já são *{days_ago} dias* sem check-in (último: {date_label}). Tudo bem por aí?"


def calculate_streak():
    """Calcula o streak atual de dias com interação."""
    streak = 0
    for i in range(1, 30):  # até 30 dias atrás
        d = (datetime.now(TZ) - timedelta(days=i)).strftime("%Y-%m-%d")
        s = load_daily_summary(d)
        if not s:
            break
        tasks = s.get("tasks") or s.get("tasks_discussed") or []
        summary = s.get("summary_text", "")
        boring_markers = ["Sem atividade", "não interagiu", "sem interação", "não respondeu"]
        has_real_summary = summary and not any(m.lower() in summary.lower() for m in boring_markers)
        if tasks or has_real_summary:
            streak += 1
        else:
            break
    return streak


def calculate_metrics(date_str):
    """Calcula métricas do dia para gamificação."""
    state = load_state()
    focus = load_focus_sessions()
    summary = load_daily_summary(date_str)

    # Tasks concluídas hoje
    tasks_completed = 0
    if summary:
        tasks = summary.get("tasks") or []
        for t in tasks:
            if t.get("status") == "concluído" and t.get("completed") == date_str:
                tasks_completed += 1

    # Focus sessions completadas hoje
    focus_completed = 0
    focus_minutes = 0
    completed_today = focus.get("completed_today", [])
    for fs in completed_today:
        if fs.get("completed_date") == date_str:
            focus_completed += 1
            focus_minutes += fs.get("duration_minutes", 0)

    # Check-ins respondidos
    windows = state.get("windows", {})
    checkins_responded = sum(1 for w in windows.values() if w.get("user_responded_at"))
    checkins_total = sum(1 for w in windows.values() if w.get("checkin_sent_at"))

    # Streak
    streak = calculate_streak()

    return {
        "tasks_completed_today": tasks_completed,
        "focus_sessions_completed": focus_completed,
        "focus_minutes_total": focus_minutes,
        "checkins_responded": checkins_responded,
        "checkins_total": checkins_total,
        "current_streak": streak,
    }


def get_active_focus_session():
    """Retorna a focus session ativa, se houver."""
    focus = load_focus_sessions()
    for fs in focus.get("active_sessions", []):
        if fs.get("status") == "active":
            return fs
    return None


def is_in_focus_session():
    """Verifica se Lucas está em uma focus session ativa agora."""
    _, now_epoch = brt_now()
    fs = get_active_focus_session()
    if not fs:
        return False
    # Verifica se a sessão ainda está no tempo (com margem para retry)
    end_epoch = fs.get("end_epoch", 0)
    return now_epoch < end_epoch + FOCUS_RETRY_WINDOW_SEC


# ─── Focus Session Retry ──────────────────────────────────────────────

def check_focus_session_retry():
    """Verifica se há focus sessions que precisam de retry de check-in.
    Retorna uma action JSON se precisar enviar, ou None se não."""
    now_brt, now_epoch = brt_now()
    focus = load_focus_sessions()

    for fs in focus.get("active_sessions", []):
        if fs.get("status") != "active":
            continue

        end_epoch = fs.get("end_epoch", 0)
        midpoint_epoch = fs.get("midpoint_epoch", 0)
        task = fs.get("task", "?")
        duration = fs.get("duration_minutes", 0)

        # Retry mid-point: se passou o midpoint_epoch e midpoint_sent é False
        # Janela: midpoint_epoch até midpoint_epoch + FOCUS_RETRY_WINDOW_SEC
        if (midpoint_epoch and
            not fs.get("midpoint_sent") and
            midpoint_epoch <= now_epoch < midpoint_epoch + FOCUS_RETRY_WINDOW_SEC):

            # Verifica se o usuário já respondeu
            if fs.get("user_responded_midpoint"):
                continue

            fs["midpoint_sent"] = True
            save_focus_sessions(focus)

            msg = f"Faz {duration // 2}min. Ainda em {task}?"
            return json.dumps({
                "action": "focus_session_checkin",
                "subtype": "midpoint",
                "session_id": fs.get("id"),
                "message": msg,
            })

        # Retry end: se passou o end_epoch e end_sent é False
        # Janela: end_epoch até end_epoch + FOCUS_RETRY_WINDOW_SEC
        if (end_epoch and
            not fs.get("end_sent") and
            end_epoch <= now_epoch < end_epoch + FOCUS_RETRY_WINDOW_SEC):

            # Verifica se o usuário já respondeu
            if fs.get("user_responded_end"):
                continue

            fs["end_sent"] = True
            save_focus_sessions(focus)

            msg = f"Tempo de {task} acabou. Como foi?"
            return json.dumps({
                "action": "focus_session_checkin",
                "subtype": "end",
                "session_id": fs.get("id"),
                "message": msg,
            })

        # Escalação: se end foi enviado mas sem resposta, após FOCUS_RETRY_WINDOW_SEC
        if (fs.get("end_sent") and
            not fs.get("user_responded_end") and
            now_epoch >= end_epoch + FOCUS_RETRY_WINDOW_SEC and
            not fs.get("escalation_sent")):

            fs["escalation_sent"] = "escalation_1"
            save_focus_sessions(focus)

            msg = f"Ei, a sessão de {task} acabou. Conseguiu avançar?"
            return json.dumps({
                "action": "focus_session_checkin",
                "subtype": "escalation",
                "session_id": fs.get("id"),
                "message": msg,
            })

        # Escalação final: após mais um FOCUS_RETRY_WINDOW_SEC
        if (fs.get("escalation_sent") == "escalation_1" and
            not fs.get("user_responded_end") and
            now_epoch >= end_epoch + (FOCUS_RETRY_WINDOW_SEC * 2) and
            fs.get("escalation_sent") != "escalation_2"):

            fs["escalation_sent"] = "escalation_2"
            fs["status"] = "expired"
            save_focus_sessions(focus)

            # Atualiza daily summary com status expirado
            today = now_brt.strftime("%Y-%m-%d")
            summary = load_daily_summary(today)
            if summary:
                tasks = summary.get("tasks") or []
                for t in tasks:
                    if t.get("id", "").startswith("focus-") and task.lower() in t.get("name", "").lower():
                        t["status"] = "em andamento"
                        t["notes"] = (t.get("notes") or "") + f" | Focus session expirada sem resposta"
                        break
                save_daily_summary(today, summary)

            msg = f"Preciso fechar o status. {task} estava em andamento. Correto?"
            return json.dumps({
                "action": "focus_session_checkin",
                "subtype": "escalation_final",
                "session_id": fs.get("id"),
                "message": msg,
            })

    return None


# ─── Task Stale Detection ─────────────────────────────────────────────

def check_stale_tasks(date_str, now_brt):
    """Verifica tasks em andamento há mais de 3 dias sem update.
    Retorna lista de tasks stale para incluir na mensagem do check-in."""
    summary = load_daily_summary(date_str)
    if not summary:
        # Tenta carregar o último summary disponível
        _, summary = load_last_available_summary(days_back=7, start_offset=1)
        if not summary:
            return []

    tasks = summary.get("tasks") or []
    stale_tasks = []
    threshold_days = 3

    for t in tasks:
        if t.get("status") != "em andamento":
            continue

        # Verifica data de início (since)
        since_str = t.get("since")
        if not since_str:
            continue

        try:
            since_date = datetime.strptime(since_str, "%Y-%m-%d").replace(tzinfo=TZ)
            days_in_progress = (now_brt - since_date).days
            if days_in_progress >= threshold_days:
                stale_tasks.append({
                    "name": t.get("name", "?"),
                    "since": since_str,
                    "days": days_in_progress,
                    "notes": t.get("notes", ""),
                })
        except ValueError:
            continue

    return stale_tasks


def format_stale_tasks_message(stale_tasks):
    """Formata mensagem de tasks stale para incluir no check-in."""
    if not stale_tasks:
        return ""

    lines = ["\n\n⚠️ *Tasks em andamento há mais de 3 dias:*"]
    for t in stale_tasks:
        lines.append(f"• {t['name']} — desde {t['since']} ({t['days']} dias)")
    lines.append("Alguma atualização sobre essas?")
    return "\n".join(lines)


# ─── Mensagens ────────────────────────────────────────────────────────

MSG_CHECKIN = {
    1: {
        "with_context": (
            "Bom dia, Lucas! 🌅\n\n"
            "📋 *Último registro ({date_label}):*\n{summary}\n\n"
            "Bora pra hoje — qual o foco?\n"
            "Qual a coisa mais importante pra entregar hoje? E tem algo burocrático que quer tirar do caminho cedo?"
        ),
        "no_context": (
            "Bom dia, Lucas! 🌅\n\n"
            "{streak_context}\n\n"
            "O que rolou? E qual o plano pra hoje?\n"
            "Qual a coisa mais importante pra entregar hoje? E tem algo burocrático que quer tirar do caminho cedo?"
        ),
        "with_yesterday_plan": (
            "Bom dia, Lucas! 🌅\n\n"
            "📋 *Último registro ({date_label}):*\n{summary}\n\n"
            "Ontem você planejou começar com: {yesterday_plan}\n"
            "Ainda faz sentido? Qual a coisa mais importante pra entregar hoje?"
        ),
    },
    2: {
        "with_context": (
            "Check-in do meio dia! 🕐\n\n"
            "Até agora:\n{today_plan}\n{today_intention}\n\n"
            "Alguma atualização? Algo travando?"
        ),
        "no_context": (
            "Check-in do meio dia! 🕐\n\n"
            "{streak_context}\n\n"
            "Como está o andamento? Conseguiu avançar? Algo travando?"
        ),
    },
    3: {
        "with_context": (
            "Fim do dia! 🌆\n\n"
            "O que você compartilhou hoje:\n{today_plan}\n{today_intention}\n\n"
            "O que mais rolou? Algo concluído ou ficou pendente?\n"
            "Qual vai ser sua primeira tarefa amanhã?"
        ),
        "no_context": (
            "Fim do dia! 🌆\n\n"
            "{streak_context}\n\n"
            "Como foi o dia? O que conseguiu concluir? Algo ficou pendente?\n"
            "Qual vai ser sua primeira tarefa amanhã?"
        ),
    },
}

MSG_FOLLOWUP = (
    "Só checando — viu a mensagem anterior? 📬\n"
    "Sem pressa, só quero saber se está por aí!"
)

MSG_REENGAGEMENT = (
    "Lucas, ainda não registramos nada hoje. 2 minutos, status rápido? 📝"
)

MSG_PROACTIVE_FOCUS = (
    "Tem {duration}min livres até {end_time}h. 📅\n"
    "{task_hint}"
    "Quer focar?"
)

MSG_MISSED_RECAP = (
    "\n\n💡 *PS:* Não nos falamos no check-in anterior — "
    "se quiser retomar algo, fique à vontade!"
)

MSG_W3_ESCALATION_1 = (
    "Fim do dia passou. Status rápido? 📝"
)

MSG_W3_ESCALATION_2 = (
    "Preciso fechar o status. Baseado no que registrei:\n"
    "{tentative_summary}\n\n"
    "Correto?"
)

# ─── Re-engagement ───────────────────────────────────────────────────

def check_reengagement():
    """Verifica se devemos enviar mensagem de re-engagement (~15h BRT).
    Dispara quando nenhum check-in do dia foi respondido até agora."""
    now_brt, now_epoch = brt_now()

    # Janela de re-engagement: 15:00–15:55 BRT (18:00-18:55 UTC)
    if now_brt.hour != 15:
        return None

    state = load_state()
    windows = state.get("windows", {})

    # Verifica se algum check-in já foi respondido hoje
    for w_str in ("1", "2", "3"):
        ws = windows.get(w_str)
        if ws and ws.get("user_responded_at"):
            return None  # usuário já respondeu algum check-in, não precisa

    # Verifica se algum check-in ainda vai acontecer (W3 ainda não passou)
    w3 = windows.get("3")
    w3_scheduled = w3.get("scheduled_epoch") if w3 else None
    if w3_scheduled and w3_scheduled > now_epoch:
        return None  # W3 ainda vai acontecer, não re-engage ainda

    # Verifica se está em focus session ativa
    if is_in_focus_session():
        return None

    return json.dumps({
        "action": "send_reengagement",
        "window": 0,
        "message": MSG_REENGAGEMENT,
    })


def build_intention_context(date_str):
    """Constrói string de contexto com a intenção do dia, se registrada."""
    summary = load_daily_summary(date_str)
    if not summary:
        return ""
    intention = summary.get("intention", "")
    if intention:
        return f"\n📌 *Intenção do dia:* {intention}"
    return ""


def load_yesterday_plan(today_date_str):
    """Carrega o plans_for_next_day do daily_summary de hoje (se foi criado na noite anterior)."""
    summary = load_daily_summary(today_date_str)
    if not summary:
        return None
    return summary.get("plans_for_next_day")


# ─── Google Calendar ─────────────────────────────────────────────────

def _get_calendar_service():
    """Autentica com service account e retorna o serviço Calendar API."""
    if not HAS_GOOGLE:
        return None
    if not os.path.exists(GOOGLE_SERVICE_ACCOUNT_PATH):
        return None
    try:
        creds = service_account.Credentials.from_service_account_file(
            GOOGLE_SERVICE_ACCOUNT_PATH,
            scopes=["https://www.googleapis.com/auth/calendar.readonly"],
        )
        return build("calendar", "v3", credentials=creds)
    except Exception:
        return None


def get_free_windows(date_brt):
    """Consulta Google Calendar e retorna blocos livres >= 60min entre 09h-18h BRT.
    Retorna lista de (start_epoch, end_epoch, duration_minutes)."""
    if not GOOGLE_CALENDAR_ID:
        return []

    service = _get_calendar_service()
    if not service:
        return []

    try:
        day_start = date_brt.replace(hour=PROACTIVE_WINDOW_START, minute=0, second=0, microsecond=0)
        day_end = date_brt.replace(hour=PROACTIVE_WINDOW_END, minute=0, second=0, microsecond=0)

        time_min = day_start.isoformat()
        time_max = day_end.isoformat()

        events_result = (
            service.events()
            .list(
                calendarId=GOOGLE_CALENDAR_ID,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        busy = []
        for event in events_result.get("items", []):
            start = event["start"].get("dateTime", event["start"].get("date"))
            end = event["end"].get("dateTime", event["end"].get("date"))
            if "T" not in start:
                continue  # eventos all-day, ignorar
            busy.append((
                int(datetime.fromisoformat(start).timestamp()),
                int(datetime.fromisoformat(end).timestamp()),
            ))

        busy.sort()

        free_windows = []
        cursor = int(day_start.timestamp())
        day_end_epoch = int(day_end.timestamp())

        for bs, be in busy:
            if bs > cursor:
                duration = (bs - cursor) // 60
                if duration >= PROACTIVE_MIN_DURATION:
                    free_windows.append((cursor, bs, duration))
            cursor = max(cursor, be)

        if day_end_epoch > cursor:
            duration = (day_end_epoch - cursor) // 60
            if duration >= PROACTIVE_MIN_DURATION:
                free_windows.append((cursor, day_end_epoch, duration))

        return free_windows

    except Exception:
        return []


def get_pending_task(date_str):
    """Busca a task pendente ou em andamento mais antiga do daily summary."""
    summary = load_daily_summary(date_str)
    if not summary:
        _, summary = load_last_available_summary(days_back=7, start_offset=1)
        if not summary:
            return None

    tasks = summary.get("tasks") or []
    for t in tasks:
        if t.get("status") in ("pendente", "em andamento"):
            return t.get("name", "")
    return None


def check_proactive_suggestion():
    """Verifica se devemos sugerir um foco baseado no calendário.
    Retorna uma action JSON ou None."""
    now_brt, now_epoch = brt_now()

    if now_brt.hour < PROACTIVE_WINDOW_START or now_brt.hour >= PROACTIVE_WINDOW_END:
        return None

    if is_in_focus_session():
        return None

    # Verifica se o usuário já interagiu hoje
    state = load_state()
    windows = state.get("windows", {})
    for w_str in ("1", "2", "3"):
        ws = windows.get(w_str)
        if ws and ws.get("user_responded_at"):
            return None

    # Cooldown
    last = state.get("proactive_suggestion_last") or 0
    if now_epoch - last < PROACTIVE_COOLDOWN_SEC:
        return None

    free_windows = get_free_windows(now_brt)
    if not free_windows:
        return None

    for start_epoch, end_epoch, duration in free_windows:
        if end_epoch <= now_epoch:
            continue
        if start_epoch < now_epoch - 1800:
            continue
        if start_epoch > now_epoch + 900:
            continue
            end_dt = datetime.fromtimestamp(end_epoch, tz=TZ)
            end_time = end_dt.strftime("%H:%M")

            task = get_pending_task(now_brt.strftime("%Y-%m-%d"))
            task_hint = f"Sugestão: {task}.\n" if task else ""

            msg = MSG_PROACTIVE_FOCUS.format(
                duration=duration,
                end_time=end_time,
                task_hint=task_hint,
            )

            state["proactive_suggestion_last"] = now_epoch
            save_state(state)

            return json.dumps({
                "action": "suggest_focus",
                "window": 0,
                "message": msg,
            })

    return None


# ─── Lógica Principal ─────────────────────────────────────────────────

def main():
    now_brt, now_epoch = brt_now()
    today = now_brt.strftime("%Y-%m-%d")
    weekday = now_brt.weekday()  # 0=Seg, 6=Dom

    # Fim de semana — não faz nada
    if weekday >= 5:
        print(json.dumps({"action": "none", "reason": "weekend"}))
        print(json.dumps({"wakeAgent": False}))
        return

    # Feriado — não faz nada
    if today in HOLIDAYS:
        print(json.dumps({"action": "none", "reason": "holiday"}))
        print(json.dumps({"wakeAgent": False}))
        return

    state = load_state()

    # ── Rollover: novo dia ──────────────────────────────────────────
    if state.get("date") != today:
        # Salva métricas do dia anterior no daily summary (se existir)
        prev_date = state.get("date")
        if prev_date:
            prev_summary = load_daily_summary(prev_date)
            if prev_summary and not prev_summary.get("metrics"):
                metrics = calculate_metrics(prev_date)
                prev_summary["metrics"] = metrics
                save_daily_summary(prev_date, prev_summary)

        state = {"date": today, "windows": {}, "weekly_report_sent": state.get("weekly_report_sent", {})}
        today_midnight = now_brt.replace(hour=0, minute=0, second=0, microsecond=0)
        for w in (1, 2, 3):
            scheduled = random_epoch_in_window(w, today_midnight)
            marker = f"RESP-W{w}-{today}-{random.randint(1000,9999)}"
            state["windows"][str(w)] = {
                "scheduled_epoch": scheduled,
                "checkin_sent_at": None,
                "user_responded_at": None,
                "followup_action": None,   # "sent" | "skipped" | "expired"
                "followup_sent_at": None,
                "escalation_sent": None,    # "escalation_1" | "escalation_2" | null
                "marker": marker,
            }
        save_state(state)

    # ── Focus Session Retry ─────────────────────────────────────────
    # Verifica se há focus sessions que precisam de retry
    focus_retry = check_focus_session_retry()
    if focus_retry:
        print(focus_retry)
        return

    # ── Resumo diário (18:30) ───────────────────────────────────────
    if now_brt.hour == 18 and now_brt.minute == 30:
        summary_path = f"{SUMMARY_PREFIX}_{today}.md"
        json_path = f"{SUMMARY_PREFIX}_{today}.json"
        if not os.path.exists(summary_path) and not os.path.exists(json_path):
            # Inclui focus sessions e métricas no resumo
            focus = load_focus_sessions()
            metrics = calculate_metrics(today)
            print(json.dumps({
                "action": "generate_daily_summary",
                "date": today,
                "windows": state["windows"],
                "focus_sessions": focus.get("completed_today", []),
                "metrics": metrics,
            }))
            return

    # ── Relatório semanal (Sexta 18:00) ─────────────────────────────
    if weekday == 4 and now_brt.hour == 18 and now_brt.minute == 0:
        week_key = now_brt.strftime("%Y-W%W")
        if not state.get("weekly_report_sent", {}).get(week_key):
            summaries = load_week_summaries()
            if summaries:
                print(json.dumps({
                    "action": "generate_weekly_report",
                    "week_key": week_key,
                    "date": today,
                    "summary_count": len(summaries),
                }))
                return

    # ── Check-ins e Follow-ups ──────────────────────────────────────
    windows = state.get("windows", {})

    for w_str in ("1", "2", "3"):
        ws = windows.get(w_str)
        if not ws:
            continue
        w_int = int(w_str)

        scheduled = ws.get("scheduled_epoch")
        sent_at = ws.get("checkin_sent_at")
        responded_at = ws.get("user_responded_at")
        followup_action = ws.get("followup_action")
        escalation_sent = ws.get("escalation_sent")
        marker = ws.get("marker")

        # Se scheduled é None — janela nunca foi agendada, pula
        if scheduled is None:
            continue

        # ── Check-in ──────────────────────────────────────────────
        if not sent_at and scheduled <= now_epoch < scheduled + CHECKIN_WINDOW_SEC:
            # Se Lucas está em focus session, pula check-in regular
            if is_in_focus_session():
                ws["followup_action"] = "skipped"
                save_state(state)
                print(json.dumps({"action": "none", "reason": "user_in_focus_session"}))
                print(json.dumps({"wakeAgent": False}))
                return

            templates = MSG_CHECKIN[w_int]
            if w_int == 1:
                # W1: busca o último daily_summary em até 7 dias
                last_date, yesterday = load_last_available_summary(days_back=7, start_offset=1)

                # Verifica se existe plano de ontem para hoje
                yesterday_plan = load_yesterday_plan(today)

                if yesterday_plan and yesterday and yesterday.get("summary_text"):
                    last_dt = datetime.strptime(last_date, "%Y-%m-%d").replace(tzinfo=TZ)
                    yesterday_dt = now_brt - timedelta(days=1)
                    if last_date == yesterday_dt.strftime("%Y-%m-%d"):
                        date_label = "ontem"
                    else:
                        dias_semana = ["segunda-feira", "terça-feira", "quarta-feira",
                                       "quinta-feira", "sexta-feira", "sábado", "domingo"]
                        date_label = f"{dias_semana[last_dt.weekday()]}, {last_dt.strftime('%d/%m')}"
                    msg = templates["with_yesterday_plan"].format(
                        date_label=date_label,
                        summary=yesterday["summary_text"],
                        yesterday_plan=yesterday_plan,
                    )
                elif yesterday and yesterday.get("summary_text"):
                    last_dt = datetime.strptime(last_date, "%Y-%m-%d").replace(tzinfo=TZ)
                    yesterday_dt = now_brt - timedelta(days=1)
                    if last_date == yesterday_dt.strftime("%Y-%m-%d"):
                        date_label = "ontem"
                    else:
                        dias_semana = ["segunda-feira", "terça-feira", "quarta-feira",
                                       "quinta-feira", "sexta-feira", "sábado", "domingo"]
                        date_label = f"{dias_semana[last_dt.weekday()]}, {last_dt.strftime('%d/%m')}"
                    msg = templates["with_context"].format(
                        date_label=date_label,
                        summary=yesterday["summary_text"],
                    )
                else:
                    streak = build_streak_context()
                    msg = templates["no_context"].format(streak_context=streak)

                # Task stale detection no W1
                stale_tasks = check_stale_tasks(today, now_brt)
                if stale_tasks:
                    msg += format_stale_tasks_message(stale_tasks)

            else:
                # W2 e W3 — carrega resumo do dia para contexto
                today_summary = load_daily_summary(today)
                # Intenção do dia
                today_intention = build_intention_context(today)
                # Fallback: se não tem do dia, busca o último disponível
                if not today_summary:
                    _, today_summary = load_last_available_summary(days_back=7, start_offset=1)
                if today_summary and (today_summary.get("tasks") or today_summary.get("tasks_discussed")):
                    tasks_list = today_summary.get("tasks") or today_summary.get("tasks_discussed") or []
                    tasks_lines = []
                    for t in tasks_list:
                        desc = t.get("name") or t.get("desc", "?")
                        status = t.get("status", "?")
                        tasks_lines.append(f"• {desc} → {status}")
                    today_plan = "\n".join(tasks_lines)
                    msg = templates["with_context"].format(today_plan=today_plan, today_intention=today_intention)
                else:
                    streak = build_streak_context()
                    msg = templates["no_context"].format(streak_context=streak)

            # Recap de janela anterior não respondida
            prev_w = str(w_int - 1)
            if prev_w in windows:
                pw = windows[prev_w]
                if pw.get("checkin_sent_at") and not pw.get("user_responded_at") and pw.get("followup_action") != "skipped":
                    msg += MSG_MISSED_RECAP

            ws["checkin_sent_at"] = now_epoch
            save_state(state)

            print(json.dumps({
                "action": "send_checkin",
                "window": w_int,
                "message": msg,
                "marker": marker,
            }))
            return

        # ── Follow-up ─────────────────────────────────────────────
        if sent_at and not responded_at and not followup_action:
            followup_start = sent_at + FOLLOWUP_DELAY_SEC
            if followup_start <= now_epoch < followup_start + FOLLOWUP_WINDOW_SEC:
                print(json.dumps({
                    "action": "send_followup",
                    "window": w_int,
                    "message": MSG_FOLLOWUP,
                    "marker": marker,
                }))
                return
            elif now_epoch >= followup_start + FOLLOWUP_WINDOW_SEC:
                ws["followup_action"] = "expired"
                save_state(state)

        # ── Escalação W3 (end-of-day obrigatório) ─────────────────
        if w_int == 3 and sent_at and not responded_at and followup_action == "expired" and not escalation_sent:
            escalation_start = sent_at + FOLLOWUP_DELAY_SEC + FOLLOWUP_WINDOW_SEC + ESCALATION_DELAY_SEC
            if escalation_start <= now_epoch < escalation_start + FOLLOWUP_WINDOW_SEC:
                # Primeira escalação
                ws["escalation_sent"] = "escalation_1"
                save_state(state)
                print(json.dumps({
                    "action": "send_escalation",
                    "window": w_int,
                    "message": MSG_W3_ESCALATION_1,
                    "marker": marker,
                }))
                return
            elif now_epoch >= escalation_start + FOLLOWUP_WINDOW_SEC and escalation_sent == "escalation_1":
                # Segunda escalação — gera resumo tentativo
                ws["escalation_sent"] = "escalation_2"
                save_state(state)

                # Monta resumo tentativo
                today_summary = load_daily_summary(today)
                tentative = "Sem atividade registrada hoje."
                if today_summary:
                    tasks = today_summary.get("tasks") or []
                    if tasks:
                        lines = []
                        for t in tasks:
                            desc = t.get("name") or t.get("desc", "?")
                            status = t.get("status", "?")
                            lines.append(f"• {desc} → {status}")
                        tentative = "\n".join(lines)
                    elif today_summary.get("summary_text"):
                        tentative = today_summary["summary_text"]

                msg = MSG_W3_ESCALATION_2.format(tentative_summary=tentative)
                print(json.dumps({
                    "action": "send_escalation",
                    "window": w_int,
                    "message": msg,
                    "marker": marker,
                }))
                return

    # ── Sugestão proativa de foco (Google Calendar) ────────────────
    proactive = check_proactive_suggestion()
    if proactive:
        print(proactive)
        return

    # ── Re-engagement (~15h BRT) ───────────────────────────────────
    reengagement = check_reengagement()
    if reengagement:
        print(reengagement)
        return

    # Nada a fazer
    print(json.dumps({"action": "none"}))
    print(json.dumps({"wakeAgent": False}))


if __name__ == "__main__":
    main()
