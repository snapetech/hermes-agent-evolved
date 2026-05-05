#!/usr/bin/env bash
set -euo pipefail

TARGET_DIR="${TARGET_DIR:-/workspace/hermes-agent}"
HERMES_HOME_DIR="${HERMES_HOME_DIR:-/home/example-user/.hermes-gateway}"
MARKER="${MARKER:-$HERMES_HOME_DIR/bare-metal-active}"
SERVICE="${SERVICE:-hermes-gateway.service}"
REMOTE="${REMOTE:-origin}"
BRANCH="${BRANCH:-main}"
TARGET_REF="${TARGET_REF:-$REMOTE/$BRANCH}"
LOCK_FILE="${LOCK_FILE:-$HERMES_HOME_DIR/deploy.lock}"
PYTHON="${PYTHON:-$TARGET_DIR/.venv/bin/python}"
HERMES_BIN="${HERMES_BIN:-$TARGET_DIR/.venv/bin/hermes}"

if [ ! -f "$MARKER" ]; then
  echo "bare-metal marker missing: $MARKER" >&2
  exit 2
fi

mkdir -p "$HERMES_HOME_DIR"

exec 9>"$LOCK_FILE"
flock -n 9 || {
  echo "another Hermes bare-metal deploy is already running" >&2
  exit 75
}

cd "$TARGET_DIR"

if [ ! -x "$PYTHON" ] || [ ! -x "$HERMES_BIN" ]; then
  echo "missing Hermes virtualenv/bin in $TARGET_DIR" >&2
  exit 2
fi

if [ "$(git branch --show-current)" != "$BRANCH" ]; then
  echo "refusing deploy: $TARGET_DIR is not on $BRANCH" >&2
  exit 2
fi

if [ -n "$(git status --porcelain)" ]; then
  echo "refusing deploy: $TARGET_DIR has uncommitted changes" >&2
  git status --short >&2
  exit 2
fi

old_head="$(git rev-parse HEAD)"
git fetch "$REMOTE" "$BRANCH" --tags

if ! git cat-file -e "$TARGET_REF^{commit}" 2>/dev/null; then
  echo "target ref is not available after fetch: $TARGET_REF" >&2
  exit 2
fi

git merge --ff-only "$TARGET_REF"
new_head="$(git rev-parse HEAD)"

git submodule update --init --recursive

if [ "${HERMES_BARE_METAL_SKIP_PIP:-0}" != "1" ]; then
  "$PYTHON" -m pip install -e .
fi

"$PYTHON" -m py_compile gateway/run.py gateway/platforms/discord.py gateway/platforms/telegram.py

sudo systemctl restart "$SERVICE"
sleep 2
sudo systemctl is-active --quiet "$SERVICE"

echo "bare_metal_deploy_complete service=$SERVICE old=$old_head new=$new_head"
