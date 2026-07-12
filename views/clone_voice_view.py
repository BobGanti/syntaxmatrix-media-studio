from __future__ import annotations

from pathlib import Path

from flask import Blueprint, current_app, redirect, request, send_from_directory


bp = Blueprint("clone_voice_view", __name__)


def _clone_voice_frontend_dir() -> Path:
    return Path(current_app.root_path) / "frontend" / "clone_voice"


@bp.get("/tasks/clone-voice")
def clone_voice_page():
    return send_from_directory(_clone_voice_frontend_dir(), "client.html")


@bp.get("/admin/clone-voice")
def clone_voice_admin_page():
    from services.firebase_page_session import require_admin_page_session

    denied = require_admin_page_session(request)
    if denied is not None:
        return denied

    return send_from_directory(_clone_voice_frontend_dir(), "admin.html")


@bp.get("/admin/clone-voice/billing")
def clone_voice_billing_admin_page():
    from services.firebase_page_session import require_admin_page_session

    denied = require_admin_page_session(request)
    if denied is not None:
        return denied

    return send_from_directory(_clone_voice_frontend_dir(), "billing.html")


@bp.get("/tasks/voice-clone")
def old_voice_clone_redirect():
    return redirect("/tasks/clone-voice", code=302)
