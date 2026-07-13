from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SUBSCRIPTION_FILE = ROOT / "billing" / "workspace_subscriptions.json"


def _should_remove(key: str, value: Any) -> bool:
    key_text = str(key or "").strip().lower()

    try:
        blob = json.dumps(value, sort_keys=True).lower()
    except Exception:
        blob = str(value).lower()

    return (
        key_text.startswith("mock_")
        or key_text.startswith("__smx_")
        or "acceptance_workspace" in key_text
        or "mock_user_" in blob
        or "__smx_" in blob
        or "cs_test_" in blob
    )


def clean_workspace_subscription_state(print_summary: bool = True) -> dict[str, list[str]]:
    if not SUBSCRIPTION_FILE.exists():
        SUBSCRIPTION_FILE.parent.mkdir(parents=True, exist_ok=True)
        SUBSCRIPTION_FILE.write_text("{}\n", encoding="utf-8")
        result = {"removed": [], "kept": []}
        if print_summary:
            print("workspace_subscriptions.json did not exist; created clean empty file.")
        return result

    try:
        data = json.loads(SUBSCRIPTION_FILE.read_text(encoding="utf-8"))
    except Exception:
        data = {}

    if not isinstance(data, dict):
        data = {}

    removed: list[str] = []
    kept: dict[str, Any] = {}

    for key, value in data.items():
        if _should_remove(key, value):
            removed.append(str(key))
        else:
            kept[str(key)] = value

    SUBSCRIPTION_FILE.write_text(
        json.dumps(kept, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    result = {"removed": removed, "kept": sorted(kept.keys())}

    if print_summary:
        print("Removed subscription records:", removed)
        print("Kept subscription records:", sorted(kept.keys()))

    return result


if __name__ == "__main__":
    clean_workspace_subscription_state(print_summary=True)
