from __future__ import annotations

import os
import py_compile
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class FakePostgresRepository:
    backend_name = "postgres"

    def __init__(self) -> None:
        self.customers: dict[str, dict[str, Any]] = {}
        self.workspaces: dict[str, dict[str, Any]] = {}
        self.memberships: dict[tuple[str, str], dict[str, Any]] = {}
        self.subscriptions: dict[str, dict[str, Any]] = {}
        self.usage: list[dict[str, Any]] = []
        self.voices: dict[tuple[str, str], dict[str, Any]] = {}

    def list_customers(self):
        return list(self.customers.values())

    def list_workspaces(self):
        return list(self.workspaces.values())

    def list_memberships(self):
        return list(self.memberships.values())

    def upsert_customer(self, record):
        item = dict(record)
        self.customers[item["customerId"]] = item
        return item

    def upsert_workspace(self, record):
        item = dict(record)

        if item["customerId"] not in self.customers:
            raise AssertionError("Workspace customer was not persisted first")

        self.workspaces[item["workspaceId"]] = item
        return item

    def upsert_membership(self, record):
        item = dict(record)
        key = (item["userId"], item["workspaceId"])
        self.memberships[key] = item
        return item

    def get_workspace_subscription(self, workspace_id):
        return self.subscriptions.get(workspace_id)

    def upsert_workspace_subscription(self, workspace_id, record):
        item = dict(record)
        item["workspaceId"] = workspace_id
        self.subscriptions[workspace_id] = item
        return item

    def append_usage_event(self, row):
        item = dict(row)
        self.usage.append(item)
        return item

    def list_usage_events(self, workspace_id=None, month=None):
        rows = []

        for item in self.usage:
            if workspace_id and item.get("workspaceId") != workspace_id:
                continue

            if month and item.get("month") != month:
                continue

            rows.append(dict(item))

        return rows

    def usage_credits_this_month(self, workspace_id, month=None):
        return sum(
            float(row.get("credits") or 0)
            for row in self.list_usage_events(
                workspace_id,
                month,
            )
        )


    def list_workspace_voices(self, workspace_id):
        return [
            dict(row)
            for (row_workspace_id, _voice_id), row in self.voices.items()
            if row_workspace_id == workspace_id and row.get("status", "active") == "active"
        ]

    def get_workspace_voice(self, workspace_id, voice_id):
        row = self.voices.get((workspace_id, voice_id))
        return dict(row) if row else None

    def upsert_workspace_voice(self, workspace_id, voice_id, record):
        item = dict(record)
        item.update({"workspaceId": workspace_id, "voiceId": voice_id})
        self.voices[(workspace_id, voice_id)] = item
        return dict(item)

    def delete_workspace_voice(self, workspace_id, voice_id):
        return self.voices.pop((workspace_id, voice_id), None) is not None


def main() -> None:
    files = [
        ROOT / "services" / "persistence_repository.py",
        ROOT / "services" / "customer_workspace.py",
        ROOT / "services" / "billing_usage.py",
    ]

    for path in files:
        py_compile.compile(
            str(path),
            doraise=True,
        )
        print(f"Compile passed: {path.relative_to(ROOT)}")

    os.environ["PERSISTENCE_BACKEND"] = "postgres"
    os.environ["AUTH_PROVIDER"] = "firebase"

    import services.customer_workspace as customer_workspace
    import services.billing_usage as billing_usage

    repository = FakePostgresRepository()

    customer_workspace.get_persistence_repository = lambda: repository
    billing_usage.get_persistence_repository = lambda: repository

    first = customer_workspace.bootstrap_firebase_user_workspace(
        user_id="firebase-user-a",
        email="user-a@example.test",
        display_name="User A",
    )

    second = customer_workspace.bootstrap_firebase_user_workspace(
        user_id="firebase-user-b",
        email="user-b@example.test",
        display_name="User B",
    )

    repeated = customer_workspace.bootstrap_firebase_user_workspace(
        user_id="firebase-user-a",
        email="user-a@example.test",
        display_name="User A",
    )

    first_workspace = first["workspace"]["workspaceId"]
    second_workspace = second["workspace"]["workspaceId"]

    assert first_workspace.startswith("ws_fb_")
    assert second_workspace.startswith("ws_fb_")
    assert first_workspace != second_workspace
    assert repeated["created"] is False

    first_visible = customer_workspace.visible_workspaces_for_user(
        "firebase-user-a",
        "client",
    )
    second_visible = customer_workspace.visible_workspaces_for_user(
        "firebase-user-b",
        "client",
    )
    admin_visible = customer_workspace.visible_workspaces_for_user(
        "firebase-admin",
        "admin",
    )

    assert [row["workspaceId"] for row in first_visible] == [
        first_workspace
    ]
    assert [row["workspaceId"] for row in second_visible] == [
        second_workspace
    ]

    admin_ids = {
        row["workspaceId"]
        for row in admin_visible
    }

    assert first_workspace in admin_ids
    assert second_workspace in admin_ids
    assert "mock_user_001" not in admin_ids
    assert "mock_user_002" not in admin_ids

    assert repository.subscriptions[first_workspace]["planKey"] == "starter"
    assert repository.subscriptions[second_workspace]["planKey"] == "starter"

    billing_usage.record_usage_event(
        first_workspace,
        "narration.generated",
        quantity=5,
        credits=3,
        metadata={"test": True},
    )

    first_events = billing_usage.read_usage_events(
        first_workspace,
    )
    second_events = billing_usage.read_usage_events(
        second_workspace,
    )

    assert len(first_events) == 1
    assert len(second_events) == 0
    assert first_events[0]["credits"] == 3

    repository_source = (
        ROOT / "services" / "persistence_repository.py"
    ).read_text(encoding="utf-8")

    customer_source = (
        ROOT / "services" / "customer_workspace.py"
    ).read_text(encoding="utf-8")

    billing_source = (
        ROOT / "services" / "billing_usage.py"
    ).read_text(encoding="utf-8")

    requirements = (
        ROOT / "requirements.txt"
    ).read_text(encoding="utf-8").lower()

    assert "def upsert_customer" in repository_source
    assert "def upsert_workspace" in repository_source
    assert "def upsert_membership" in repository_source
    assert "def list_usage_events" in repository_source

    assert "_repository().upsert_customer" in customer_source
    assert "_repository().upsert_workspace" in customer_source
    assert "_repository().upsert_membership" in customer_source

    assert (
        "get_persistence_repository().append_usage_event"
        in billing_source
    )
    assert "psycopg" in requirements

    print()
    print("Gate 1 acceptance results")
    print("=========================")
    print("Repository compilation: passed")
    print("Firebase onboarding persistence: passed")
    print("Deterministic workspace restoration: passed")
    print("Two-user tenant isolation: passed")
    print("Admin sees real workspaces: passed")
    print("Production mock workspace exclusion: passed")
    print("Starter subscription persistence: passed")
    print("Usage event persistence: passed")
    print("Gate 1B local acceptance: PASSED")


if __name__ == "__main__":
    main()
