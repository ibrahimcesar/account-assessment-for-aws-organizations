#!/usr/bin/env bash
# Configure git to use the project's .githooks directory.
# Run once after cloning:
#   chmod +x scripts/setup-hooks.sh && ./scripts/setup-hooks.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOOKS_DIR="$REPO_ROOT/.githooks"

if [ ! -d "$HOOKS_DIR" ]; then
  echo "ERROR: $HOOKS_DIR not found. Are you running from the repo root?" >&2
  exit 1
fi

# Make all hooks executable
chmod +x "$HOOKS_DIR"/*

# Point git at .githooks instead of the default .git/hooks
git -C "$REPO_ROOT" config core.hooksPath ".githooks"

echo "Git hooks installed from $HOOKS_DIR"
echo ""
echo "Active hooks:"
for f in "$HOOKS_DIR"/*; do
  echo "  $(basename "$f")"
done
