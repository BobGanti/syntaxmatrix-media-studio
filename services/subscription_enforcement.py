from __future__ import annotations

import datetime as _dt
import json
import math
import pathlib
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parent.parent
BILLING_DIR = ROOT / "billing"
USAGE_DIR = ROOT / "usage"

SUBSCRIPTIONS_PATH = BILLING_DIR / "workspace_subscriptions.json"
USAGE_EVENTS_PATH = USAGE_DIR / "usage_events.jsonl"


BLOCKED_SUBSCRIPTION_STATUSES = {
    "past_due",
    "canceled",
    "cancelled",
    "unpaid",
    "incomplete",
    "incomplete_expired",
    "paused",
}


ALLOWED_SUBSCRIPTION_STATUSES = {
    "active",
    "trialing",
}


NARRATION_PATHS = {
    "/api/clone-voice/from-saved",
    "/api/clone-voice/from-system",
}


VOICE_PARAMETER_PATHS = {
    "/api/clone-voice/voices/from-source",
}


TEXT_KEYS = (
    "text",
    "narrationText",
    "narration_text",
    "script",
    "content",
    "prompt",
)


def _clean(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


def _now_month() -> str:
    return _dt.datetime.now(_dt.UTC).strftime("%Y-%m")


def _number(value: Any, fallback: float = 0.0) -> float:
    if value is None:
        return fallback

    if isinstance(value, bool):
        return fallback

    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip().lower()

    if text in {"", "none", "null"}:
        return fallback

    if text in {"unlimited", "infinite", "inf"}:
        return math.inf

    try:
        return float(text)
    except Exception:
        return fallback


def _read_json(path: pathlib.Path, default: Any) -> Any:
    if not path.exists():
        return default

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _billing_plan_map() -> dict[str, dict[str, Any]]:
    try:
        from services.billing_pricing import get_billing_plan_map

        plans = get_billing_plan_map()
        if isinstance(plans, dict):
            return {
                str(key): dict(value)
                for key, value in plans.items()
                if isinstance(value, dict)
            }
    except Exception:
        pass

    return {
        "starter": {
            "key": "starter",
            "label": "Starter",
            "monthlyCredits": 1000,
            "monthlyPrice": 9,
        },
        "pro": {
            "key": "pro",
            "label": "Pro",
            "monthlyCredits": 5000,
            "monthlyPrice": 29,
        },
        "business": {
            "key": "business",
            "label": "Business",
            "monthlyCredits": 20000,
            "monthlyPrice": 99,
        },
        "enterprise": {
            "key": "enterprise",
            "label": "Enterprise",
            "monthlyCredits": None,
            "monthlyPrice": None,
        },
    }


def _default_subscription(workspace_id: str) -> dict[str, Any]:
    plan = _billing_plan_map().get("starter", {})

    return {
        "workspaceId": workspace_id,
        "plan": "starter",
        "planKey": "starter",
        "planLabel": plan.get("label", "Starter"),
        "monthlyCreditLimit": plan.get("monthlyCredits", 1000),
        "monthlyCredits": plan.get("monthlyCredits", 1000),
        "status": "active",
        "provider": "local",
    }


def _subscription_from_file(workspace_id: str) -> dict[str, Any]:
    data = _read_json(SUBSCRIPTIONS_PATH, {})

    if isinstance(data, dict) and isinstance(data.get("subscriptions"), dict):
        data = data["subscriptions"]

    if isinstance(data, dict):
        record = data.get(workspace_id)
        if isinstance(record, dict):
            return dict(record)

    if isinstance(data, list):
        for row in data:
            if isinstance(row, dict) and row.get("workspaceId") == workspace_id:
                return dict(row)

    return _default_subscription(workspace_id)


def get_subscription_for_entitlement(workspace_id: str) -> dict[str, Any]:
    workspace_id = _clean(workspace_id, "mock_user_001")

    # Stripe webhook state is the highest-trust billing source after checkout.
    # It contains the real Stripe customer/subscription IDs needed by the
    # client billing portal.
    file_record = _subscription_from_file(workspace_id)

    if isinstance(file_record, dict):
        has_stripe_identity = bool(
            _clean(file_record.get("stripeCustomerId"))
            or _clean(file_record.get("stripeSubscriptionId"))
            or _clean(file_record.get("subscriptionId")).startswith("sub_")
            or _clean(file_record.get("customerId")).startswith("cus_")
        )

        if _clean(file_record.get("provider")).lower() == "stripe" or has_stripe_identity:
            merged = _default_subscription(workspace_id)
            merged.update(file_record)
            return merged

    # Fallback for local/manual/dev subscriptions.
    try:
        from services.billing_usage import get_workspace_subscription

        record = get_workspace_subscription(workspace_id)

        if isinstance(record, dict):
            if isinstance(record.get("subscription"), dict):
                record = record["subscription"]

            if record:
                merged = _default_subscription(workspace_id)
                merged.update(record)
                return merged
    except Exception:
        pass

    merged = _default_subscription(workspace_id)
    merged.update(file_record)
    return merged


def _subscription_status(subscription: dict[str, Any]) -> str:
    return _clean(subscription.get("status"), "active").lower()


def _plan_key(subscription: dict[str, Any]) -> str:
    return _clean(
        subscription.get("planKey")
        or subscription.get("plan")
        or subscription.get("plan_id"),
        "starter",
    ).lower()


def _monthly_limit(subscription: dict[str, Any]) -> float | None:
    raw = (
        subscription.get("monthlyCreditLimit")
        if "monthlyCreditLimit" in subscription
        else subscription.get("monthlyCredits")
    )

    if raw is None:
        plan = _billing_plan_map().get(_plan_key(subscription), {})
        raw = plan.get("monthlyCredits")

    if raw is None:
        return None

    value = _number(raw, fallback=0)

    if value == math.inf:
        return None

    return value


def _extract_credit_value(payload: Any) -> float | None:
    if isinstance(payload, (int, float)) and not isinstance(payload, bool):
        return float(payload)

    if isinstance(payload, dict):
        for key in (
            "credits",
            "creditCost",
            "estimatedCredits",
            "requiredCredits",
            "totalCredits",
            "usedCredits",
            "creditsUsed",
            "currentMonthCredits",
        ):
            if key in payload:
                return _number(payload.get(key), fallback=0)

        for value in payload.values():
            nested = _extract_credit_value(value)
            if nested is not None:
                return nested

    return None


def _used_credits_from_usage_summary(workspace_id: str) -> float | None:
    try:
        from services.billing_usage import usage_summary

        summary = usage_summary(workspace_id)

        value = _extract_credit_value(summary)

        if value is not None:
            return value
    except Exception:
        pass

    return None


def _used_credits_from_jsonl(workspace_id: str) -> float:
    if not USAGE_EVENTS_PATH.exists():
        return 0.0

    month = _now_month()
    total = 0.0

    try:
        for line in USAGE_EVENTS_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()

            if not line:
                continue

            try:
                row = json.loads(line)
            except Exception:
                continue

            if not isinstance(row, dict):
                continue

            if _clean(row.get("workspaceId")) != workspace_id:
                continue

            timestamp = _clean(row.get("createdAt") or row.get("timestamp") or row.get("time"))

            if timestamp and not timestamp.startswith(month):
                continue

            value = _extract_credit_value(row)

            if value is not None:
                total += value
    except Exception:
        return 0.0

    return total


def used_credits_this_month(workspace_id: str) -> float:
    value = _used_credits_from_usage_summary(workspace_id)

    if value is not None:
        return max(0.0, value)

    return max(0.0, _used_credits_from_jsonl(workspace_id))


def _extract_text_from_request(flask_request) -> str:
    data = flask_request.get_json(silent=True)

    if not isinstance(data, dict):
        data = {}

    for source in (data, flask_request.form, flask_request.args):
        for key in TEXT_KEYS:
            value = source.get(key) if hasattr(source, "get") else None

            if value:
                return str(value)

    return ""


def _credits_from_existing_estimators(action: str, text: str = "") -> float | None:
    try:
        import services.billing_usage as billing_usage
    except Exception:
        return None

    if action == "narration.generated":
        fn = getattr(billing_usage, "estimate_narration_credits_from_text", None)

        if callable(fn):
            for call in (
                lambda: fn(text),
                lambda: fn(narration_text=text),
                lambda: fn(text=text),
            ):
                try:
                    value = _extract_credit_value(call())
                    if value is not None:
                        return value
                except TypeError:
                    continue
                except Exception:
                    return None

    fn = getattr(billing_usage, "estimate_credits", None)

    if callable(fn):
        for call in (
            lambda: fn(action),
            lambda: fn(action, text),
            lambda: fn(event_type=action),
            lambda: fn(event_type=action, text=text),
            lambda: fn(action=action, text=text),
        ):
            try:
                value = _extract_credit_value(call())
                if value is not None:
                    return value
            except TypeError:
                continue
            except Exception:
                return None

    return None


def estimate_requested_credits(action: str, flask_request=None) -> float:
    action = _clean(action)

    text = _extract_text_from_request(flask_request) if flask_request is not None else ""

    existing = _credits_from_existing_estimators(action, text)

    if existing is not None:
        return max(0.0, existing)

    if action == "narration.generated":
        # Conservative fallback: about one generated audio second per 15 chars,
        # then one credit per estimated generated second.
        chars = len(text.strip())
        return max(1.0, math.ceil(chars / 15)) if chars else 1.0

    if action == "voice.parameter.saved":
        # Conservative fallback. Existing billing_pricing rules override this
        # whenever billing_usage estimators are available.
        return 25.0

    return 1.0


def action_for_request(path: str, method: str) -> str:
    path = _clean(path).rstrip("/")
    method = _clean(method).upper()

    if method not in {"POST", "PUT", "PATCH"}:
        return ""

    if path in NARRATION_PATHS:
        return "narration.generated"

    if path in VOICE_PARAMETER_PATHS:
        return "voice.parameter.saved"

    if path.startswith("/api/clone-voice/my-voices/") and path.endswith("/replace-source"):
        return "voice.parameter.saved"

    return ""


def entitlement_payload(
    *,
    workspace_id: str,
    action: str = "",
    requested_credits: float = 0,
) -> dict[str, Any]:
    workspace_id = _clean(workspace_id, "mock_user_001")
    action = _clean(action, "status")
    requested_credits = max(0.0, _number(requested_credits, fallback=0))

    subscription = get_subscription_for_entitlement(workspace_id)
    status = _subscription_status(subscription)
    plan_key = _plan_key(subscription)
    plan = _billing_plan_map().get(plan_key, {})

    monthly_limit = _monthly_limit(subscription)
    used = used_credits_this_month(workspace_id)

    remaining = None
    quota_state = "unlimited"

    if monthly_limit is not None:
        remaining = max(0.0, monthly_limit - used)
        quota_state = "ok" if used + requested_credits <= monthly_limit else "exceeded"

    allowed = True
    reason = "allowed"
    message = "Subscription and credits allow this action."

    if status in BLOCKED_SUBSCRIPTION_STATUSES:
        allowed = False
        reason = f"subscription_{status}"
        message = f"Your subscription is {status}. Please update billing before using this feature."

    elif status not in ALLOWED_SUBSCRIPTION_STATUSES:
        allowed = False
        reason = f"subscription_{status or 'unknown'}"
        message = "Your subscription is not active. Please activate billing before using this feature."

    elif quota_state == "exceeded":
        allowed = False
        reason = "monthly_credit_limit_exceeded"
        message = "Monthly usage credits are exhausted. Please upgrade or wait for the next billing cycle."

    return {
        "allowed": allowed,
        "reason": reason,
        "message": message,
        "workspaceId": workspace_id,
        "action": action,
        "requestedCredits": requested_credits,
        "subscription": {
            "provider": subscription.get("provider", "local"),
            "status": status,
            "plan": plan_key,
            "planKey": plan_key,
            "planLabel": subscription.get("planLabel") or plan.get("label") or plan_key,
            "stripeCustomerId": subscription.get("stripeCustomerId") or subscription.get("customerId") or "",
            "stripeSubscriptionId": subscription.get("stripeSubscriptionId") or subscription.get("subscriptionId") or "",
        },
        "usage": {
            "usedCredits": used,
            "monthlyCreditLimit": monthly_limit,
            "remainingCredits": remaining,
            "quotaState": quota_state,
        },
    }


def evaluate_flask_request(flask_request, auth_context) -> dict[str, Any]:
    action = action_for_request(flask_request.path, flask_request.method)

    if not action:
        return {
            "enforced": False,
            "allowed": True,
            "reason": "not_metered_action",
        }

    data = flask_request.get_json(silent=True)
    if not isinstance(data, dict):
        data = {}

    workspace_id = (
        flask_request.args.get("workspaceId")
        or flask_request.form.get("workspaceId")
        or data.get("workspaceId")
        or getattr(auth_context, "workspace_id", "")
        or "mock_user_001"
    )

    requested_credits = estimate_requested_credits(action, flask_request)

    payload = entitlement_payload(
        workspace_id=workspace_id,
        action=action,
        requested_credits=requested_credits,
    )
    payload["enforced"] = True

    return payload
