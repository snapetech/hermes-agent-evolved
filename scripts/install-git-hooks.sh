#!/usr/bin/env bash
# install-git-hooks.sh — install fork-safety git hooks for this checkout.
#
# Hooks installed:
#   pre-push  → scripts/hooks/pre-push
#     - Hard-blocks pushes to NousResearch upstream remotes.
#     - Warns when commits being pushed lack HERMES_CHANGELOG entries.
#
# Idempotent. Re-run after upstream syncs or fresh clones.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
HOOKS_SRC="$REPO_ROOT/scripts/hooks"
HOOKS_DST="$(git -C "$REPO_ROOT" rev-parse --git-path hooks)"

mkdir -p "$HOOKS_DST"

for hook in pre-push; do
  src="$HOOKS_SRC/$hook"
  dst="$HOOKS_DST/$hook"
  if [[ ! -f "$src" ]]; then
    echo "missing source hook: $src" >&2
    exit 1
  fi
  # Use symlinks when possible so hook changes flow without reinstall.
  if [[ -L "$dst" || -f "$dst" ]]; then
    rm -f "$dst"
  fi
  ln -s "$src" "$dst"
  chmod +x "$src"
  echo "installed: $dst -> $src"
done

echo ""
echo "Hooks installed. Verify with: ls -la $HOOKS_DST"
echo "Test: git push --dry-run origin main  (should succeed, optionally warn)"
echo "Test: git push --dry-run upstream main (should hard-block)"
