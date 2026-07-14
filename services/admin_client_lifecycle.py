from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus


ROOT = Path(__file__).resolve().parents[1]
BILLING_DIR = ROOT / "billing"

CUSTOMERS_FILE = BILLING_DIR / "customers.json"
WORKSPACES_FILE = BILLING_DIR / "workspaces.json"
MEMBERSHIPS_FILE = BILLING_DIR / "memberships.json"
SUBSCRIPTIONS_FILE = BILLING_DIR / "workspace_subscriptions.json"

ACTIVE_STRIPE_STATUSES = {"active", "trialing", "past_due"}


class AdminClientLifecycleError(RuntimeError):
    def __init__(self, message: str, *, status_code: int = 400, payload: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.payload = payload or {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _clean(value: Any, fallback: str = "") -> str:
    value = str(value or "").strip()
    return value or fallback


def _lower(value: Any) -> str:
    return _clean(value).lower()


def _record_value(record: dict[str, Any], *keys: str, fallback: str = "") -> str:
    for key in keys:
        value = record.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return str(fallback or "").strip()


def _workspace_id_from_record(record: dict[str, Any]) -> str:
    return _record_value(record, "workspaceId", "workspace_id", "id")


def _customer_id_from_record(record: dict[str, Any]) -> str:
    return _record_value(record, "customerId", "customer_id")


def _status_is_archived(value: Any) -> bool:
    return _lower(value) in {"archived", "deleted", "inactive", "disabled"}


def _subscription_plan_key(subscription: dict[str, Any]) -> str:
    return _record_value(subscription, "planKey", "plan_key", "plan")


def _subscription_status(subscription: dict[str, Any]) -> str:
    return _record_value(subscription, "status", "subscriptionStatus", "subscription_status", fallback="free")


def _stripe_subscription_id(subscription: dict[str, Any]) -> str:
    return _record_value(subscription, "stripeSubscriptionId", "stripe_subscription_id", "subscriptionId", "subscription_id")


def _stripe_customer_id(subscription: dict[str, Any]) -> str:
    return _record_value(subscription, "stripeCustomerId", "stripe_customer_id", "customerId", "customer_id")


def _is_active_stripe_subscription(subscription: dict[str, Any]) -> bool:
    provider = _lower(subscription.get("provider"))
    status = _lower(_subscription_status(subscription))
    sub_id = _stripe_subscription_id(subscription)

    return provider == "stripe" and status in ACTIVE_STRIPE_STATUSES and bool(sub_id)


def _price_to_plan_map() -> dict[str, str]:
    path = BILLING_DIR / "stripe_price_map.json"
    data = _read_json(path, {})
    plans = data.get("plans") if isinstance(data, dict) else {}

    result: dict[str, str] = {}

    if isinstance(plans, dict):
        for key, row in plans.items():
            if not isinstance(row, dict):
                continue

            for price_key in ["priceId", "price_id", "livePriceId", "testPriceId"]:
                price_id = _clean(row.get(price_key))
                if price_id:
                    result[price_id] = str(key)

    return result


def _get_subscription(workspace_id: str) -> dict[str, Any]:
    try:
        from services.billing_usage import get_workspace_subscription
        row = get_workspace_subscription(workspace_id)
        return row if isinstance(row, dict) else {}
    except Exception:
        subscriptions = _read_json(SUBSCRIPTIONS_FILE, {})
        if isinstance(subscriptions, dict):
            row = subscriptions.get(workspace_id) or {}
            return row if isinstance(row, dict) else {}

    return {}


def _set_subscription_record(
    workspace_id: str,
    *,
    plan_key: str,
    status: str,
    provider: str,
    stripe_customer_id: str = "",
    stripe_subscription_id: str = "",
    checkout_session_id: str = "",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    extra = extra or {}

    # First use existing app service so any normal persistence path is respected.
    service_result: dict[str, Any] = {}

    try:
        from services.billing_usage import set_workspace_plan

        try:
            result = set_workspace_plan(
                workspace_id=workspace_id,
                plan_key=plan_key,
                status=status,
                provider=provider,
                stripeCustomerId=stripe_customer_id,
                stripeSubscriptionId=stripe_subscription_id,
                checkoutSessionId=checkout_session_id,
                **extra,
            )
        except TypeError:
            try:
                result = set_workspace_plan(
                    workspace_id=workspace_id,
                    plan_key=plan_key,
                    status=status,
                    provider=provider,
                )
            except TypeError:
                result = set_workspace_plan(workspace_id, plan_key)

        if isinstance(result, dict):
            service_result = result
    except Exception as exc:
        service_result = {"serviceSetWorkspacePlanError": repr(exc)}

    # Also update JSON fallback state.
    subscriptions = _read_json(SUBSCRIPTIONS_FILE, {})
    if not isinstance(subscriptions, dict):
        subscriptions = {}

    current = subscriptions.get(workspace_id)
    if not isinstance(current, dict):
        current = {"workspaceId": workspace_id}

    current.update({
        "workspaceId": workspace_id,
        "planKey": plan_key,
        "plan": plan_key,
        "status": status,
        "provider": provider,
        "updatedAt": _now_iso(),
    })

    if stripe_customer_id:
        current["stripeCustomerId"] = stripe_customer_id
        current["customerId"] = stripe_customer_id

    if stripe_subscription_id:
        current["stripeSubscriptionId"] = stripe_subscription_id
        current["subscriptionId"] = stripe_subscription_id

    if checkout_session_id:
        current["checkoutSessionId"] = checkout_session_id

    current.update(extra)
    subscriptions[workspace_id] = current
    _write_json(SUBSCRIPTIONS_FILE, subscriptions)

    # Best-effort direct DB update for enterprise Cloud SQL / future DATABASE_URL profiles.
    db_result = _update_subscription_database(
        workspace_id=workspace_id,
        plan_key=plan_key,
        status=status,
        provider=provider,
        stripe_customer_id=stripe_customer_id,
        stripe_subscription_id=stripe_subscription_id,
        checkout_session_id=checkout_session_id,
    )

    return {
        "workspaceId": workspace_id,
        "planKey": plan_key,
        "status": status,
        "provider": provider,
        "serviceResult": service_result,
        "databaseResult": db_result,
        "jsonFallback": current,
    }


def _database_url() -> str:
    for name in ["DATABASE_URL", "SQLALCHEMY_DATABASE_URI", "POSTGRES_URL"]:
        value = _clean(os.environ.get(name))
        if value:
            return value

    connection_name = _clean(os.environ.get("CLOUD_SQL_CONNECTION_NAME"))
    db_name = _clean(os.environ.get("DB_NAME") or os.environ.get("POSTGRES_DB"))
    db_user = _clean(os.environ.get("DB_USER") or os.environ.get("POSTGRES_USER"))
    db_password = _clean(os.environ.get("DB_PASSWORD") or os.environ.get("POSTGRES_PASSWORD"))

    if connection_name and db_name and db_user and db_password:
        return (
            "postgresql://"
            f"{quote_plus(db_user)}:{quote_plus(db_password)}"
            f"@/{quote_plus(db_name)}"
            f"?host=/cloudsql/{quote_plus(connection_name)}"
        )

    return ""


def _connect_db():
    url = _database_url()

    if not url:
        return None

    try:
        import psycopg
        return psycopg.connect(url)
    except Exception:
        return None


def _columns(conn, table: str) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            select column_name
            from information_schema.columns
            where table_schema = 'public'
              and table_name = %s
            order by ordinal_position
            """,
            (table,),
        )
        return [row[0] for row in cur.fetchall()]


def _tables(conn) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            select table_name
            from information_schema.tables
            where table_schema = 'public'
              and table_type = 'BASE TABLE'
            order by table_name
            """
        )
        return [row[0] for row in cur.fetchall()]


def _normalise_column(name: str) -> str:
    return name.replace("_", "").lower()


def _pick_column(columns: list[str], *names: str) -> str:
    normalised = {_normalise_column(column): column for column in columns}

    for name in names:
        key = _normalise_column(name)
        if key in normalised:
            return normalised[key]

    return ""


def _find_table_with_columns(conn, required: list[str], preferred_terms: list[str]) -> tuple[str, list[str]]:
    for table in _tables(conn):
        columns = _columns(conn, table)
        normalised = {_normalise_column(column) for column in columns}

        if all(_normalise_column(item) in normalised for item in required):
            if preferred_terms and not any(term.lower() in table.lower() for term in preferred_terms):
                continue

            return table, columns

    for table in _tables(conn):
        columns = _columns(conn, table)
        normalised = {_normalise_column(column) for column in columns}

        if all(_normalise_column(item) in normalised for item in required):
            return table, columns

    return "", []


def _sql_quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _update_table_by_workspace(
    conn,
    *,
    preferred_terms: list[str],
    workspace_id: str,
    updates: dict[str, Any],
) -> dict[str, Any]:
    table, columns = _find_table_with_columns(conn, ["workspaceId"], preferred_terms)

    if not table:
        return {"updated": 0, "reason": "table_not_found", "preferredTerms": preferred_terms}

    workspace_col = _pick_column(columns, "workspaceId", "workspace_id")
    update_pairs: list[tuple[str, Any]] = []

    for logical, value in updates.items():
        col = _pick_column(columns, logical)
        if col:
            update_pairs.append((col, value))

    if not update_pairs:
        return {"updated": 0, "table": table, "reason": "no_matching_update_columns"}

    set_sql = ", ".join(f"{_sql_quote(col)} = %s" for col, _ in update_pairs)
    params = [value for _, value in update_pairs] + [workspace_id]

    with conn.cursor() as cur:
        cur.execute(
            f"update {_sql_quote(table)} set {set_sql} where {_sql_quote(workspace_col)} = %s",
            params,
        )
        return {"updated": cur.rowcount, "table": table}


def _update_subscription_database(
    *,
    workspace_id: str,
    plan_key: str,
    status: str,
    provider: str,
    stripe_customer_id: str = "",
    stripe_subscription_id: str = "",
    checkout_session_id: str = "",
) -> dict[str, Any]:
    conn = _connect_db()

    if conn is None:
        return {"available": False, "reason": "no_database_connection"}

    try:
        with conn:
            return _update_table_by_workspace(
                conn,
                preferred_terms=["subscription", "billing"],
                workspace_id=workspace_id,
                updates={
                    "planKey": plan_key,
                    "plan": plan_key,
                    "status": status,
                    "provider": provider,
                    "stripeCustomerId": stripe_customer_id,
                    "stripeSubscriptionId": stripe_subscription_id,
                    "checkoutSessionId": checkout_session_id,
                    "updatedAt": _now_iso(),
                },
            )
    except Exception as exc:
        return {"available": True, "error": repr(exc)}
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _archive_json_state(workspace_id: str, actor_user_id: str, reason: str) -> dict[str, Any]:
    now = _now_iso()
    result: dict[str, Any] = {}

    workspaces = _read_json(WORKSPACES_FILE, [])
    if isinstance(workspaces, list):
        count = 0
        customer_ids: set[str] = set()

        for row in workspaces:
            if isinstance(row, dict) and _workspace_id_from_record(row) == workspace_id:
                row["status"] = "archived"
                row["archivedAt"] = now
                row["archivedBy"] = actor_user_id
                row["archiveReason"] = reason
                customer_id = _customer_id_from_record(row)
                if customer_id:
                    customer_ids.add(customer_id)
                count += 1

        _write_json(WORKSPACES_FILE, workspaces)
        result["workspacesArchived"] = count
    else:
        customer_ids = set()

    memberships = _read_json(MEMBERSHIPS_FILE, [])
    if isinstance(memberships, list):
        count = 0

        for row in memberships:
            if isinstance(row, dict) and _workspace_id_from_record(row) == workspace_id:
                row["status"] = "archived"
                row["archivedAt"] = now
                row["archivedBy"] = actor_user_id
                row["archiveReason"] = reason
                count += 1

        _write_json(MEMBERSHIPS_FILE, memberships)
        result["membershipsArchived"] = count

    customers = _read_json(CUSTOMERS_FILE, [])
    if isinstance(customers, list) and customer_ids:
        count = 0

        for row in customers:
            if isinstance(row, dict) and _customer_id_from_record(row) in customer_ids:
                row["status"] = "archived"
                row["archivedAt"] = now
                row["archivedBy"] = actor_user_id
                row["archiveReason"] = reason
                count += 1

        _write_json(CUSTOMERS_FILE, customers)
        result["customersArchived"] = count

    subscriptions = _read_json(SUBSCRIPTIONS_FILE, {})
    if isinstance(subscriptions, dict):
        row = subscriptions.get(workspace_id)
        if isinstance(row, dict):
            row["status"] = "archived"
            row["archivedAt"] = now
            row["archivedBy"] = actor_user_id
            row["archiveReason"] = reason
            row["updatedAt"] = now
            subscriptions[workspace_id] = row
            _write_json(SUBSCRIPTIONS_FILE, subscriptions)
            result["subscriptionArchived"] = True
        else:
            result["subscriptionArchived"] = False

    return result


def _archive_database_state(workspace_id: str, actor_user_id: str, reason: str) -> dict[str, Any]:
    conn = _connect_db()

    if conn is None:
        return {"available": False, "reason": "no_database_connection"}

    now = _now_iso()

    try:
        with conn:
            return {
                "workspaces": _update_table_by_workspace(
                    conn,
                    preferred_terms=["workspace"],
                    workspace_id=workspace_id,
                    updates={
                        "status": "archived",
                        "archivedAt": now,
                        "archivedBy": actor_user_id,
                        "archiveReason": reason,
                        "updatedAt": now,
                    },
                ),
                "memberships": _update_table_by_workspace(
                    conn,
                    preferred_terms=["membership"],
                    workspace_id=workspace_id,
                    updates={
                        "status": "archived",
                        "archivedAt": now,
                        "archivedBy": actor_user_id,
                        "archiveReason": reason,
                        "updatedAt": now,
                    },
                ),
                "subscriptions": _update_table_by_workspace(
                    conn,
                    preferred_terms=["subscription", "billing"],
                    workspace_id=workspace_id,
                    updates={
                        "status": "archived",
                        "archivedAt": now,
                        "archivedBy": actor_user_id,
                        "archiveReason": reason,
                        "updatedAt": now,
                    },
                ),
            }
    except Exception as exc:
        return {"available": True, "error": repr(exc)}
    finally:
        try:
            conn.close()
        except Exception:
            pass


def list_admin_clients(*, include_archived: bool = False) -> dict[str, Any]:
    from services.customer_workspace import list_customers, list_workspaces, list_memberships

    customers = list_customers()
    workspaces = list_workspaces()
    memberships = list_memberships()

    customer_by_id = {
        _customer_id_from_record(row): row
        for row in customers
        if isinstance(row, dict) and _customer_id_from_record(row)
    }

    member_count_by_workspace: dict[str, int] = {}

    for row in memberships:
        if not isinstance(row, dict):
            continue

        workspace_id = _workspace_id_from_record(row)

        if not workspace_id:
            continue

        if not _status_is_archived(row.get("status")):
            member_count_by_workspace[workspace_id] = member_count_by_workspace.get(workspace_id, 0) + 1

    clients: list[dict[str, Any]] = []

    for workspace in workspaces:
        if not isinstance(workspace, dict):
            continue

        workspace_id = _workspace_id_from_record(workspace)

        if not workspace_id:
            continue

        workspace_status = _record_value(workspace, "status", fallback="active")

        if not include_archived and _status_is_archived(workspace_status):
            continue

        customer_id = _customer_id_from_record(workspace)
        customer = customer_by_id.get(customer_id, {}) if customer_id else {}

        email = _record_value(
            customer,
            "billingEmail",
            "billing_email",
            "email",
            "ownerEmail",
            "owner_email",
        )

        owner_user_id = _record_value(
            workspace,
            "subscriptionOwnerUserId",
            "subscription_owner_user_id",
            "ownerUserId",
            "owner_user_id",
        )

        subscription = _get_subscription(workspace_id)
        plan_key = _subscription_plan_key(subscription) or "free"
        subscription_status = _subscription_status(subscription) or "active"
        active_stripe = _is_active_stripe_subscription(subscription)

        client = {
            "workspaceId": workspace_id,
            "workspaceLabel": _record_value(workspace, "label", "name", fallback=workspace_id),
            "workspaceStatus": workspace_status,
            "customerId": customer_id,
            "customerName": _record_value(customer, "name", "label"),
            "billingEmail": email,
            "ownerUserId": owner_user_id,
            "memberCount": member_count_by_workspace.get(workspace_id, 0),
            "planKey": plan_key,
            "subscriptionStatus": subscription_status,
            "provider": _record_value(subscription, "provider"),
            "stripeCustomerId": _stripe_customer_id(subscription),
            "stripeSubscriptionId": _stripe_subscription_id(subscription),
            "activeStripeSubscription": active_stripe,
            "canArchive": not active_stripe,
            "archiveBlockedReason": "Cancel subscription first" if active_stripe else "",
            "createdAt": _record_value(workspace, "createdAt", "created_at"),
            "updatedAt": _record_value(workspace, "updatedAt", "updated_at"),
            "archivedAt": _record_value(workspace, "archivedAt", "archived_at"),
        }

        clients.append(client)

    email_groups: dict[str, list[str]] = {}

    for client in clients:
        email = _lower(client.get("billingEmail"))
        if email:
            email_groups.setdefault(email, []).append(client["workspaceId"])

    duplicate_emails = {
        email: workspace_ids
        for email, workspace_ids in email_groups.items()
        if len(workspace_ids) > 1
    }

    for client in clients:
        email = _lower(client.get("billingEmail"))
        ids = duplicate_emails.get(email, [])
        client["duplicateEmail"] = bool(ids)
        client["duplicateWorkspaceIds"] = ids

    return {
        "ok": True,
        "includeArchived": include_archived,
        "clients": clients,
        "duplicates": duplicate_emails,
        "count": len(clients),
    }


def archive_client_workspace(
    *,
    workspace_id: str,
    actor_user_id: str = "",
    reason: str = "admin_archive",
) -> dict[str, Any]:
    workspace_id = _clean(workspace_id)

    if not workspace_id:
        raise AdminClientLifecycleError("workspaceId is required", status_code=400)

    subscription = _get_subscription(workspace_id)

    if _is_active_stripe_subscription(subscription):
        raise AdminClientLifecycleError(
            "Cancel subscription first before deleting or archiving this client.",
            status_code=409,
            payload={
                "workspaceId": workspace_id,
                "planKey": _subscription_plan_key(subscription),
                "status": _subscription_status(subscription),
                "stripeSubscriptionId": _stripe_subscription_id(subscription),
                "reason": "active_stripe_subscription",
            },
        )

    json_result = _archive_json_state(workspace_id, actor_user_id, reason)
    db_result = _archive_database_state(workspace_id, actor_user_id, reason)

    return {
        "ok": True,
        "workspaceId": workspace_id,
        "archived": True,
        "jsonResult": json_result,
        "databaseResult": db_result,
    }


def _load_stripe():
    try:
        import stripe
        secret_key = _clean(os.environ.get("STRIPE_SECRET_KEY"))
        if not secret_key:
            raise AdminClientLifecycleError("STRIPE_SECRET_KEY is not configured", status_code=503)
        stripe.api_key = secret_key
        return stripe
    except AdminClientLifecycleError:
        raise
    except Exception as exc:
        raise AdminClientLifecycleError(f"Stripe is not available: {exc}", status_code=503)


def _plan_from_subscription(subscription: Any) -> str:
    metadata = getattr(subscription, "metadata", None) or {}
    if isinstance(metadata, dict):
        plan = _clean(metadata.get("planKey") or metadata.get("plan"))
        if plan:
            return plan

    items = getattr(subscription, "items", None)
    data = getattr(items, "data", None) or []

    price_to_plan = _price_to_plan_map()

    for item in data:
        price = getattr(item, "price", None)
        price_id = _clean(getattr(price, "id", ""))
        if price_id and price_id in price_to_plan:
            return price_to_plan[price_id]

    return ""


def reconcile_checkout_session(
    *,
    session_id: str,
    workspace_id: str = "",
    actor_user_id: str = "",
) -> dict[str, Any]:
    session_id = _clean(session_id)
    workspace_id = _clean(workspace_id)

    if not session_id:
        raise AdminClientLifecycleError("sessionId is required", status_code=400)

    stripe = _load_stripe()

    try:
        session = stripe.checkout.Session.retrieve(
            session_id,
            expand=["subscription", "customer"],
        )
    except Exception as exc:
        raise AdminClientLifecycleError(f"Could not retrieve Stripe checkout session: {exc}", status_code=502)

    metadata = getattr(session, "metadata", None) or {}

    if isinstance(metadata, dict):
        workspace_id = workspace_id or _clean(metadata.get("workspaceId") or metadata.get("workspace_id"))

    workspace_id = workspace_id or _clean(getattr(session, "client_reference_id", ""))

    if not workspace_id:
        raise AdminClientLifecycleError("Stripe session is missing workspaceId metadata.", status_code=409)

    subscription = getattr(session, "subscription", None)
    stripe_subscription_id = ""

    if isinstance(subscription, str):
        stripe_subscription_id = subscription
        try:
            subscription = stripe.Subscription.retrieve(stripe_subscription_id)
        except Exception:
            subscription = None
    elif subscription is not None:
        stripe_subscription_id = _clean(getattr(subscription, "id", ""))

    stripe_customer_id = ""

    customer = getattr(session, "customer", None)

    if isinstance(customer, str):
        stripe_customer_id = customer
    elif customer is not None:
        stripe_customer_id = _clean(getattr(customer, "id", ""))

    if not stripe_customer_id:
        stripe_customer_id = _clean(getattr(session, "customer", ""))

    plan_key = ""

    if isinstance(metadata, dict):
        plan_key = _clean(metadata.get("planKey") or metadata.get("plan"))

    if not plan_key and subscription is not None:
        plan_key = _plan_from_subscription(subscription)

    if not plan_key:
        raise AdminClientLifecycleError("Could not determine plan from Stripe session.", status_code=409)

    subscription_status = "active"

    if subscription is not None and not isinstance(subscription, str):
        subscription_status = _clean(getattr(subscription, "status", ""), "active")

    result = _set_subscription_record(
        workspace_id,
        plan_key=plan_key,
        status=subscription_status,
        provider="stripe",
        stripe_customer_id=stripe_customer_id,
        stripe_subscription_id=stripe_subscription_id,
        checkout_session_id=session_id,
        extra={
            "reconciledAt": _now_iso(),
            "reconciledBy": actor_user_id,
            "lastStripeSyncSource": "checkout_session_reconcile",
        },
    )

    return {
        "ok": True,
        "action": "reconciled_checkout_session",
        "workspaceId": workspace_id,
        "planKey": plan_key,
        "status": subscription_status,
        "stripeCustomerId": stripe_customer_id,
        "stripeSubscriptionId": stripe_subscription_id,
        "checkoutSessionId": session_id,
        "result": result,
    }


def sync_workspace_billing_from_stripe(
    *,
    workspace_id: str,
    actor_user_id: str = "",
) -> dict[str, Any]:
    workspace_id = _clean(workspace_id)

    if not workspace_id:
        raise AdminClientLifecycleError("workspaceId is required", status_code=400)

    current = _get_subscription(workspace_id)
    stripe_subscription_id = _stripe_subscription_id(current)

    if not stripe_subscription_id:
        raise AdminClientLifecycleError(
            "This workspace has no stored Stripe subscription ID. Reconcile with a checkout session ID instead.",
            status_code=409,
            payload={"workspaceId": workspace_id, "reason": "missing_stripe_subscription_id"},
        )

    stripe = _load_stripe()

    try:
        subscription = stripe.Subscription.retrieve(stripe_subscription_id)
    except Exception as exc:
        raise AdminClientLifecycleError(f"Could not retrieve Stripe subscription: {exc}", status_code=502)

    plan_key = _plan_from_subscription(subscription)

    if not plan_key:
        raise AdminClientLifecycleError("Could not map Stripe subscription price to a local plan.", status_code=409)

    stripe_customer_id = _clean(getattr(subscription, "customer", ""))
    status = _clean(getattr(subscription, "status", ""), "active")

    result = _set_subscription_record(
        workspace_id,
        plan_key=plan_key,
        status=status,
        provider="stripe",
        stripe_customer_id=stripe_customer_id,
        stripe_subscription_id=stripe_subscription_id,
        extra={
            "syncedAt": _now_iso(),
            "syncedBy": actor_user_id,
            "lastStripeSyncSource": "admin_subscription_sync",
        },
    )

    return {
        "ok": True,
        "action": "synced_subscription",
        "workspaceId": workspace_id,
        "planKey": plan_key,
        "status": status,
        "stripeCustomerId": stripe_customer_id,
        "stripeSubscriptionId": stripe_subscription_id,
        "result": result,
    }

# >>> SMX_ADMIN_DELETE_ARCHIVE_FIX >>>
def _smx_is_archived_client_state(*values: Any) -> bool:
    for value in values:
        if _status_is_archived(value):
            return True
    return False


def _smx_find_table_with_identifier(conn, preferred_terms: list[str], identifier_candidates: list[str]) -> tuple[str, list[str], str]:
    tables = _tables(conn)

    preferred = []
    fallback = []

    for table in tables:
        if preferred_terms and any(term.lower() in table.lower() for term in preferred_terms):
            preferred.append(table)
        else:
            fallback.append(table)

    for table in preferred + fallback:
        columns = _columns(conn, table)

        for candidate in identifier_candidates:
            col = _pick_column(columns, candidate)

            if col:
                return table, columns, col

    return "", [], ""


def _smx_update_table_by_identifier(
    conn,
    *,
    preferred_terms: list[str],
    identifier_candidates: list[str],
    identifier_value: str,
    updates: dict[str, Any],
) -> dict[str, Any]:
    table, columns, identifier_col = _smx_find_table_with_identifier(
        conn,
        preferred_terms,
        identifier_candidates,
    )

    if not table or not identifier_col:
        return {
            "updated": 0,
            "reason": "table_or_identifier_not_found",
            "preferredTerms": preferred_terms,
            "identifierCandidates": identifier_candidates,
        }

    update_pairs: list[tuple[str, Any]] = []

    for logical, value in updates.items():
        col = _pick_column(columns, logical)

        if col:
            update_pairs.append((col, value))

    if not update_pairs:
        return {
            "updated": 0,
            "table": table,
            "reason": "no_matching_update_columns",
        }

    set_sql = ", ".join(f"{_sql_quote(col)} = %s" for col, _ in update_pairs)
    params = [value for _, value in update_pairs] + [identifier_value]

    with conn.cursor() as cur:
        cur.execute(
            f"update {_sql_quote(table)} set {set_sql} where {_sql_quote(identifier_col)} = %s",
            params,
        )
        return {
            "updated": cur.rowcount,
            "table": table,
            "identifierColumn": identifier_col,
        }


def _archive_database_state(workspace_id: str, actor_user_id: str, reason: str) -> dict[str, Any]:
    conn = _connect_db()

    if conn is None:
        return {"available": False, "reason": "no_database_connection"}

    now = _now_iso()

    updates = {
        "status": "archived",
        "archivedAt": now,
        "archivedBy": actor_user_id,
        "archiveReason": reason,
        "updatedAt": now,
    }

    try:
        with conn:
            return {
                "workspaces": _smx_update_table_by_identifier(
                    conn,
                    preferred_terms=["workspace"],
                    identifier_candidates=["workspaceId", "workspace_id", "id"],
                    identifier_value=workspace_id,
                    updates=updates,
                ),
                "memberships": _smx_update_table_by_identifier(
                    conn,
                    preferred_terms=["membership"],
                    identifier_candidates=["workspaceId", "workspace_id"],
                    identifier_value=workspace_id,
                    updates=updates,
                ),
                "subscriptions": _smx_update_table_by_identifier(
                    conn,
                    preferred_terms=["subscription", "billing"],
                    identifier_candidates=["workspaceId", "workspace_id"],
                    identifier_value=workspace_id,
                    updates=updates,
                ),
            }
    except Exception as exc:
        return {"available": True, "error": repr(exc)}
    finally:
        try:
            conn.close()
        except Exception:
            pass


def archive_client_workspace(
    *,
    workspace_id: str,
    actor_user_id: str = "",
    reason: str = "admin_archive",
) -> dict[str, Any]:
    workspace_id = _clean(workspace_id)

    if not workspace_id:
        raise AdminClientLifecycleError("workspaceId is required", status_code=400)

    subscription = _get_subscription(workspace_id)

    if _is_active_stripe_subscription(subscription):
        raise AdminClientLifecycleError(
            "Cancel subscription first before deleting or archiving this client.",
            status_code=409,
            payload={
                "workspaceId": workspace_id,
                "planKey": _subscription_plan_key(subscription),
                "status": _subscription_status(subscription),
                "stripeSubscriptionId": _stripe_subscription_id(subscription),
                "reason": "active_stripe_subscription",
            },
        )

    existing_plan = _subscription_plan_key(subscription) or "free"
    existing_provider = _record_value(subscription, "provider", fallback="internal")
    existing_stripe_customer_id = _stripe_customer_id(subscription)
    existing_stripe_subscription_id = _stripe_subscription_id(subscription)

    json_result = _archive_json_state(workspace_id, actor_user_id, reason)
    db_result = _archive_database_state(workspace_id, actor_user_id, reason)

    subscription_result = _set_subscription_record(
        workspace_id,
        plan_key=existing_plan,
        status="archived",
        provider=existing_provider,
        stripe_customer_id=existing_stripe_customer_id,
        stripe_subscription_id=existing_stripe_subscription_id,
        extra={
            "archivedAt": _now_iso(),
            "archivedBy": actor_user_id,
            "archiveReason": reason,
            "lastAdminAction": "archive_client_workspace",
        },
    )

    return {
        "ok": True,
        "workspaceId": workspace_id,
        "archived": True,
        "jsonResult": json_result,
        "databaseResult": db_result,
        "subscriptionResult": subscription_result,
    }


def list_admin_clients(*, include_archived: bool = False) -> dict[str, Any]:
    from services.customer_workspace import list_customers, list_workspaces, list_memberships

    customers = list_customers()
    workspaces = list_workspaces()
    memberships = list_memberships()

    customer_by_id = {
        _customer_id_from_record(row): row
        for row in customers
        if isinstance(row, dict) and _customer_id_from_record(row)
    }

    member_count_by_workspace: dict[str, int] = {}

    for row in memberships:
        if not isinstance(row, dict):
            continue

        workspace_id = _workspace_id_from_record(row)

        if not workspace_id:
            continue

        if not _status_is_archived(row.get("status")):
            member_count_by_workspace[workspace_id] = member_count_by_workspace.get(workspace_id, 0) + 1

    clients: list[dict[str, Any]] = []

    for workspace in workspaces:
        if not isinstance(workspace, dict):
            continue

        workspace_id = _workspace_id_from_record(workspace)

        if not workspace_id:
            continue

        workspace_status = _record_value(workspace, "status", fallback="active")
        customer_id = _customer_id_from_record(workspace)
        customer = customer_by_id.get(customer_id, {}) if customer_id else {}
        customer_status = _record_value(customer, "status", fallback="active")

        subscription = _get_subscription(workspace_id)
        plan_key = _subscription_plan_key(subscription) or "free"
        subscription_status = _subscription_status(subscription) or "active"

        if not include_archived and _smx_is_archived_client_state(
            workspace_status,
            customer_status,
            subscription_status,
            workspace.get("archivedAt"),
            customer.get("archivedAt") if isinstance(customer, dict) else "",
            subscription.get("archivedAt") if isinstance(subscription, dict) else "",
        ):
            continue

        email = _record_value(
            customer,
            "billingEmail",
            "billing_email",
            "email",
            "ownerEmail",
            "owner_email",
        )

        owner_user_id = _record_value(
            workspace,
            "subscriptionOwnerUserId",
            "subscription_owner_user_id",
            "ownerUserId",
            "owner_user_id",
        )

        active_stripe = _is_active_stripe_subscription(subscription)

        client = {
            "workspaceId": workspace_id,
            "workspaceLabel": _record_value(workspace, "label", "name", fallback=workspace_id),
            "workspaceStatus": workspace_status,
            "customerId": customer_id,
            "customerName": _record_value(customer, "name", "label"),
            "billingEmail": email,
            "ownerUserId": owner_user_id,
            "memberCount": member_count_by_workspace.get(workspace_id, 0),
            "planKey": plan_key,
            "subscriptionStatus": subscription_status,
            "provider": _record_value(subscription, "provider"),
            "stripeCustomerId": _stripe_customer_id(subscription),
            "stripeSubscriptionId": _stripe_subscription_id(subscription),
            "activeStripeSubscription": active_stripe,
            "canArchive": not active_stripe,
            "archiveBlockedReason": "Cancel subscription first" if active_stripe else "",
            "createdAt": _record_value(workspace, "createdAt", "created_at"),
            "updatedAt": _record_value(workspace, "updatedAt", "updated_at"),
            "archivedAt": _record_value(
                workspace,
                "archivedAt",
                "archived_at",
                fallback=_record_value(subscription, "archivedAt", "archived_at"),
            ),
        }

        clients.append(client)

    email_groups: dict[str, list[str]] = {}

    for client in clients:
        email = _lower(client.get("billingEmail"))

        if email:
            email_groups.setdefault(email, []).append(client["workspaceId"])

    duplicate_emails = {
        email: workspace_ids
        for email, workspace_ids in email_groups.items()
        if len(workspace_ids) > 1
    }

    for client in clients:
        email = _lower(client.get("billingEmail"))
        ids = duplicate_emails.get(email, [])
        client["duplicateEmail"] = bool(ids)
        client["duplicateWorkspaceIds"] = ids

    return {
        "ok": True,
        "includeArchived": include_archived,
        "clients": clients,
        "duplicates": duplicate_emails,
        "count": len(clients),
    }
# <<< SMX_ADMIN_DELETE_ARCHIVE_FIX >>>

# >>> SMX_STRIPE_RECONCILE_ANY_ID >>>
def _smx_subscription_data(subscription_list: Any) -> list[Any]:
    if subscription_list is None:
        return []

    if isinstance(subscription_list, dict):
        data = subscription_list.get("data") or []
    else:
        data = getattr(subscription_list, "data", []) or []

    return list(data)


def _smx_reconcile_subscription_object(
    *,
    subscription: Any,
    workspace_id: str,
    actor_user_id: str = "",
    source: str = "admin_subscription_reconcile",
) -> dict[str, Any]:
    workspace_id = _clean(workspace_id)

    if not workspace_id:
        raise AdminClientLifecycleError("workspaceId is required", status_code=400)

    stripe_subscription_id = _clean(getattr(subscription, "id", ""))

    if not stripe_subscription_id:
        raise AdminClientLifecycleError("Stripe subscription ID is missing.", status_code=409)

    plan_key = _plan_from_subscription(subscription)

    if not plan_key:
        raise AdminClientLifecycleError(
            "Could not map Stripe subscription price to a local plan. Check billing/stripe_price_map.json.",
            status_code=409,
            payload={"stripeSubscriptionId": stripe_subscription_id},
        )

    stripe_customer_id = _clean(getattr(subscription, "customer", ""))
    status = _clean(getattr(subscription, "status", ""), "active")

    result = _set_subscription_record(
        workspace_id,
        plan_key=plan_key,
        status=status,
        provider="stripe",
        stripe_customer_id=stripe_customer_id,
        stripe_subscription_id=stripe_subscription_id,
        extra={
            "syncedAt": _now_iso(),
            "syncedBy": actor_user_id,
            "lastStripeSyncSource": source,
        },
    )

    return {
        "ok": True,
        "action": "reconciled_subscription",
        "workspaceId": workspace_id,
        "planKey": plan_key,
        "status": status,
        "stripeCustomerId": stripe_customer_id,
        "stripeSubscriptionId": stripe_subscription_id,
        "result": result,
    }


def reconcile_stripe_subscription_id(
    *,
    subscription_id: str,
    workspace_id: str,
    actor_user_id: str = "",
) -> dict[str, Any]:
    subscription_id = _clean(subscription_id)

    if not subscription_id:
        raise AdminClientLifecycleError("subscriptionId is required", status_code=400)

    stripe = _load_stripe()

    try:
        subscription = stripe.Subscription.retrieve(subscription_id)
    except Exception as exc:
        raise AdminClientLifecycleError(f"Could not retrieve Stripe subscription: {exc}", status_code=502)

    return _smx_reconcile_subscription_object(
        subscription=subscription,
        workspace_id=workspace_id,
        actor_user_id=actor_user_id,
        source="admin_subscription_id_reconcile",
    )


def reconcile_stripe_customer_id(
    *,
    customer_id: str,
    workspace_id: str,
    actor_user_id: str = "",
) -> dict[str, Any]:
    customer_id = _clean(customer_id)

    if not customer_id:
        raise AdminClientLifecycleError("customerId is required", status_code=400)

    stripe = _load_stripe()

    try:
        subscriptions = stripe.Subscription.list(
            customer=customer_id,
            status="all",
            limit=20,
        )
    except Exception as exc:
        raise AdminClientLifecycleError(f"Could not list Stripe subscriptions for customer: {exc}", status_code=502)

    rows = _smx_subscription_data(subscriptions)

    if not rows:
        raise AdminClientLifecycleError(
            "No Stripe subscriptions found for this customer.",
            status_code=404,
            payload={"stripeCustomerId": customer_id},
        )

    preferred_statuses = {"active", "trialing", "past_due"}
    chosen = None

    for row in rows:
        if _clean(getattr(row, "status", "")).lower() in preferred_statuses:
            chosen = row
            break

    chosen = chosen or rows[0]

    return _smx_reconcile_subscription_object(
        subscription=chosen,
        workspace_id=workspace_id,
        actor_user_id=actor_user_id,
        source="admin_customer_id_reconcile",
    )


def reconcile_stripe_payment_intent_id(
    *,
    payment_intent_id: str,
    workspace_id: str,
    actor_user_id: str = "",
) -> dict[str, Any]:
    payment_intent_id = _clean(payment_intent_id)

    if not payment_intent_id:
        raise AdminClientLifecycleError("paymentIntentId is required", status_code=400)

    stripe = _load_stripe()

    try:
        payment_intent = stripe.PaymentIntent.retrieve(
            payment_intent_id,
            expand=["invoice.subscription", "customer"],
        )
    except Exception as exc:
        raise AdminClientLifecycleError(f"Could not retrieve Stripe payment intent: {exc}", status_code=502)

    invoice = getattr(payment_intent, "invoice", None)
    subscription = None

    if isinstance(invoice, str) and invoice:
        try:
            invoice_obj = stripe.Invoice.retrieve(invoice, expand=["subscription"])
            subscription = getattr(invoice_obj, "subscription", None)
        except Exception:
            subscription = None
    elif invoice is not None:
        subscription = getattr(invoice, "subscription", None)

    if isinstance(subscription, str) and subscription:
        return reconcile_stripe_subscription_id(
            subscription_id=subscription,
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
        )

    if subscription is not None:
        return _smx_reconcile_subscription_object(
            subscription=subscription,
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            source="admin_payment_intent_reconcile",
        )

    customer = getattr(payment_intent, "customer", None)
    customer_id = customer if isinstance(customer, str) else _clean(getattr(customer, "id", ""))

    if customer_id:
        return reconcile_stripe_customer_id(
            customer_id=customer_id,
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
        )

    raise AdminClientLifecycleError(
        "Payment Intent did not expose a subscription or customer. Use the Subscription ID instead.",
        status_code=409,
        payload={"paymentIntentId": payment_intent_id},
    )


def reconcile_stripe_identifier(
    *,
    stripe_id: str,
    workspace_id: str,
    actor_user_id: str = "",
) -> dict[str, Any]:
    stripe_id = _clean(stripe_id)

    if not stripe_id:
        raise AdminClientLifecycleError("Stripe ID is required", status_code=400)

    if stripe_id.startswith("cs_"):
        return reconcile_checkout_session(
            session_id=stripe_id,
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
        )

    if stripe_id.startswith("sub_"):
        return reconcile_stripe_subscription_id(
            subscription_id=stripe_id,
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
        )

    if stripe_id.startswith("cus_"):
        return reconcile_stripe_customer_id(
            customer_id=stripe_id,
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
        )

    if stripe_id.startswith("pi_"):
        return reconcile_stripe_payment_intent_id(
            payment_intent_id=stripe_id,
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
        )

    raise AdminClientLifecycleError(
        "Unsupported Stripe ID. Use cs_, sub_, pi_, or cus_.",
        status_code=400,
        payload={"stripeId": stripe_id},
    )
# <<< SMX_STRIPE_RECONCILE_ANY_ID <<<

# >>> SMX_STRIPE_PRICE_PLAN_RESOLVER_FIX >>>
def _smx_obj_get(obj: Any, *names: str) -> Any:
    for name in names:
        if isinstance(obj, dict):
            value = obj.get(name)
        else:
            value = getattr(obj, name, None)

        if value is not None and str(value).strip():
            return value

    return None


def _smx_price_amount_plan(price: Any) -> str:
    amount = _smx_obj_get(price, "unit_amount", "amount")
    currency = str(_smx_obj_get(price, "currency") or "").lower().strip()

    try:
        amount_int = int(amount)
    except Exception:
        amount_int = -1

    try:
        from services.billing_pricing import smx_plan_key_from_monthly_minor_amount

        return smx_plan_key_from_monthly_minor_amount(amount_int, currency or "eur") or ""
    except Exception:
        return ""


def _smx_price_text_plan(price: Any, subscription: Any = None) -> str:
    values = []

    for source in [price, subscription]:
        if source is None:
            continue

        for name in [
            "lookup_key",
            "nickname",
            "id",
            "description",
            "name",
        ]:
            value = _smx_obj_get(source, name)

            if value:
                values.append(str(value).lower())

    product = _smx_obj_get(price, "product")

    if product and not isinstance(product, str):
        for name in ["name", "description", "id"]:
            value = _smx_obj_get(product, name)

            if value:
                values.append(str(value).lower())

    blob = " ".join(values)

    for key in ["starter", "pro", "business", "enterprise"]:
        if key in blob:
            return key

    return ""


def _smx_subscription_price_debug(subscription: Any) -> list[dict[str, Any]]:
    debug = []
    items = _smx_obj_get(subscription, "items")
    data = _smx_obj_get(items, "data") if items is not None else []

    for item in list(data or []):
        price = _smx_obj_get(item, "price") or _smx_obj_get(item, "plan")

        if not price:
            continue

        debug.append({
            "priceId": str(_smx_obj_get(price, "id") or ""),
            "lookupKey": str(_smx_obj_get(price, "lookup_key") or ""),
            "nickname": str(_smx_obj_get(price, "nickname") or ""),
            "unitAmount": _smx_obj_get(price, "unit_amount", "amount"),
            "currency": str(_smx_obj_get(price, "currency") or ""),
        })

    return debug


def _plan_from_subscription(subscription: Any) -> str:
    metadata = _smx_obj_get(subscription, "metadata") or {}

    if isinstance(metadata, dict):
        plan = _clean(metadata.get("planKey") or metadata.get("plan") or metadata.get("plan_key"))

        if plan:
            return plan

    items = _smx_obj_get(subscription, "items")
    data = _smx_obj_get(items, "data") if items is not None else []

    price_to_plan = _price_to_plan_map()

    for item in list(data or []):
        price = _smx_obj_get(item, "price") or _smx_obj_get(item, "plan")

        if not price:
            continue

        price_id = _clean(_smx_obj_get(price, "id"))

        if price_id and price_id in price_to_plan:
            return price_to_plan[price_id]

        text_plan = _smx_price_text_plan(price, subscription)

        if text_plan:
            return text_plan

        amount_plan = _smx_price_amount_plan(price)

        if amount_plan:
            return amount_plan

    return ""
# <<< SMX_STRIPE_PRICE_PLAN_RESOLVER_FIX >>>

# >>> SMX_ADMIN_CENTRAL_PRICING_RESOLVER >>>
def _plan_from_subscription(subscription: Any) -> str:
    try:
        from services.billing_pricing import smx_plan_key_from_stripe_subscription

        return smx_plan_key_from_stripe_subscription(subscription) or ""
    except Exception:
        metadata = getattr(subscription, "metadata", None) or {}

        if isinstance(metadata, dict):
            return _clean(metadata.get("planKey") or metadata.get("plan_key") or metadata.get("plan"))

    return ""
# <<< SMX_ADMIN_CENTRAL_PRICING_RESOLVER <<<
