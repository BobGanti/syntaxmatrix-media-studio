from __future__ import annotations

import os
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from services.billing_pricing import get_billing_plan_map, get_pricing_config
from services.customer_workspace import get_customer_record, get_workspace_record


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

    plan = plans[plan_key]

    if plan_key == "enterprise":
        raise StripeCheckoutError("Enterprise is contract-priced. Use manual subscription management for this plan.")

    return plan


def _customer_email_for_workspace(workspace_id: str) -> str:
    workspace = get_workspace_record(workspace_id)

    if not workspace:
        return ""

    customer = get_customer_record(workspace.get("customerId"))

    if not customer:
        return ""

    return _clean(customer.get("billingEmail"))


def stripe_checkout_status_payload() -> dict[str, Any]:
    key = _clean(os.getenv("STRIPE_SECRET_KEY"))
    app_url = _app_public_url()

    return {
        "provider": "stripe",
        "configured": bool(key and not key.startswith("replace")),
        "appPublicUrl": app_url,
        "mode": "subscription",
        "pricingSource": "billing/pricing_config.json",
        "notes": [
            "Checkout Session uses Admin-managed pricing_config values.",
            "Real subscription activation still requires verified Stripe webhook handling in the next step.",
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

    plan = _plan_payload(plan_key)
    pricing = get_pricing_config()
    currency = _clean(pricing.get("currency"), "EUR").lower()
    unit_amount = _minor_unit_amount(plan.get("monthlyPrice"))
    monthly_credits = plan.get("monthlyCredits")

    stripe = _load_stripe_module()
    stripe.api_key = _stripe_secret_key()

    app_url = _app_public_url()
    customer_email = _clean(customer_email) or _customer_email_for_workspace(workspace_id)

    metadata = {
        "workspaceId": workspace_id,
        "planKey": plan["key"],
        "userId": user_id,
        "monthlyCredits": "unlimited" if monthly_credits is None else str(monthly_credits),
        "source": "syntaxmatrix_media_studio",
    }

    session_args: dict[str, Any] = {
        "mode": "subscription",
        "success_url": f"{app_url}/admin/clone-voice/billing?checkout=success&session_id={{CHECKOUT_SESSION_ID}}",
        "cancel_url": f"{app_url}/admin/clone-voice/billing?checkout=cancelled",
        "client_reference_id": workspace_id,
        "line_items": [
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
        ],
        "metadata": metadata,
        "subscription_data": {
            "metadata": metadata,
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
        "currency": currency.upper(),
        "sessionId": getattr(session, "id", None) or session.get("id"),
        "checkoutUrl": getattr(session, "url", None) or session.get("url"),
        "status": getattr(session, "status", None) or session.get("status"),
    }
