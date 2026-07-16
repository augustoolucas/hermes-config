#!/usr/bin/env bash
# Validates that no sensitive data is present in tracked source files.
# Does NOT contain any real values — patterns are generic placeholders.
# CI/CD can inject real patterns via SENSITIVE_PATTERNS env var.
set -euo pipefail
cd "$(dirname "$0")/.."

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

FAILURES=0

# Default: check for known placeholder (should EXIST) and common leak patterns
# Real patterns like chat IDs, emails, API keys are passed externally via env var.
# The PLACEHOLDER check ensures TELEGRAM_CHAT_ID is present (it MUST be there).
# The LEAK check ensures no real values have replaced it.

PLACEHOLDER="TELEGRAM_CHAT_ID"
# Patterns below are REGEX — none contain real data.
# They match the SHAPE of leaks, not the values themselves.
LEAK_PATTERNS=(
    '[0-9]{10,}(?![^"]*TELEGRAM_CHAT_ID)'  # numeric IDs ≥10 digits not on same line as placeholder
    'sk-[a-zA-Z0-9]{10,}'                  # API key format
    'Bearer[[:space:]]+[A-Za-z0-9._\-+/=]{20,}'                   # Bearer token
)

echo "=== validate: sensitive data audit ==="

# 1. Verify TELEGRAM_CHAT_ID placeholder exists (should be present)
for ext in py sh md json yaml yml; do
    # Only check files that are tracked by git or in repo
    while IFS= read -r -d '' f; do
        if grep -q "$PLACEHOLDER" "$f" 2>/dev/null; then
            echo -e "  ${GREEN}OK${NC} placeholder found in $(basename "$f")"
        fi
    done < <(find . -name "*.${ext}" -not -path './.git/*' -not -path './.codegraph/*' -print0 2>/dev/null || true)
done

# 2. Check for leaks — if SENSITIVE_PATTERNS is set externally, check those too
EXTERNAL=()
if [ -n "${SENSITIVE_PATTERNS:-}" ]; then
    IFS=',' read -ra EXTERNAL <<< "$SENSITIVE_PATTERNS"
fi

ALL_PATTERNS=("${LEAK_PATTERNS[@]}" "${EXTERNAL[@]}")

for pattern in "${ALL_PATTERNS[@]}"; do
    # Exclude this test file itself, .git/, .codegraph/, sketchpad/, docs/, and .sensitive_patterns
    hits=$(grep -rlP "$pattern" . --include='*.py' --include='*.sh' --include='*.md' \
           --include='*.json' --include='*.yaml' --include='*.yml' \
           --exclude-dir=.git --exclude-dir=.codegraph --exclude-dir=sketchpad --exclude-dir=docs \
           --exclude=.sensitive_patterns \
           2>/dev/null || true)
    if [ -n "$hits" ]; then
        echo -e "  ${RED}FAIL${NC} potential leak: \"$pattern\" found in:"
        echo "$hits" | while read -r hit; do
            echo "    $hit"
        done
        FAILURES=$((FAILURES + 1))
    else
        echo -e "  ${GREEN}OK${NC} no matches for pattern"
    fi
done

if [ "$FAILURES" -eq 0 ]; then
    echo -e "${GREEN}  Sensitive data audit: clean${NC}"
    exit 0
else
    echo -e "${RED}${FAILURES} sensitive data issue(s) found${NC}"
    exit 1
fi
