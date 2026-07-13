from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CUSTOMERS_FILE = ROOT / "billing" / "customers.json"


def _should_remove(row: Any) -> bool:
    if not isinstance(row, dict):
        return False

    try:
        blob = json.dumps(row, sort_keys=True).lower()
    except Exception:
        blob = str(row).lower()

    customer_id = str(row.get("customerId", "")).lower()
    email = str(row.get("billingEmail", "")).lower()
    name = str(row.get("name", "")).lower()
    owner = str(row.get("ownerUserId", "")).lower()

    return (
        customer_id.startswith("cust_mock_")
        or customer_id.startswith("cust_fb_")
        or email.endswith("@example.test")
        or "example.test" in email
        or "client a" in name
        or "client b" in name
        or "stage9" in name
        or "stage9" in owner
        or owner.startswith("firebase_test_user")
        or "cust_mock_" in blob
        or "firebase_test_user" in blob
        or "stage9" in blob
    )


def clean_customer_registry_state(print_summary: bool = True) -> dict[str, list[dict[str, str]]]:
    if not CUSTOMERS_FILE.exists():
        CUSTOMERS_FILE.parent.mkdir(parents=True, exist_ok=True)
        CUSTOMERS_FILE.write_text("[]\n", encoding="utf-8")
        result = {"removed": [], "kept": []}
        if print_summary:
            print("customers.json did not exist; created clean empty list.")
        return result

    try:
        data = json.loads(CUSTOMERS_FILE.read_text(encoding="utf-8"))
    except Exception:
        data = []

    if not isinstance(data, list):
        data = []

    removed: list[dict[str, str]] = []
    kept: list[dict[str, Any]] = []

    for row in data:
        if isinstance(row, dict) and _should_remove(row):
            removed.append({
                "customerId": str(row.get("customerId", "")),
                "billingEmail": str(row.get("billingEmail", "")),
                "ownerUserId": str(row.get("ownerUserId", "")),
            })
        else:
            kept.append(row)

    CUSTOMERS_FILE.write_text(
        json.dumps(kept, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    result = {
        "removed": removed,
        "kept": [
            {
                "customerId": str(row.get("customerId", "")),
                "billingEmail": str(row.get("billingEmail", "")),
                "ownerUserId": str(row.get("ownerUserId", "")),
            }
            for row in kept
            if isinstance(row, dict)
        ],
    }

    if print_summary:
        print("Removed customer records:", result["removed"])
        print("Kept customer records:", result["kept"])

    return result


if __name__ == "__main__":
    clean_customer_registry_state(print_summary=True)
