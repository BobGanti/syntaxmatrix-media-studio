from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
BILLING = ROOT / "billing"
USAGE = ROOT / "usage"
REPORTS = ROOT / "reports"

PATHS = {
    "customers": BILLING / "customers.json",
    "workspaces": BILLING / "workspaces.json",
    "memberships": BILLING / "memberships.json",
    "workspaceSubscriptions": BILLING / "workspace_subscriptions.json",
    "usageEvents": USAGE / "usage_events.jsonl",
    "stripeWebhookEvents": BILLING / "stripe_webhook_events.jsonl",
    "stripeProcessedEvents": BILLING / "stripe_processed_events.json",
    "stripePriceMap": BILLING / "stripe_price_map.json",
}


def now_stamp() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    rows: list[dict[str, Any]] = []

    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()

        if not line:
            continue

        try:
            row = json.loads(line)
        except Exception:
            continue

        if isinstance(row, dict):
            rows.append(row)

    return rows


def normalise_subscription_map(data: Any) -> dict[str, dict[str, Any]]:
    if isinstance(data, dict) and isinstance(data.get("subscriptions"), dict):
        data = data["subscriptions"]

    if isinstance(data, dict):
        return {
            str(workspace_id): dict(record)
            for workspace_id, record in data.items()
            if isinstance(record, dict)
        }

    if isinstance(data, list):
        result: dict[str, dict[str, Any]] = {}

        for record in data:
            if isinstance(record, dict) and record.get("workspaceId"):
                result[str(record["workspaceId"])] = dict(record)

        return result

    return {}


def normalise_processed_events(data: Any) -> list[str]:
    if isinstance(data, list):
        return [str(item) for item in data if item]

    if isinstance(data, dict):
        return [str(item) for item in data.get("eventIds", []) if item]

    return []


def build_snapshot() -> dict[str, Any]:
    customers = read_json(PATHS["customers"], [])
    workspaces = read_json(PATHS["workspaces"], [])
    memberships = read_json(PATHS["memberships"], [])
    subscriptions = normalise_subscription_map(read_json(PATHS["workspaceSubscriptions"], {}))
    usage_events = read_jsonl(PATHS["usageEvents"])
    stripe_webhook_events = read_jsonl(PATHS["stripeWebhookEvents"])
    stripe_processed_events = normalise_processed_events(read_json(PATHS["stripeProcessedEvents"], []))
    stripe_price_map = read_json(PATHS["stripePriceMap"], {})

    if not isinstance(customers, list):
        customers = []

    if not isinstance(workspaces, list):
        workspaces = []

    if not isinstance(memberships, list):
        memberships = []

    plans = stripe_price_map.get("plans") if isinstance(stripe_price_map, dict) else {}

    if not isinstance(plans, dict):
        plans = {}

    return {
        "exportedAt": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "source": "json_runtime_storage",
        "paths": {
            key: str(path.relative_to(ROOT))
            for key, path in PATHS.items()
        },
        "counts": {
            "customers": len(customers),
            "workspaces": len(workspaces),
            "memberships": len(memberships),
            "workspaceSubscriptions": len(subscriptions),
            "usageEvents": len(usage_events),
            "stripeWebhookEvents": len(stripe_webhook_events),
            "stripeProcessedEvents": len(stripe_processed_events),
            "stripePriceCatalog": len(plans),
        },
        "data": {
            "customers": customers,
            "workspaces": workspaces,
            "memberships": memberships,
            "workspaceSubscriptions": subscriptions,
            "usageEvents": usage_events,
            "stripeWebhookEvents": stripe_webhook_events,
            "stripeProcessedEvents": stripe_processed_events,
            "stripePriceCatalog": plans,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export local JSON persistence files into one migration snapshot."
    )
    parser.add_argument(
        "--output",
        default="",
        help="Optional output JSON file. Default: reports/json_persistence_snapshot_<timestamp>.json",
    )

    args = parser.parse_args()

    snapshot = build_snapshot()

    if args.output:
        output = Path(args.output)
        if not output.is_absolute():
            output = ROOT / output
    else:
        REPORTS.mkdir(exist_ok=True)
        output = REPORTS / f"json_persistence_snapshot_{now_stamp()}.json"

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(snapshot, indent=2, default=str), encoding="utf-8")

    print("JSON persistence snapshot exported.")
    print(f"Output: {output.relative_to(ROOT)}")
    print("Counts:")
    for key, value in snapshot["counts"].items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
