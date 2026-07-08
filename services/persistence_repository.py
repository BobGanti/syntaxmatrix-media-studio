from __future__ import annotations

import datetime as _dt
import json
import os
import pathlib
from dataclasses import dataclass
from typing import Any, Protocol


ROOT = pathlib.Path(__file__).resolve().parent.parent
BILLING_DIR = ROOT / "billing"
USAGE_DIR = ROOT / "usage"

CUSTOMERS_PATH = BILLING_DIR / "customers.json"
WORKSPACES_PATH = BILLING_DIR / "workspaces.json"
MEMBERSHIPS_PATH = BILLING_DIR / "memberships.json"
SUBSCRIPTIONS_PATH = BILLING_DIR / "workspace_subscriptions.json"
USAGE_EVENTS_PATH = USAGE_DIR / "usage_events.jsonl"
STRIPE_EVENTS_PATH = BILLING_DIR / "stripe_webhook_events.jsonl"
STRIPE_PROCESSED_PATH = BILLING_DIR / "stripe_processed_events.json"
STRIPE_PRICE_MAP_PATH = BILLING_DIR / "stripe_price_map.json"


def _now() -> str:
    return _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds")


def _clean(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


def _backend() -> str:
    value = _clean(os.getenv("PERSISTENCE_BACKEND"), "json").lower()

    if value not in {"json", "postgres"}:
        return "json"

    return value


def _database_url() -> str:
    return _clean(os.getenv("DATABASE_URL"))


def _read_json(path: pathlib.Path, default: Any) -> Any:
    if not path.exists():
        return default

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path: pathlib.Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(path)


def _append_jsonl(path: pathlib.Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def _read_jsonl(path: pathlib.Path) -> list[dict[str, Any]]:
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


def _normalise_subscription_map(data: Any) -> dict[str, dict[str, Any]]:
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


def _to_float(value: Any) -> float:
    if value is None or isinstance(value, bool):
        return 0.0

    if isinstance(value, (int, float)):
        return float(value)

    try:
        return float(str(value).strip())
    except Exception:
        return 0.0


def _month_prefix(month: str | None = None) -> str:
    return _clean(month) or _dt.datetime.now(_dt.UTC).strftime("%Y-%m")


def _extract_credit_value(row: dict[str, Any]) -> float:
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
            return _to_float(row.get(key))

    metadata = row.get("metadata")

    if isinstance(metadata, dict):
        return _extract_credit_value(metadata)

    return 0.0


@dataclass(frozen=True)
class RepositoryStatus:
    backend: str
    ready: bool
    database_url_configured: bool
    driver_installed: bool
    error: str = ""

    def to_payload(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "ready": self.ready,
            "databaseUrlConfigured": self.database_url_configured,
            "driverInstalled": self.driver_installed,
            "error": self.error,
        }


class PersistenceRepository(Protocol):
    backend_name: str

    def status(self) -> RepositoryStatus:
        ...

    def list_customers(self) -> list[dict[str, Any]]:
        ...

    def list_workspaces(self) -> list[dict[str, Any]]:
        ...

    def list_memberships(self) -> list[dict[str, Any]]:
        ...

    def get_workspace_subscription(self, workspace_id: str) -> dict[str, Any] | None:
        ...

    def upsert_workspace_subscription(self, workspace_id: str, record: dict[str, Any]) -> dict[str, Any]:
        ...

    def append_usage_event(self, row: dict[str, Any]) -> dict[str, Any]:
        ...

    def usage_credits_this_month(self, workspace_id: str, month: str | None = None) -> float:
        ...

    def stripe_event_processed(self, event_id: str) -> bool:
        ...

    def mark_stripe_event_processed(self, event_id: str) -> None:
        ...

    def append_stripe_webhook_event(self, row: dict[str, Any]) -> dict[str, Any]:
        ...

    def list_stripe_price_catalog(self) -> list[dict[str, Any]]:
        ...


class JsonPersistenceRepository:
    backend_name = "json"

    def status(self) -> RepositoryStatus:
        return RepositoryStatus(
            backend="json",
            ready=True,
            database_url_configured=False,
            driver_installed=False,
            error="",
        )

    def list_customers(self) -> list[dict[str, Any]]:
        data = _read_json(CUSTOMERS_PATH, [])

        return [dict(row) for row in data if isinstance(row, dict)] if isinstance(data, list) else []

    def list_workspaces(self) -> list[dict[str, Any]]:
        data = _read_json(WORKSPACES_PATH, [])

        return [dict(row) for row in data if isinstance(row, dict)] if isinstance(data, list) else []

    def list_memberships(self) -> list[dict[str, Any]]:
        data = _read_json(MEMBERSHIPS_PATH, [])

        return [dict(row) for row in data if isinstance(row, dict)] if isinstance(data, list) else []

    def get_workspace_subscription(self, workspace_id: str) -> dict[str, Any] | None:
        workspace_id = _clean(workspace_id)
        records = _normalise_subscription_map(_read_json(SUBSCRIPTIONS_PATH, {}))

        record = records.get(workspace_id)

        return dict(record) if isinstance(record, dict) else None

    def upsert_workspace_subscription(self, workspace_id: str, record: dict[str, Any]) -> dict[str, Any]:
        workspace_id = _clean(workspace_id)

        if not workspace_id:
            raise ValueError("workspace_id is required")

        records = _normalise_subscription_map(_read_json(SUBSCRIPTIONS_PATH, {}))
        previous = dict(records.get(workspace_id, {}))

        updated = dict(previous)
        updated.update(dict(record))
        updated["workspaceId"] = workspace_id
        updated["updatedAt"] = _now()

        if not updated.get("createdAt"):
            updated["createdAt"] = _now()

        records[workspace_id] = updated
        _write_json(SUBSCRIPTIONS_PATH, records)

        return updated

    def append_usage_event(self, row: dict[str, Any]) -> dict[str, Any]:
        record = dict(row)

        if not record.get("createdAt"):
            record["createdAt"] = _now()

        _append_jsonl(USAGE_EVENTS_PATH, record)

        return record

    def usage_credits_this_month(self, workspace_id: str, month: str | None = None) -> float:
        workspace_id = _clean(workspace_id)
        prefix = _month_prefix(month)
        total = 0.0

        for row in _read_jsonl(USAGE_EVENTS_PATH):
            if _clean(row.get("workspaceId")) != workspace_id:
                continue

            timestamp = _clean(row.get("createdAt") or row.get("timestamp") or row.get("time"))

            if timestamp and not timestamp.startswith(prefix):
                continue

            total += _extract_credit_value(row)

        return total

    def stripe_event_processed(self, event_id: str) -> bool:
        event_id = _clean(event_id)

        if not event_id:
            return False

        data = _read_json(STRIPE_PROCESSED_PATH, [])

        if isinstance(data, list):
            return event_id in {str(item) for item in data}

        if isinstance(data, dict):
            return event_id in {str(item) for item in data.get("eventIds", [])}

        return False

    def mark_stripe_event_processed(self, event_id: str) -> None:
        event_id = _clean(event_id)

        if not event_id:
            return

        data = _read_json(STRIPE_PROCESSED_PATH, [])

        if isinstance(data, list):
            event_ids = {str(item) for item in data}
        elif isinstance(data, dict):
            event_ids = {str(item) for item in data.get("eventIds", [])}
        else:
            event_ids = set()

        event_ids.add(event_id)
        _write_json(STRIPE_PROCESSED_PATH, sorted(event_ids)[-5000:])

    def append_stripe_webhook_event(self, row: dict[str, Any]) -> dict[str, Any]:
        record = dict(row)

        if not record.get("receivedAt"):
            record["receivedAt"] = _now()

        _append_jsonl(STRIPE_EVENTS_PATH, record)

        return record

    def list_stripe_price_catalog(self) -> list[dict[str, Any]]:
        data = _read_json(STRIPE_PRICE_MAP_PATH, {})
        plans = data.get("plans") if isinstance(data, dict) else {}

        if not isinstance(plans, dict):
            return []

        rows = []

        for key, record in plans.items():
            if not isinstance(record, dict):
                continue

            item = dict(record)
            item.setdefault("planKey", key)
            rows.append(item)

        return rows


class PostgresPersistenceRepository:
    backend_name = "postgres"

    def __init__(self, database_url: str | None = None):
        self.database_url = _clean(database_url or _database_url())

    def _connect(self):
        if not self.database_url or self.database_url.startswith("replace"):
            raise RuntimeError("DATABASE_URL is not configured.")

        try:
            import psycopg  # type: ignore
        except Exception as exc:
            raise RuntimeError("psycopg is not installed. Run: pip install psycopg[binary]") from exc

        return psycopg.connect(self.database_url)

    def status(self) -> RepositoryStatus:
        db_configured = bool(self.database_url and not self.database_url.startswith("replace"))

        try:
            import psycopg  # type: ignore

            driver_installed = True
        except Exception as exc:
            return RepositoryStatus(
                backend="postgres",
                ready=False,
                database_url_configured=db_configured,
                driver_installed=False,
                error=str(exc),
            )

        if not db_configured:
            return RepositoryStatus(
                backend="postgres",
                ready=False,
                database_url_configured=False,
                driver_installed=driver_installed,
                error="DATABASE_URL is not configured.",
            )

        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    cur.fetchone()

            return RepositoryStatus(
                backend="postgres",
                ready=True,
                database_url_configured=True,
                driver_installed=True,
                error="",
            )
        except Exception as exc:
            return RepositoryStatus(
                backend="postgres",
                ready=False,
                database_url_configured=True,
                driver_installed=True,
                error=str(exc),
            )

    def _fetch_all(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                columns = [desc[0] for desc in cur.description]
                return [
                    {
                        columns[index]: value
                        for index, value in enumerate(row)
                    }
                    for row in cur.fetchall()
                ]

    def _execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
            conn.commit()

    def list_customers(self) -> list[dict[str, Any]]:
        return self._fetch_all(
            """
            SELECT
                customer_id AS "customerId",
                name,
                billing_email AS "billingEmail",
                status,
                created_at AS "createdAt",
                updated_at AS "updatedAt"
            FROM customers
            ORDER BY created_at ASC
            """
        )

    def list_workspaces(self) -> list[dict[str, Any]]:
        return self._fetch_all(
            """
            SELECT
                workspace_id AS "workspaceId",
                customer_id AS "customerId",
                label,
                status,
                subscription_owner_user_id AS "subscriptionOwnerUserId",
                created_at AS "createdAt",
                updated_at AS "updatedAt"
            FROM workspaces
            ORDER BY created_at ASC
            """
        )

    def list_memberships(self) -> list[dict[str, Any]]:
        return self._fetch_all(
            """
            SELECT
                user_id AS "userId",
                workspace_id AS "workspaceId",
                role,
                status,
                created_at AS "createdAt",
                updated_at AS "updatedAt"
            FROM workspace_memberships
            ORDER BY created_at ASC
            """
        )

    def get_workspace_subscription(self, workspace_id: str) -> dict[str, Any] | None:
        rows = self._fetch_all(
            """
            SELECT
                workspace_id AS "workspaceId",
                plan_key AS "planKey",
                plan_label AS "planLabel",
                status,
                provider,
                monthly_credit_limit AS "monthlyCreditLimit",
                monthly_credits AS "monthlyCredits",
                monthly_price AS "monthlyPrice",
                customer_id AS "customerId",
                subscription_id AS "subscriptionId",
                stripe_customer_id AS "stripeCustomerId",
                stripe_subscription_id AS "stripeSubscriptionId",
                checkout_session_id AS "checkoutSessionId",
                current_period_start AS "currentPeriodStart",
                current_period_end AS "currentPeriodEnd",
                last_stripe_event_id AS "lastStripeEventId",
                last_stripe_event_type AS "lastStripeEventType",
                last_stripe_invoice_id AS "lastStripeInvoiceId",
                raw_payload AS "rawPayload",
                created_at AS "createdAt",
                updated_at AS "updatedAt"
            FROM workspace_subscriptions
            WHERE workspace_id = %s
            """,
            (_clean(workspace_id),),
        )

        return rows[0] if rows else None

    def upsert_workspace_subscription(self, workspace_id: str, record: dict[str, Any]) -> dict[str, Any]:
        workspace_id = _clean(workspace_id)

        if not workspace_id:
            raise ValueError("workspace_id is required")

        payload = dict(record)
        plan_key = _clean(payload.get("planKey") or payload.get("plan"), "starter")

        self._execute(
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
                payload.get("planLabel") or payload.get("label") or plan_key,
                payload.get("status") or "active",
                payload.get("provider") or "local",
                payload.get("monthlyCreditLimit"),
                payload.get("monthlyCredits"),
                payload.get("monthlyPrice"),
                payload.get("customerId"),
                payload.get("subscriptionId"),
                payload.get("stripeCustomerId"),
                payload.get("stripeSubscriptionId"),
                payload.get("checkoutSessionId"),
                payload.get("lastStripeEventId"),
                payload.get("lastStripeEventType"),
                payload.get("lastStripeInvoiceId"),
                json.dumps(payload),
            ),
        )

        result = self.get_workspace_subscription(workspace_id)

        return result or {
            "workspaceId": workspace_id,
            **payload,
        }

    def append_usage_event(self, row: dict[str, Any]) -> dict[str, Any]:
        record = dict(row)
        workspace_id = _clean(record.get("workspaceId"))

        if not workspace_id:
            raise ValueError("workspaceId is required")

        self._execute(
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
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, NOW())
            """,
            (
                workspace_id,
                record.get("eventType") or record.get("event_type") or "usage",
                _extract_credit_value(record),
                record.get("provider"),
                record.get("model"),
                record.get("sourceId") or record.get("source_id"),
                record.get("outputId") or record.get("output_id"),
                json.dumps(record.get("metadata") if isinstance(record.get("metadata"), dict) else record),
            ),
        )

        return record

    def usage_credits_this_month(self, workspace_id: str, month: str | None = None) -> float:
        prefix = _month_prefix(month)

        rows = self._fetch_all(
            """
            SELECT COALESCE(SUM(credits), 0) AS credits
            FROM usage_events
            WHERE workspace_id = %s
              AND to_char(created_at, 'YYYY-MM') = %s
            """,
            (_clean(workspace_id), prefix),
        )

        return _to_float(rows[0].get("credits") if rows else 0)

    def stripe_event_processed(self, event_id: str) -> bool:
        rows = self._fetch_all(
            "SELECT event_id AS \"eventId\" FROM stripe_processed_events WHERE event_id = %s",
            (_clean(event_id),),
        )

        return bool(rows)

    def mark_stripe_event_processed(self, event_id: str) -> None:
        event_id = _clean(event_id)

        if not event_id:
            return

        self._execute(
            """
            INSERT INTO stripe_processed_events (event_id, processed_at)
            VALUES (%s, NOW())
            ON CONFLICT (event_id) DO NOTHING
            """,
            (event_id,),
        )

    def append_stripe_webhook_event(self, row: dict[str, Any]) -> dict[str, Any]:
        record = dict(row)

        self._execute(
            """
            INSERT INTO stripe_webhook_events (
                event_id,
                event_type,
                result,
                received_at
            )
            VALUES (%s, %s, %s::jsonb, NOW())
            ON CONFLICT (event_id)
            DO UPDATE SET
                event_type = EXCLUDED.event_type,
                result = EXCLUDED.result,
                received_at = EXCLUDED.received_at
            """,
            (
                record.get("eventId"),
                record.get("eventType") or "unknown",
                json.dumps(record.get("result") if isinstance(record.get("result"), dict) else record),
            ),
        )

        return record

    def list_stripe_price_catalog(self) -> list[dict[str, Any]]:
        return self._fetch_all(
            """
            SELECT
                plan_key AS "planKey",
                plan_label AS "planLabel",
                product_id AS "productId",
                price_id AS "priceId",
                currency,
                unit_amount AS "unitAmount",
                monthly_price AS "monthlyPrice",
                monthly_credits AS "monthlyCredits",
                active,
                stripe_mode AS "stripeMode",
                metadata,
                created_at AS "createdAt",
                updated_at AS "updatedAt"
            FROM stripe_price_catalog
            ORDER BY created_at ASC
            """
        )


def get_persistence_repository() -> PersistenceRepository:
    backend = _backend()

    if backend == "postgres":
        return PostgresPersistenceRepository()

    return JsonPersistenceRepository()


def repository_smoke_test() -> dict[str, Any]:
    repo = get_persistence_repository()
    status = repo.status()

    payload: dict[str, Any] = {
        "status": status.to_payload(),
        "backend": repo.backend_name,
        "canRead": False,
        "counts": {},
        "sample": {},
    }

    if not status.ready:
        payload["error"] = status.error
        return payload

    customers = repo.list_customers()
    workspaces = repo.list_workspaces()
    memberships = repo.list_memberships()
    price_catalog = repo.list_stripe_price_catalog()

    payload["canRead"] = True
    payload["counts"] = {
        "customers": len(customers),
        "workspaces": len(workspaces),
        "memberships": len(memberships),
        "stripePriceCatalog": len(price_catalog),
    }
    payload["sample"] = {
        "firstCustomer": customers[0] if customers else None,
        "firstWorkspace": workspaces[0] if workspaces else None,
    }

    return payload


# ---------------------------------------------------------------------
# Step 33C repository helpers
# These keep service modules from directly reading JSON files.
# ---------------------------------------------------------------------
def list_workspace_subscriptions() -> list[dict[str, Any]]:
    repo = get_persistence_repository()

    if repo.backend_name == "json":
        records = _normalise_subscription_map(_read_json(SUBSCRIPTIONS_PATH, {}))
        return [dict(record) for record in records.values()]

    if isinstance(repo, PostgresPersistenceRepository):
        return repo._fetch_all(
            """
            SELECT
                workspace_id AS "workspaceId",
                plan_key AS "planKey",
                plan_label AS "planLabel",
                status,
                provider,
                monthly_credit_limit AS "monthlyCreditLimit",
                monthly_credits AS "monthlyCredits",
                monthly_price AS "monthlyPrice",
                customer_id AS "customerId",
                subscription_id AS "subscriptionId",
                stripe_customer_id AS "stripeCustomerId",
                stripe_subscription_id AS "stripeSubscriptionId",
                checkout_session_id AS "checkoutSessionId",
                current_period_start AS "currentPeriodStart",
                current_period_end AS "currentPeriodEnd",
                last_stripe_event_id AS "lastStripeEventId",
                last_stripe_event_type AS "lastStripeEventType",
                last_stripe_invoice_id AS "lastStripeInvoiceId",
                raw_payload AS "rawPayload",
                created_at AS "createdAt",
                updated_at AS "updatedAt"
            FROM workspace_subscriptions
            ORDER BY updated_at DESC
            """
        )

    return []


def find_workspace_subscription_by_stripe_subscription_id(subscription_id: str) -> dict[str, Any] | None:
    subscription_id = _clean(subscription_id)

    if not subscription_id:
        return None

    repo = get_persistence_repository()

    if repo.backend_name == "json":
        for record in list_workspace_subscriptions():
            if (
                _clean(record.get("subscriptionId")) == subscription_id
                or _clean(record.get("stripeSubscriptionId")) == subscription_id
            ):
                return dict(record)

        return None

    if isinstance(repo, PostgresPersistenceRepository):
        rows = repo._fetch_all(
            """
            SELECT
                workspace_id AS "workspaceId",
                plan_key AS "planKey",
                plan_label AS "planLabel",
                status,
                provider,
                monthly_credit_limit AS "monthlyCreditLimit",
                monthly_credits AS "monthlyCredits",
                monthly_price AS "monthlyPrice",
                customer_id AS "customerId",
                subscription_id AS "subscriptionId",
                stripe_customer_id AS "stripeCustomerId",
                stripe_subscription_id AS "stripeSubscriptionId",
                checkout_session_id AS "checkoutSessionId",
                current_period_start AS "currentPeriodStart",
                current_period_end AS "currentPeriodEnd",
                last_stripe_event_id AS "lastStripeEventId",
                last_stripe_event_type AS "lastStripeEventType",
                last_stripe_invoice_id AS "lastStripeInvoiceId",
                raw_payload AS "rawPayload",
                created_at AS "createdAt",
                updated_at AS "updatedAt"
            FROM workspace_subscriptions
            WHERE stripe_subscription_id = %s OR subscription_id = %s
            LIMIT 1
            """,
            (subscription_id, subscription_id),
        )

        return rows[0] if rows else None

    return None


def processed_stripe_event_ids(limit: int = 5000) -> set[str]:
    repo = get_persistence_repository()

    if repo.backend_name == "json":
        data = _read_json(STRIPE_PROCESSED_PATH, [])

        if isinstance(data, list):
            return {str(item) for item in data if item}

        if isinstance(data, dict):
            return {str(item) for item in data.get("eventIds", []) if item}

        return set()

    if isinstance(repo, PostgresPersistenceRepository):
        rows = repo._fetch_all(
            """
            SELECT event_id AS "eventId"
            FROM stripe_processed_events
            ORDER BY processed_at DESC
            LIMIT %s
            """,
            (int(limit),),
        )

        return {str(row.get("eventId")) for row in rows if row.get("eventId")}

    return set()
