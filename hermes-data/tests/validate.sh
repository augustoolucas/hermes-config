#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

FAILURES=0

echo "=== validate: syntax ==="
for py in scripts/checkin.py plugins/accountability-tools/tools.py plugins/accountability-tools/__init__.py; do
    if python3 -c "import ast; ast.parse(open('$py').read())" 2>/dev/null; then
        echo -e "  ${GREEN}OK${NC} $py"
    else
        echo -e "  ${RED}SYNTAX ERROR${NC} $py"
        FAILURES=$((FAILURES + 1))
    fi
done

echo ""
echo "=== validate: path leaks ==="
for f in SOUL.md cron/jobs.json skills/productivity/daily-status-session/SKILL.md skills/productivity/focus-session-handler/SKILL.md skills/productivity/end-of-day-reflect/SKILL.md skills/productivity/context-recall/SKILL.md skills/productivity/task-breakdown/SKILL.md; do
    bad=$(grep -c "~/.cron/responsibility_partner\|/opt/data/.cron/responsibility_partner" "$f" 2>/dev/null || true)
    if [ "$bad" -gt 0 ]; then
        echo -e "  ${RED}FAIL${NC} $f: $bad stale path reference(s)"
        FAILURES=$((FAILURES + 1))
    else
        echo -e "  ${GREEN}OK${NC} $f"
    fi
done

echo ""
echo "=== validate: checkin.py actions have 'message' field ==="
if python3 tests/test_checkin_actions.py 2>&1; then
    echo -e "  ${GREEN}OK${NC} all actions have message field"
else
    echo -e "  ${RED}FAIL${NC} checkin.py action validation failed"
    FAILURES=$((FAILURES + 1))
fi

echo ""
echo "=== validate: tools documented in SOUL.md/SKILL.md ==="
# Extract tool names from __init__.py
tools=$(grep 'name="' plugins/accountability-tools/__init__.py | sed 's/.*name="\([^"]*\)".*/\1/')
for tool in $tools; do
    found=0
    for doc in SOUL.md skills/productivity/daily-status-session/SKILL.md skills/productivity/focus-session-handler/SKILL.md; do
        if grep -q "$tool" "$doc" 2>/dev/null; then
            found=1
            break
        fi
    done
    if [ "$found" -eq 0 ]; then
        echo -e "  ${YELLOW}WARN${NC} tool '$tool' not referenced in any doc (SOUL.md, SKILL.md)"
    else
        echo -e "  ${GREEN}OK${NC} $tool documented"
    fi
done

echo ""
echo "=== validate: cron prompt is generic (catches all actions) ==="
# The prompt now says "Para QUALQUER outro action" — no need to list each one
if grep -q "QUALQUER outro action" cron/jobs.json 2>/dev/null; then
    echo -e "  ${GREEN}OK${NC} prompt is generic — covers all actions"
else
    echo -e "  ${RED}FAIL${NC} prompt does not have generic catch-all"
    FAILURES=$((FAILURES + 1))
fi

echo ""
echo "=== validate: state machine transitions ==="
if python3 tests/test_state_machine.py 2>&1; then
    echo -e "  ${GREEN}OK${NC} state machine transitions correct"
else
    echo -e "  ${RED}FAIL${NC} state machine test failed"
    FAILURES=$((FAILURES + 1))
fi

echo ""
echo "=== validate: tool output format compatibility ==="
if python3 tests/test_tool_format.py 2>&1; then
    echo -e "  ${GREEN}OK${NC} tool outputs match consumer expectations"
else
    echo -e "  ${RED}FAIL${NC} tool format test failed"
    FAILURES=$((FAILURES + 1))
fi

echo ""
echo "=== validate: sensitive data audit ==="
if bash tests/test_sensitive_data.sh 2>&1; then
    echo -e "  ${GREEN}OK${NC} no sensitive data leaks"
else
    echo -e "  ${RED}FAIL${NC} sensitive data found"
    FAILURES=$((FAILURES + 1))
fi

echo ""
echo "=== validate: docs ↔ deploy consistency ==="
cd "$(dirname "$0")/.."
REPO_ROOT="$(git rev-parse --show-toplevel)"
if bash "$REPO_ROOT/hermes-data/tests/validate-docs.sh" 2>&1; then
    echo -e "  ${GREEN}OK${NC} docs consistent with deploy.sh"
else
    echo -e "  ${RED}FAIL${NC} docs/deploy mismatch"
    FAILURES=$((FAILURES + 1))
fi

echo ""
if [ "$FAILURES" -eq 0 ]; then
    echo -e "${GREEN}All validation checks passed.${NC}"
    exit 0
else
    echo -e "${RED}$FAILURES validation failure(s). Fix before deploying.${NC}"
    exit 1
fi
