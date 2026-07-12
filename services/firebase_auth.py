from __future__ import annotations

import datetime as _dt
import os
from functools import lru_cache
from typing import Any


class FirebaseAuthError(PermissionError):
    pass


def _clean(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


def firebase_project_id() -> str:
    return (
        _clean(os.getenv("FIREBASE_PROJECT_ID"))
        or _clean(os.getenv("GOOGLE_CLOUD_PROJECT"))
        or _clean(os.getenv("GCLOUD_PROJECT"))
    )


@lru_cache(maxsize=1)
def _firebase_app():
    try:
        import firebase_admin
    except Exception as exc:  # pragma: no cover
        raise FirebaseAuthError(
            "firebase-admin is not installed. Run: pip install -r requirements.txt"
        ) from exc

    if firebase_admin._apps:
        return firebase_admin.get_app()

    project_id = firebase_project_id()
    options = {"projectId": project_id} if project_id else None

    try:
        return firebase_admin.initialize_app(options=options)
    except Exception as exc:
        raise FirebaseAuthError(f"Could not initialise Firebase Admin SDK: {exc}") from exc


def verify_firebase_id_token(id_token: str) -> dict[str, Any]:
    token = _clean(id_token)
    if not token:
        raise FirebaseAuthError("Missing Firebase ID token.")

    try:
        from firebase_admin import auth
    except Exception as exc:  # pragma: no cover
        raise FirebaseAuthError(
            "firebase-admin auth module is unavailable. Run: pip install -r requirements.txt"
        ) from exc

    _firebase_app()

    try:
        decoded = auth.verify_id_token(token, check_revoked=False)
    except Exception as exc:
        raise FirebaseAuthError(f"Firebase ID token verification failed: {exc}") from exc

    if not isinstance(decoded, dict):
        raise FirebaseAuthError("Firebase ID token verification returned an invalid payload.")

    return decoded


def create_firebase_session_cookie(
    id_token: str,
    *,
    expires_in_seconds: int,
) -> str:
    """Exchange a Firebase ID token for a server session cookie."""
    token = _clean(id_token)

    if not token:
        raise FirebaseAuthError("Missing Firebase ID token.")

    try:
        seconds = int(expires_in_seconds)
    except (TypeError, ValueError) as exc:
        raise FirebaseAuthError(
            "Invalid Firebase session duration."
        ) from exc

    maximum_seconds = 14 * 24 * 60 * 60

    if seconds <= 0 or seconds > maximum_seconds:
        raise FirebaseAuthError(
            "Firebase session duration must be between "
            "1 second and 14 days."
        )

    try:
        from firebase_admin import auth
    except Exception as exc:
        raise FirebaseAuthError(
            "firebase-admin auth module is unavailable. "
            "Run: pip install -r requirements.txt"
        ) from exc

    _firebase_app()

    try:
        cookie = auth.create_session_cookie(
            token,
            expires_in=_dt.timedelta(seconds=seconds),
        )
    except Exception as exc:
        raise FirebaseAuthError(
            f"Firebase session cookie creation failed: {exc}"
        ) from exc

    if isinstance(cookie, bytes):
        cookie = cookie.decode("utf-8")

    cookie = _clean(cookie)

    if not cookie:
        raise FirebaseAuthError(
            "Firebase session cookie creation returned "
            "an empty value."
        )

    return cookie


def verify_firebase_session_cookie(
    session_cookie: str,
) -> dict[str, Any]:
    """Verify a Firebase session cookie."""
    cookie = _clean(session_cookie)

    if not cookie:
        raise FirebaseAuthError(
            "Missing Firebase session cookie."
        )

    try:
        from firebase_admin import auth
    except Exception as exc:
        raise FirebaseAuthError(
            "firebase-admin auth module is unavailable. "
            "Run: pip install -r requirements.txt"
        ) from exc

    _firebase_app()

    try:
        decoded = auth.verify_session_cookie(
            cookie,
            check_revoked=False,
        )
    except Exception as exc:
        raise FirebaseAuthError(
            f"Firebase session cookie verification failed: {exc}"
        ) from exc

    if not isinstance(decoded, dict):
        raise FirebaseAuthError(
            "Firebase session cookie verification returned "
            "an invalid payload."
        )

    return decoded
