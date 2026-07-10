from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any

from services.customer_workspace import user_has_workspace_access, user_workspace_memberships


ADMIN_ROLES = {"admin", "owner"}
CLIENT_ROLES = {"client", "member", "admin", "owner"}
FIREBASE_AUTH_PROVIDERS = {"firebase", "identity_platform", "google_identity_platform"}


class AuthError(PermissionError):
    def __init__(self, message: str, *, status_code: int = 403, payload: dict[str, Any] | None = None):
        self.status_code = status_code
        self.payload = payload or {}
        super().__init__(message)


@dataclass(frozen=True)
class AuthContext:
    user_id: str
    role: str
    workspace_id: str
    auth_mode: str
    is_admin: bool
    email: str = ""

    def to_payload(self) -> dict[str, Any]:
        return {
            "userId": self.user_id,
            "email": self.email,
            "role": self.role,
            "workspaceId": self.workspace_id,
            "authMode": self.auth_mode,
            "isAdmin": self.is_admin,
        }


def _clean(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


def _normalise_role(value: Any) -> str:
    role = _clean(value, "client").lower()

    if role in {"administrator", "superadmin", "super_admin"}:
        return "admin"

    if role not in {"admin", "owner", "client", "member"}:
        return "client"

    return role


def auth_provider() -> str:
    return _clean(os.getenv("AUTH_PROVIDER")).lower()


def firebase_auth_enabled() -> bool:
    return auth_provider() in FIREBASE_AUTH_PROVIDERS


def dev_auth_enabled() -> bool:
    if firebase_auth_enabled():
        return False

    value = _clean(os.getenv("DEV_AUTH_ENABLED"), "true").lower()
    return value in {"1", "true", "yes", "on"}


def _json_body_from_request(request) -> dict[str, Any]:
    if getattr(request, "method", "GET") not in {"POST", "PUT", "PATCH", "DELETE"}:
        return {}

    try:
        json_body = request.get_json(silent=True)
    except Exception:
        json_body = None

    return json_body if isinstance(json_body, dict) else {}


def _env_email_set(name: str) -> set[str]:
    raw = _clean(os.getenv(name))
    if not raw:
        return set()

    return {
        part.strip().lower()
        for part in re.split(r"[,;\s]+", raw)
        if part.strip()
    }


def _firebase_admin_emails() -> set[str]:
    return _env_email_set("FIREBASE_ADMIN_EMAILS")


def _extract_bearer_token(request) -> str:
    header = _clean(getattr(request, "headers", {}).get("Authorization"))
    if not header:
        return ""

    parts = header.split(None, 1)
    if len(parts) != 2:
        return ""

    scheme, token = parts
    if scheme.lower() != "bearer":
        return ""

    return _clean(token)


def _request_workspace_id(request, json_body: dict[str, Any], fallback: str = "") -> str:
    return _clean(
        getattr(request, "headers", {}).get("X-Workspace-Id")
        or getattr(request, "args", {}).get("workspaceId")
        or getattr(request, "form", {}).get("workspaceId")
        or json_body.get("workspaceId")
        or fallback
    )


def _first_membership_workspace(user_id: str) -> str:
    for membership in user_workspace_memberships(user_id):
        workspace_id = _clean(membership.get("workspaceId"))
        if workspace_id:
            return workspace_id
    return ""


def _auth_context_from_firebase_request(request, json_body: dict[str, Any]) -> AuthContext:
    token = _extract_bearer_token(request)

    if not token:
        raise AuthError(
            "Authentication required.",
            status_code=401,
            payload={
                "authMode": "firebase",
                "reason": "missing_bearer_token",
            },
        )

    try:
        from services.firebase_auth import verify_firebase_id_token

        decoded = verify_firebase_id_token(token)
    except Exception as exc:
        raise AuthError(
            "Invalid or expired authentication token.",
            status_code=401,
            payload={
                "authMode": "firebase",
                "reason": exc.__class__.__name__,
            },
        ) from exc

    user_id = _clean(decoded.get("uid"))
    if not user_id:
        raise AuthError(
            "Invalid authentication token.",
            status_code=401,
            payload={
                "authMode": "firebase",
                "reason": "missing_uid",
            },
        )

    email = _clean(decoded.get("email")).lower()
    role = "admin" if email and email in _firebase_admin_emails() else "client"

    requested_workspace = _request_workspace_id(request, json_body, "")
    default_workspace = _first_membership_workspace(user_id)

    if role in ADMIN_ROLES:
        workspace_id = requested_workspace or default_workspace
    elif requested_workspace and user_has_workspace_access(user_id, requested_workspace):
        workspace_id = requested_workspace
    else:
        workspace_id = default_workspace

    return AuthContext(
        user_id=user_id,
        email=email,
        role=role,
        workspace_id=workspace_id,
        auth_mode="firebase",
        is_admin=role in ADMIN_ROLES,
    )


def _auth_context_from_dev_request(request, json_body: dict[str, Any]) -> AuthContext:
    auth_mode = "dev"

    role = (
        getattr(request, "headers", {}).get("X-Dev-Role")
        or getattr(request, "args", {}).get("devRole")
        or getattr(request, "form", {}).get("devRole")
        or json_body.get("devRole")
        or os.getenv("DEV_AUTH_ROLE")
        or "admin"
    )

    workspace_id = (
        getattr(request, "headers", {}).get("X-Workspace-Id")
        or getattr(request, "args", {}).get("workspaceId")
        or getattr(request, "form", {}).get("workspaceId")
        or json_body.get("workspaceId")
        or os.getenv("DEV_AUTH_WORKSPACE_ID")
        or "mock_user_001"
    )

    user_id = (
        getattr(request, "headers", {}).get("X-User-Id")
        or getattr(request, "args", {}).get("userId")
        or getattr(request, "form", {}).get("userId")
        or json_body.get("userId")
        or os.getenv("DEV_AUTH_USER_ID")
        or "dev_admin"
    )

    role = _normalise_role(role)
    workspace_id = _clean(workspace_id, "mock_user_001")
    user_id = _clean(user_id, "dev_user")

    return AuthContext(
        user_id=user_id,
        role=role,
        workspace_id=workspace_id,
        auth_mode=auth_mode,
        is_admin=role in ADMIN_ROLES,
    )


def auth_context_from_request(request) -> AuthContext:
    """Return the current auth context.

    Firebase mode:
      AUTH_PROVIDER=firebase
      Requires: Authorization: Bearer <Firebase ID token>

    Local dev mode:
      AUTH_PROVIDER unset
      DEV_AUTH_ENABLED=true
      Allows X-Dev-* headers / env var fallback for manual testing.
    """
    json_body = _json_body_from_request(request)

    if firebase_auth_enabled():
        return _auth_context_from_firebase_request(request, json_body)

    if not dev_auth_enabled():
        raise AuthError(
            "Authentication is disabled.",
            status_code=401,
            payload={
                "authMode": "disabled",
                "reason": "no_auth_provider",
            },
        )

    return _auth_context_from_dev_request(request, json_body)


def require_admin(ctx: AuthContext) -> None:
    if ctx.role not in ADMIN_ROLES:
        raise AuthError(
            "Admin access required.",
            status_code=403,
            payload={
                "requiredRole": "admin",
                "currentRole": ctx.role,
                "workspaceId": ctx.workspace_id,
                "authMode": ctx.auth_mode,
            },
        )


def require_workspace_access(ctx: AuthContext, workspace_id: str | None) -> None:
    requested_workspace = _clean(workspace_id, ctx.workspace_id)

    if not requested_workspace:
        raise AuthError(
            "Workspace is required.",
            status_code=403,
            payload={
                "currentWorkspaceId": ctx.workspace_id,
                "requestedWorkspaceId": requested_workspace,
                "userId": ctx.user_id,
                "authMode": ctx.auth_mode,
            },
        )

    if ctx.role in ADMIN_ROLES:
        return

    if ctx.role not in CLIENT_ROLES:
        raise AuthError(
            "Workspace access required.",
            status_code=403,
            payload={
                "requiredRole": "client",
                "currentRole": ctx.role,
                "workspaceId": ctx.workspace_id,
                "requestedWorkspaceId": requested_workspace,
                "authMode": ctx.auth_mode,
            },
        )

    if user_has_workspace_access(ctx.user_id, requested_workspace):
        return

    # Dev-only convenience. Firebase mode must never fall back to a declared workspace.
    if ctx.auth_mode == "dev" and requested_workspace == ctx.workspace_id:
        return

    raise AuthError(
        "Workspace access denied.",
        status_code=403,
        payload={
            "currentWorkspaceId": ctx.workspace_id,
            "requestedWorkspaceId": requested_workspace,
            "userId": ctx.user_id,
            "authMode": ctx.auth_mode,
        },
    )


def auth_error_payload(exc: AuthError) -> dict[str, Any]:
    return {
        "ok": False,
        "error": str(exc),
        "message": str(exc),
        **getattr(exc, "payload", {}),
    }
