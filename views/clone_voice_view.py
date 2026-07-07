from __future__ import annotations

from pathlib import Path

from flask import Blueprint, current_app, redirect, send_from_directory


bp = Blueprint("clone_voice_view", __name__)


def _clone_voice_frontend_dir() -> Path:
    return Path(current_app.root_path) / "frontend" / "clone_voice"


@bp.get("/tasks/clone-voice")
def clone_voice_page():
    return send_from_directory(_clone_voice_frontend_dir(), "client.html")


@bp.get("/admin/clone-voice")
def clone_voice_admin_page():
    return send_from_directory(_clone_voice_frontend_dir(), "admin.html")


@bp.get("/tasks/voice-clone")
def old_voice_clone_redirect():
    return redirect("/tasks/clone-voice", code=302)
