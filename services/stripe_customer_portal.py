from __future__ import annotations

import os
from typing import Any

from services.subscription_enforcement import get_subscription_for_entitlement


class StripeCustomerPortalError(RuntimeError):
    pass


class StripeCustomerPortalNotConfigured(StripeCustomerPortalError):
    pass


class StripeCustomerPortalMissingCustomer(StripeCustomerPortalError):
    pass


def _clean(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


def _app_public_url() -> str:
    return _clean(os.getenv("APP_PUBLIC_URL"), "http://127.0.0.1:5055").rstrip("/")


def _load_stripe_module():
    try:
        import stripe  # type: ignore
        return stripe
    except Exception as exc:
        raise StripeCustomerPortalNotConfigured(
            "Stripe Python package is not installed. Install it with: pip install stripe"
        ) from exc


def _stripe_secret_key() -> str:
    key = _clean(os.getenv("STRIPE_SECRET_KEY"))

    if not key or key.startswith("replace"):
        raise StripeCustomerPortalNotConfigured("STRIPE_SECRET_KEY is not configured.")

    return key


def _stripe_customer_id_from_subscription(subscription: dict[str, Any]) -> str:
    customer_id = _clean(
        subscription.get("stripeCustomerId")
        or subscription.get("stripe_customer_id")
        or ""
    )

    if customer_id.startswith("cus_"):
        return customer_id

    return ""


def stripe_customer_portal_status_payload(workspace_id: str) -> dict[str, Any]:
    subscription = get_subscription_for_entitlement(workspace_id)
    stripe_customer_id = _stripe_customer_id_from_subscription(subscription)

    return {
        "provider": "stripe",
        "configured": bool(
            _clean(os.getenv("STRIPE_SECRET_KEY"))
            and not _clean(os.getenv("STRIPE_SECRET_KEY")).startswith("replace")
        ),
        "hasStripeCustomer": bool(stripe_customer_id),
        "workspaceId": workspace_id,
        "subscriptionStatus": subscription.get("status", "active"),
        "planKey": subscription.get("planKey") or subscription.get("plan") or "starter",
        "returnUrl": f"{_app_public_url()}/tasks/clone-voice?workspaceId={workspace_id}&billing=portal-return",
    }


def create_stripe_customer_portal_session(*, workspace_id: str) -> dict[str, Any]:
    workspace_id = _clean(workspace_id)

    if not workspace_id:
        raise StripeCustomerPortalError("workspaceId is required")

    subscription = get_subscription_for_entitlement(workspace_id)
    stripe_customer_id = _stripe_customer_id_from_subscription(subscription)

    if not stripe_customer_id:
        raise StripeCustomerPortalMissingCustomer(
            "This workspace does not yet have a Stripe customer. Start a subscription checkout first."
        )

    stripe = _load_stripe_module()
    stripe.api_key = _stripe_secret_key()

    return_url = f"{_app_public_url()}/tasks/clone-voice?workspaceId={workspace_id}&billing=portal-return"

    session = stripe.billing_portal.Session.create(
        customer=stripe_customer_id,
        return_url=return_url,
    )

    return {
        "provider": "stripe",
        "workspaceId": workspace_id,
        "stripeCustomerId": stripe_customer_id,
        "portalUrl": getattr(session, "url", None) or session.get("url"),
        "returnUrl": return_url,
    }
