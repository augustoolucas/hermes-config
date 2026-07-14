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

echo "=== Rodando validação pré-deploy ==="
if bash hermes-data/tests/validate.sh; then
    echo -e "${GREEN}Validação OK.${NC}"
else
    echo -e "${RED}Validação falhou. Corrija os erros antes de deploy.${NC}"
    exit 1
fi

echo "=== Substituindo placeholder e injectando no container ==="
# Write template to temp file, then merge preserving scheduler state
TEMPLATE_FILE=$(mktemp)
sed "s/TELEGRAM_CHAT_ID/${TELEGRAM_CHAT_ID}/g" hermes-data/cron/jobs.json > "$TEMPLATE_FILE"
docker cp "$TEMPLATE_FILE" hermes:/tmp/cron_jobs_template.json
rm -f "$TEMPLATE_FILE"

docker exec hermes python3 -c "
import json

with open('/tmp/cron_jobs_template.json') as f:
    template = json.load(f)

CONTAINER_PATH = '/opt/data/profiles/accountability/cron/jobs.json'
try:
    with open(CONTAINER_PATH) as f:
        container = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    container = {'jobs': []}

TEMPLATE_FIELDS = {'prompt','skills','skill','model','provider','base_url','script',
                   'context_from','schedule','schedule_display','deliver','origin',
                   'enabled_toolsets','workdir','name','enabled'}

container_jobs = {j['id']: j for j in container.get('jobs', [])}

for tjob in template.get('jobs', []):
    jid = tjob['id']
    if jid in container_jobs:
        existing = container_jobs[jid]
        for key in TEMPLATE_FIELDS:
            if key in tjob:
                existing[key] = tjob[key]
    else:
        container['jobs'].append(tjob)

with open(CONTAINER_PATH, 'w') as f:
    json.dump(container, f, indent=2, ensure_ascii=False)
print(f'Merged {len(template.get(\"jobs\", []))} job(s) — scheduler state preserved')
"

echo "=== Sincronizando cron/jobs.json para o perfil accountability ==="
docker exec hermes cp /opt/data/profiles/accountability/cron/jobs.json /opt/data/cron/jobs.json

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

echo "=== Copiando plugin accountability-tools ==="
docker exec hermes mkdir -p /opt/data/plugins/accountability-tools
docker exec hermes mkdir -p /opt/data/profiles/accountability/plugins
docker cp hermes-data/plugins/accountability-tools/plugin.yaml \
    hermes:/opt/data/plugins/accountability-tools/plugin.yaml
docker cp hermes-data/plugins/accountability-tools/__init__.py \
    hermes:/opt/data/plugins/accountability-tools/__init__.py
docker cp hermes-data/plugins/accountability-tools/tools.py \
    hermes:/opt/data/plugins/accountability-tools/tools.py
# Symlink profile plugins dir to shared plugins dir
docker exec hermes sh -c '
    TARGET=/opt/data/profiles/accountability/plugins/accountability-tools
    if [ ! -L "$TARGET" ] && [ ! -d "$TARGET" ]; then
        ln -s /opt/data/plugins/accountability-tools "$TARGET"
    fi
'
echo -e "${GREEN}Plugin accountability-tools copiado.${NC}"

echo "=== Criando diretórios dos skills ==="
docker exec hermes mkdir -p /opt/data/skills/productivity/unblock-helper

docker exec hermes cp /opt/data/scripts/checkin.py /opt/data/home/scripts/checkin.py
docker exec hermes cp /opt/data/scripts/checkin.py /opt/data/home/.cron/responsibility_partner/checkin.py
docker exec hermes mkdir -p /opt/data/profiles/accountability/scripts
docker exec hermes cp /opt/data/scripts/checkin.py /opt/data/profiles/accountability/scripts/checkin.py

echo "=== Verificando integridade de paths ==="
BAD_REFS=$(docker exec hermes sh -c '
    bad=0
    for f in /opt/data/SOUL.md \
             /opt/data/profiles/accountability/SOUL.md \
             /opt/data/profiles/accountability/cron/jobs.json \
             /opt/data/skills/productivity/daily-status-session/SKILL.md \
             /opt/data/skills/productivity/focus-session-handler/SKILL.md; do
        count=$(grep -c "~/.cron/responsibility_partner\|/opt/data/.cron/responsibility_partner" "$f" 2>/dev/null || true)
        if [ "$count" -gt 0 ]; then
            echo "  $f: $count stale path(s)" >&2
            bad=$((bad + 1))
        fi
    done
    echo "$bad"
')
if [ "$BAD_REFS" -eq 0 ]; then
    echo -e "${GREEN}Paths: todos apontam para o profile.${NC}"
else
    echo -e "${RED}Paths: $BAD_REFS arquivo(s) com referências obsoletas (~/.cron/ ou /opt/data/.cron/). Corrija antes de deploy.${NC}"
    exit 1
fi

echo "=== Verificando md5sum ==="
HASHES=$(docker exec hermes md5sum \
    /opt/data/scripts/checkin.py \
    /opt/data/home/scripts/checkin.py \
    /opt/data/home/.cron/responsibility_partner/checkin.py \
    /opt/data/profiles/accountability/scripts/checkin.py \
    | awk '{print $1}' | sort -u | wc -l)

if [ "$HASHES" -eq 1 ]; then
    echo -e "${GREEN}checkin.py: 4 cópias idênticas.${NC}"
else
    echo -e "${RED}checkin.py: cópias divergiram! Execute o passo 2 manualmente.${NC}"
    exit 1
fi

echo "=== Garantindo symlink de safety net ==="
docker exec hermes sh -c '
    TARGET=/opt/data/.cron/responsibility_partner
    SOURCE=/opt/data/profiles/accountability/.cron/responsibility_partner
    if [ ! -L "$TARGET" ]; then
        if [ -d "$TARGET" ]; then
            mv "$TARGET" "${TARGET}.bak.$(date +%s)"
        fi
        ln -s "$SOURCE" "$TARGET"
        echo "Symlink criado: $TARGET -> $SOURCE"
    else
        CURRENT=$(readlink "$TARGET")
        if [ "$CURRENT" != "$SOURCE" ]; then
            rm "$TARGET"
            ln -s "$SOURCE" "$TARGET"
            echo "Symlink corrigido: $TARGET -> $SOURCE"
        else
            echo "Symlink já existe e está correto."
        fi
    fi
'

echo "=== Reiniciando container ==="
docker restart hermes
sleep 3

echo "=== Pausando jobs no perfil default (só accountability deve rodar) ==="
docker exec hermes hermes -p default cron pause c9e31c8f7b6a 2>/dev/null || true
docker exec hermes hermes -p default cron pause c102a47935ce 2>/dev/null || true

echo -e "${GREEN}Deploy concluído.${NC}"
