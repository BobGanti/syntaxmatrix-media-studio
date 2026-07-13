from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MEMBERSHIPS_FILE = ROOT / "billing" / "memberships.json"


def _should_remove(row: Any) -> bool:
    if not isinstance(row, dict):
        return False

    try:
        blob = json.dumps(row, sort_keys=True).lower()
    except Exception:
        blob = str(row).lower()

    user_id = str(row.get("userId", "")).lower()
    workspace_id = str(row.get("workspaceId", "")).lower()

    return (
        user_id == "dev_admin"
        or user_id.startswith("dev_client_")
        or user_id.startswith("firebase_test_user")
        or user_id.startswith("stage9")
        or workspace_id.startswith("mock_")
        or "mock_user_" in blob
        or "firebase_test_user" in blob
        or "stage9" in blob
        or "dev_client_" in blob
        or "dev_admin" in blob
    )


def clean_workspace_membership_state(print_summary: bool = True) -> dict[str, list[dict[str, str]]]:
    if not MEMBERSHIPS_FILE.exists():
        MEMBERSHIPS_FILE.parent.mkdir(parents=True, exist_ok=True)
        MEMBERSHIPS_FILE.write_text("[]\n", encoding="utf-8")
        result = {"removed": [], "kept": []}
        if print_summary:
            print("memberships.json did not exist; created clean empty list.")
        return result

    try:
        data = json.loads(MEMBERSHIPS_FILE.read_text(encoding="utf-8"))
    except Exception:
        data = []

    if not isinstance(data, list):
        data = []

    removed: list[dict[str, str]] = []
    kept: list[dict[str, Any]] = []

    for row in data:
        if isinstance(row, dict) and _should_remove(row):
            removed.append({
                "userId": str(row.get("userId", "")),
                "workspaceId": str(row.get("workspaceId", "")),
            })
        else:
            kept.append(row)

    MEMBERSHIPS_FILE.write_text(
        json.dumps(kept, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    result = {
        "removed": removed,
        "kept": [
            {
                "userId": str(row.get("userId", "")),
                "workspaceId": str(row.get("workspaceId", "")),
            }
            for row in kept
            if isinstance(row, dict)
        ],
    }

    if print_summary:
        print("Removed membership records:", result["removed"])
        print("Kept membership records:", result["kept"])

    return result


if __name__ == "__main__":
    clean_workspace_membership_state(print_summary=True)
