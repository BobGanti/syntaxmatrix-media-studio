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
  latest="$(ls -t "$target".bak.asset-actions-* 2>/dev/null | head -n 1 || true)"

  if [ -z "$latest" ]; then
    echo "ERROR: No asset-actions backup found for $target" >&2
    echo "Expected backup like:"
    echo "  $target.bak.asset-actions-*"
    exit 1
  fi

  cp "$target" "$target.frozen-after-asset-actions-$STAMP"
  cp "$latest" "$target"

  echo "Restored $label from:"
  echo "  $latest"
  echo "Saved frozen file as:"
  echo "  $target.frozen-after-asset-actions-$STAMP"
  echo
}

restore_latest_backup "$ROOT/frontend/app.js" "frontend/app.js"
restore_latest_backup "$ROOT/frontend/styles.css" "frontend/styles.css"
restore_latest_backup "$ROOT/app.py" "app.py"

echo "UNDO COMPLETE."
echo
echo "Now restart:"
echo "  python app.py"
echo
echo "Then hard refresh browser:"
echo "  Ctrl + F5"
