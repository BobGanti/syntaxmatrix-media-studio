from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
WORKSPACES_FILE = ROOT / "billing" / "workspaces.json"


def _should_remove(row: Any) -> bool:
    if not isinstance(row, dict):
        return False

    try:
        blob = json.dumps(row, sort_keys=True).lower()
    except Exception:
        blob = str(row).lower()

    workspace_id = str(row.get("workspaceId", "")).lower()
    customer_id = str(row.get("customerId", "")).lower()
    owner = str(row.get("subscriptionOwnerUserId", "")).lower()
    label = str(row.get("label", "")).lower()

    return (
        workspace_id.startswith("mock_")
        or customer_id.startswith("cust_mock_")
        or "mock_user_" in blob
        or "cust_mock_" in blob
        or owner.startswith("firebase_test_user")
        or owner.startswith("stage9")
        or "stage9" in owner
        or "stage9" in label
        or "test workspace" in label
        or "-test workspace" in label
    )


def clean_workspace_registry_state(print_summary: bool = True) -> dict[str, list[str]]:
    if not WORKSPACES_FILE.exists():
        WORKSPACES_FILE.parent.mkdir(parents=True, exist_ok=True)
        WORKSPACES_FILE.write_text("[]\n", encoding="utf-8")
        result = {"removed": [], "kept": []}
        if print_summary:
            print("workspaces.json did not exist; created clean empty list.")
        return result

    try:
        data = json.loads(WORKSPACES_FILE.read_text(encoding="utf-8"))
    except Exception:
        data = []

    if not isinstance(data, list):
        data = []

    removed: list[str] = []
    kept: list[dict[str, Any]] = []

    for row in data:
        if isinstance(row, dict) and _should_remove(row):
            removed.append(str(row.get("workspaceId", "<missing>")))
        else:
            kept.append(row)

    WORKSPACES_FILE.write_text(
        json.dumps(kept, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    result = {
        "removed": removed,
        "kept": [
            str(row.get("workspaceId", "<missing>"))
            for row in kept
            if isinstance(row, dict)
        ],
    }

    if print_summary:
        print("Removed workspace records:", result["removed"])
        print("Kept workspace records:", result["kept"])

    return result


if __name__ == "__main__":
    clean_workspace_registry_state(print_summary=True)
