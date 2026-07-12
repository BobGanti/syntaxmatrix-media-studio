from __future__ import annotations

import html
import os
from typing import Any
from urllib.parse import quote

from flask import Response, redirect

from services.auth_context import (
    dev_auth_enabled,
    firebase_auth_enabled,
    is_firebase_admin_email,
)
from services.firebase_auth import (
    FirebaseAuthError,
    verify_firebase_session_cookie,
)


def _clean(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


def session_cookie_name() -> str:
    return _clean(os.getenv("FIREBASE_SESSION_COOKIE_NAME"), "smx_session")


def _forbidden_page(email: str = "") -> Response:
    safe_email = html.escape(email or "this account")
    body = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Admin access required</title>
<style>body{{margin:0;min-height:100vh;display:grid;place-items:center;background:#07111f;color:#eef5ff;font-family:Inter,system-ui,sans-serif}}main{{max-width:620px;padding:32px;border:1px solid #28435e;border-radius:24px;background:#0d1b2a}}a{{color:#9ddcff}}code{{color:#9be7d0}}</style></head>
<body><main><h1>Admin access required</h1><p>{safe_email} is signed in, but is not authorised for the SyntaxMatrix administration console.</p><p><a href="/tasks/clone-voice">Return to Clone Voice</a></p></main></body></html>"""
    return Response(body, status=403, content_type="text/html; charset=utf-8")


def require_admin_page_session(flask_request):
    """Return None when authorised, otherwise a redirect/403 response.

    Admin HTML is protected with an HttpOnly Firebase session cookie. API routes
    continue to use Firebase Bearer tokens and their existing role checks.
    """
    if not firebase_auth_enabled():
        if dev_auth_enabled() and _clean(os.getenv("DEV_AUTH_ROLE"), "admin").lower() in {"admin", "owner"}:
            return None
        return _forbidden_page()

    cookie = _clean(flask_request.cookies.get(session_cookie_name()))
    if not cookie:
        next_url = quote(flask_request.full_path.rstrip("?") or flask_request.path, safe="")
        return redirect(f"/auth?next={next_url}", code=302)

    try:
        decoded = verify_firebase_session_cookie(cookie)
    except FirebaseAuthError:
        response = redirect(
            f"/auth?next={quote(flask_request.full_path.rstrip('?') or flask_request.path, safe='')}",
            code=302,
        )
        response.delete_cookie(session_cookie_name(), path="/")
        return response

    email = _clean(decoded.get("email")).lower()
    if not email or not is_firebase_admin_email(email):
        return _forbidden_page(email)

    return None
