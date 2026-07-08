from __future__ import annotations

import datetime as _dt
import json
import math
import pathlib
import shutil
import subprocess
import uuid
from collections import defaultdict
from typing import Any

from services.billing_pricing import (
    estimate_provider_cost_for_event,
    get_billing_plan_map,
    get_credit_rule_map,
    get_pricing_config,
    save_pricing_config,
)


ROOT = pathlib.Path(__file__).resolve().parent.parent

USAGE_DIR = ROOT / "usage"
LEDGER_PATH = USAGE_DIR / "usage_events.jsonl"

BILLING_DIR = ROOT / "billing"
SUBSCRIPTIONS_PATH = BILLING_DIR / "workspace_subscriptions.json"

DEFAULT_PLAN_KEY = "starter"


class QuotaExceededError(RuntimeError):
    def __init__(self, payload: dict[str, Any]):
        self.payload = payload
        super().__init__(payload.get("message") or "Workspace quota exceeded.")


def _utc_now() -> str:
    return _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds")


def _month_key(value: str | None = None) -> str:
    if value:
        try:
            parsed = _dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.strftime("%Y-%m")
        except Exception:
            pass

    return _dt.datetime.now(_dt.UTC).strftime("%Y-%m")


def _safe_number(value: Any, fallback: float = 0.0) -> float:
    try:
        parsed = float(value)
        if parsed < 0:
            return fallback
        return parsed
    except Exception:
        return fallback


def _ensure_dirs() -> None:
    USAGE_DIR.mkdir(parents=True, exist_ok=True)
    BILLING_DIR.mkdir(parents=True, exist_ok=True)


def _read_subscriptions() -> dict[str, Any]:
    _ensure_dirs()

    if not SUBSCRIPTIONS_PATH.exists():
        SUBSCRIPTIONS_PATH.write_text(json.dumps({}, indent=2), encoding="utf-8")
        return {}

    try:
        data = json.loads(SUBSCRIPTIONS_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception as exc:
        print("[billing_usage] Could not read subscriptions:", repr(exc), flush=True)

    return {}


def _write_subscriptions(data: dict[str, Any]) -> None:
    _ensure_dirs()
    SUBSCRIPTIONS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def pricing_config_payload() -> dict[str, Any]:
    return get_pricing_config()


def update_pricing_config(payload: dict[str, Any]) -> dict[str, Any]:
    return save_pricing_config(payload)


def billing_plans_payload() -> dict[str, Any]:
    plans = get_billing_plan_map()
    credit_rules = get_credit_rule_map()

    return {
        "defaultPlan": DEFAULT_PLAN_KEY,
        "plans": list(plans.values()),
        "creditRules": credit_rules,
        "pricingConfig": get_pricing_config(),
    }


def get_workspace_subscription(workspace_id: str) -> dict[str, Any]:
    workspace_id = str(workspace_id or "unknown_workspace").strip() or "unknown_workspace"
    data = _read_subscriptions()
    row = data.get(workspace_id) or {}

    plans = get_billing_plan_map()
    plan_key = row.get("planKey") or DEFAULT_PLAN_KEY

    if plan_key not in plans:
        plan_key = DEFAULT_PLAN_KEY

    plan = plans[plan_key]

    return {
        "workspaceId": workspace_id,
        "planKey": plan_key,
        "plan": plan,
        "status": row.get("status") or "active",
        "provider": row.get("provider") or "manual",
        "customerId": row.get("customerId") or "",
        "subscriptionId": row.get("subscriptionId") or "",
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

    data = _read_subscriptions()

    data[workspace_id] = {
        "planKey": plan_key,
        "status": status or "active",
        "provider": provider or "manual",
        "customerId": customer_id or "",
        "subscriptionId": subscription_id or "",
        "updatedAt": _utc_now(),
    }

    _write_subscriptions(data)

    return get_workspace_subscription(workspace_id)


def estimate_credits(event_type: str, quantity: float = 1.0) -> int:
    rules = get_credit_rule_map()
    rule = rules.get(event_type)

    if not rule:
        return 0

    quantity = _safe_number(quantity, 1.0)

    credits = quantity * float(rule.get("creditsPerUnit", 0))
    credits = max(float(rule.get("minimumCredits", 0)), credits)

    return int(math.ceil(credits))


def estimate_narration_seconds_from_text(prompt: str, speed_key: str = "normal") -> float:
    words = [item for item in str(prompt or "").split() if item.strip()]
    word_count = max(1, len(words))

    speed_multiplier = {
        "slower": 0.80,
        "slow": 0.90,
        "normal": 1.00,
        "fast": 1.10,
        "faster": 1.20,
    }.get(str(speed_key or "normal").strip().lower(), 1.00)

    estimated_seconds = (word_count / 155.0) * 60.0
    estimated_seconds = estimated_seconds / max(0.5, speed_multiplier)

    return max(1.0, estimated_seconds)


def estimate_narration_credits_from_text(prompt: str, speed_key: str = "normal") -> int:
    estimated_seconds = estimate_narration_seconds_from_text(prompt, speed_key)
    return estimate_credits("narration.generated", estimated_seconds)


def record_usage_event(
    workspace_id: str,
    event_type: str,
    *,
    quantity: float = 1.0,
    credits: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _ensure_dirs()

    workspace_id = str(workspace_id or "unknown_workspace").strip() or "unknown_workspace"
    event_type = str(event_type or "unknown_event").strip() or "unknown_event"
    quantity = _safe_number(quantity, 1.0)

    if credits is None:
        credits = estimate_credits(event_type, quantity)

    event = {
        "eventId": str(uuid.uuid4()),
        "timestamp": _utc_now(),
        "month": _month_key(),
        "workspaceId": workspace_id,
        "eventType": event_type,
        "quantity": quantity,
        "credits": int(credits or 0),
        "estimatedProviderCost": estimate_provider_cost_for_event(event_type, quantity),
        "metadata": metadata or {},
    }

    with LEDGER_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")

    print("[billing_usage] recorded:", event, flush=True)

    return event


def read_usage_events(workspace_id: str | None = None, month: str | None = None) -> list[dict[str, Any]]:
    if not LEDGER_PATH.exists():
        return []

    month = month or _month_key()
    rows: list[dict[str, Any]] = []

    with LEDGER_PATH.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()

            if not line:
                continue

            try:
                event = json.loads(line)
            except Exception:
                continue

            if workspace_id and event.get("workspaceId") != workspace_id:
                continue

            if month and event.get("month") != month:
                continue

            rows.append(event)

    return rows


def usage_summary(workspace_id: str, month: str | None = None) -> dict[str, Any]:
    month = month or _month_key()
    events = read_usage_events(workspace_id=workspace_id, month=month)
    subscription = get_workspace_subscription(workspace_id)
    plan = subscription["plan"]

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

    monthly_limit = plan.get("monthlyCredits")
    remaining = None if monthly_limit is None else max(0, int(monthly_limit) - total_credits)

    return {
        "workspaceId": workspace_id,
        "month": month,
        "subscription": subscription,
        "plan": plan,
        "monthlyCreditLimit": monthly_limit,
        "totalCredits": total_credits,
        "remainingCredits": remaining,
        "eventCount": len(events),
        "byEventType": list(by_event.values()),
        "events": events[-50:],
    }


def economics_summary(workspace_id: str, month: str | None = None) -> dict[str, Any]:
    month = month or _month_key()
    summary = usage_summary(workspace_id, month)
    events = read_usage_events(workspace_id=workspace_id, month=month)
    config = get_pricing_config()
    currency = config.get("currency") or "EUR"

    estimated_provider_cost = 0.0
    by_event: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "eventType": "",
        "quantity": 0.0,
        "credits": 0,
        "estimatedProviderCost": 0.0,
    })

    for event in events:
        event_type = event.get("eventType") or "unknown_event"
        quantity = _safe_number(event.get("quantity"), 0)
        cost = event.get("estimatedProviderCost")

        if cost is None:
            cost = estimate_provider_cost_for_event(event_type, quantity)

        cost = _safe_number(cost, 0)

        row = by_event[event_type]
        row["eventType"] = event_type
        row["quantity"] += quantity
        row["credits"] += int(event.get("credits") or 0)
        row["estimatedProviderCost"] += cost

        estimated_provider_cost += cost

    monthly_revenue = _safe_number(summary["plan"].get("monthlyPrice"), 0)
    gross_margin = monthly_revenue - estimated_provider_cost
    gross_margin_percent = None

    if monthly_revenue > 0:
        gross_margin_percent = round((gross_margin / monthly_revenue) * 100, 2)

    return {
        "workspaceId": workspace_id,
        "month": month,
        "currency": currency,
        "monthlyRevenue": round(monthly_revenue, 2),
        "estimatedProviderCost": round(estimated_provider_cost, 4),
        "estimatedGrossMargin": round(gross_margin, 4),
        "estimatedGrossMarginPercent": gross_margin_percent,
        "byEventType": [
            {
                **row,
                "estimatedProviderCost": round(row["estimatedProviderCost"], 4),
            }
            for row in by_event.values()
        ],
        "pricingConfig": config,
        "usage": summary,
    }


def quota_status(workspace_id: str, month: str | None = None) -> dict[str, Any]:
    summary = usage_summary(workspace_id, month)
    monthly_limit = summary["monthlyCreditLimit"]

    if monthly_limit is None:
        state = "unlimited"
        percent_used = None
    elif monthly_limit <= 0:
        state = "blocked"
        percent_used = 100
    else:
        percent_used = round((summary["totalCredits"] / monthly_limit) * 100, 2)
        state = "ok" if summary["totalCredits"] < monthly_limit else "exhausted"

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

    monthly_limit = status["monthlyCreditLimit"]

    if monthly_limit is None:
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

    if projected_total > int(monthly_limit):
        raise QuotaExceededError({
            "message": "Monthly credits exhausted. Upgrade the plan or wait for the next billing month.",
            "workspaceId": workspace_id,
            "eventType": event_type,
            "estimatedCredits": estimated,
            "currentCredits": status["totalCredits"],
            "projectedCredits": projected_total,
            "monthlyCreditLimit": monthly_limit,
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
        "monthlyCreditLimit": monthly_limit,
        "remainingCreditsAfter": int(monthly_limit) - projected_total,
        "quotaState": "ok",
        "plan": plan,
    }


def audio_duration_seconds(audio_path: pathlib.Path) -> float:
    ffprobe = shutil.which("ffprobe")

    if not ffprobe:
        return 0.0

    try:
        result = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(audio_path),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        if result.returncode != 0:
            return 0.0

        return max(0.0, float((result.stdout or "0").strip() or 0))
    except Exception:
        return 0.0
