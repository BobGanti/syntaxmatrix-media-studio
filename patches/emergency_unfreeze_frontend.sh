#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-.}"
INDEX="$ROOT/frontend/index.html"
APP="$ROOT/frontend/app.js"
CSS="$ROOT/frontend/styles.css"

if [ ! -f "$INDEX" ] || [ ! -f "$APP" ] || [ ! -f "$CSS" ]; then
  echo "ERROR: Run this from the project root where frontend/index.html, frontend/app.js and frontend/styles.css exist." >&2
  exit 1
fi

STAMP="$(date +%Y%m%d%H%M%S)"

cp "$INDEX" "$INDEX.bak.emergency-unfreeze-$STAMP"
cp "$APP" "$APP.bak.emergency-unfreeze-$STAMP"
cp "$CSS" "$CSS.bak.emergency-unfreeze-$STAMP"

python - "$INDEX" "$APP" "$CSS" "$STAMP" <<'PY'
from pathlib import Path
import re
import sys

index_path = Path(sys.argv[1])
app_path = Path(sys.argv[2])
css_path = Path(sys.argv[3])
stamp = sys.argv[4]

html = index_path.read_text(encoding="utf-8")
app = app_path.read_text(encoding="utf-8")
css = css_path.read_text(encoding="utf-8")

# Remove the bad asset actions patch from JS if it is still present.
app = re.sub(
    r"\n// BEGIN_ASSET_ACTIONS_PATCH[\s\S]*?// END_ASSET_ACTIONS_PATCH\n?",
    "\n",
    app,
)

# Remove the bad asset actions patch from CSS if it is still present.
css = re.sub(
    r"\n/\* BEGIN_ASSET_ACTIONS_PATCH \*/[\s\S]*?/\* END_ASSET_ACTIONS_PATCH \*/\n?",
    "\n",
    css,
)

# Add a tiny emergency guard so one JS error does not swallow visibility/debugging.
if "EMERGENCY_UNFREEZE_ERROR_GUARD" not in html:
    guard = f"""
<script id="EMERGENCY_UNFREEZE_ERROR_GUARD">
  window.addEventListener('error', function (event) {{
    console.error('[AlibabaMedia frontend error]', event.error || event.message);
  }});
  window.addEventListener('unhandledrejection', function (event) {{
    console.error('[AlibabaMedia promise error]', event.reason);
  }});
  try {{
    localStorage.removeItem('alibaba-media-studio-state-v1');
    sessionStorage.setItem('alibaba-media-emergency-unfreeze', '{stamp}');
  }} catch (e) {{
    console.warn('Could not clear frontend state', e);
  }}
</script>
""".strip()

    html = re.sub(r"(<head[^>]*>)", r"\1\n" + guard, html, count=1, flags=re.I)

# Add no-cache meta tags.
if "EMERGENCY_UNFREEZE_NO_CACHE" not in html:
    no_cache = """
<meta id="EMERGENCY_UNFREEZE_NO_CACHE" http-equiv="Cache-Control" content="no-store, no-cache, must-revalidate, max-age=0">
<meta http-equiv="Pragma" content="no-cache">
<meta http-equiv="Expires" content="0">
""".strip()
    html = re.sub(r"(<head[^>]*>)", r"\1\n" + no_cache, html, count=1, flags=re.I)

# Force fresh app.js/styles.css by cache-busting references.
def bust_asset_ref(text: str, filename: str) -> str:
    # Matches app.js, ./app.js, styles.css, ./styles.css with optional existing query string.
    pattern = rf'(["\'])(\.\/)?{re.escape(filename)}(?:\?[^"\']*)?\1'
    return re.sub(
        pattern,
        lambda m: f'{m.group(1)}{m.group(2) or ""}{filename}?v=emergency-{stamp}{m.group(1)}',
        text,
    )

html = bust_asset_ref(html, "app.js")
html = bust_asset_ref(html, "styles.css")

index_path.write_text(html, encoding="utf-8")
app_path.write_text(app, encoding="utf-8")
css_path.write_text(css, encoding="utf-8")
PY

echo "Emergency frontend unfreeze applied."
echo
echo "Changed only:"
echo "  frontend/index.html"
echo "  frontend/app.js"
echo "  frontend/styles.css"
echo
echo "Backups saved with:"
echo "  .bak.emergency-unfreeze-$STAMP"
echo
echo "Now restart Flask:"
echo "  python app.py"
echo
echo "Then open a NEW browser tab:"
echo "  http://127.0.0.1:5055/?fresh=$STAMP"
