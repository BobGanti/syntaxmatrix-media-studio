from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SCHEMA = ROOT / "sql" / "postgres_schema.sql"


def clean(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


def database_url() -> str:
    return clean(os.getenv("DATABASE_URL"))


def load_snapshot(path: str = "") -> dict[str, Any]:
    if path:
        source = Path(path)
        if not source.is_absolute():
            source = ROOT / source

        if not source.exists():
            raise SystemExit(f"Snapshot not found: {source}")

        return json.loads(source.read_text(encoding="utf-8"))

    from scripts.export_json_persistence_snapshot import build_snapshot

    return build_snapshot()


def ensure_psycopg():
    try:
        import psycopg  # type: ignore

        return psycopg
    except Exception as exc:
        raise SystemExit(f"psycopg is not installed. Run: pip install psycopg[binary]\n{exc}")


def ensure_schema(conn: Any) -> None:
    if not SCHEMA.exists():
        raise SystemExit(f"Schema file not found: {SCHEMA}")

    sql = SCHEMA.read_text(encoding="utf-8")

    with conn.cursor() as cur:
        cur.execute(sql)

    conn.commit()


def json_dump(value: Any) -> str:
    return json.dumps(value if value is not None else {}, default=str)


def to_float_or_none(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None

    try:
        return float(value)
    except Exception:
        return None


def event_id_from_row(row: dict[str, Any], index: int) -> str:
    for key in ("eventId", "id", "stripeEventId"):
        value = clean(row.get(key))
        if value:
            return value

    return f"jsonl_event_{index}"


def event_type_from_row(row: dict[str, Any]) -> str:
    for key in ("eventType", "type", "event_type"):
        value = clean(row.get(key))
        if value:
            return value

    return "unknown"


def credit_value(row: dict[str, Any]) -> float:
    for key in (
        "credits",
        "creditCost",
        "estimatedCredits",
        "requiredCredits",
        "totalCredits",
        "usedCredits",
        "creditsUsed",
    ):
        if key in row:
            try:
                return float(row.get(key) or 0)
            except Exception:
                return 0.0

    metadata = row.get("metadata")

    if isinstance(metadata, dict):
        return credit_value(metadata)

    return 0.0


def insert_customers(cur: Any, rows: list[dict[str, Any]]) -> int:
    count = 0

    for row in rows:
        customer_id = clean(row.get("customerId") or row.get("customer_id"))

        if not customer_id:
            continue

        cur.execute(
            """
            INSERT INTO customers (
                customer_id,
                name,
                billing_email,
                status,
                updated_at
            )
            VALUES (%s, %s, %s, %s, NOW())
            ON CONFLICT (customer_id)
            DO UPDATE SET
                name = EXCLUDED.name,
                billing_email = EXCLUDED.billing_email,
                status = EXCLUDED.status,
                updated_at = NOW()
            """,
            (
                customer_id,
                clean(row.get("name"), customer_id),
                clean(row.get("billingEmail") or row.get("billing_email")),
                clean(row.get("status"), "active"),
            ),
        )
        count += 1

    return count


def insert_workspaces(cur: Any, rows: list[dict[str, Any]]) -> int:
    count = 0

    for row in rows:
        workspace_id = clean(row.get("workspaceId") or row.get("workspace_id"))
        customer_id = clean(row.get("customerId") or row.get("customer_id"))

        if not workspace_id or not customer_id:
            continue

        cur.execute(
            """
            INSERT INTO workspaces (
                workspace_id,
                customer_id,
                label,
                status,
                subscription_owner_user_id,
                updated_at
            )
            VALUES (%s, %s, %s, %s, %s, NOW())
            ON CONFLICT (workspace_id)
            DO UPDATE SET
                customer_id = EXCLUDED.customer_id,
                label = EXCLUDED.label,
                status = EXCLUDED.status,
                subscription_owner_user_id = EXCLUDED.subscription_owner_user_id,
                updated_at = NOW()
            """,
            (
                workspace_id,
                customer_id,
                clean(row.get("label"), workspace_id),
                clean(row.get("status"), "active"),
                clean(row.get("subscriptionOwnerUserId") or row.get("subscription_owner_user_id")),
            ),
        )
        count += 1

    return count


def insert_memberships(cur: Any, rows: list[dict[str, Any]]) -> int:
    count = 0

    for row in rows:
        user_id = clean(row.get("userId") or row.get("user_id"))
        workspace_id = clean(row.get("workspaceId") or row.get("workspace_id"))

        if not user_id or not workspace_id:
            continue

        cur.execute(
            """
            INSERT INTO workspace_memberships (
                user_id,
                workspace_id,
                role,
                status,
                updated_at
            )
            VALUES (%s, %s, %s, %s, NOW())
            ON CONFLICT (user_id, workspace_id)
            DO UPDATE SET
                role = EXCLUDED.role,
                status = EXCLUDED.status,
                updated_at = NOW()
            """,
            (
                user_id,
                workspace_id,
                clean(row.get("role"), "member"),
                clean(row.get("status"), "active"),
            ),
        )
        count += 1

    return count


def insert_subscriptions(cur: Any, rows: dict[str, dict[str, Any]]) -> int:
    count = 0

    for workspace_id, row in rows.items():
        workspace_id = clean(row.get("workspaceId") or workspace_id)

        if not workspace_id:
            continue

        plan_key = clean(row.get("planKey") or row.get("plan"), "starter")

        cur.execute(
            """
            INSERT INTO workspace_subscriptions (
                workspace_id,
                plan_key,
                plan_label,
                status,
                provider,
                monthly_credit_limit,
                monthly_credits,
                monthly_price,
                customer_id,
                subscription_id,
                stripe_customer_id,
                stripe_subscription_id,
                checkout_session_id,
                last_stripe_event_id,
                last_stripe_event_type,
                last_stripe_invoice_id,
                raw_payload,
                updated_at
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, NOW()
            )
            ON CONFLICT (workspace_id)
            DO UPDATE SET
                plan_key = EXCLUDED.plan_key,
                plan_label = EXCLUDED.plan_label,
                status = EXCLUDED.status,
                provider = EXCLUDED.provider,
                monthly_credit_limit = EXCLUDED.monthly_credit_limit,
                monthly_credits = EXCLUDED.monthly_credits,
                monthly_price = EXCLUDED.monthly_price,
                customer_id = EXCLUDED.customer_id,
                subscription_id = EXCLUDED.subscription_id,
                stripe_customer_id = EXCLUDED.stripe_customer_id,
                stripe_subscription_id = EXCLUDED.stripe_subscription_id,
                checkout_session_id = EXCLUDED.checkout_session_id,
                last_stripe_event_id = EXCLUDED.last_stripe_event_id,
                last_stripe_event_type = EXCLUDED.last_stripe_event_type,
                last_stripe_invoice_id = EXCLUDED.last_stripe_invoice_id,
                raw_payload = EXCLUDED.raw_payload,
                updated_at = NOW()
            """,
            (
                workspace_id,
                plan_key,
                clean(row.get("planLabel") or row.get("label"), plan_key),
                clean(row.get("status"), "active"),
                clean(row.get("provider"), "local"),
                to_float_or_none(row.get("monthlyCreditLimit")),
                to_float_or_none(row.get("monthlyCredits")),
                to_float_or_none(row.get("monthlyPrice")),
                clean(row.get("customerId")),
                clean(row.get("subscriptionId")),
                clean(row.get("stripeCustomerId") or row.get("customerId")),
                clean(row.get("stripeSubscriptionId") or row.get("subscriptionId")),
                clean(row.get("checkoutSessionId")),
                clean(row.get("lastStripeEventId")),
                clean(row.get("lastStripeEventType")),
                clean(row.get("lastStripeInvoiceId")),
                json_dump(row),
            ),
        )
        count += 1

    return count


def insert_usage_events(cur: Any, rows: list[dict[str, Any]]) -> int:
    count = 0

    for row in rows:
        workspace_id = clean(row.get("workspaceId") or row.get("workspace_id"))

        if not workspace_id:
            continue

        cur.execute(
            """
            INSERT INTO usage_events (
                workspace_id,
                event_type,
                credits,
                provider,
                model,
                source_id,
                output_id,
                metadata,
                created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, COALESCE(%s::timestamptz, NOW()))
            """,
            (
                workspace_id,
                clean(row.get("eventType") or row.get("event_type"), "usage"),
                credit_value(row),
                clean(row.get("provider")),
                clean(row.get("model")),
                clean(row.get("sourceId") or row.get("source_id")),
                clean(row.get("outputId") or row.get("output_id")),
                json_dump(row.get("metadata") if isinstance(row.get("metadata"), dict) else row),
                clean(row.get("createdAt") or row.get("timestamp") or row.get("time")) or None,
            ),
        )
        count += 1

    return count


def insert_stripe_webhook_events(cur: Any, rows: list[dict[str, Any]]) -> int:
    count = 0

    for index, row in enumerate(rows):
        event_id = event_id_from_row(row, index)
        event_type = event_type_from_row(row)

        cur.execute(
            """
            INSERT INTO stripe_webhook_events (
                event_id,
                event_type,
                result,
                received_at
            )
            VALUES (%s, %s, %s::jsonb, COALESCE(%s::timestamptz, NOW()))
            ON CONFLICT (event_id)
            DO UPDATE SET
                event_type = EXCLUDED.event_type,
                result = EXCLUDED.result,
                received_at = EXCLUDED.received_at
            """,
            (
                event_id,
                event_type,
                json_dump(row.get("result") if isinstance(row.get("result"), dict) else row),
                clean(row.get("receivedAt") or row.get("createdAt")) or None,
            ),
        )
        count += 1

    return count


def insert_processed_events(cur: Any, rows: list[str]) -> int:
    count = 0

    for event_id in rows:
        event_id = clean(event_id)

        if not event_id:
            continue

        cur.execute(
            """
            INSERT INTO stripe_processed_events (event_id, processed_at)
            VALUES (%s, NOW())
            ON CONFLICT (event_id) DO NOTHING
            """,
            (event_id,),
        )
        count += 1

    return count


def insert_price_catalog(cur: Any, plans: dict[str, dict[str, Any]]) -> int:
    count = 0

    for plan_key, row in plans.items():
        plan_key = clean(row.get("planKey") or plan_key)
        price_id = clean(row.get("priceId"))

        if not plan_key or not price_id:
            continue

        cur.execute(
            """
            INSERT INTO stripe_price_catalog (
                plan_key,
                plan_label,
                product_id,
                price_id,
                currency,
                unit_amount,
                monthly_price,
                monthly_credits,
                active,
                stripe_mode,
                metadata,
                updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, NOW())
            ON CONFLICT (plan_key)
            DO UPDATE SET
                plan_label = EXCLUDED.plan_label,
                product_id = EXCLUDED.product_id,
                price_id = EXCLUDED.price_id,
                currency = EXCLUDED.currency,
                unit_amount = EXCLUDED.unit_amount,
                monthly_price = EXCLUDED.monthly_price,
                monthly_credits = EXCLUDED.monthly_credits,
                active = EXCLUDED.active,
                stripe_mode = EXCLUDED.stripe_mode,
                metadata = EXCLUDED.metadata,
                updated_at = NOW()
            """,
            (
                plan_key,
                clean(row.get("planLabel"), plan_key),
                clean(row.get("productId")),
                price_id,
                clean(row.get("currency"), "eur").lower(),
                int(row.get("unitAmount") or 0),
                to_float_or_none(row.get("monthlyPrice")),
                to_float_or_none(row.get("monthlyCredits")),
                bool(row.get("active", True)),
                clean(row.get("stripeMode") or row.get("mode"), "test"),
                json_dump(row.get("metadata") if isinstance(row.get("metadata"), dict) else row),
            ),
        )
        count += 1

    return count


def run_migration(snapshot: dict[str, Any], *, dry_run: bool, init_schema: bool) -> dict[str, Any]:
    data = snapshot.get("data") if isinstance(snapshot.get("data"), dict) else {}

    counts = {
        "customers": len(data.get("customers") or []),
        "workspaces": len(data.get("workspaces") or []),
        "memberships": len(data.get("memberships") or []),
        "workspaceSubscriptions": len(data.get("workspaceSubscriptions") or {}),
        "usageEvents": len(data.get("usageEvents") or []),
        "stripeWebhookEvents": len(data.get("stripeWebhookEvents") or []),
        "stripeProcessedEvents": len(data.get("stripeProcessedEvents") or []),
        "stripePriceCatalog": len(data.get("stripePriceCatalog") or {}),
    }

    if dry_run:
        return {
            "dryRun": True,
            "wouldWrite": counts,
        }

    url = database_url()

    if not url or url.startswith("replace"):
        raise SystemExit("DATABASE_URL is not configured.")

    psycopg = ensure_psycopg()

    with psycopg.connect(url) as conn:
        if init_schema:
            ensure_schema(conn)

        with conn.cursor() as cur:
            written = {
                "customers": insert_customers(cur, data.get("customers") or []),
                "workspaces": insert_workspaces(cur, data.get("workspaces") or []),
                "memberships": insert_memberships(cur, data.get("memberships") or []),
                "workspaceSubscriptions": insert_subscriptions(cur, data.get("workspaceSubscriptions") or {}),
                "usageEvents": insert_usage_events(cur, data.get("usageEvents") or []),
                "stripeWebhookEvents": insert_stripe_webhook_events(cur, data.get("stripeWebhookEvents") or []),
                "stripeProcessedEvents": insert_processed_events(cur, data.get("stripeProcessedEvents") or []),
                "stripePriceCatalog": insert_price_catalog(cur, data.get("stripePriceCatalog") or {}),
            }

        conn.commit()

    return {
        "dryRun": False,
        "written": written,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migrate local JSON persistence data to PostgreSQL / Cloud SQL."
    )
    parser.add_argument(
        "--snapshot",
        default="",
        help="Optional exported snapshot file. Default: read live JSON files.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only show what would be written. This is safe and requires no database.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually write to DATABASE_URL.",
    )
    parser.add_argument(
        "--init-schema",
        action="store_true",
        help="Initialise sql/postgres_schema.sql before writing.",
    )

    args = parser.parse_args()

    if args.apply and args.dry_run:
        raise SystemExit("Use either --dry-run or --apply, not both.")

    if not args.apply:
        args.dry_run = True

    snapshot = load_snapshot(args.snapshot)
    result = run_migration(snapshot, dry_run=args.dry_run, init_schema=args.init_schema)

    print(json.dumps({
        "ok": True,
        "source": snapshot.get("source"),
        "exportedAt": snapshot.get("exportedAt"),
        **result,
    }, indent=2, default=str))

    if args.dry_run:
        print()
        print("Dry run only. No database was changed.")
        print("To apply later:")
        print("  python scripts/migrate_json_to_postgres.py --apply --init-schema")


if __name__ == "__main__":
    main()
