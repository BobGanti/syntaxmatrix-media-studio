from __future__ import annotations

import datetime as _dt
import math
import pathlib
import shutil
import subprocess
import uuid
from collections import defaultdict
from typing import Any

from services.persistence_repository import get_persistence_repository
from services.billing_pricing import (
    calculate_event_pricing,
    estimate_credits_for_event,
    estimate_provider_cost_for_event,
    get_billing_plan_map,
    get_credit_rule_map,
    get_pricing_config,
    save_pricing_config,
)


ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_PLAN_KEY = "free"


class QuotaExceededError(RuntimeError):
    def __init__(self, payload: dict[str, Any]):
        self.payload = payload
        super().__init__(payload.get("message") or "Workspace quota exceeded.")


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.UTC)


def _utc_now() -> str:
    return _now().isoformat(timespec="seconds")


def _month_key(value: str | None = None) -> str:
    if value:
        try:
            parsed = _dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.strftime("%Y-%m")
        except Exception:
            pass
    return _now().strftime("%Y-%m")


def _safe_number(value: Any, fallback: float = 0.0) -> float:
    try:
        parsed = float(value)
        return fallback if parsed < 0 else parsed
    except Exception:
        return fallback


def _parse_time(value: Any) -> _dt.datetime | None:
    if isinstance(value, _dt.datetime):
        parsed = value
    else:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            parsed = _dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
        except Exception:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_dt.UTC)
    return parsed.astimezone(_dt.UTC)


def pricing_config_payload() -> dict[str, Any]:
    return get_pricing_config()


def update_pricing_config(payload: dict[str, Any]) -> dict[str, Any]:
    return save_pricing_config(payload)


def billing_plans_payload() -> dict[str, Any]:
    plans = get_billing_plan_map()
    rows = []
    for plan in plans.values():
        item = dict(plan)
        key = item.get("key")
        available = bool(item.get("enabled", True))
        if key not in {"free", "enterprise"}:
            try:
                from services.stripe_price_catalog import get_stripe_price_for_plan
                available = available and bool(get_stripe_price_for_plan(str(key)))
            except Exception:
                available = False
        elif key == "enterprise":
            available = False
        item["available"] = available
        rows.append(item)
    return {
        "defaultPlan": DEFAULT_PLAN_KEY,
        "plans": rows,
        "creditRules": get_credit_rule_map(),
        "pricingConfig": get_pricing_config(),
    }


def _has_stripe_identity(row: dict[str, Any]) -> bool:
    return bool(
        str(row.get("stripeCustomerId") or row.get("customerId") or "").startswith("cus_")
        or str(row.get("stripeSubscriptionId") or row.get("subscriptionId") or "").startswith("sub_")
    )


def _free_subscription_record(workspace_id: str, previous: dict[str, Any] | None = None) -> dict[str, Any]:
    plan = get_billing_plan_map()["free"]
    previous = dict(previous or {})
    return {
        **previous,
        "workspaceId": workspace_id,
        "plan": "free",
        "planKey": "free",
        "planLabel": plan["label"],
        "status": "active",
        "provider": "internal",
        "monthlyCredits": plan.get("monthlyCredits"),
        "monthlyCreditLimit": plan.get("monthlyCredits"),
        "monthlyPrice": 0.0,
    }


def get_workspace_subscription(workspace_id: str) -> dict[str, Any]:
    workspace_id = str(workspace_id or "unknown_workspace").strip() or "unknown_workspace"
    repo = get_persistence_repository()
    row = repo.get_workspace_subscription(workspace_id) or {}

    # Convert only legacy unpaid onboarding records. Real Stripe identities and
    # active paid subscriptions are never overwritten.
    legacy_pending = (
        bool(row)
        and str(row.get("planKey") or row.get("plan") or "").lower() == "starter"
        and str(row.get("status") or "").lower() == "incomplete"
        and not _has_stripe_identity(row)
    )
    if not row or legacy_pending:
        row = _free_subscription_record(workspace_id, row)
        try:
            row = repo.upsert_workspace_subscription(workspace_id, row)
        except Exception as exc:
            print("[billing_usage] Could not persist Free subscription:", repr(exc), flush=True)

    plans = get_billing_plan_map()
    plan_key = str(row.get("planKey") or row.get("plan") or DEFAULT_PLAN_KEY).lower()
    if plan_key not in plans:
        plan_key = DEFAULT_PLAN_KEY
    plan = plans[plan_key]

    return {
        "workspaceId": workspace_id,
        "planKey": plan_key,
        "plan": plan,
        "status": row.get("status") or ("active" if plan_key == "free" else "incomplete"),
        "provider": row.get("provider") or ("internal" if plan_key == "free" else "stripe"),
        "customerId": row.get("customerId") or "",
        "subscriptionId": row.get("subscriptionId") or "",
        "stripeCustomerId": row.get("stripeCustomerId") or "",
        "stripeSubscriptionId": row.get("stripeSubscriptionId") or "",
        "checkoutSessionId": row.get("checkoutSessionId") or "",
        "updatedAt": row.get("updatedAt") or "",
    }


def set_workspace_plan(
    workspace_id: str,
    plan_key: str,
    *,
    status: str = "active",
    provider: str = "manual",
    customer_id: str = "",
    subscription_id: str = "",
) -> dict[str, Any]:
    workspace_id = str(workspace_id or "").strip()
    if not workspace_id:
        raise ValueError("workspaceId is required")
    plans = get_billing_plan_map()
    plan_key = str(plan_key or "").strip().lower()
    if plan_key not in plans:
        raise ValueError(f"Unknown planKey: {plan_key}")
    plan = plans[plan_key]
    get_persistence_repository().upsert_workspace_subscription(
        workspace_id,
        {
            "workspaceId": workspace_id,
            "plan": plan_key,
            "planKey": plan_key,
            "planLabel": plan.get("label") or plan_key.title(),
            "status": status or "active",
            "provider": provider or ("internal" if plan_key == "free" else "manual"),
            "customerId": customer_id or "",
            "subscriptionId": subscription_id or "",
            "monthlyCredits": plan.get("monthlyCredits"),
            "monthlyCreditLimit": plan.get("monthlyCredits"),
            "monthlyPrice": plan.get("monthlyPrice"),
        },
    )
    return get_workspace_subscription(workspace_id)


def estimate_credits(event_type: str, quantity: float = 1.0) -> int:
    return estimate_credits_for_event(event_type, quantity)


def estimate_narration_seconds_from_text(prompt: str, speed_key: str = "normal") -> float:
    # Preserved as non-billing analytics only.
    words = [item for item in str(prompt or "").split() if item.strip()]
    word_count = max(1, len(words))
    speed_multiplier = {"slower": 0.80, "slow": 0.90, "normal": 1.00, "fast": 1.10, "faster": 1.20}.get(str(speed_key or "normal").lower(), 1.00)
    return max(1.0, ((word_count / 155.0) * 60.0) / max(0.5, speed_multiplier))


def estimate_narration_credits_from_text(prompt: str, speed_key: str = "normal") -> int:
    del speed_key
    return estimate_credits("narration.generated", len(str(prompt or "")))


def estimate_voice_creation_credits(preview_text: str) -> int:
    return estimate_credits("voice.clone.succeeded", 1) + estimate_credits("voice.preview.generated", len(str(preview_text or "")))


def record_usage_event(
    workspace_id: str,
    event_type: str,
    *,
    quantity: float = 1.0,
    credits: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    workspace_id = str(workspace_id or "unknown_workspace").strip() or "unknown_workspace"
    event_type = str(event_type or "unknown_event").strip() or "unknown_event"
    quantity = _safe_number(quantity, 1.0)
    pricing = calculate_event_pricing(event_type, quantity)
    if credits is None:
        credits = int(pricing["credits"])
    now = _utc_now()
    merged_metadata = dict(metadata or {})
    merged_metadata["pricingSnapshot"] = pricing
    event = {
        "eventId": str(uuid.uuid4()),
        "timestamp": now,
        "createdAt": now,
        "month": _month_key(now),
        "workspaceId": workspace_id,
        "eventType": pricing["eventType"],
        "quantity": quantity,
        "quantityUnit": pricing["unit"],
        "credits": int(credits or 0),
        "estimatedProviderCost": pricing["supplierCostUsd"],
        "supplierCostUsd": pricing["supplierCostUsd"],
        "supplierCostUsdExact": pricing["supplierCostUsdExact"],
        "retailCostUsd": pricing["retailCostUsd"],
        "retailCostUsdExact": pricing["retailCostUsdExact"],
        "markupPercent": pricing["markupPercent"],
        "creditValueUsd": pricing["creditValueUsd"],
        "metadata": merged_metadata,
    }
    get_persistence_repository().append_usage_event(event)
    print("[billing_usage] recorded:", event, flush=True)
    return event


def read_usage_events(workspace_id: str | None = None, month: str | None = None) -> list[dict[str, Any]]:
    month = month or _month_key()
    return get_persistence_repository().list_usage_events(workspace_id=workspace_id, month=month)


def _period_contract(plan: dict[str, Any], now: _dt.datetime | None = None) -> dict[str, Any]:
    now = (now or _now()).astimezone(_dt.UTC)
    period = str(plan.get("creditPeriod") or ("weekly" if plan.get("key") == "free" else "monthly")).lower()
    if period == "weekly":
        config = get_pricing_config().get("freePlan") or {}
        reset_weekday = int(config.get("resetWeekday") or 0)
        reset_hour = int(config.get("resetHourUtc") or 0)
        candidate = now.replace(hour=reset_hour, minute=0, second=0, microsecond=0)
        days_back = (candidate.weekday() - reset_weekday) % 7
        start = candidate - _dt.timedelta(days=days_back)
        if start > now:
            start -= _dt.timedelta(days=7)
        end = start + _dt.timedelta(days=7)
        limit = plan.get("weeklyCredits")
        if limit is None:
            limit = config.get("weeklyCredits")
        return {"period": "weekly", "limit": limit, "start": start, "end": end, "label": "week"}

    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return {"period": "monthly", "limit": plan.get("monthlyCredits"), "start": start, "end": end, "label": "month"}


def _events_for_contract(workspace_id: str, contract: dict[str, Any]) -> list[dict[str, Any]]:
    if contract["period"] == "monthly":
        rows = get_persistence_repository().list_usage_events(workspace_id=workspace_id, month=contract["start"].strftime("%Y-%m"))
    else:
        rows = get_persistence_repository().list_usage_events(workspace_id=workspace_id, month=None)
    result = []
    for event in rows:
        when = _parse_time(event.get("createdAt") or event.get("timestamp"))
        if when is None:
            continue
        if contract["start"] <= when < contract["end"]:
            result.append(event)
    return result


def usage_summary(workspace_id: str, month: str | None = None) -> dict[str, Any]:
    del month
    subscription = get_workspace_subscription(workspace_id)
    plan = subscription["plan"]
    contract = _period_contract(plan)
    events = _events_for_contract(workspace_id, contract)
    by_event: dict[str, dict[str, Any]] = defaultdict(lambda: {"eventType": "", "count": 0, "quantity": 0.0, "credits": 0})
    total_credits = 0
    for event in events:
        event_type = event.get("eventType") or "unknown_event"
        row = by_event[event_type]
        row["eventType"] = event_type
        row["count"] += 1
        row["quantity"] += _safe_number(event.get("quantity"), 0)
        row["credits"] += int(_safe_number(event.get("credits"), 0))
        total_credits += int(_safe_number(event.get("credits"), 0))
    limit = contract["limit"]
    remaining = None if limit is None else max(0, int(limit) - total_credits)
    return {
        "workspaceId": workspace_id,
        "month": contract["start"].strftime("%Y-%m"),
        "periodKey": f"{contract['start'].date()}_{contract['end'].date()}",
        "creditPeriod": contract["period"],
        "creditPeriodLabel": contract["label"],
        "periodStart": contract["start"].isoformat(timespec="seconds"),
        "periodEnd": contract["end"].isoformat(timespec="seconds"),
        "subscription": subscription,
        "plan": plan,
        "monthlyCreditLimit": limit,
        "creditLimit": limit,
        "totalCredits": total_credits,
        "remainingCredits": remaining,
        "eventCount": len(events),
        "byEventType": list(by_event.values()),
        "events": events[-50:],
    }


def economics_summary(workspace_id: str, month: str | None = None) -> dict[str, Any]:
    summary = usage_summary(workspace_id, month)
    contract = _period_contract(summary["plan"])
    events = _events_for_contract(workspace_id, contract)
    config = get_pricing_config()
    supplier_cost = 0.0
    retail_usage = 0.0
    by_event: dict[str, dict[str, Any]] = defaultdict(lambda: {"eventType": "", "quantity": 0.0, "credits": 0, "estimatedProviderCost": 0.0, "retailUsageCostUsd": 0.0})
    for event in events:
        event_type = event.get("eventType") or "unknown_event"
        quantity = _safe_number(event.get("quantity"), 0)
        cost = _safe_number(event.get("supplierCostUsd", event.get("estimatedProviderCost")), 0)
        retail = _safe_number(event.get("retailCostUsd"), 0)
        row = by_event[event_type]
        row["eventType"] = event_type
        row["quantity"] += quantity
        row["credits"] += int(_safe_number(event.get("credits"), 0))
        row["estimatedProviderCost"] += cost
        row["retailUsageCostUsd"] += retail
        supplier_cost += cost
        retail_usage += retail
    monthly_revenue = _safe_number(summary["plan"].get("monthlyPrice"), 0)
    return {
        "workspaceId": workspace_id,
        "month": summary["month"],
        "currency": config.get("currency") or "EUR",
        "planCurrency": config.get("currency") or "EUR",
        "supplierCurrency": config.get("supplierCurrency") or "USD",
        "monthlyRevenue": round(monthly_revenue, 2),
        "estimatedProviderCost": round(supplier_cost, 10),
        "estimatedProviderCostUsd": round(supplier_cost, 10),
        "estimatedRetailUsageUsd": round(retail_usage, 10),
        "estimatedGrossMargin": None,
        "estimatedGrossMarginPercent": None,
        "byEventType": [{**row, "estimatedProviderCost": round(row["estimatedProviderCost"], 10), "retailUsageCostUsd": round(row["retailUsageCostUsd"], 10)} for row in by_event.values()],
        "pricingConfig": config,
        "usage": summary,
    }


def quota_status(workspace_id: str, month: str | None = None) -> dict[str, Any]:
    summary = usage_summary(workspace_id, month)
    limit = summary["creditLimit"]
    if limit is None:
        state, percent_used = "unlimited", None
    elif limit <= 0:
        state, percent_used = "blocked", 100
    else:
        percent_used = round((summary["totalCredits"] / limit) * 100, 2)
        state = "ok" if summary["totalCredits"] < limit else "exhausted"
    return {**summary, "quotaState": state, "percentUsed": percent_used}


def assert_workspace_can_spend(
    workspace_id: str,
    event_type: str,
    *,
    quantity: float = 1.0,
    estimated_credits: int | None = None,
    month: str | None = None,
) -> dict[str, Any]:
    status = quota_status(workspace_id, month)
    plan = status["plan"]
    subscription_status = str(status["subscription"].get("status") or "").lower()
    if subscription_status not in {"active", "trialing"}:
        raise QuotaExceededError({"message": "Workspace subscription is not active.", "workspaceId": workspace_id, "plan": plan, "quotaState": "inactive_subscription"})
    limit = status["creditLimit"]
    estimated = int(estimated_credits if estimated_credits is not None else estimate_credits(event_type, quantity))
    if limit is None:
        return {"allowed": True, "workspaceId": workspace_id, "eventType": event_type, "estimatedCredits": estimated, "quotaState": "unlimited", "plan": plan}
    projected = int(status["totalCredits"]) + estimated
    if projected > int(limit):
        period_label = status.get("creditPeriodLabel") or "period"
        raise QuotaExceededError({
            "message": f"{period_label.title()} credits exhausted. Upgrade the plan or wait for the next reset.",
            "workspaceId": workspace_id,
            "eventType": event_type,
            "estimatedCredits": estimated,
            "currentCredits": status["totalCredits"],
            "projectedCredits": projected,
            "creditLimit": limit,
            "monthlyCreditLimit": limit,
            "remainingCredits": status["remainingCredits"],
            "plan": plan,
            "quotaState": "exhausted",
            "creditPeriod": status.get("creditPeriod"),
        })
    return {"allowed": True, "workspaceId": workspace_id, "eventType": event_type, "estimatedCredits": estimated, "currentCredits": status["totalCredits"], "projectedCredits": projected, "creditLimit": limit, "monthlyCreditLimit": limit, "remainingCreditsAfter": int(limit) - projected, "quotaState": "ok", "plan": plan}


def custom_voice_entitlement(workspace_id: str) -> dict[str, Any]:
    subscription = get_workspace_subscription(workspace_id)
    plan = subscription["plan"]
    slots = plan.get("cloneSlots")
    try:
        count = len(get_persistence_repository().list_workspace_voices(workspace_id))
    except Exception:
        count = 0
    allowed = slots is None or int(slots) > 0
    remaining = None if slots is None else max(0, int(slots) - count)
    return {
        "allowed": allowed,
        "workspaceId": workspace_id,
        "planKey": subscription["planKey"],
        "cloneSlots": slots,
        "activeCustomVoices": count,
        "remainingCloneSlots": remaining,
        "systemVoicesOnly": bool(plan.get("systemVoicesOnly")),
    }


def assert_workspace_can_create_custom_voice(workspace_id: str, *, replacing: bool = False) -> dict[str, Any]:
    entitlement = custom_voice_entitlement(workspace_id)
    if not entitlement["allowed"]:
        raise QuotaExceededError({**entitlement, "message": "The Free plan uses system voices only. Upgrade to clone a custom voice.", "quotaState": "custom_voice_not_in_plan"})
    if not replacing and entitlement["remainingCloneSlots"] is not None and entitlement["remainingCloneSlots"] <= 0:
        raise QuotaExceededError({**entitlement, "message": f"This plan allows {entitlement['cloneSlots']} active custom voice slot(s). Delete a voice or upgrade the plan.", "quotaState": "clone_slot_limit"})
    return entitlement


def assert_workspace_can_use_custom_voice(workspace_id: str) -> dict[str, Any]:
    entitlement = custom_voice_entitlement(workspace_id)
    if not entitlement["allowed"] or entitlement["systemVoicesOnly"]:
        raise QuotaExceededError({**entitlement, "message": "The Free plan can generate narration with system voices only.", "quotaState": "system_voices_only"})
    return entitlement


def audio_duration_seconds(audio_path: pathlib.Path) -> float:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return 0.0
    try:
        result = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            return 0.0
        return max(0.0, float((result.stdout or "0").strip() or 0))
    except Exception:
        return 0.0

# >>> SMX_SAFE_PRICING_CORE_REPAIR >>>
# Overrides old duration-based estimates with supplier-cost character metering.
def estimate_credits(event_type: str, quantity: float = 1.0) -> int:
    try:
        from services.billing_pricing import calculate_event_charge
        return int(calculate_event_charge(event_type, quantity).get("credits") or 0)
    except Exception:
        return 0


def estimate_narration_credits_from_text(prompt: str, speed_key: str = "normal") -> int:
    del speed_key
    return estimate_credits("narration.generated", len(str(prompt or "")))


def estimate_preview_credits_from_text(text: str) -> int:
    return estimate_credits("voice.preview.generated", len(str(text or "")))


def estimate_voice_setup_credits(
    preview_text: str,
    *,
    include_clone: bool = True,
    include_preview: bool = True,
) -> int:
    total = 0

    if include_clone:
        total += estimate_credits("voice.clone.succeeded", 1)

    if include_preview:
        total += estimate_preview_credits_from_text(preview_text)

    return total
# <<< SMX_SAFE_PRICING_CORE_REPAIR <<<

# >>> SMX_FREE_PLAN_WEEKLY_QUOTA_GUARD >>>
# Free-plan launch contract:
# - new workspaces default to Free
# - Free has weekly credits
# - Free cannot create/replace custom voices
DEFAULT_PLAN_KEY = "free"


def _smx_plan_period(plan: dict[str, Any]) -> str:
    period = str(plan.get("creditPeriod") or "").strip().lower()
    if period in {"week", "weekly"}:
        return "week"
    return "month"


def _smx_credit_limit(plan: dict[str, Any]) -> int | None:
    if _smx_plan_period(plan) == "week":
        value = plan.get("weeklyCredits")
    else:
        value = plan.get("monthlyCredits")

    if value is None:
        return None

    try:
        return max(0, int(float(value)))
    except Exception:
        return 0


def _smx_event_time(row: dict[str, Any]):
    value = str(row.get("createdAt") or row.get("timestamp") or "").strip()
    if not value:
        return None

    try:
        parsed = _dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=_dt.UTC)
        return parsed.astimezone(_dt.UTC)
    except Exception:
        return None


def _smx_current_week_window():
    config = get_pricing_config()
    free = config.get("freePlan") if isinstance(config.get("freePlan"), dict) else {}

    weekday = int(free.get("resetWeekday", 0) or 0)
    hour = int(free.get("resetHourUtc", 0) or 0)
    minute = int(free.get("resetMinuteUtc", 0) or 0)

    now = _dt.datetime.now(_dt.UTC)
    start = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

    days_back = (start.weekday() - weekday) % 7
    start = start - _dt.timedelta(days=days_back)

    if start > now:
        start = start - _dt.timedelta(days=7)

    end = start + _dt.timedelta(days=7)
    return start, end


def _smx_events_for_plan_period(events: list[dict[str, Any]], plan: dict[str, Any]) -> list[dict[str, Any]]:
    if _smx_plan_period(plan) != "week":
        return events

    start, end = _smx_current_week_window()
    filtered = []

    for row in events:
        timestamp = _smx_event_time(row)

        if timestamp is None:
            continue

        if start <= timestamp < end:
            filtered.append(row)

    return filtered


def _smx_is_custom_voice_action(event_type: str) -> bool:
    return str(event_type or "").strip() in {
        "voice.parameter.saved",
        "voice.clone.succeeded",
        "voice.clone.with_preview",
        "voice.preview.generated",
    }


def _smx_plan_blocks_custom_voice(plan: dict[str, Any]) -> bool:
    if bool(plan.get("systemVoicesOnly")):
        return True

    raw = plan.get("maxCustomVoices", plan.get("cloneSlots"))

    if raw is None:
        return False

    try:
        return int(float(raw)) <= 0
    except Exception:
        return True


def billing_plans_payload() -> dict[str, Any]:
    plans = get_billing_plan_map()
    credit_rules = get_credit_rule_map()

    return {
        "defaultPlan": DEFAULT_PLAN_KEY,
        "plans": list(plans.values()),
        "creditRules": credit_rules,
        "pricingConfig": get_pricing_config(),
    }


def usage_summary(workspace_id: str, month: str | None = None) -> dict[str, Any]:
    month = month or _month_key()
    events = read_usage_events(workspace_id=workspace_id, month=month)
    subscription = get_workspace_subscription(workspace_id)
    plan = subscription["plan"]
    period = _smx_plan_period(plan)
    events = _smx_events_for_plan_period(events, plan)

    by_event: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "eventType": "",
        "count": 0,
        "quantity": 0.0,
        "credits": 0,
    })

    total_credits = 0

    for event in events:
        event_type = event.get("eventType") or "unknown_event"
        row = by_event[event_type]
        row["eventType"] = event_type
        row["count"] += 1
        row["quantity"] += _safe_number(event.get("quantity"), 0)
        row["credits"] += int(event.get("credits") or 0)
        total_credits += int(event.get("credits") or 0)

    credit_limit = _smx_credit_limit(plan)
    remaining = None if credit_limit is None else max(0, int(credit_limit) - total_credits)

    return {
        "workspaceId": workspace_id,
        "month": month,
        "creditPeriod": period,
        "subscription": subscription,
        "plan": plan,
        "monthlyCreditLimit": credit_limit,
        "weeklyCreditLimit": credit_limit if period == "week" else None,
        "creditLimit": credit_limit,
        "totalCredits": total_credits,
        "usedCredits": total_credits,
        "remainingCredits": remaining,
        "eventCount": len(events),
        "byEventType": list(by_event.values()),
        "events": events[-50:],
    }


def quota_status(workspace_id: str, month: str | None = None) -> dict[str, Any]:
    summary = usage_summary(workspace_id, month)
    limit = summary["creditLimit"]

    if limit is None:
        state = "unlimited"
        percent_used = None
    elif limit <= 0:
        state = "blocked"
        percent_used = 100
    else:
        percent_used = round((summary["totalCredits"] / limit) * 100, 2)
        state = "ok" if summary["totalCredits"] < limit else "exhausted"

    return {
        **summary,
        "quotaState": state,
        "percentUsed": percent_used,
    }


def assert_workspace_can_spend(
    workspace_id: str,
    event_type: str,
    *,
    quantity: float = 1.0,
    estimated_credits: int | None = None,
    month: str | None = None,
) -> dict[str, Any]:
    status = quota_status(workspace_id, month)
    plan = status["plan"]

    if status["subscription"].get("status") != "active":
        raise QuotaExceededError({
            "message": "Workspace subscription is not active.",
            "workspaceId": workspace_id,
            "plan": plan,
            "quotaState": "inactive_subscription",
        })

    if _smx_is_custom_voice_action(event_type) and _smx_plan_blocks_custom_voice(plan):
        raise QuotaExceededError({
            "message": "Your Free plan uses system voices only. Upgrade to Starter or higher to create saved custom voices.",
            "workspaceId": workspace_id,
            "eventType": event_type,
            "plan": plan,
            "quotaState": "custom_voice_not_allowed",
        })

    limit = status["creditLimit"]

    if limit is None:
        return {
            "allowed": True,
            "workspaceId": workspace_id,
            "eventType": event_type,
            "estimatedCredits": int(estimated_credits or estimate_credits(event_type, quantity)),
            "quotaState": "unlimited",
            "plan": plan,
        }

    estimated = int(estimated_credits if estimated_credits is not None else estimate_credits(event_type, quantity))
    projected_total = int(status["totalCredits"]) + estimated

    if projected_total > int(limit):
        period = status.get("creditPeriod") or "month"
        raise QuotaExceededError({
            "message": f"{period.capitalize()} credits exhausted. Upgrade the plan or wait for the next reset.",
            "workspaceId": workspace_id,
            "eventType": event_type,
            "estimatedCredits": estimated,
            "currentCredits": status["totalCredits"],
            "projectedCredits": projected_total,
            "creditLimit": limit,
            "monthlyCreditLimit": limit,
            "remainingCredits": status["remainingCredits"],
            "plan": plan,
            "quotaState": "exhausted",
        })

    return {
        "allowed": True,
        "workspaceId": workspace_id,
        "eventType": event_type,
        "estimatedCredits": estimated,
        "currentCredits": status["totalCredits"],
        "projectedCredits": projected_total,
        "creditLimit": limit,
        "monthlyCreditLimit": limit,
        "remainingCreditsAfter": int(limit) - projected_total,
        "quotaState": "ok",
        "plan": plan,
    }
# <<< SMX_FREE_PLAN_WEEKLY_QUOTA_GUARD <<<
