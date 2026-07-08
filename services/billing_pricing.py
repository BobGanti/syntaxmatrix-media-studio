from __future__ import annotations

import copy
import json
import pathlib
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parent.parent
BILLING_DIR = ROOT / "billing"
PRICING_CONFIG_PATH = BILLING_DIR / "pricing_config.json"


DEFAULT_PRICING_CONFIG = {
    "currency": "EUR",
    "plans": [
        {
            "key": "starter",
            "label": "Starter",
            "monthlyPrice": 9.00,
            "monthlyCredits": 1000,
            "description": "Small team / early usage plan.",
        },
        {
            "key": "pro",
            "label": "Pro",
            "monthlyPrice": 29.00,
            "monthlyCredits": 5000,
            "description": "Regular narration and voice generation.",
        },
        {
            "key": "business",
            "label": "Business",
            "monthlyPrice": 99.00,
            "monthlyCredits": 20000,
            "description": "Higher usage with multiple workspaces and users.",
        },
        {
            "key": "enterprise",
            "label": "Enterprise",
            "monthlyPrice": 0.00,
            "monthlyCredits": None,
            "description": "Contract pricing, limits, and governance.",
        },
    ],
    "creditRules": [
        {
            "eventType": "voice.parameter.saved",
            "unit": "event",
            "creditsPerUnit": 25,
            "minimumCredits": 25,
            "description": "Creating or replacing a saved voice parameter.",
        },
        {
            "eventType": "narration.generated",
            "unit": "second",
            "creditsPerUnit": 1,
            "minimumCredits": 1,
            "description": "Final narration audio generation, charged by generated audio second.",
        },
    ],
    "providerCostRules": [
        {
            "eventType": "voice.parameter.saved",
            "unit": "event",
            "fixedCost": 0.50,
            "costPerUnit": 0.00,
            "description": "Internal estimated provider cost for creating/replacing a voice parameter and preview. Placeholder; update with real provider pricing.",
        },
        {
            "eventType": "narration.generated",
            "unit": "second",
            "fixedCost": 0.00,
            "costPerUnit": 0.004,
            "description": "Internal estimated provider cost per generated narration second. Placeholder; update with real provider pricing.",
        },
    ],
}


def _ensure_dir() -> None:
    BILLING_DIR.mkdir(parents=True, exist_ok=True)


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        parsed = float(value)
        if parsed < 0:
            return fallback
        return parsed
    except Exception:
        return fallback


def _safe_int_or_none(value: Any) -> int | None:
    if value is None:
        return None

    text = str(value).strip()

    if text == "" or text.lower() in {"none", "null", "unlimited"}:
        return None

    try:
        parsed = int(float(text))
        if parsed < 0:
            return 0
        return parsed
    except Exception:
        return None


def _safe_text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


def _normalise_plan(raw: dict[str, Any]) -> dict[str, Any]:
    key = _safe_text(raw.get("key")).lower()

    if not key:
        raise ValueError("Plan key is required")

    return {
        "key": key,
        "label": _safe_text(raw.get("label"), key.title()),
        "monthlyPrice": _safe_float(raw.get("monthlyPrice"), 0.0),
        "monthlyCredits": _safe_int_or_none(raw.get("monthlyCredits")),
        "description": _safe_text(raw.get("description")),
    }


def _normalise_credit_rule(raw: dict[str, Any]) -> dict[str, Any]:
    event_type = _safe_text(raw.get("eventType"))

    if not event_type:
        raise ValueError("Credit rule eventType is required")

    return {
        "eventType": event_type,
        "unit": _safe_text(raw.get("unit"), "event"),
        "creditsPerUnit": _safe_float(raw.get("creditsPerUnit"), 0.0),
        "minimumCredits": _safe_float(raw.get("minimumCredits"), 0.0),
        "description": _safe_text(raw.get("description")),
    }


def _normalise_provider_cost_rule(raw: dict[str, Any]) -> dict[str, Any]:
    event_type = _safe_text(raw.get("eventType"))

    if not event_type:
        raise ValueError("Provider cost rule eventType is required")

    return {
        "eventType": event_type,
        "unit": _safe_text(raw.get("unit"), "event"),
        "fixedCost": _safe_float(raw.get("fixedCost"), 0.0),
        "costPerUnit": _safe_float(raw.get("costPerUnit"), 0.0),
        "description": _safe_text(raw.get("description")),
    }


def normalise_pricing_config(raw: dict[str, Any]) -> dict[str, Any]:
    source = copy.deepcopy(DEFAULT_PRICING_CONFIG)

    if isinstance(raw, dict):
        source.update({k: v for k, v in raw.items() if k in {"currency", "plans", "creditRules", "providerCostRules"}})

    plans = source.get("plans") or DEFAULT_PRICING_CONFIG["plans"]
    credit_rules = source.get("creditRules") or DEFAULT_PRICING_CONFIG["creditRules"]
    provider_cost_rules = source.get("providerCostRules") or DEFAULT_PRICING_CONFIG["providerCostRules"]

    return {
        "currency": _safe_text(source.get("currency"), "EUR").upper(),
        "plans": [_normalise_plan(item) for item in plans],
        "creditRules": [_normalise_credit_rule(item) for item in credit_rules],
        "providerCostRules": [_normalise_provider_cost_rule(item) for item in provider_cost_rules],
    }


def ensure_pricing_config() -> pathlib.Path:
    _ensure_dir()

    if not PRICING_CONFIG_PATH.exists():
        PRICING_CONFIG_PATH.write_text(
            json.dumps(DEFAULT_PRICING_CONFIG, indent=2),
            encoding="utf-8",
        )

    return PRICING_CONFIG_PATH


def get_pricing_config() -> dict[str, Any]:
    ensure_pricing_config()

    try:
        raw = json.loads(PRICING_CONFIG_PATH.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            config = normalise_pricing_config(raw)
        else:
            config = normalise_pricing_config(DEFAULT_PRICING_CONFIG)
    except Exception as exc:
        print("[billing_pricing] Could not read pricing config:", repr(exc), flush=True)
        config = normalise_pricing_config(DEFAULT_PRICING_CONFIG)

    return {
        **config,
        "configPath": str(PRICING_CONFIG_PATH.relative_to(ROOT)).replace("\\", "/"),
    }


def save_pricing_config(raw: dict[str, Any]) -> dict[str, Any]:
    config = normalise_pricing_config(raw)
    _ensure_dir()
    PRICING_CONFIG_PATH.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return get_pricing_config()


def get_billing_plan_map() -> dict[str, dict[str, Any]]:
    config = get_pricing_config()
    return {plan["key"]: plan for plan in config["plans"]}


def get_credit_rule_map() -> dict[str, dict[str, Any]]:
    config = get_pricing_config()
    return {rule["eventType"]: rule for rule in config["creditRules"]}


def get_provider_cost_rule_map() -> dict[str, dict[str, Any]]:
    config = get_pricing_config()
    return {rule["eventType"]: rule for rule in config["providerCostRules"]}


def estimate_provider_cost_for_event(event_type: str, quantity: float = 1.0) -> float:
    rules = get_provider_cost_rule_map()
    rule = rules.get(event_type)

    if not rule:
        return 0.0

    try:
        quantity = max(0.0, float(quantity))
    except Exception:
        quantity = 1.0

    return round(float(rule.get("fixedCost") or 0.0) + quantity * float(rule.get("costPerUnit") or 0.0), 6)
