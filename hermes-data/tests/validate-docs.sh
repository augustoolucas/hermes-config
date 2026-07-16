#!/usr/bin/env bash
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

REPO_ROOT="$(git rev-parse --show-toplevel)"
FAILURES=0

# Extract container paths from deploy.sh docker cp commands
echo "=== extract: container paths from deploy.sh ==="
CONTAINER_PATHS=$(grep -oP 'hermes:/\S+' "$REPO_ROOT/deploy.sh" | sed 's/hermes://' | sed 's/[\"\\]//g' | sort -u)

# Also include well-known runtime paths (not copied by deploy.sh, but created at runtime)
KNOWN_RUNTIME=(
    "/opt/data/profiles/accountability/.cron/responsibility_partner/state.json"
    "/opt/data/profiles/accountability/.cron/responsibility_partner/focus_sessions.json"
    "/opt/data/profiles/accountability/.cron/responsibility_partner/daily_summary_*.md"
    "/opt/data/profiles/accountability/sessions/"
    "/opt/data/profiles/accountability/sessions/request_dump_cron_*"
    "/opt/data/profiles/accountability/sessions/request_dump_cron_c9e31c8f7b6a*"
    "/opt/data/profiles/accountability/cron/jobs.json"
    "/opt/data/cron/jobs.json"
    "/tmp/cron_jobs_template.json"
    "/opt/data/home/scripts/checkin.py"
    "/opt/data/home/.cron/responsibility_partner/checkin.py"
    "/opt/data/profiles/accountability/scripts/checkin.py"
    "/opt/data/plugins/accountability-tools"
    "/opt/data/profiles/accountability/plugins"
    "/opt/data/profiles/accountability/plugins/accountability-tools"
)

echo "  $(echo "$CONTAINER_PATHS" | wc -l) deployment paths found"

# --- Check 1: Container paths in AGENTS.md must exist in deploy.sh or known runtime ---
echo ""
echo "=== validate: container paths in AGENTS.md ==="
# Extract /opt/data/... paths from AGENTS.md
AGENT_PATHS=$(grep -oP '/opt/[a-zA-Z0-9_/.-]+' "$REPO_ROOT/AGENTS.md" | sort -u || true)

for path in $AGENT_PATHS; do
    # Skip /opt/hermes/ (bundled plugin paths), /opt/data/profiles/ (parent dirs)
    found=false
    # Check against deploy.sh container paths
    for cp in $CONTAINER_PATHS; do
        if [[ "$path" == "$cp" ]] || [[ "$cp" == "$path"* ]] || [[ "$path" == "$cp"* ]]; then
            found=true
            break
        fi
    done
    # Check against known runtime
    if [ "$found" = false ]; then
        for kr in "${KNOWN_RUNTIME[@]}"; do
            if [[ "$path" == "$kr" ]] || [[ "$kr" == "$path"* ]] || [[ "$path" == "$kr"* ]]; then
                found=true
                break
            fi
        done
    fi
    if [ "$found" = false ]; then
        echo -e "  ${RED}FAIL${NC} AGENTS.md: '$path' — not found in deploy.sh or known runtime"
        FAILURES=$((FAILURES + 1))
    else
        echo -e "  ${GREEN}OK${NC}   $path"
    fi
done
if [ -z "$AGENT_PATHS" ]; then
    echo "  (no container paths found in AGENTS.md)"
fi

# --- Check 2: Container paths in hermes-dev.md must exist ---
echo ""
echo "=== validate: container paths in .opencode/skills/hermes-dev.md ==="
SKILL="$REPO_ROOT/.opencode/skills/hermes-dev.md"
if [ -f "$SKILL" ]; then
    SKILL_PATHS=$(grep -oP '/opt/[a-zA-Z0-9_/.-]+' "$SKILL" | sort -u || true)
    for path in $SKILL_PATHS; do
        found=false
        for cp in $CONTAINER_PATHS; do
            if [[ "$path" == "$cp" ]] || [[ "$cp" == "$path"* ]] || [[ "$path" == "$cp"* ]]; then
                found=true
                break
            fi
        done
        if [ "$found" = false ]; then
            for kr in "${KNOWN_RUNTIME[@]}"; do
                # Handle wildcard patterns in known runtime
                kr_pattern="${kr//\*/.*}"
                if echo "$path" | grep -q "$kr_pattern"; then
                    found=true
                    break
                fi
                if [[ "$path" == "$kr" ]] || [[ "$kr" == "$path"* ]]; then
                    found=true
                    break
                fi
            done
        fi
        if [ "$found" = false ]; then
            echo -e "  ${RED}FAIL${NC} hermes-dev.md: '$path' — not found in deploy.sh or known runtime"
            FAILURES=$((FAILURES + 1))
        else
            echo -e "  ${GREEN}OK${NC}   $path"
        fi
    done
    if [ -z "$SKILL_PATHS" ]; then
        echo "  (no container paths found in hermes-dev.md)"
    fi
else
    echo "  ${RED}SKIP${NC} hermes-dev.md not found"
fi

# --- Check 3: Codeblocks in hermes-dev.md must use docker exec ---
echo ""
echo "=== validate: codeblocks in hermes-dev.md use docker exec ==="
if [ -f "$SKILL" ]; then
    # Find all bare commands referencing /opt/data/ — these should have docker exec
    BARE_REFS=$(grep -n '/opt/data/' "$SKILL" | grep -v 'docker exec' | grep -v '^#' | grep -v '^\s*#' || true)
    if [ -n "$BARE_REFS" ]; then
        echo -e "  ${RED}FAIL${NC} paths referencing /opt/data/ without docker exec wrapper:"
        echo "$BARE_REFS" | while read line; do
            echo "    $line"
        done
        FAILURES=$((FAILURES + 1))
    else
        echo -e "  ${GREEN}OK${NC}   all /opt/data/ references use docker exec"
    fi
else
    echo "  ${RED}SKIP${NC} hermes-dev.md not found"
fi

# --- Report ---
echo ""
if [ "$FAILURES" -eq 0 ]; then
    echo -e "${GREEN}  Docs ↔ deploy: consistent${NC}"
    exit 0
else
    echo -e "${RED}${FAILURES} doc/deploy inconsistencies found${NC}"
    exit 1
fi
