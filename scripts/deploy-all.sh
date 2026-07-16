#!/usr/bin/env bash
set -uo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

failures=()

step() { echo -e "\n${GREEN}==>${NC} $1"; }
fail() { echo -e "${RED}  FAIL:${NC} $1"; failures+=("$1"); }

verify_checksum() {
    local host_path="$1"
    local container_path="$2"
    local host_sum
    local container_sum
    host_sum=$(md5sum "$REPO_ROOT/$host_path" | awk '{print $1}')
    container_sum=$(docker exec hermes md5sum "$container_path" 2>/dev/null | awk '{print $1}')
    if [ "$host_sum" = "$container_sum" ]; then
        echo -e "  ${GREEN}OK${NC}   $host_path"
    else
        fail "Checksum mismatch: $host_path ($host_sum) vs container ($container_sum)"
    fi
}

step "Step 1: Validation"
if bash "$REPO_ROOT/hermes-data/tests/validate.sh"; then
    echo -e "  ${GREEN}OK${NC}   validation passed"
else
    fail "Validation failed"
fi

step "Step 2: Deploy"
if bash "$REPO_ROOT/deploy.sh"; then
    echo -e "  ${GREEN}OK${NC}   deploy succeeded"
else
    fail "Deploy script failed"
fi

step "Step 3: Wait for container restart"
sleep 5

step "Step 4: Health check — checksum verification"
verify_checksum "hermes-data/scripts/checkin.py"         "/opt/data/scripts/checkin.py"
verify_checksum "hermes-data/SOUL.md"                    "/opt/data/profiles/accountability/SOUL.md"
verify_checksum "hermes-data/plugins/accountability-tools/tools.py" "/opt/data/plugins/accountability-tools/tools.py"

step "Step 5: Cron health"
if docker exec hermes hermes -p accountability cron list 2>/dev/null | grep c9e31c8f7b6a | grep -q 'ok'; then
    echo -e "  ${GREEN}OK${NC}   cron job healthy (last_status=ok)"
else
    fail "Cron job c9e31c8f7b6a not healthy"
fi

echo
if [ ${#failures[@]} -eq 0 ]; then
    echo -e "Deploy: ${GREEN}OK ✅${NC}"
else
    echo -e "Deploy: ${RED}FAILED ❌${NC}"
    for f in "${failures[@]}"; do
        echo -e "  ${RED}•${NC} $f"
    done
    exit 1
fi
