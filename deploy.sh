#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

# ─── Carrega .env se existir ──────────────────────────────────────────
if [ -f .env ]; then
    set -a; source .env; set +a
fi

if [ -z "${TELEGRAM_CHAT_ID:-}" ]; then
    echo -e "${RED}Erro: TELEGRAM_CHAT_ID não definido. Configure no .env ou exporte.${NC}"
    exit 1
fi

echo "=== Substituindo placeholder e injetando no container ==="
sed "s/TELEGRAM_CHAT_ID/${TELEGRAM_CHAT_ID}/g" hermes-data/cron/jobs.json | \
    docker exec -i hermes tee /opt/data/cron/jobs.json > /dev/null

echo "=== Sincronizando cron/jobs.json para o perfil accountability ==="
docker exec hermes cp /opt/data/cron/jobs.json /opt/data/profiles/accountability/cron/jobs.json

echo "=== Criando diretório do novo skill ==="
docker exec hermes mkdir -p /opt/data/skills/productivity/unblock-helper

echo "=== Copiando arquivos para o container ==="
docker cp hermes-data/SOUL.md                         hermes:/opt/data/SOUL.md
docker cp hermes-data/SOUL.md                         hermes:/opt/data/profiles/accountability/SOUL.md
docker cp hermes-data/scripts/checkin.py               hermes:/opt/data/scripts/checkin.py
docker cp hermes-data/skills/productivity/daily-status-session/SKILL.md \
    hermes:/opt/data/skills/productivity/daily-status-session/SKILL.md
docker cp hermes-data/skills/productivity/daily-status-session/SKILL.md \
    hermes:/opt/data/profiles/accountability/skills/productivity/daily-status-session/SKILL.md
docker cp hermes-data/skills/productivity/focus-session-handler/SKILL.md \
    hermes:/opt/data/skills/productivity/focus-session-handler/SKILL.md
docker cp hermes-data/skills/productivity/focus-session-handler/SKILL.md \
    hermes:/opt/data/profiles/accountability/skills/productivity/focus-session-handler/SKILL.md
docker cp hermes-data/skills/productivity/unblock-helper/SKILL.md \
    hermes:/opt/data/skills/productivity/unblock-helper/SKILL.md
docker cp hermes-data/skills/productivity/unblock-helper/SKILL.md \
    hermes:/opt/data/profiles/accountability/skills/productivity/unblock-helper/SKILL.md

echo "=== Copiando plugin gemini_meet ==="
docker exec hermes mkdir -p /opt/data/plugins/gemini_meet
docker cp hermes-data/plugins/gemini_meet/plugin.yaml \
    hermes:/opt/data/plugins/gemini_meet/plugin.yaml
docker cp hermes-data/plugins/gemini_meet/__init__.py \
    hermes:/opt/data/plugins/gemini_meet/__init__.py
docker cp hermes-data/plugins/gemini_meet/tools.py \
    hermes:/opt/data/plugins/gemini_meet/tools.py
docker cp hermes-data/plugins/gemini_meet/gemini_live.py \
    hermes:/opt/data/plugins/gemini_meet/gemini_live.py
docker cp hermes-data/plugins/gemini_meet/realtime_speaker.py \
    hermes:/opt/data/plugins/gemini_meet/realtime_speaker.py
docker cp hermes-data/plugins/gemini_meet/meet_bot.py \
    hermes:/opt/data/plugins/gemini_meet/meet_bot.py
docker cp hermes-data/plugins/gemini_meet/process_manager.py \
    hermes:/opt/data/plugins/gemini_meet/process_manager.py
docker cp hermes-data/plugins/gemini_meet/audio_bridge.py \
    hermes:/opt/data/plugins/gemini_meet/audio_bridge.py

echo "=== Symlink no accountability profile ==="
docker exec hermes mkdir -p /opt/data/profiles/accountability/plugins
docker exec hermes rm -rf /opt/data/profiles/accountability/plugins/gemini_meet 2>/dev/null
docker exec hermes ln -sf /opt/data/plugins/gemini_meet /opt/data/profiles/accountability/plugins/gemini_meet
docker exec hermes cp /opt/data/scripts/checkin.py /opt/data/home/scripts/checkin.py
docker exec hermes cp /opt/data/scripts/checkin.py /opt/data/home/.cron/responsibility_partner/checkin.py

echo "=== Verificando md5sum ==="
HASHES=$(docker exec hermes md5sum \
    /opt/data/scripts/checkin.py \
    /opt/data/home/scripts/checkin.py \
    /opt/data/home/.cron/responsibility_partner/checkin.py \
    | awk '{print $1}' | sort -u | wc -l)

if [ "$HASHES" -eq 1 ]; then
    echo -e "${GREEN}checkin.py: 3 cópias idênticas.${NC}"
else
    echo -e "${RED}checkin.py: cópias divergiram! Execute o passo 2 manualmente.${NC}"
    exit 1
fi

echo "=== Reiniciando container ==="
docker restart hermes

echo -e "${GREEN}Deploy concluído.${NC}"
