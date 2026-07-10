from __future__ import annotations

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
