#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
HOOK_SRC="$REPO_ROOT/scripts/pre-commit"
HOOK_DST="$REPO_ROOT/.git/hooks/pre-commit"

if [ -f "$HOOK_DST" ]; then
    echo "pre-commit hook already exists at .git/hooks/pre-commit — not overwriting."
    exit 0
fi

cp "$HOOK_SRC" "$HOOK_DST"
chmod +x "$HOOK_DST"

echo "pre-commit hook installed successfully."
echo ""
echo "IMPORTANT: Create .sensitive_patterns with your audit patterns:"
echo "  echo 'SEU_CHAT_ID' > .sensitive_patterns"
echo "  echo 'sk-'          >> .sensitive_patterns"
echo "  echo '@gmail'       >> .sensitive_patterns"
echo ""
echo "To reinstall: rm .git/hooks/pre-commit && bash scripts/setup-hooks.sh"
