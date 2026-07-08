from __future__ import annotations

import os
from typing import Any

from services.billing_usage import get_workspace_subscription, set_workspace_plan


SUPPORTED_BILLING_PROVIDERS = {"dev", "stripe", "paddle"}
SUPPORTED_PLAN_KEYS = {"starter", "pro", "business", "enterprise"}


class BillingProviderError(RuntimeError):
    pass


class BillingWebhookNotReady(BillingProviderError):
    pass


def _safe_text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


def _safe_provider(value: Any = None) -> str:
    provider = _safe_text(value or os.getenv("BILLING_PROVIDER") or "dev", "dev").lower()

    if provider not in SUPPORTED_BILLING_PROVIDERS:
        return "dev"

    return provider


def _safe_plan_key(value: Any) -> str:
    plan_key = _safe_text(value, "starter").lower()

    if plan_key not in SUPPORTED_PLAN_KEYS:
        raise BillingProviderError(f"Unknown planKey: {plan_key}")

    return plan_key


def billing_provider_status_payload() -> dict[str, Any]:
    provider = _safe_provider()

    stripe_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "").strip()
    paddle_secret = os.getenv("PADDLE_WEBHOOK_SECRET", "").strip()

    return {
        "provider": provider,
        "supportedProviders": sorted(SUPPORTED_BILLING_PROVIDERS),
        "webhookAdapterReady": provider == "dev",
        "realWebhookVerificationReady": False,
        "devSimulationEnabled": True,
        "secrets": {
            "stripeWebhookSecretConfigured": bool(stripe_secret and not stripe_secret.startswith("replace")),
            "paddleWebhookSecretConfigured": bool(paddle_secret and not paddle_secret.startswith("replace")),
        },
        "notes": [
            "Development simulator can update workspace subscriptions now.",
            "Real Stripe/Paddle signature verification is intentionally deferred to the next production step.",
            "Do not enable unverified real provider webhooks in production.",
        ],
    }


def normalize_dev_subscription_event(payload: dict[str, Any]) -> dict[str, Any]:
    workspace_id = _safe_text(payload.get("workspaceId") or payload.get("workspace_id"))

    if not workspace_id:
        raise BillingProviderError("workspaceId is required")

    plan_key = _safe_plan_key(payload.get("planKey") or payload.get("plan") or "starter")
    status = _safe_text(payload.get("status"), "active")
    provider = _safe_provider(payload.get("provider") or "dev")

    return {
        "provider": provider,
        "eventType": "subscription.updated",
        "workspaceId": workspace_id,
        "planKey": plan_key,
        "status": status,
        "customerId": _safe_text(payload.get("customerId") or payload.get("customer_id")),
        "subscriptionId": _safe_text(payload.get("subscriptionId") or payload.get("subscription_id")),
        "raw": payload,
    }


def normalize_stripe_subscription_event(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize common Stripe webhook payload shapes.

    Signature verification is intentionally not implemented here yet.
    Step 23 should add verified Stripe webhooks using the official Stripe SDK.
    """
    event_type = _safe_text(payload.get("type"), "stripe.event")
    data_object = (payload.get("data") or {}).get("object") or {}
    metadata = data_object.get("metadata") or {}

    workspace_id = _safe_text(
        metadata.get("workspaceId")
        or metadata.get("workspace_id")
        or data_object.get("client_reference_id")
    )

    plan_key = metadata.get("planKey") or metadata.get("plan_key") or metadata.get("plan") or "starter"

    if not workspace_id:
        raise BillingProviderError("Stripe event is missing workspaceId in metadata/client_reference_id")

    return {
        "provider": "stripe",
        "eventType": event_type,
        "workspaceId": workspace_id,
        "planKey": _safe_plan_key(plan_key),
        "status": _safe_text(data_object.get("status"), "active"),
        "customerId": _safe_text(data_object.get("customer")),
        "subscriptionId": _safe_text(data_object.get("subscription") or data_object.get("id")),
        "raw": payload,
    }


def normalize_paddle_subscription_event(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize common Paddle Billing webhook payload shapes.

    Signature verification is intentionally not implemented here yet.
    """
    event_type = _safe_text(payload.get("event_type") or payload.get("eventType"), "paddle.event")
    data = payload.get("data") or {}
    custom_data = data.get("custom_data") or data.get("customData") or {}

    workspace_id = _safe_text(custom_data.get("workspaceId") or custom_data.get("workspace_id"))
    plan_key = custom_data.get("planKey") or custom_data.get("plan_key") or custom_data.get("plan") or "starter"

    if not workspace_id:
        raise BillingProviderError("Paddle event is missing workspaceId in custom_data")

    return {
        "provider": "paddle",
        "eventType": event_type,
        "workspaceId": workspace_id,
        "planKey": _safe_plan_key(plan_key),
        "status": _safe_text(data.get("status"), "active"),
        "customerId": _safe_text(data.get("customer_id") or data.get("customerId")),
        "subscriptionId": _safe_text(data.get("id") or data.get("subscription_id") or data.get("subscriptionId")),
        "raw": payload,
    }


def normalize_subscription_event(provider: str, payload: dict[str, Any]) -> dict[str, Any]:
    provider = _safe_provider(provider)

    if provider == "dev":
        return normalize_dev_subscription_event(payload)

    if provider == "stripe":
        return normalize_stripe_subscription_event(payload)

    if provider == "paddle":
        return normalize_paddle_subscription_event(payload)

    raise BillingProviderError(f"Unsupported billing provider: {provider}")


def apply_normalized_subscription_event(event: dict[str, Any]) -> dict[str, Any]:
    subscription = set_workspace_plan(
        event["workspaceId"],
        event["planKey"],
        status=event.get("status") or "active",
        provider=event.get("provider") or "dev",
        customer_id=event.get("customerId") or "",
        subscription_id=event.get("subscriptionId") or "",
    )

    return {
        "event": {
            "provider": event.get("provider"),
            "eventType": event.get("eventType"),
            "workspaceId": event.get("workspaceId"),
            "planKey": event.get("planKey"),
            "status": event.get("status"),
            "customerId": event.get("customerId"),
            "subscriptionId": event.get("subscriptionId"),
        },
        "subscription": subscription,
    }


def process_dev_subscription_simulation(payload: dict[str, Any]) -> dict[str, Any]:
    event = normalize_dev_subscription_event(payload)
    return apply_normalized_subscription_event(event)


def process_provider_webhook(provider: str, payload: dict[str, Any], *, headers: dict[str, Any] | None = None) -> dict[str, Any]:
    provider = _safe_provider(provider)

    if provider != "dev":
        allow_unverified = os.getenv("BILLING_ACCEPT_UNVERIFIED_WEBHOOKS", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

        if not allow_unverified:
            raise BillingWebhookNotReady(
                "Real provider webhook verification is not enabled yet. "
                "Use /api/billing/dev/simulate-subscription for development, "
                "then add verified Stripe/Paddle webhook handling before production."
            )

    event = normalize_subscription_event(provider, payload)
    return apply_normalized_subscription_event(event)


def current_provider_subscription_status(workspace_id: str) -> dict[str, Any]:
    return {
        "provider": _safe_provider(),
        "subscription": get_workspace_subscription(workspace_id),
    }
