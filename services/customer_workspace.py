from __future__ import annotations

import datetime as _dt
import json
import pathlib
from typing import Any


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


def _ensure_dir() -> None:
    BILLING_DIR.mkdir(parents=True, exist_ok=True)


def _write_if_missing(path: pathlib.Path, rows: list[dict[str, Any]]) -> None:
    _ensure_dir()

    if path.exists():
        return

    seeded = []

    for row in rows:
        item = dict(row)
        if not item.get("createdAt"):
            item["createdAt"] = _now()
        seeded.append(item)

    path.write_text(json.dumps(seeded, indent=2), encoding="utf-8")


def ensure_customer_workspace_files() -> None:
    _write_if_missing(CUSTOMERS_PATH, DEFAULT_CUSTOMERS)
    _write_if_missing(WORKSPACES_PATH, DEFAULT_WORKSPACES)
    _write_if_missing(MEMBERSHIPS_PATH, DEFAULT_MEMBERSHIPS)


def _read_list(path: pathlib.Path, default_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ensure_customer_workspace_files()

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [dict(row) for row in data if isinstance(row, dict)]
    except Exception as exc:
        print("[customer_workspace] Could not read", path, repr(exc), flush=True)

    return [dict(row) for row in default_rows]


def _write_list(path: pathlib.Path, rows: list[dict[str, Any]]) -> None:
    _ensure_dir()
    path.write_text(json.dumps(rows, indent=2), encoding="utf-8")


def list_customers() -> list[dict[str, Any]]:
    return _read_list(CUSTOMERS_PATH, DEFAULT_CUSTOMERS)


def list_workspaces() -> list[dict[str, Any]]:
    return _read_list(WORKSPACES_PATH, DEFAULT_WORKSPACES)


def list_memberships() -> list[dict[str, Any]]:
    return _read_list(MEMBERSHIPS_PATH, DEFAULT_MEMBERSHIPS)


def get_workspace_record(workspace_id: str) -> dict[str, Any] | None:
    workspace_id = _clean(workspace_id)

    for workspace in list_workspaces():
        if workspace.get("workspaceId") == workspace_id:
            return workspace

    return None


def get_customer_record(customer_id: str) -> dict[str, Any] | None:
    customer_id = _clean(customer_id)

    for customer in list_customers():
        if customer.get("customerId") == customer_id:
            return customer

    return None


def user_workspace_memberships(user_id: str) -> list[dict[str, Any]]:
    user_id = _clean(user_id)

    return [
        membership
        for membership in list_memberships()
        if membership.get("userId") == user_id and membership.get("status", "active") == "active"
    ]


def user_has_workspace_access(user_id: str, workspace_id: str) -> bool:
    user_id = _clean(user_id)
    workspace_id = _clean(workspace_id)

    if not user_id or not workspace_id:
        return False

    return any(
        membership.get("workspaceId") == workspace_id
        for membership in user_workspace_memberships(user_id)
    )


def workspace_label(workspace_id: str) -> str:
    workspace = get_workspace_record(workspace_id)

    if workspace:
        return workspace.get("label") or workspace_id

    return workspace_id


def visible_workspaces_for_user(user_id: str, role: str, fallback_workspace_id: str = "mock_user_001") -> list[dict[str, Any]]:
    role = _clean(role, "client").lower()
    user_id = _clean(user_id)
    fallback_workspace_id = _clean(fallback_workspace_id, "mock_user_001")

    workspaces = list_workspaces()

    if role in {"admin", "owner"}:
        return [
            {
                "workspaceId": row.get("workspaceId"),
                "label": row.get("label") or row.get("workspaceId"),
                "customerId": row.get("customerId"),
                "status": row.get("status", "active"),
            }
            for row in workspaces
            if row.get("status", "active") == "active"
        ]

    allowed_ids = {
        membership.get("workspaceId")
        for membership in user_workspace_memberships(user_id)
    }

    if not allowed_ids and fallback_workspace_id:
        allowed_ids.add(fallback_workspace_id)

    return [
        {
            "workspaceId": row.get("workspaceId"),
            "label": row.get("label") or row.get("workspaceId"),
            "customerId": row.get("customerId"),
            "status": row.get("status", "active"),
        }
        for row in workspaces
        if row.get("workspaceId") in allowed_ids and row.get("status", "active") == "active"
    ]


def workspace_selector_payload(user_id: str, role: str, fallback_workspace_id: str = "mock_user_001") -> dict[str, Any]:
    rows = visible_workspaces_for_user(user_id, role, fallback_workspace_id)

    default_workspace_id = fallback_workspace_id

    if rows and default_workspace_id not in {row["workspaceId"] for row in rows}:
        default_workspace_id = rows[0]["workspaceId"]

    return {
        "defaultWorkspaceId": default_workspace_id,
        "workspaces": rows,
    }


def create_customer(
    *,
    name: str,
    billing_email: str = "",
    customer_id: str = "",
) -> dict[str, Any]:
    customers = list_customers()

    name = _clean(name)
    if not name:
        raise ValueError("Customer name is required")

    customer_id = _clean(customer_id) or f"cust_{len(customers) + 1:04d}"

    if any(row.get("customerId") == customer_id for row in customers):
        raise ValueError(f"Customer already exists: {customer_id}")

    customer = {
        "customerId": customer_id,
        "name": name,
        "billingEmail": _clean(billing_email),
        "status": "active",
        "createdAt": _now(),
    }

    customers.append(customer)
    _write_list(CUSTOMERS_PATH, customers)

    return customer


def create_workspace(
    *,
    customer_id: str,
    label: str,
    workspace_id: str = "",
    subscription_owner_user_id: str = "",
) -> dict[str, Any]:
    workspaces = list_workspaces()

    customer_id = _clean(customer_id)
    label = _clean(label)

    if not customer_id:
        raise ValueError("customerId is required")

    if not get_customer_record(customer_id):
        raise ValueError(f"Customer not found: {customer_id}")

    if not label:
        raise ValueError("Workspace label is required")

    workspace_id = _clean(workspace_id) or f"workspace_{len(workspaces) + 1:04d}"

    if any(row.get("workspaceId") == workspace_id for row in workspaces):
        raise ValueError(f"Workspace already exists: {workspace_id}")

    workspace = {
        "workspaceId": workspace_id,
        "customerId": customer_id,
        "label": label,
        "status": "active",
        "subscriptionOwnerUserId": _clean(subscription_owner_user_id),
        "createdAt": _now(),
    }

    workspaces.append(workspace)
    _write_list(WORKSPACES_PATH, workspaces)

    return workspace


def add_workspace_membership(
    *,
    user_id: str,
    workspace_id: str,
    role: str = "member",
) -> dict[str, Any]:
    memberships = list_memberships()

    user_id = _clean(user_id)
    workspace_id = _clean(workspace_id)
    role = _clean(role, "member").lower()

    if role not in {"owner", "admin", "member", "billing_admin"}:
        role = "member"

    if not user_id:
        raise ValueError("userId is required")

    if not get_workspace_record(workspace_id):
        raise ValueError(f"Workspace not found: {workspace_id}")

    for membership in memberships:
        if membership.get("userId") == user_id and membership.get("workspaceId") == workspace_id:
            membership["role"] = role
            membership["status"] = "active"
            _write_list(MEMBERSHIPS_PATH, memberships)
            return membership

    membership = {
        "userId": user_id,
        "workspaceId": workspace_id,
        "role": role,
        "status": "active",
        "createdAt": _now(),
    }

    memberships.append(membership)
    _write_list(MEMBERSHIPS_PATH, memberships)

    return membership
