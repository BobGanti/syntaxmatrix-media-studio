from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import pathlib
from typing import Any

from services.persistence_repository import get_persistence_repository


ROOT = pathlib.Path(__file__).resolve().parent.parent
BILLING_DIR = ROOT / "billing"

CUSTOMERS_PATH = BILLING_DIR / "customers.json"
WORKSPACES_PATH = BILLING_DIR / "workspaces.json"
MEMBERSHIPS_PATH = BILLING_DIR / "memberships.json"


DEFAULT_CUSTOMERS = [
    {
        "customerId": "cust_mock_001",
        "name": "Client A",
        "billingEmail": "client-a@example.test",
        "status": "active",
        "createdAt": "",
    },
    {
        "customerId": "cust_mock_002",
        "name": "Client B",
        "billingEmail": "client-b@example.test",
        "status": "active",
        "createdAt": "",
    },
]


DEFAULT_WORKSPACES = [
    {
        "workspaceId": "mock_user_001",
        "customerId": "cust_mock_001",
        "label": "Client A / Workspace 001",
        "status": "active",
        "subscriptionOwnerUserId": "dev_admin",
        "createdAt": "",
    },
    {
        "workspaceId": "mock_user_002",
        "customerId": "cust_mock_002",
        "label": "Client B / Workspace 002",
        "status": "active",
        "subscriptionOwnerUserId": "dev_admin",
        "createdAt": "",
    },
]


DEFAULT_MEMBERSHIPS = [
    {
        "userId": "dev_admin",
        "workspaceId": "mock_user_001",
        "role": "owner",
        "status": "active",
        "createdAt": "",
    },
    {
        "userId": "dev_admin",
        "workspaceId": "mock_user_002",
        "role": "owner",
        "status": "active",
        "createdAt": "",
    },
    {
        "userId": "dev_client_001",
        "workspaceId": "mock_user_001",
        "role": "member",
        "status": "active",
        "createdAt": "",
    },
    {
        "userId": "dev_client_002",
        "workspaceId": "mock_user_002",
        "role": "member",
        "status": "active",
        "createdAt": "",
    },
]


def _now() -> str:
    return _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds")


def _clean(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


def _repository():
    return get_persistence_repository()


def _write_json_if_missing(
    path: pathlib.Path,
    rows: list[dict[str, Any]],
) -> None:
    if path.exists():
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    seeded: list[dict[str, Any]] = []

    for row in rows:
        item = dict(row)
        item["createdAt"] = item.get("createdAt") or _now()
        seeded.append(item)

    path.write_text(json.dumps(seeded, indent=2), encoding="utf-8")


def ensure_customer_workspace_files() -> None:
    """Seed mock data only for the explicit JSON development backend."""
    if _repository().backend_name != "json":
        return

    _write_json_if_missing(CUSTOMERS_PATH, DEFAULT_CUSTOMERS)
    _write_json_if_missing(WORKSPACES_PATH, DEFAULT_WORKSPACES)
    _write_json_if_missing(MEMBERSHIPS_PATH, DEFAULT_MEMBERSHIPS)


def list_customers() -> list[dict[str, Any]]:
    ensure_customer_workspace_files()
    return _repository().list_customers()


def list_workspaces() -> list[dict[str, Any]]:
    ensure_customer_workspace_files()
    return _repository().list_workspaces()


def list_memberships() -> list[dict[str, Any]]:
    ensure_customer_workspace_files()
    return _repository().list_memberships()


def get_workspace_record(workspace_id: str) -> dict[str, Any] | None:
    workspace_id = _clean(workspace_id)

    for workspace in list_workspaces():
        if _clean(workspace.get("workspaceId")) == workspace_id:
            return workspace

    return None


def get_customer_record(customer_id: str) -> dict[str, Any] | None:
    customer_id = _clean(customer_id)

    for customer in list_customers():
        if _clean(customer.get("customerId")) == customer_id:
            return customer

    return None


def user_workspace_memberships(user_id: str) -> list[dict[str, Any]]:
    user_id = _clean(user_id)

    return [
        membership
        for membership in list_memberships()
        if (
            _clean(membership.get("userId")) == user_id
            and _clean(membership.get("status"), "active").lower() == "active"
        )
    ]


def user_has_workspace_access(user_id: str, workspace_id: str) -> bool:
    workspace_id = _clean(workspace_id)

    if not _clean(user_id) or not workspace_id:
        return False

    return any(
        _clean(membership.get("workspaceId")) == workspace_id
        for membership in user_workspace_memberships(user_id)
    )


def workspace_label(workspace_id: str) -> str:
    workspace = get_workspace_record(workspace_id)

    if workspace:
        return _clean(workspace.get("label"), workspace_id)

    return workspace_id


def _auth_provider() -> str:
    return _clean(os.getenv("AUTH_PROVIDER")).lower()


def _firebase_auth_mode() -> bool:
    return _auth_provider() in {
        "firebase",
        "identity_platform",
        "google_identity_platform",
    }


def _workspace_payload_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "workspaceId": row.get("workspaceId"),
        "label": row.get("label") or row.get("workspaceId"),
        "customerId": row.get("customerId"),
        "status": row.get("status", "active"),
    }


def visible_workspaces_for_user(
    user_id: str,
    role: str,
    fallback_workspace_id: str = "mock_user_001",
) -> list[dict[str, Any]]:
    role = _clean(role, "client").lower()
    user_id = _clean(user_id)
    fallback_workspace_id = _clean(fallback_workspace_id)

    workspaces = list_workspaces()

    if role in {"admin", "owner"}:
        return [
            _workspace_payload_row(row)
            for row in workspaces
            if _clean(row.get("status"), "active").lower() == "active"
        ]

    allowed_ids = {
        _clean(membership.get("workspaceId"))
        for membership in user_workspace_memberships(user_id)
        if _clean(membership.get("workspaceId"))
    }

    if (
        not allowed_ids
        and fallback_workspace_id
        and not _firebase_auth_mode()
        and _repository().backend_name == "json"
    ):
        allowed_ids.add(fallback_workspace_id)

    return [
        _workspace_payload_row(row)
        for row in workspaces
        if (
            _clean(row.get("workspaceId")) in allowed_ids
            and _clean(row.get("status"), "active").lower() == "active"
        )
    ]


def workspace_selector_payload(
    user_id: str,
    role: str,
    fallback_workspace_id: str = "mock_user_001",
) -> dict[str, Any]:
    rows = visible_workspaces_for_user(
        user_id,
        role,
        fallback_workspace_id,
    )

    fallback_allowed = (
        not _firebase_auth_mode()
        and _repository().backend_name == "json"
    )

    default_workspace_id = (
        _clean(fallback_workspace_id, "mock_user_001")
        if fallback_allowed
        else ""
    )

    visible_ids = {
        _clean(row.get("workspaceId"))
        for row in rows
    }

    if rows and default_workspace_id not in visible_ids:
        default_workspace_id = _clean(rows[0].get("workspaceId"))

    if not rows and not fallback_allowed:
        default_workspace_id = ""

    return {
        "defaultWorkspaceId": default_workspace_id,
        "workspaces": rows,
    }


def _next_identifier(
    prefix: str,
    rows: list[dict[str, Any]],
    key: str,
) -> str:
    existing = {
        _clean(row.get(key))
        for row in rows
    }

    number = len(existing) + 1

    while True:
        candidate = f"{prefix}_{number:04d}"

        if candidate not in existing:
            return candidate

        number += 1


def create_customer(
    *,
    name: str,
    billing_email: str = "",
    customer_id: str = "",
) -> dict[str, Any]:
    name = _clean(name)

    if not name:
        raise ValueError("Customer name is required")

    customers = list_customers()
    customer_id = _clean(customer_id) or _next_identifier(
        "cust",
        customers,
        "customerId",
    )

    if get_customer_record(customer_id):
        raise ValueError(f"Customer already exists: {customer_id}")

    return _repository().upsert_customer({
        "customerId": customer_id,
        "name": name,
        "billingEmail": _clean(billing_email),
        "status": "active",
        "createdAt": _now(),
    })


def create_workspace(
    *,
    customer_id: str,
    label: str,
    workspace_id: str = "",
    subscription_owner_user_id: str = "",
) -> dict[str, Any]:
    customer_id = _clean(customer_id)
    label = _clean(label)

    if not customer_id:
        raise ValueError("customerId is required")

    if not get_customer_record(customer_id):
        raise ValueError(f"Customer not found: {customer_id}")

    if not label:
        raise ValueError("Workspace label is required")

    workspaces = list_workspaces()
    workspace_id = _clean(workspace_id) or _next_identifier(
        "workspace",
        workspaces,
        "workspaceId",
    )

    if get_workspace_record(workspace_id):
        raise ValueError(f"Workspace already exists: {workspace_id}")

    return _repository().upsert_workspace({
        "workspaceId": workspace_id,
        "customerId": customer_id,
        "label": label,
        "status": "active",
        "subscriptionOwnerUserId": _clean(
            subscription_owner_user_id
        ),
        "createdAt": _now(),
    })


def add_workspace_membership(
    *,
    user_id: str,
    workspace_id: str,
    role: str = "member",
) -> dict[str, Any]:
    user_id = _clean(user_id)
    workspace_id = _clean(workspace_id)
    role = _clean(role, "member").lower()

    if role not in {
        "owner",
        "admin",
        "member",
        "billing_admin",
    }:
        role = "member"

    if not user_id:
        raise ValueError("userId is required")

    if not get_workspace_record(workspace_id):
        raise ValueError(f"Workspace not found: {workspace_id}")

    return _repository().upsert_membership({
        "userId": user_id,
        "workspaceId": workspace_id,
        "role": role,
        "status": "active",
        "createdAt": _now(),
    })


def _stable_hash(value: str, length: int = 12) -> str:
    return hashlib.sha256(
        _clean(value).encode("utf-8")
    ).hexdigest()[:length]


def _display_root(email: str, display_name: str) -> str:
    if _clean(display_name):
        return _clean(display_name)

    if _clean(email) and "@" in email:
        return email.split("@", 1)[0]

    return "My"


def bootstrap_firebase_user_workspace(
    *,
    user_id: str,
    email: str = "",
    display_name: str = "",
) -> dict[str, Any]:
    """Idempotently create durable Firebase tenant records."""
    user_id = _clean(user_id)
    email = _clean(email).lower()
    display_name = _clean(display_name)

    if not user_id:
        raise ValueError("user_id is required")

    for membership in user_workspace_memberships(user_id):
        workspace = get_workspace_record(
            membership.get("workspaceId")
        )

        if (
            workspace
            and _clean(
                workspace.get("status"),
                "active",
            ).lower() == "active"
        ):
            customer = get_customer_record(
                workspace.get("customerId")
            )

            _seed_default_subscription_for_workspace(
                workspace.get("workspaceId"),
                user_id,
            )

            return {
                "created": False,
                "userId": user_id,
                "email": email,
                "customer": customer,
                "workspace": workspace,
                "membership": membership,
            }

    stable = _stable_hash(user_id)
    customer_id = f"cust_fb_{stable}"
    workspace_id = f"ws_fb_{stable}"
    display_root = _display_root(email, display_name)

    customer = get_customer_record(customer_id)

    if not customer:
        customer = _repository().upsert_customer({
            "customerId": customer_id,
            "name": display_root,
            "billingEmail": email,
            "status": "active",
            "createdAt": _now(),
        })

    workspace = get_workspace_record(workspace_id)

    if not workspace:
        workspace = _repository().upsert_workspace({
            "workspaceId": workspace_id,
            "customerId": customer_id,
            "label": f"{display_root} Workspace",
            "status": "active",
            "subscriptionOwnerUserId": user_id,
            "createdAt": _now(),
        })

    membership = _repository().upsert_membership({
        "userId": user_id,
        "workspaceId": workspace_id,
        "role": "owner",
        "status": "active",
        "createdAt": _now(),
    })

    _seed_default_subscription_for_workspace(
        workspace_id,
        user_id,
    )

    return {
        "created": True,
        "userId": user_id,
        "email": email,
        "customer": customer,
        "workspace": workspace,
        "membership": membership,
    }


def _seed_default_subscription_for_workspace(
    workspace_id: str,
    user_id: str = "",
) -> None:
    workspace_id = _clean(workspace_id)

    if not workspace_id:
        raise ValueError("workspaceId is required")

    from services.billing_usage import set_workspace_plan

    # Check the persistence repository directly. The public billing helper
    # returns a synthetic starter plan when no stored subscription exists,
    # which must not be mistaken for a durable database record.
    existing = _repository().get_workspace_subscription(workspace_id)

    if isinstance(existing, dict):
        status = _clean(existing.get("status")).lower()
        plan_key = _clean(existing.get("planKey")).lower()

        if status in {"active", "trialing"} and plan_key:
            return

    set_workspace_plan(
        workspace_id=workspace_id,
        plan_key="starter",
        status="active",
        provider="private_beta",
        subscription_id=f"private_beta_{workspace_id}",
    )
