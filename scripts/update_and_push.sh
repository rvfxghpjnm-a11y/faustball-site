#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$REPO_DIR/logs"
LOG_FILE="$LOG_DIR/update.log"
mkdir -p "$LOG_DIR"

cd "$REPO_DIR"

{
  echo "==== $(date '+%F %T') ===="
  if [ ! -d .venv ]; then
    echo "FEHLER: .venv fehlt in $REPO_DIR"
    exit 1
  fi

  "$REPO_DIR/.venv/bin/python" scripts/update_faustball_data.py

  if ! git diff --quiet -- data/faustball_data.json data/debug 2>/dev/null; then
    git add data/faustball_data.json data/debug || true
    git commit -m "auto: faustball data update" || true
    git push
    echo "Push erledigt"
  else
    echo "Keine Änderungen"
  fi
} >> "$LOG_FILE" 2>&1
