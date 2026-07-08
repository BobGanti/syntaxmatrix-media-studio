from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from services.customer_workspace import user_has_workspace_access


ADMIN_ROLES = {"admin", "owner"}
CLIENT_ROLES = {"client", "admin", "owner"}


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

    def to_payload(self) -> dict[str, Any]:
        return {
            "userId": self.user_id,
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

    if role not in {"admin", "owner", "client"}:
        return "client"

    return role


def dev_auth_enabled() -> bool:
    value = _clean(os.getenv("DEV_AUTH_ENABLED"), "true").lower()
    return value in {"1", "true", "yes", "on"}


def auth_context_from_request(request) -> AuthContext:
    """Return the current auth context.

    This is a development-safe boundary. In production, real login/session/JWT
    middleware can replace this function while the rest of the app continues to
    call require_admin() and require_workspace_access().
    """
    auth_mode = "dev" if dev_auth_enabled() else "disabled"

    # Local development priority:
    # 1. headers, useful for API tests
    # 2. query/form/json, useful for quick manual tests
    # 3. environment variables
    json_body = request.get_json(silent=True) if request.method in {"POST", "PUT", "PATCH", "DELETE"} else None
    if not isinstance(json_body, dict):
        json_body = {}

    role = (
        request.headers.get("X-Dev-Role")
        or request.args.get("devRole")
        or request.form.get("devRole")
        or json_body.get("devRole")
        or os.getenv("DEV_AUTH_ROLE")
        or "admin"
    )

    workspace_id = (
        request.headers.get("X-Workspace-Id")
        or request.args.get("workspaceId")
        or request.form.get("workspaceId")
        or json_body.get("workspaceId")
        or os.getenv("DEV_AUTH_WORKSPACE_ID")
        or "mock_user_001"
    )

    user_id = (
        request.headers.get("X-User-Id")
        or request.args.get("userId")
        or request.form.get("userId")
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


def require_admin(ctx: AuthContext) -> None:
    if ctx.role not in ADMIN_ROLES:
        raise AuthError(
            "Admin access required.",
            status_code=403,
            payload={
                "requiredRole": "admin",
                "currentRole": ctx.role,
                "workspaceId": ctx.workspace_id,
            },
        )


def require_workspace_access(ctx: AuthContext, workspace_id: str | None) -> None:
    requested_workspace = _clean(workspace_id, ctx.workspace_id)

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
            },
        )

    # Real foundation: membership grants access.
    if user_has_workspace_access(ctx.user_id, requested_workspace):
        return

    # Local dev fallback: allow the workspace declared in DEV_AUTH_WORKSPACE_ID.
    if requested_workspace == ctx.workspace_id:
        return

    raise AuthError(
        "Workspace access denied.",
        status_code=403,
        payload={
            "currentWorkspaceId": ctx.workspace_id,
            "requestedWorkspaceId": requested_workspace,
            "userId": ctx.user_id,
        },
    )


def auth_error_payload(exc: AuthError) -> dict[str, Any]:
    return {
        "ok": False,
        "error": str(exc),
        "message": str(exc),
        **getattr(exc, "payload", {}),
    }
