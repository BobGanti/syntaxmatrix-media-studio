from __future__ import annotations

import datetime as _dt
import json
import os
import pathlib
from typing import Any

from services.billing_pricing import get_billing_plan_map


ROOT = pathlib.Path(__file__).resolve().parent.parent
BILLING_DIR = ROOT / "billing"

SUBSCRIPTIONS_PATH = BILLING_DIR / "workspace_subscriptions.json"
EVENT_LOG_PATH = BILLING_DIR / "stripe_webhook_events.jsonl"
PROCESSED_EVENTS_PATH = BILLING_DIR / "stripe_processed_events.json"


class StripeWebhookError(RuntimeError):
    status_code = 400


class StripeWebhookNotConfigured(StripeWebhookError):
    status_code = 501


class StripeWebhookSignatureError(StripeWebhookError):
    status_code = 400


def _now() -> str:
    return _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds")


def _clean(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


def _get(obj: Any, key: str, fallback: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, fallback)

    try:
        return obj.get(key, fallback)
    except Exception:
        return getattr(obj, key, fallback)


def _metadata(obj: Any) -> dict[str, Any]:
    data = _get(obj, "metadata", {}) or {}

    if isinstance(data, dict):
        return dict(data)

    try:
        return dict(data)
    except Exception:
        return {}


def _ensure_billing_dir() -> None:
    BILLING_DIR.mkdir(parents=True, exist_ok=True)


def _read_json(path: pathlib.Path, default: Any) -> Any:
    _ensure_billing_dir()

    if not path.exists():
        return default

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print("[stripe_webhooks] Could not read", path, repr(exc), flush=True)
        return default


def _write_json(path: pathlib.Path, data: Any) -> None:
    _ensure_billing_dir()
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(path)


def _append_jsonl(path: pathlib.Path, row: dict[str, Any]) -> None:
    if path == EVENT_LOG_PATH:
        try:
            from services.persistence_repository import get_persistence_repository

            get_persistence_repository().append_stripe_webhook_event(row)
            return
        except Exception:
            pass

    _ensure_billing_dir()
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")

def _load_subscriptions() -> dict[str, dict[str, Any]]:
    try:
        from services.persistence_repository import list_workspace_subscriptions

        rows = list_workspace_subscriptions()

        return {
            str(record["workspaceId"]): dict(record)
            for record in rows
            if isinstance(record, dict) and record.get("workspaceId")
        }
    except Exception:
        pass

    data = _read_json(SUBSCRIPTIONS_PATH, {})

    if isinstance(data, dict) and isinstance(data.get("subscriptions"), dict):
        data = data["subscriptions"]

    if isinstance(data, dict):
        return {
            str(workspace_id): dict(record)
            for workspace_id, record in data.items()
            if isinstance(record, dict)
        }

    if isinstance(data, list):
        converted: dict[str, dict[str, Any]] = {}
        for record in data:
            if isinstance(record, dict) and record.get("workspaceId"):
                converted[str(record["workspaceId"])] = dict(record)
        return converted

    return {}



def _save_subscriptions(records: dict[str, dict[str, Any]]) -> None:
    try:
        from services.persistence_repository import get_persistence_repository

        repo = get_persistence_repository()

        for workspace_id, record in records.items():
            if isinstance(record, dict):
                repo.upsert_workspace_subscription(str(workspace_id), dict(record))

        return
    except Exception:
        pass

    _write_json(SUBSCRIPTIONS_PATH, records)



def _plan_for_key(plan_key: str) -> dict[str, Any]:
    plan_key = _clean(plan_key, "starter").lower()
    plans = get_billing_plan_map()

    if plan_key not in plans:
        raise StripeWebhookError(f"Unknown planKey from Stripe metadata: {plan_key}")

    return dict(plans[plan_key])


def _unix_to_iso(value: Any) -> str:
    try:
        number = int(value)
    except Exception:
        return ""

    try:
        return _dt.datetime.fromtimestamp(number, tz=_dt.UTC).isoformat(timespec="seconds")
    except Exception:
        return ""


def _processed_events() -> set[str]:
    try:
        from services.persistence_repository import processed_stripe_event_ids

        return processed_stripe_event_ids()
    except Exception:
        pass

    data = _read_json(PROCESSED_EVENTS_PATH, [])

    if isinstance(data, list):
        return {str(item) for item in data if item}

    if isinstance(data, dict):
        return {str(item) for item in data.get("eventIds", []) if item}

    return set()



def _mark_processed(event_id: str) -> None:
    event_id = _clean(event_id)

    if not event_id:
        return

    try:
        from services.persistence_repository import get_persistence_repository

        get_persistence_repository().mark_stripe_event_processed(event_id)
        return
    except Exception:
        pass

    events = sorted(_processed_events() | {event_id})
    _write_json(PROCESSED_EVENTS_PATH, events[-5000:])



def _find_workspace_by_subscription_id(subscription_id: str) -> str:
    subscription_id = _clean(subscription_id)

    if not subscription_id:
        return ""

    try:
        from services.persistence_repository import find_workspace_subscription_by_stripe_subscription_id

        record = find_workspace_subscription_by_stripe_subscription_id(subscription_id)

        if isinstance(record, dict) and record.get("workspaceId"):
            return _clean(record.get("workspaceId"))
    except Exception:
        pass

    for workspace_id, record in _load_subscriptions().items():
        if (
            record.get("subscriptionId") == subscription_id
            or record.get("stripeSubscriptionId") == subscription_id
        ):
            return workspace_id

    return ""



def _upsert_workspace_subscription(
    *,
    workspace_id: str,
    plan_key: str,
    status: str,
    stripe_customer_id: str = "",
    stripe_subscription_id: str = "",
    checkout_session_id: str = "",
    event_id: str = "",
    event_type: str = "",
    current_period_start: Any = None,
    current_period_end: Any = None,
    invoice_id: str = "",
) -> dict[str, Any]:
    workspace_id = _clean(workspace_id)

    if not workspace_id:
        raise StripeWebhookError("Stripe event did not include workspaceId metadata.")

    plan = _plan_for_key(plan_key)
    plan_key = plan["key"]

    records = _load_subscriptions()
    previous = dict(records.get(workspace_id, {}))

    period_start_iso = _unix_to_iso(current_period_start)
    period_end_iso = _unix_to_iso(current_period_end)

    record = dict(previous)
    record.update({
        "workspaceId": workspace_id,
        "plan": plan_key,
        "planKey": plan_key,
        "planLabel": plan.get("label") or plan_key,
        "monthlyCreditLimit": plan.get("monthlyCredits"),
        "monthlyCredits": plan.get("monthlyCredits"),
        "monthlyPrice": plan.get("monthlyPrice"),
        "status": _clean(status, "active"),
        "provider": "stripe",
        "customerId": _clean(stripe_customer_id) or previous.get("customerId") or previous.get("stripeCustomerId") or "",
        "subscriptionId": _clean(stripe_subscription_id) or previous.get("subscriptionId") or previous.get("stripeSubscriptionId") or "",
        "stripeCustomerId": _clean(stripe_customer_id) or previous.get("stripeCustomerId") or previous.get("customerId") or "",
        "stripeSubscriptionId": _clean(stripe_subscription_id) or previous.get("stripeSubscriptionId") or previous.get("subscriptionId") or "",
        "checkoutSessionId": _clean(checkout_session_id) or previous.get("checkoutSessionId") or "",
        "lastStripeEventId": _clean(event_id),
        "lastStripeEventType": _clean(event_type),
        "lastStripeInvoiceId": _clean(invoice_id) or previous.get("lastStripeInvoiceId") or "",
        "updatedAt": _now(),
    })

    if not record.get("createdAt"):
        record["createdAt"] = _now()

    if period_start_iso:
        record["currentPeriodStart"] = period_start_iso

    if period_end_iso:
        record["currentPeriodEnd"] = period_end_iso

    records[workspace_id] = record
    _save_subscriptions(records)

    return record


def _update_existing_subscription_status(
    *,
    stripe_subscription_id: str,
    status: str,
    event_id: str,
    event_type: str,
    invoice_id: str = "",
) -> dict[str, Any]:
    workspace_id = _find_workspace_by_subscription_id(stripe_subscription_id)

    if not workspace_id:
        return {
            "action": "ignored",
            "reason": "subscription_not_linked_to_workspace",
            "stripeSubscriptionId": stripe_subscription_id,
        }

    records = _load_subscriptions()
    record = dict(records.get(workspace_id, {}))
    record.update({
        "status": _clean(status, "active"),
        "provider": "stripe",
        "lastStripeEventId": _clean(event_id),
        "lastStripeEventType": _clean(event_type),
        "lastStripeInvoiceId": _clean(invoice_id) or record.get("lastStripeInvoiceId") or "",
        "updatedAt": _now(),
    })

    records[workspace_id] = record
    _save_subscriptions(records)

    return {
        "action": "updated_status",
        "workspaceId": workspace_id,
        "status": record["status"],
        "stripeSubscriptionId": stripe_subscription_id,
    }


def _handle_checkout_session(session: Any, *, event_id: str, event_type: str) -> dict[str, Any]:
    metadata = _metadata(session)

    mode = _clean(_get(session, "mode"))
    if mode and mode != "subscription":
        return {
            "action": "ignored",
            "reason": "checkout_session_not_subscription_mode",
            "mode": mode,
        }

    workspace_id = metadata.get("workspaceId") or _get(session, "client_reference_id")
    plan_key = metadata.get("planKey") or metadata.get("plan") or "starter"

    payment_status = _clean(_get(session, "payment_status"))
    session_status = _clean(_get(session, "status"))

    status = "active"
    if session_status and session_status != "complete":
        status = session_status
    elif payment_status and payment_status not in {"paid", "no_payment_required"}:
        status = payment_status

    record = _upsert_workspace_subscription(
        workspace_id=workspace_id,
        plan_key=plan_key,
        status=status,
        stripe_customer_id=_get(session, "customer", ""),
        stripe_subscription_id=_get(session, "subscription", ""),
        checkout_session_id=_get(session, "id", ""),
        event_id=event_id,
        event_type=event_type,
    )

    return {
        "action": "activated_from_checkout",
        "workspaceId": record["workspaceId"],
        "planKey": record["planKey"],
        "status": record["status"],
        "stripeSubscriptionId": record.get("stripeSubscriptionId"),
    }


def _handle_subscription(subscription: Any, *, event_id: str, event_type: str) -> dict[str, Any]:
    metadata = _metadata(subscription)

    workspace_id = metadata.get("workspaceId")
    plan_key = metadata.get("planKey") or metadata.get("plan") or "starter"
    status = _clean(_get(subscription, "status"), "active")

    subscription_deleted = event_type == "customer.subscription.deleted"
    if subscription_deleted:
        plan_key = "free"
        status = "active"

    if not workspace_id:
        workspace_id = _find_workspace_by_subscription_id(_get(subscription, "id", ""))

    if not workspace_id:
        return {
            "action": "ignored",
            "reason": "subscription_missing_workspace_metadata",
            "stripeSubscriptionId": _get(subscription, "id", ""),
            "status": status,
        }

    if subscription_deleted:
        records = _load_subscriptions()
        previous = dict(records.get(workspace_id) or {})
        free_plan = get_billing_plan_map().get("free") or {}
        record = {
            **previous,
            "workspaceId": workspace_id,
            "plan": "free",
            "planKey": "free",
            "planLabel": free_plan.get("label", "Free"),
            "status": "active",
            "provider": "internal",
            "monthlyCredits": free_plan.get("monthlyCredits", 10),
            "monthlyCreditLimit": free_plan.get("monthlyCredits", 10),
            "monthlyPrice": 0.0,
            "stripeCustomerId": _clean(_get(subscription, "customer")) or _clean(previous.get("stripeCustomerId")),
            "stripeSubscriptionId": "",
            "subscriptionId": "",
            "checkoutSessionId": "",
            "currentPeriodStart": None,
            "currentPeriodEnd": None,
            "lastStripeEventId": event_id,
            "lastStripeEventType": event_type,
            "updatedAt": _now(),
        }
        records[workspace_id] = record
        _save_subscriptions(records)
    else:
        record = _upsert_workspace_subscription(
            workspace_id=workspace_id,
            plan_key=plan_key,
            status=status,
            stripe_customer_id=_get(subscription, "customer", ""),
            stripe_subscription_id=_get(subscription, "id", ""),
            event_id=event_id,
            event_type=event_type,
            current_period_start=_get(subscription, "current_period_start"),
            current_period_end=_get(subscription, "current_period_end"),
        )

    return {
        "action": "updated_from_subscription",
        "workspaceId": record["workspaceId"],
        "planKey": record["planKey"],
        "status": record["status"],
        "stripeSubscriptionId": record.get("stripeSubscriptionId"),
    }


def _handle_invoice(invoice: Any, *, event_id: str, event_type: str) -> dict[str, Any]:
    stripe_subscription_id = _clean(_get(invoice, "subscription"))

    if not stripe_subscription_id:
        parent = _get(invoice, "parent", {}) or {}
        subscription_details = _get(parent, "subscription_details", {}) or {}
        stripe_subscription_id = _clean(_get(subscription_details, "subscription"))

    invoice_id = _clean(_get(invoice, "id"))

    if event_type == "invoice.payment_failed":
        return _update_existing_subscription_status(
            stripe_subscription_id=stripe_subscription_id,
            status="past_due",
            event_id=event_id,
            event_type=event_type,
            invoice_id=invoice_id,
        )

    if event_type in {"invoice.paid", "invoice.payment_succeeded"}:
        return _update_existing_subscription_status(
            stripe_subscription_id=stripe_subscription_id,
            status="active",
            event_id=event_id,
            event_type=event_type,
            invoice_id=invoice_id,
        )

    return {
        "action": "ignored",
        "reason": "invoice_event_not_handled",
        "eventType": event_type,
    }


def _load_stripe_module():
    try:
        import stripe  # type: ignore
        return stripe
    except Exception as exc:
        raise StripeWebhookNotConfigured(
            "Stripe Python package is not installed. Install it with: pip install stripe"
        ) from exc


def _webhook_secret() -> str:
    secret = _clean(os.getenv("STRIPE_WEBHOOK_SECRET"))

    if not secret or secret.startswith("replace"):
        raise StripeWebhookNotConfigured(
            "STRIPE_WEBHOOK_SECRET is not configured. Run stripe listen and copy the whsec_... value into your .env."
        )

    return secret


def stripe_webhook_status_payload() -> dict[str, Any]:
    return {
        "provider": "stripe",
        "configured": bool(_clean(os.getenv("STRIPE_WEBHOOK_SECRET")) and not _clean(os.getenv("STRIPE_WEBHOOK_SECRET")).startswith("replace")),
        "endpoint": "/api/billing/webhook/stripe",
        "eventsHandled": [
            "checkout.session.completed",
            "checkout.session.async_payment_succeeded",
            "customer.subscription.created",
            "customer.subscription.updated",
            "customer.subscription.deleted",
            "invoice.paid",
            "invoice.payment_succeeded",
            "invoice.payment_failed",
        ],
        "eventLog": str(EVENT_LOG_PATH.relative_to(ROOT)),
        "processedEvents": str(PROCESSED_EVENTS_PATH.relative_to(ROOT)),
    }


def verify_and_process_stripe_webhook(payload: bytes, signature_header: str) -> dict[str, Any]:
    stripe = _load_stripe_module()
    secret = _webhook_secret()

    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=signature_header,
            secret=secret,
        )
    except Exception as exc:
        raise StripeWebhookSignatureError(f"Stripe webhook signature verification failed: {exc}") from exc

    event_id = _clean(_get(event, "id"))
    event_type = _clean(_get(event, "type"))

    if not event_id:
        raise StripeWebhookError("Stripe event id is missing.")

    if event_id in _processed_events():
        return {
            "duplicate": True,
            "eventId": event_id,
            "eventType": event_type,
            "action": "already_processed",
        }

    data = _get(event, "data", {}) or {}
    obj = _get(data, "object", {}) or {}

    if event_type in {"checkout.session.completed", "checkout.session.async_payment_succeeded"}:
        result = _handle_checkout_session(obj, event_id=event_id, event_type=event_type)

    elif event_type in {
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    }:
        result = _handle_subscription(obj, event_id=event_id, event_type=event_type)

    elif event_type in {"invoice.paid", "invoice.payment_succeeded", "invoice.payment_failed"}:
        result = _handle_invoice(obj, event_id=event_id, event_type=event_type)

    else:
        result = {
            "action": "ignored",
            "reason": "event_type_not_handled",
            "eventType": event_type,
        }

    _append_jsonl(EVENT_LOG_PATH, {
        "receivedAt": _now(),
        "eventId": event_id,
        "eventType": event_type,
        "result": result,
    })

    _mark_processed(event_id)

    return {
        "duplicate": False,
        "eventId": event_id,
        "eventType": event_type,
        **result,
    }
