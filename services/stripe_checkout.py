from __future__ import annotations

import os
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from services.billing_pricing import get_billing_plan_map, get_pricing_config
from services.customer_workspace import get_customer_record, get_workspace_record
from services.stripe_price_catalog import get_stripe_price_for_plan, stripe_price_catalog_status_payload


class StripeCheckoutError(RuntimeError):
    pass


class StripeCheckoutNotConfigured(StripeCheckoutError):
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
        raise StripeCheckoutNotConfigured(
            "Stripe Python package is not installed. Install it with: pip install stripe"
        ) from exc


def _stripe_secret_key() -> str:
    key = _clean(os.getenv("STRIPE_SECRET_KEY"))

    if not key or key.startswith("replace"):
        raise StripeCheckoutNotConfigured(
            "STRIPE_SECRET_KEY is not configured. Add your Stripe test secret key to your environment."
        )

    return key


def _minor_unit_amount(monthly_price: Any) -> int:
    amount = Decimal(str(monthly_price or "0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    if amount <= 0:
        raise StripeCheckoutError("Selected plan has no monthly price. Stripe checkout is not available for this plan.")

    return int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _plan_payload(plan_key: str) -> dict[str, Any]:
    plan_key = _clean(plan_key, "starter").lower()
    plans = get_billing_plan_map()

    if plan_key not in plans:
        raise StripeCheckoutError(f"Unknown planKey: {plan_key}")

    plan = dict(plans[plan_key])

    if plan_key == "enterprise":
        raise StripeCheckoutError("Enterprise is contract-priced. Use manual subscription management for this plan.")

    plan["key"] = plan.get("key") or plan_key

    return plan


def _customer_email_for_workspace(workspace_id: str) -> str:
    workspace = get_workspace_record(workspace_id)

    if not workspace:
        return ""

    customer = get_customer_record(workspace.get("customerId"))

    if not customer:
        return ""

    return _clean(customer.get("billingEmail"))


def _existing_stripe_customer_id(workspace_id: str) -> str:
    try:
        from services.subscription_enforcement import get_subscription_for_entitlement

        subscription = get_subscription_for_entitlement(workspace_id)
        if isinstance(subscription, dict):
            customer_id = _clean(
                subscription.get("stripeCustomerId")
                or subscription.get("customerId")
            )
            if customer_id.startswith("cus_"):
                return customer_id
    except Exception:
        pass
    return ""


def _existing_stripe_subscription(workspace_id: str) -> dict[str, Any] | None:
    try:
        from services.subscription_enforcement import get_subscription_for_entitlement

        subscription = get_subscription_for_entitlement(workspace_id)

        if not isinstance(subscription, dict):
            return None

        status = _clean(subscription.get("status")).lower()
        customer_id = _clean(subscription.get("stripeCustomerId") or subscription.get("customerId"))
        subscription_id = _clean(subscription.get("stripeSubscriptionId") or subscription.get("subscriptionId"))

        if customer_id.startswith("cus_") and subscription_id.startswith("sub_") and status in {
            "active",
            "trialing",
            "past_due",
            "unpaid",
            "incomplete",
            "paused",
        }:
            return subscription
    except Exception:
        return None

    return None


def _checkout_line_items(plan: dict[str, Any], metadata: dict[str, str]) -> tuple[list[dict[str, Any]], str]:
    price_record = get_stripe_price_for_plan(plan["key"])

    if price_record:
        return [
            {
                "price": price_record["priceId"],
                "quantity": 1,
            }
        ], "stripe_price_map"

    pricing = get_pricing_config()
    currency = _clean(pricing.get("currency"), "EUR").lower()
    unit_amount = _minor_unit_amount(plan.get("monthlyPrice"))
    monthly_credits = plan.get("monthlyCredits")

    return [
        {
            "price_data": {
                "currency": currency,
                "unit_amount": unit_amount,
                "recurring": {
                    "interval": "month",
                },
                "product_data": {
                    "name": f"SyntaxMatrix Media Studio — {plan['label']}",
                    "description": f"{'Unlimited' if monthly_credits is None else monthly_credits} monthly credits",
                    "metadata": metadata,
                },
            },
            "quantity": 1,
        }
    ], "inline_price_data"


def stripe_checkout_status_payload() -> dict[str, Any]:
    key = _clean(os.getenv("STRIPE_SECRET_KEY"))
    app_url = _app_public_url()
    catalog = stripe_price_catalog_status_payload()

    return {
        "provider": "stripe",
        "configured": bool(key and not key.startswith("replace")),
        "appPublicUrl": app_url,
        "mode": "subscription",
        "pricingSource": "billing/pricing_config.json",
        "persistentPriceCatalog": catalog,
        "notes": [
            "Checkout uses Stripe persistent Price IDs when billing/stripe_price_map.json contains a matching active price.",
            "If no Stripe price map exists yet, Checkout falls back to inline price_data for local MVP testing.",
            "Existing active Stripe subscriptions should use the customer portal, not a second Checkout Session.",
        ],
    }


def create_stripe_checkout_session(
    *,
    workspace_id: str,
    plan_key: str,
    user_id: str,
    customer_email: str = "",
) -> dict[str, Any]:
    workspace_id = _clean(workspace_id)
    user_id = _clean(user_id, "unknown_user")

    if not workspace_id:
        raise StripeCheckoutError("workspaceId is required")

    existing_subscription = _existing_stripe_subscription(workspace_id)

    if existing_subscription:
        raise StripeCheckoutError(
            "This workspace already has a Stripe subscription. Use the billing portal to manage or change the plan."
        )

    plan = _plan_payload(plan_key)
    monthly_credits = plan.get("monthlyCredits")

    stripe = _load_stripe_module()
    stripe.api_key = _stripe_secret_key()

    app_url = _app_public_url()
    existing_customer_id = _existing_stripe_customer_id(workspace_id)
    customer_email = _clean(customer_email) or _customer_email_for_workspace(workspace_id)

    metadata = {
        "workspaceId": workspace_id,
        "planKey": plan["key"],
        "userId": user_id,
        "monthlyCredits": "unlimited" if monthly_credits is None else str(monthly_credits),
        "source": "syntaxmatrix_media_studio",
    }

    line_items, pricing_source = _checkout_line_items(plan, metadata)

    session_args: dict[str, Any] = {
        "mode": "subscription",
        "success_url": f"{app_url}/plans?checkout=success&session_id={{CHECKOUT_SESSION_ID}}",
        "cancel_url": f"{app_url}/plans?checkout=cancelled",
        "client_reference_id": workspace_id,
        "line_items": line_items,
        "metadata": {
            **metadata,
            "pricingSource": pricing_source,
        },
        "subscription_data": {
            "metadata": {
                **metadata,
                "pricingSource": pricing_source,
            },
        },
        "allow_promotion_codes": True,
    }

    if existing_customer_id:
        session_args["customer"] = existing_customer_id
    elif customer_email:
        session_args["customer_email"] = customer_email

    session = stripe.checkout.Session.create(**session_args)

    return {
        "provider": "stripe",
        "mode": "subscription",
        "workspaceId": workspace_id,
        "planKey": plan["key"],
        "planLabel": plan["label"],
        "monthlyPrice": plan.get("monthlyPrice"),
        "monthlyCredits": monthly_credits,
        "currency": _clean(get_pricing_config().get("currency"), "EUR").upper(),
        "pricingSource": pricing_source,
        "sessionId": getattr(session, "id", None) or session.get("id"),
        "checkoutUrl": getattr(session, "url", None) or session.get("url"),
        "status": getattr(session, "status", None) or session.get("status"),
    }

# >>> SMX_STRIPE_CHECKOUT_RETURN_URL_OVERRIDE >>>
def _smx_same_origin_checkout_return_url(value: Any, app_url: str, fallback: str) -> str:
    raw = _clean(value)

    if not raw:
        return fallback

    if raw.startswith("/") and not raw.startswith("//"):
        return f"{app_url}{raw}"

    if raw == app_url or raw.startswith(f"{app_url}/"):
        return raw

    return fallback


def _smx_append_checkout_session_id(url: str) -> str:
    if "{CHECKOUT_SESSION_ID}" in url:
        return url

    separator = "&" if "?" in url else "?"
    return f"{url}{separator}session_id={{CHECKOUT_SESSION_ID}}"


def create_stripe_checkout_session(
    *,
    workspace_id: str,
    plan_key: str,
    user_id: str,
    customer_email: str = "",
    success_url: str = "",
    cancel_url: str = "",
) -> dict[str, Any]:
    workspace_id = _clean(workspace_id)
    user_id = _clean(user_id, "unknown_user")

    if not workspace_id:
        raise StripeCheckoutError("workspaceId is required")

    existing_subscription = _existing_stripe_subscription(workspace_id)

    if existing_subscription:
        raise StripeCheckoutError(
            "This workspace already has a Stripe subscription. Use the billing portal to manage or change the plan."
        )

    plan = _plan_payload(plan_key)
    monthly_credits = plan.get("monthlyCredits")

    stripe = _load_stripe_module()
    stripe.api_key = _stripe_secret_key()

    app_url = _app_public_url()
    customer_email = _clean(customer_email) or _customer_email_for_workspace(workspace_id)

    default_success_url = (
        f"{app_url}/tasks/clone-voice"
        f"?workspaceId={workspace_id}"
        f"&billing=success"
    )
    default_cancel_url = (
        f"{app_url}/plans"
        f"?workspaceId={workspace_id}"
        f"&checkout=cancelled"
    )

    safe_success_url = _smx_append_checkout_session_id(
        _smx_same_origin_checkout_return_url(success_url, app_url, default_success_url)
    )
    safe_cancel_url = _smx_same_origin_checkout_return_url(cancel_url, app_url, default_cancel_url)

    metadata = {
        "workspaceId": workspace_id,
        "planKey": plan["key"],
        "userId": user_id,
        "monthlyCredits": "unlimited" if monthly_credits is None else str(monthly_credits),
        "source": "syntaxmatrix_media_studio",
    }

    line_items, pricing_source = _checkout_line_items(plan, metadata)

    session_args: dict[str, Any] = {
        "mode": "subscription",
        "success_url": safe_success_url,
        "cancel_url": safe_cancel_url,
        "client_reference_id": workspace_id,
        "line_items": line_items,
        "metadata": {
            **metadata,
            "pricingSource": pricing_source,
        },
        "subscription_data": {
            "metadata": {
                **metadata,
                "pricingSource": pricing_source,
            },
        },
        "allow_promotion_codes": True,
    }

    if customer_email:
        session_args["customer_email"] = customer_email

    session = stripe.checkout.Session.create(**session_args)

    return {
        "provider": "stripe",
        "mode": "subscription",
        "workspaceId": workspace_id,
        "planKey": plan["key"],
        "planLabel": plan["label"],
        "monthlyPrice": plan.get("monthlyPrice"),
        "monthlyCredits": monthly_credits,
        "currency": _clean(get_pricing_config().get("currency"), "EUR").upper(),
        "pricingSource": pricing_source,
        "sessionId": getattr(session, "id", None) or session.get("id"),
        "checkoutUrl": getattr(session, "url", None) or session.get("url"),
        "status": getattr(session, "status", None) or session.get("status"),
        "successUrl": safe_success_url,
        "cancelUrl": safe_cancel_url,
    }
# <<< SMX_STRIPE_CHECKOUT_RETURN_URL_OVERRIDE <<<

