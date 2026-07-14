from __future__ import annotations

import datetime as _dt
import json
import os
import pathlib
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from services.billing_pricing import get_billing_plan_map, get_pricing_config


ROOT = pathlib.Path(__file__).resolve().parent.parent
BILLING_DIR = ROOT / "billing"
PRICE_MAP_PATH = BILLING_DIR / "stripe_price_map.json"

PRODUCT_NAME = "SyntaxMatrix Media Studio Subscription"
PRODUCT_DESCRIPTION = "Workspace-based AI voice and narration generation subscription."

# PAID_PLAN_RUNTIME_PRICE_IDS
RUNTIME_PRICE_ENV = {
    "starter": "STRIPE_PRICE_STARTER",
    "pro": "STRIPE_PRICE_PRO",
    "business": "STRIPE_PRICE_BUSINESS",
}


class StripePriceCatalogError(RuntimeError):
    pass


class StripePriceCatalogNotConfigured(StripePriceCatalogError):
    pass


def _now() -> str:
    return _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds")


def _clean(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


def _load_stripe_module():
    try:
        import stripe  # type: ignore
        return stripe
    except Exception as exc:
        raise StripePriceCatalogNotConfigured(
            "Stripe Python package is not installed. Install it with: pip install stripe"
        ) from exc


def _stripe_secret_key() -> str:
    key = _clean(os.getenv("STRIPE_SECRET_KEY"))

    if not key or key.startswith("replace"):
        raise StripePriceCatalogNotConfigured("STRIPE_SECRET_KEY is not configured.")

    return key


def stripe_mode() -> str:
    key = _clean(os.getenv("STRIPE_SECRET_KEY"))

    if key.startswith("sk_live_"):
        return "live"

    if key.startswith("sk_test_"):
        return "test"

    return "unknown"


def _ensure_billing_dir() -> None:
    BILLING_DIR.mkdir(parents=True, exist_ok=True)


def _read_price_map() -> dict[str, Any]:
    _ensure_billing_dir()

    if not PRICE_MAP_PATH.exists():
        return {
            "version": 1,
            "stripeMode": stripe_mode(),
            "product": {},
            "plans": {},
            "updatedAt": "",
        }

    try:
        data = json.loads(PRICE_MAP_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("version", 1)
            data.setdefault("stripeMode", stripe_mode())
            data.setdefault("product", {})
            data.setdefault("plans", {})
            return data
    except Exception:
        pass

    return {
        "version": 1,
        "stripeMode": stripe_mode(),
        "product": {},
        "plans": {},
        "updatedAt": "",
    }


def _write_price_map(data: dict[str, Any]) -> None:
    _ensure_billing_dir()
    data["updatedAt"] = _now()
    data["stripeMode"] = stripe_mode()

    tmp = PRICE_MAP_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(PRICE_MAP_PATH)


def _minor_unit_amount(monthly_price: Any) -> int:
    amount = Decimal(str(monthly_price or "0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    if amount <= 0:
        raise StripePriceCatalogError("Monthly price must be greater than zero.")

    return int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _normalise_currency(value: Any) -> str:
    return _clean(value, "EUR").lower()


def _active_billable_plans() -> list[dict[str, Any]]:
    plans = get_billing_plan_map()
    order = ["starter", "pro", "business", "enterprise"]
    rows = []

    for key in order:
        plan = plans.get(key)

        if not isinstance(plan, dict):
            continue

        monthly_price = plan.get("monthlyPrice")

        if monthly_price is None:
            continue

        try:
            unit_amount = _minor_unit_amount(monthly_price)
        except StripePriceCatalogError:
            continue

        if unit_amount <= 0:
            continue

        rows.append({
            "key": key,
            "label": plan.get("label") or key.title(),
            "monthlyPrice": float(monthly_price),
            "monthlyCredits": plan.get("monthlyCredits"),
            "unitAmount": unit_amount,
        })

    return rows


def _price_record_matches(record: dict[str, Any], *, currency: str, unit_amount: int) -> bool:
    return (
        _clean(record.get("priceId")).startswith("price_")
        and _clean(record.get("currency")).lower() == currency
        and int(record.get("unitAmount") or 0) == int(unit_amount)
        and bool(record.get("active", True))
    )


def _metadata_for_plan(plan: dict[str, Any]) -> dict[str, str]:
    monthly_credits = plan.get("monthlyCredits")

    return {
        "source": "syntaxmatrix_media_studio",
        "planKey": str(plan["key"]),
        "planLabel": str(plan["label"]),
        "monthlyCredits": "unlimited" if monthly_credits is None else str(monthly_credits),
        "pricingSource": "billing/pricing_config.json",
    }


def _get_or_create_product(stripe, price_map: dict[str, Any]) -> dict[str, Any]:
    product = price_map.get("product") if isinstance(price_map.get("product"), dict) else {}
    product_id = _clean(product.get("id"))

    if product_id.startswith("prod_"):
        try:
            stripe.Product.retrieve(product_id)
            return {
                "id": product_id,
                "name": product.get("name") or PRODUCT_NAME,
                "description": product.get("description") or PRODUCT_DESCRIPTION,
            }
        except Exception:
            pass

    created = stripe.Product.create(
        name=PRODUCT_NAME,
        description=PRODUCT_DESCRIPTION,
        metadata={
            "source": "syntaxmatrix_media_studio",
            "catalog": "subscription_plans",
        },
    )

    return {
        "id": getattr(created, "id", None) or created.get("id"),
        "name": PRODUCT_NAME,
        "description": PRODUCT_DESCRIPTION,
    }


def _create_price(stripe, *, product_id: str, currency: str, plan: dict[str, Any]) -> dict[str, Any]:
    metadata = _metadata_for_plan(plan)

    created = stripe.Price.create(
        product=product_id,
        currency=currency,
        unit_amount=plan["unitAmount"],
        recurring={
            "interval": "month",
        },
        nickname=f"{plan['label']} monthly",
        metadata=metadata,
    )

    return {
        "planKey": plan["key"],
        "planLabel": plan["label"],
        "productId": product_id,
        "priceId": getattr(created, "id", None) or created.get("id"),
        "currency": currency,
        "unitAmount": plan["unitAmount"],
        "monthlyPrice": plan["monthlyPrice"],
        "monthlyCredits": plan.get("monthlyCredits"),
        "active": True,
        "createdAt": _now(),
        "metadata": metadata,
    }


def sync_stripe_price_catalog() -> dict[str, Any]:
    stripe = _load_stripe_module()
    stripe.api_key = _stripe_secret_key()

    pricing = get_pricing_config()
    currency = _normalise_currency(pricing.get("currency"))

    price_map = _read_price_map()
    product = _get_or_create_product(stripe, price_map)
    price_map["product"] = product

    plans_map = price_map.get("plans")
    if not isinstance(plans_map, dict):
        plans_map = {}
        price_map["plans"] = plans_map

    changed = []
    reused = []

    for plan in _active_billable_plans():
        existing = plans_map.get(plan["key"])
        if not isinstance(existing, dict):
            existing = {}

        if _price_record_matches(existing, currency=currency, unit_amount=plan["unitAmount"]):
            reused.append({
                "planKey": plan["key"],
                "priceId": existing.get("priceId"),
                "unitAmount": existing.get("unitAmount"),
                "currency": existing.get("currency"),
            })
            continue

        old_price_id = _clean(existing.get("priceId"))

        if old_price_id.startswith("price_"):
            try:
                stripe.Price.modify(old_price_id, active=False)
            except Exception:
                pass

        record = _create_price(
            stripe,
            product_id=product["id"],
            currency=currency,
            plan=plan,
        )

        plans_map[plan["key"]] = record
        changed.append({
            "planKey": plan["key"],
            "priceId": record["priceId"],
            "unitAmount": record["unitAmount"],
            "currency": record["currency"],
        })

    _write_price_map(price_map)

    return {
        "provider": "stripe",
        "configured": True,
        "stripeMode": stripe_mode(),
        "product": product,
        "priceMapPath": str(PRICE_MAP_PATH.relative_to(ROOT)),
        "createdOrUpdated": changed,
        "reused": reused,
        "plans": plans_map,
    }


def _runtime_price_record(
    plan_key: str,
) -> dict[str, Any] | None:
    """Resolve a recurring Stripe Price from Cloud Run configuration."""
    plan_key = _clean(plan_key).lower()
    environment_name = RUNTIME_PRICE_ENV.get(plan_key)

    if not environment_name:
        return None

    price_id = _clean(os.getenv(environment_name))

    if not price_id.startswith("price_"):
        return None

    plan = get_billing_plan_map().get(plan_key)

    if not isinstance(plan, dict):
        return None

    monthly_price = plan.get("monthlyPrice")

    try:
        unit_amount = _minor_unit_amount(monthly_price)
    except StripePriceCatalogError:
        return None

    pricing = get_pricing_config()

    return {
        "planKey": plan_key,
        "planLabel": (
            plan.get("label")
            or plan_key.title()
        ),
        "priceId": price_id,
        "currency": _normalise_currency(
            pricing.get("currency")
        ),
        "unitAmount": unit_amount,
        "monthlyPrice": monthly_price,
        "monthlyCredits": plan.get("monthlyCredits"),
        "active": True,
        "stripeMode": stripe_mode(),
        "source": "cloud_run_environment",
    }


def get_stripe_price_for_plan(plan_key: str) -> dict[str, Any] | None:
    plan_key = _clean(plan_key).lower()

    runtime_record = _runtime_price_record(plan_key)

    if runtime_record:
        return runtime_record

    # Local JSON remains a development and migration fallback.
    price_map = _read_price_map()
    plans = price_map.get("plans")

    if not isinstance(plans, dict):
        return None

    record = plans.get(plan_key)

    if not isinstance(record, dict):
        return None

    if not _clean(record.get("priceId")).startswith("price_"):
        return None

    if not bool(record.get("active", True)):
        return None

    return dict(record)


def stripe_price_catalog_status_payload() -> dict[str, Any]:
    price_map = _read_price_map()
    plans = price_map.get("plans") if isinstance(price_map.get("plans"), dict) else {}

    configured_plans = []

    for key, record in plans.items():
        if not isinstance(record, dict):
            continue

        configured_plans.append({
            "planKey": key,
            "planLabel": record.get("planLabel") or key,
            "priceId": record.get("priceId") or "",
            "productId": record.get("productId") or "",
            "currency": record.get("currency") or "",
            "unitAmount": record.get("unitAmount"),
            "monthlyPrice": record.get("monthlyPrice"),
            "active": bool(record.get("active", True)),
        })

    return {
        "provider": "stripe",
        "configured": bool(_clean(os.getenv("STRIPE_SECRET_KEY")) and not _clean(os.getenv("STRIPE_SECRET_KEY")).startswith("replace")),
        "stripeMode": stripe_mode(),
        "priceMapPath": str(PRICE_MAP_PATH.relative_to(ROOT)),
        "product": price_map.get("product") or {},
        "configuredPlans": configured_plans,
        "usingPersistentPrices": bool(configured_plans),
    }

# >>> SMX_STRIPE_PRICE_MAP_PROVIDER_IDS_ONLY >>>
def _smx_clean_text(value, fallback=""):
    value = str(value or "").strip()
    return value or fallback


def _smx_walk_price_map(node, plan_key, inherited_plan=""):
    plan_key = _smx_clean_text(plan_key).lower()

    if isinstance(node, dict):
        current_plan = _smx_clean_text(
            node.get("planKey")
            or node.get("plan_key")
            or node.get("plan")
            or inherited_plan
        ).lower()

        for key in ["priceId", "price_id", "livePriceId", "live_price_id", "testPriceId", "test_price_id"]:
            price_id = _smx_clean_text(node.get(key))

            if price_id and current_plan == plan_key:
                return price_id

        for key, value in node.items():
            next_plan = current_plan

            if isinstance(key, str) and key.lower() == plan_key:
                next_plan = plan_key

            found = _smx_walk_price_map(value, plan_key, next_plan)

            if found:
                return found

    elif isinstance(node, list):
        for value in node:
            found = _smx_walk_price_map(value, plan_key, inherited_plan)

            if found:
                return found

    return ""


def smx_stripe_price_id_for_plan(plan_key):
    from services.billing_pricing import smx_stripe_price_map

    return _smx_walk_price_map(smx_stripe_price_map(), plan_key)


def get_stripe_price_for_plan(plan_key):
    from services.billing_pricing import (
        smx_get_plan,
        smx_plan_currency,
        smx_plan_monthly_minor_amount,
    )

    plan_key = _smx_clean_text(plan_key).lower()
    price_id = smx_stripe_price_id_for_plan(plan_key)

    if not price_id:
        return None

    plan = smx_get_plan(plan_key)
    amount = smx_plan_monthly_minor_amount(plan_key)

    return {
        "planKey": plan_key,
        "priceId": price_id,
        "active": True,
        "source": "stripe_price_map.provider_id_plus_pricing_config",
        "currency": smx_plan_currency(plan),
        "unitAmount": amount,
    }


def stripe_price_catalog_status_payload():
    from services.billing_pricing import smx_pricing_source_summary, smx_stripe_price_map

    price_map = smx_stripe_price_map()
    plans = price_map.get("plans") if isinstance(price_map, dict) else {}

    mapped = {}

    if isinstance(plans, dict):
        for plan_key in sorted(plans):
            mapped[plan_key] = get_stripe_price_for_plan(plan_key)

    return {
        "ok": True,
        "source": "stripe_price_map.provider_ids_only",
        "stripeMode": price_map.get("stripeMode") if isinstance(price_map, dict) else "",
        "pricingSource": smx_pricing_source_summary(),
        "mappedPlans": mapped,
    }
# <<< SMX_STRIPE_PRICE_MAP_PROVIDER_IDS_ONLY <<<
