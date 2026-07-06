from pathlib import Path
from datetime import datetime
import re
import py_compile

ROOT = Path(".").resolve()
APP = ROOT / "app.py"
FRONTEND = ROOT / "frontend"
VOICE_CLIENT = FRONTEND / "voice_clone_client.html"
VIEWS = ROOT / "views"

if not APP.exists():
    print("ERROR: app.py not found. Run from the project root.")
    raise SystemExit(1)

if not FRONTEND.exists():
    print("ERROR: frontend/ folder not found. Run from the project root.")
    raise SystemExit(1)

if not VOICE_CLIENT.exists():
    print("ERROR: frontend/voice_clone_client.html not found.")
    print("The Voice Clone client page must exist before creating the view route.")
    raise SystemExit(1)

stamp = datetime.now().strftime("%Y%m%d%H%M%S")

backup = APP.with_name(APP.name + f".bak.views-package-{stamp}")
backup.write_text(APP.read_text(encoding="utf-8"), encoding="utf-8")
print("Backup:", backup)

VIEWS.mkdir(exist_ok=True)

(VIEWS / "__init__.py").write_text(r'''from __future__ import annotations


def register_views(app):
    """Register SyntaxMatrix view routes.

    Controllers own API/workflow logic.
    Views own client/admin pages.
    app.py should only call this registrar.
    """
    from .clone_voice_view import bp as clone_voice_bp

    if "clone_voice_view" not in app.blueprints:
        app.register_blueprint(clone_voice_bp)
''', encoding="utf-8")

(VIEWS / "clone_voice_view.py").write_text(r'''from __future__ import annotations

from pathlib import Path

from flask import Blueprint, current_app, send_from_directory


bp = Blueprint("clone_voice_view", __name__)


def _frontend_dir() -> Path:
    return Path(current_app.root_path) / "frontend"


@bp.get("/tasks/voice-clone")
def voice_clone_client_view():
    """Client Voice Clone page.

    This is intentionally a view route, not a controller route.
    The page talks to API controllers after it loads.
    """
    return send_from_directory(_frontend_dir(), "voice_clone_client.html")
''', encoding="utf-8")

app_text = APP.read_text(encoding="utf-8")

# Remove previous view registration block if this patch was run before.
app_text = re.sub(
    r'\n?# SMX_VIEWS_PACKAGE_START[\s\S]*?# SMX_VIEWS_PACKAGE_END\n?',
    '\n',
    app_text,
)

register_block = r'''
# SMX_VIEWS_PACKAGE_START
from views import register_views as _smx_register_views
_smx_register_views(app)
# SMX_VIEWS_PACKAGE_END

'''

marker_double = '\nif __name__ == "__main__":'
marker_single = "\nif __name__ == '__main__':"

if marker_double in app_text:
    app_text = app_text.replace(marker_double, "\n" + register_block + marker_double, 1)
elif marker_single in app_text:
    app_text = app_text.replace(marker_single, "\n" + register_block + marker_single, 1)
else:
    app_text = app_text.rstrip() + "\n\n" + register_block

APP.write_text(app_text, encoding="utf-8")

py_compile.compile(str(VIEWS / "__init__.py"), doraise=True)
py_compile.compile(str(VIEWS / "clone_voice_view.py"), doraise=True)
py_compile.compile(str(APP), doraise=True)

print()
print("Views package created successfully.")
print()
print("Created:")
print("  views/__init__.py")
print("  views/clone_voice_view.py")
print()
print("Updated:")
print("  app.py now only registers views with register_views(app)")
print()
print("Restart Flask:")
print("  python app.py")
print()
print("Open:")
print("  http://127.0.0.1:5055/tasks/voice-clone?v=views")
