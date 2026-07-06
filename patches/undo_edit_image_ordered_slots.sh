#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-.}"
STAMP="$(date +%Y%m%d%H%M%S)"

restore_latest_backup() {
  local target="$1"
  local label="$2"

  if [ ! -f "$target" ]; then
    echo "ERROR: Missing $target" >&2
    exit 1
  fi

  local latest
  latest="$(ls -t "$target".bak.edit-slots-* 2>/dev/null | head -n 1 || true)"

  if [ -z "$latest" ]; then
    echo "ERROR: No edit-slots backup found for $target" >&2
    echo "I did not restore $label because there is no backup matching:" >&2
    echo "  $target.bak.edit-slots-*" >&2
    exit 1
  fi

  cp "$target" "$target.broken-after-edit-slots-$STAMP"
  cp "$latest" "$target"

  echo "Restored $label from:"
  echo "  $latest"
  echo "Saved broken current version as:"
  echo "  $target.broken-after-edit-slots-$STAMP"
  echo
}

restore_latest_backup "$ROOT/frontend/app.js" "frontend/app.js"
restore_latest_backup "$ROOT/frontend/styles.css" "frontend/styles.css"
restore_latest_backup "$ROOT/app.py" "app.py"

echo "UNDO COMPLETE."
echo "Restart the app:"
echo "  python app.py"
echo
echo "Then hard refresh the browser:"
echo "  Ctrl + F5"
