#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
SKETCHPAD="$REPO_ROOT/hermes-data/sketchpad"
CHANGELOG="$SKETCHPAD/CHANGELOG.md"
TODAY=$(date +%Y-%m-%d)

mkdir -p "$SKETCHPAD"

hash=$(git -C "$REPO_ROOT" log -1 --format="%h")
msg=$(git -C "$REPO_ROOT" log -1 --format="%s")
files_changed=$(git -C "$REPO_ROOT" log -1 --shortstat --format="" | sed 's/^ *//')
insertions=$(git -C "$REPO_ROOT" log -1 --shortstat --format="" | grep -oP '\d+(?= insertion)' || echo "0")
deletions=$(git -C "$REPO_ROOT" log -1 --shortstat --format="" | grep -oP '\d+(?= deletion)' || echo "0")

if [ ! -f "$CHANGELOG" ]; then
    echo "# Changelog" > "$CHANGELOG"
    echo >> "$CHANGELOG"
fi

if grep -q "$hash" "$CHANGELOG" 2>/dev/null; then
    echo "Commit $hash already in CHANGELOG.md — skipping"
    exit 0
fi

{
    echo "## $TODAY"
    echo "- \`$hash\` $msg"
    echo "  - ${files_changed:-(no stat)} (${insertions}/-${deletions})"
    echo
} >> "$CHANGELOG"

echo "Appended commit $hash to $CHANGELOG"
