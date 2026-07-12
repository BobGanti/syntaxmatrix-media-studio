from __future__ import annotations

import argparse

from services.persistence_repository import (
    get_persistence_repository,
    list_workspace_subscriptions,
)


def clean(value):
    return str(value or "").strip()


def main():
    parser = argparse.ArgumentParser(
        description="Require payment for existing non-Stripe beta workspaces."
    )
    parser.add_argument("--apply", action="store_true", help="Write changes. Default is dry-run.")
    args = parser.parse_args()

    repo = get_persistence_repository()
    changed = 0

    for record in list_workspace_subscriptions():
        workspace_id = clean(record.get("workspaceId"))
        provider = clean(record.get("provider")).lower()
        stripe_customer = clean(record.get("stripeCustomerId") or record.get("customerId"))
        stripe_subscription = clean(record.get("stripeSubscriptionId") or record.get("subscriptionId"))

        if not workspace_id:
            continue
        if provider == "stripe" and (stripe_customer.startswith("cus_") or stripe_subscription.startswith("sub_")):
            continue

        print(f"{'APPLY' if args.apply else 'WOULD UPDATE'}: {workspace_id} -> incomplete / stripe")
        changed += 1

        if args.apply:
            updated = dict(record)
            updated.update({
                "workspaceId": workspace_id,
                "planKey": clean(record.get("planKey") or record.get("plan") or "starter"),
                "status": "incomplete",
                "provider": "stripe",
                "customerId": "",
                "subscriptionId": "",
                "stripeCustomerId": "",
                "stripeSubscriptionId": "",
            })
            repo.upsert_workspace_subscription(workspace_id, updated)

    print(f"Candidates: {changed}")
    print("Existing paid Stripe subscriptions were preserved.")
    print("Mode:", "APPLIED" if args.apply else "DRY RUN")


if __name__ == "__main__":
    main()
