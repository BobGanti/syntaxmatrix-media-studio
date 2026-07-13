from __future__ import annotations

import copy
import json
import os
import pathlib
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parent.parent
BILLING_DIR = ROOT / "billing"
PRICING_CONFIG_PATH = BILLING_DIR / "pricing_config.json"
PRICING_OBJECT_KEY = "configuration/billing/pricing_config.json"


DEFAULT_PRICING_CONFIG = {
    "currency": "EUR",
    "supplierCurrency": "USD",
    "metering": {
        "voiceCloneCostUsd": 0.01,
        "ttsCostPer10000CharactersUsd": 0.115,
        "retailMarkupPercent": 100.0,
        "retailValuePerCreditUsd": 0.005,
    },
    "freePlan": {
        "weeklyCredits": 10,
        "resetWeekday": 0,
        "resetHourUtc": 0,
        "rollover": False,
    },
    "plans": [
        {
            "key": "free",
            "label": "Free",
            "monthlyPrice": 0.0,
            "monthlyCredits": 10,
            "weeklyCredits": 10,
            "creditPeriod": "weekly",
            "cloneSlots": 0,
            "systemVoicesOnly": True,
            "enabled": True,
            "description": "Small weekly allowance using system voices only.",
        },
        {
            "key": "starter",
            "label": "Starter",
            "monthlyPrice": 9.0,
            "monthlyCredits": 1000,
            "weeklyCredits": None,
            "creditPeriod": "monthly",
            "cloneSlots": 1,
            "systemVoicesOnly": False,
            "enabled": True,
            "description": "Small team / early usage plan.",
        },
        {
            "key": "pro",
            "label": "Pro",
            "monthlyPrice": 29.0,
            "monthlyCredits": 5000,
            "weeklyCredits": None,
            "creditPeriod": "monthly",
            "cloneSlots": 3,
            "systemVoicesOnly": False,
            "enabled": True,
            "description": "Regular narration and voice generation.",
        },
        {
            "key": "business",
            "label": "Business",
            "monthlyPrice": 99.0,
            "monthlyCredits": 20000,
            "weeklyCredits": None,
            "creditPeriod": "monthly",
            "cloneSlots": 10,
            "systemVoicesOnly": False,
            "enabled": True,
            "description": "Higher usage with multiple workspaces and users.",
        },
        {
            "key": "enterprise",
            "label": "Enterprise",
            "monthlyPrice": 0.0,
            "monthlyCredits": None,
            "weeklyCredits": None,
            "creditPeriod": "monthly",
            "cloneSlots": None,
            "systemVoicesOnly": False,
            "enabled": True,
            "description": "Contract pricing, limits, and governance.",
        },
    ],
}


def _ensure_dir() -> None:
    BILLING_DIR.mkdir(parents=True, exist_ok=True)


def _decimal(value: Any, fallback: str = "0") -> Decimal:
    try:
        parsed = Decimal(str(value))
        if not parsed.is_finite() or parsed < 0:
            return Decimal(fallback)
        return parsed
    except (InvalidOperation, ValueError, TypeError):
        return Decimal(fallback)


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    return float(_decimal(value, str(fallback)))


def _safe_int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if text == "" or text.lower() in {"none", "null", "unlimited"}:
        return None
    try:
        return max(0, int(Decimal(text)))
    except Exception:
        return None


def _safe_bool(value: Any, fallback: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return fallback
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return fallback


def _safe_text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


def _normalise_plan(raw: dict[str, Any]) -> dict[str, Any]:
    key = _safe_text(raw.get("key")).lower()
    if not key:
        raise ValueError("Plan key is required")

    credit_period = _safe_text(raw.get("creditPeriod"), "weekly" if key == "free" else "monthly").lower()
    if credit_period not in {"weekly", "monthly"}:
        credit_period = "monthly"

    clone_slots = _safe_int_or_none(raw.get("cloneSlots"))
    if key == "free":
        clone_slots = 0

    weekly_credits = _safe_int_or_none(raw.get("weeklyCredits"))
    monthly_credits = _safe_int_or_none(raw.get("monthlyCredits"))

    if key == "free" and weekly_credits is None:
        weekly_credits = monthly_credits if monthly_credits is not None else 10
    if key == "free":
        monthly_credits = weekly_credits

    return {
        "key": key,
        "label": _safe_text(raw.get("label"), key.title()),
        "monthlyPrice": _safe_float(raw.get("monthlyPrice"), 0.0),
        "monthlyCredits": monthly_credits,
        "weeklyCredits": weekly_credits,
        "creditPeriod": credit_period,
        "cloneSlots": clone_slots,
        "systemVoicesOnly": True if key == "free" else _safe_bool(raw.get("systemVoicesOnly"), False),
        "enabled": _safe_bool(raw.get("enabled"), True),
        "description": _safe_text(raw.get("description")),
    }


def _legacy_metering(raw: dict[str, Any]) -> dict[str, Any]:
    provider_rules = raw.get("providerCostRules") if isinstance(raw, dict) else None
    voice_cost = Decimal("0.01")
    tts_cost = Decimal("0.115")

    if isinstance(provider_rules, list):
        for rule in provider_rules:
            if not isinstance(rule, dict):
                continue
            event_type = _safe_text(rule.get("eventType"))
            if event_type == "voice.parameter.saved":
                candidate = _decimal(rule.get("fixedCost"), "0.01")
                if candidate > 0:
                    voice_cost = candidate
            elif event_type == "narration.generated":
                candidate = _decimal(rule.get("costPerUnit"), "0")
                if candidate > 0:
                    tts_cost = candidate * Decimal("10000")

    return {
        "voiceCloneCostUsd": float(voice_cost),
        "ttsCostPer10000CharactersUsd": float(tts_cost),
        "retailMarkupPercent": 100.0,
        "retailValuePerCreditUsd": 0.005,
    }


def normalise_pricing_config(raw: dict[str, Any]) -> dict[str, Any]:
    source = copy.deepcopy(DEFAULT_PRICING_CONFIG)
    if isinstance(raw, dict):
        source.update({k: v for k, v in raw.items() if k in {"currency", "supplierCurrency", "metering", "freePlan", "plans"}})

    plans = source.get("plans") or DEFAULT_PRICING_CONFIG["plans"]
    normalised_plans = [_normalise_plan(item) for item in plans if isinstance(item, dict)]
    plan_map = {plan["key"]: plan for plan in normalised_plans}

    for default in DEFAULT_PRICING_CONFIG["plans"]:
        if default["key"] not in plan_map:
            normalised_plans.append(_normalise_plan(default))

    metering_source = source.get("metering")
    if not isinstance(metering_source, dict):
        metering_source = _legacy_metering(raw if isinstance(raw, dict) else {})

    free_source = source.get("freePlan") if isinstance(source.get("freePlan"), dict) else {}
    free_plan = next(plan for plan in normalised_plans if plan["key"] == "free")
    weekly_credits = _safe_int_or_none(free_source.get("weeklyCredits"))
    if weekly_credits is None:
        weekly_credits = free_plan.get("weeklyCredits") or 10
    free_plan["weeklyCredits"] = weekly_credits
    free_plan["monthlyCredits"] = weekly_credits

    reset_weekday = _safe_int_or_none(free_source.get("resetWeekday"))
    reset_hour = _safe_int_or_none(free_source.get("resetHourUtc"))

    config = {
        "currency": _safe_text(source.get("currency"), "EUR").upper(),
        "supplierCurrency": _safe_text(source.get("supplierCurrency"), "USD").upper(),
        "metering": {
            "voiceCloneCostUsd": _safe_float(metering_source.get("voiceCloneCostUsd"), 0.01),
            "ttsCostPer10000CharactersUsd": _safe_float(metering_source.get("ttsCostPer10000CharactersUsd"), 0.115),
            "retailMarkupPercent": _safe_float(metering_source.get("retailMarkupPercent"), 100.0),
            "retailValuePerCreditUsd": max(0.00000001, _safe_float(metering_source.get("retailValuePerCreditUsd"), 0.005)),
        },
        "freePlan": {
            "weeklyCredits": weekly_credits,
            "resetWeekday": min(6, max(0, 0 if reset_weekday is None else reset_weekday)),
            "resetHourUtc": min(23, max(0, 0 if reset_hour is None else reset_hour)),
            "rollover": False,
        },
        "plans": normalised_plans,
    }

    # Compatibility payloads for existing consumers. New calculations do not
    # use seconds or fixed placeholder credit rules.
    clone = config["metering"]["voiceCloneCostUsd"]
    tts_per_char = config["metering"]["ttsCostPer10000CharactersUsd"] / 10000.0
    config["creditRules"] = [
        {"eventType": "voice.clone.succeeded", "unit": "event", "description": "Successful customer voice enrolment."},
        {"eventType": "voice.preview.generated", "unit": "character", "description": "Standard preview narration characters."},
        {"eventType": "narration.generated", "unit": "character", "description": "Submitted narration characters."},
    ]
    config["providerCostRules"] = [
        {"eventType": "voice.clone.succeeded", "unit": "event", "fixedCost": clone, "costPerUnit": 0.0},
        {"eventType": "voice.preview.generated", "unit": "character", "fixedCost": 0.0, "costPerUnit": tts_per_char},
        {"eventType": "narration.generated", "unit": "character", "fixedCost": 0.0, "costPerUnit": tts_per_char},
    ]
    return config


def _read_durable_config() -> dict[str, Any] | None:
    if str(os.getenv("OBJECT_STORAGE_BACKEND") or "").strip().lower() != "gcs":
        return None
    try:
        from services.object_storage import get_object_storage
        storage = get_object_storage()
        if not storage.exists(PRICING_OBJECT_KEY):
            return None
        data = json.loads(storage.read_bytes(PRICING_OBJECT_KEY).decode("utf-8"))
        return data if isinstance(data, dict) else None
    except Exception as exc:
        print("[billing_pricing] Could not read durable pricing config:", repr(exc), flush=True)
        return None


def _write_durable_config(config: dict[str, Any]) -> bool:
    if str(os.getenv("OBJECT_STORAGE_BACKEND") or "").strip().lower() != "gcs":
        return False
    try:
        from services.object_storage import get_object_storage
        get_object_storage().save_bytes(
            PRICING_OBJECT_KEY,
            json.dumps(config, indent=2).encode("utf-8"),
            content_type="application/json",
        )
        return True
    except Exception as exc:
        raise RuntimeError(f"Could not persist pricing configuration to GCS: {exc}") from exc


def ensure_pricing_config() -> pathlib.Path:
    _ensure_dir()
    if not PRICING_CONFIG_PATH.exists():
        PRICING_CONFIG_PATH.write_text(json.dumps(DEFAULT_PRICING_CONFIG, indent=2), encoding="utf-8")
    return PRICING_CONFIG_PATH


def get_pricing_config() -> dict[str, Any]:
    ensure_pricing_config()
    durable = _read_durable_config()
    source_name = PRICING_OBJECT_KEY if durable is not None else str(PRICING_CONFIG_PATH.relative_to(ROOT)).replace("\\", "/")
    try:
        raw = durable if durable is not None else json.loads(PRICING_CONFIG_PATH.read_text(encoding="utf-8"))
        config = normalise_pricing_config(raw if isinstance(raw, dict) else DEFAULT_PRICING_CONFIG)
    except Exception as exc:
        print("[billing_pricing] Could not read pricing config:", repr(exc), flush=True)
        config = normalise_pricing_config(DEFAULT_PRICING_CONFIG)
    return {**config, "configPath": source_name, "durable": durable is not None}


def save_pricing_config(raw: dict[str, Any]) -> dict[str, Any]:
    config = normalise_pricing_config(raw)
    _ensure_dir()
    # In production, persist to GCS first. A failed durable write must not leave
    # one Cloud Run instance using a local-only configuration.
    durable = _write_durable_config(config)
    PRICING_CONFIG_PATH.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return {**config, "configPath": PRICING_OBJECT_KEY if durable else str(PRICING_CONFIG_PATH.relative_to(ROOT)).replace("\\", "/"), "durable": durable}


def get_billing_plan_map() -> dict[str, dict[str, Any]]:
    return {plan["key"]: plan for plan in get_pricing_config()["plans"]}


def get_credit_rule_map() -> dict[str, dict[str, Any]]:
    return {rule["eventType"]: rule for rule in get_pricing_config()["creditRules"]}


def get_provider_cost_rule_map() -> dict[str, dict[str, Any]]:
    return {rule["eventType"]: rule for rule in get_pricing_config()["providerCostRules"]}


def _canonical_event_type(event_type: str) -> str:
    value = _safe_text(event_type)
    aliases = {
        "voice.parameter.saved": "voice.clone.succeeded",
        "voice.clone.created": "voice.clone.succeeded",
        "preview.generated": "voice.preview.generated",
    }
    return aliases.get(value, value)


def calculate_event_pricing(event_type: str, quantity: float = 1.0) -> dict[str, Any]:
    config = get_pricing_config()
    metering = config["metering"]
    canonical = _canonical_event_type(event_type)
    qty = _decimal(quantity, "0")

    if canonical == "voice.clone.succeeded":
        supplier = _decimal(metering["voiceCloneCostUsd"], "0.01") * max(Decimal("0"), qty)
        unit = "event"
    elif canonical in {"voice.preview.generated", "narration.generated"}:
        supplier = (_decimal(metering["ttsCostPer10000CharactersUsd"], "0.115") * max(Decimal("0"), qty)) / Decimal("10000")
        unit = "character"
    else:
        supplier = Decimal("0")
        unit = "event"

    markup = _decimal(metering["retailMarkupPercent"], "100")
    credit_value = _decimal(metering["retailValuePerCreditUsd"], "0.005")
    if credit_value <= 0:
        credit_value = Decimal("0.005")

    retail = supplier * (Decimal("1") + markup / Decimal("100"))
    credits = 0
    if retail > 0:
        credits = int((retail / credit_value).to_integral_value(rounding=ROUND_CEILING))

    def exact(value: Decimal) -> str:
        return format(value.quantize(Decimal("0.0000000001")), "f")

    return {
        "eventType": canonical,
        "quantity": float(qty),
        "unit": unit,
        "supplierCostUsd": float(supplier),
        "supplierCostUsdExact": exact(supplier),
        "retailCostUsd": float(retail),
        "retailCostUsdExact": exact(retail),
        "credits": credits,
        "markupPercent": float(markup),
        "creditValueUsd": float(credit_value),
        "voiceCloneCostUsd": float(_decimal(metering["voiceCloneCostUsd"], "0.01")),
        "ttsCostPer10000CharactersUsd": float(_decimal(metering["ttsCostPer10000CharactersUsd"], "0.115")),
    }


def estimate_provider_cost_for_event(event_type: str, quantity: float = 1.0) -> float:
    return round(float(calculate_event_pricing(event_type, quantity)["supplierCostUsd"]), 10)


def estimate_credits_for_event(event_type: str, quantity: float = 1.0) -> int:
    return int(calculate_event_pricing(event_type, quantity)["credits"])

# >>> SMX_SAFE_PRICING_CORE_REPAIR >>>
# Safe runtime pricing repair. Appended instead of replacing the module so existing imports remain compatible.
from decimal import Decimal as _SMX_Decimal, ROUND_CEILING as _SMX_ROUND_CEILING

_SMX_ORIGINAL_GET_PRICING_CONFIG = get_pricing_config


def _smx_decimal(value, fallback="0"):
    try:
        value = _SMX_Decimal(str(value))
        if value.is_finite() and value >= 0:
            return value
    except Exception:
        pass
    return _SMX_Decimal(str(fallback))


def _smx_read_pricing_json():
    try:
        raw = json.loads(PRICING_CONFIG_PATH.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def _smx_default_supplier_rules(raw):
    supplier = raw.get("supplierMetering") if isinstance(raw.get("supplierMetering"), dict) else {}
    clone_cost = _smx_decimal(supplier.get("voiceCloneCostUsd"), "0.01")
    tts_per_10k = _smx_decimal(supplier.get("ttsCostUsdPer10000Characters"), "0.115")
    per_char = tts_per_10k / _SMX_Decimal("10000")

    return [
        {"eventType": "voice.clone.succeeded", "unit": "event", "fixedCostUsd": float(clone_cost), "costPerUnitUsd": 0.0, "description": "Qwen voice enrollment after a successful custom voice clone."},
        {"eventType": "voice.preview.generated", "unit": "character", "fixedCostUsd": 0.0, "costPerUnitUsd": float(per_char), "description": "Qwen TTS preview narration, billed by submitted character."},
        {"eventType": "narration.generated", "unit": "character", "fixedCostUsd": 0.0, "costPerUnitUsd": float(per_char), "description": "Qwen TTS script narration, billed by submitted character."},
    ]


def get_pricing_config():
    base = {}

    try:
        base = _SMX_ORIGINAL_GET_PRICING_CONFIG()
    except Exception:
        base = {}

    raw = _smx_read_pricing_json()
    merged = dict(base if isinstance(base, dict) else {})

    for key in (
        "currency",
        "supplierCurrency",
        "retailMarkupPercent",
        "retailUsdPerCredit",
        "retailValuePerCreditUsd",
        "supplierMetering",
        "freePlan",
        "plans",
        "supplierCostRules",
        "creditRules",
        "providerCostRules",
    ):
        if key in raw:
            merged[key] = raw[key]

    if "retailUsdPerCredit" not in merged and "retailValuePerCreditUsd" in merged:
        merged["retailUsdPerCredit"] = merged["retailValuePerCreditUsd"]

    if "retailValuePerCreditUsd" not in merged and "retailUsdPerCredit" in merged:
        merged["retailValuePerCreditUsd"] = merged["retailUsdPerCredit"]

    if not merged.get("supplierCostRules"):
        merged["supplierCostRules"] = _smx_default_supplier_rules(merged)

    return merged


def save_pricing_config(raw):
    config = dict(raw or {})
    PRICING_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    PRICING_CONFIG_PATH.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return get_pricing_config()


def get_billing_plan_map():
    config = get_pricing_config()
    return {
        plan["key"]: plan
        for plan in config.get("plans", [])
        if isinstance(plan, dict) and plan.get("key")
    }


def get_credit_rule_map():
    config = get_pricing_config()
    return {
        rule["eventType"]: rule
        for rule in config.get("creditRules", [])
        if isinstance(rule, dict) and rule.get("eventType")
    }


def get_provider_cost_rule_map():
    config = get_pricing_config()
    return {
        rule["eventType"]: rule
        for rule in config.get("providerCostRules", [])
        if isinstance(rule, dict) and rule.get("eventType")
    }


def get_supplier_cost_rule_map():
    config = get_pricing_config()
    return {
        rule["eventType"]: rule
        for rule in config.get("supplierCostRules", [])
        if isinstance(rule, dict) and rule.get("eventType")
    }


def calculate_event_charge(event_type, quantity=1):
    event_type = str(event_type or "").strip()
    quantity_decimal = _smx_decimal(quantity, "0")
    rule = get_supplier_cost_rule_map().get(event_type)

    fixed = _SMX_Decimal("0")
    per_unit = _SMX_Decimal("0")
    unit = "event"

    if rule:
        fixed = _smx_decimal(rule.get("fixedCostUsd", rule.get("fixedCost", 0)), "0")
        per_unit = _smx_decimal(rule.get("costPerUnitUsd", rule.get("costPerUnit", 0)), "0")
        unit = str(rule.get("unit") or "event")

    supplier_cost = fixed + (quantity_decimal * per_unit)
    config = get_pricing_config()
    markup = _smx_decimal(config.get("retailMarkupPercent"), "100")
    credit_value = _smx_decimal(
        config.get("retailUsdPerCredit", config.get("retailValuePerCreditUsd")),
        "0.005",
    )

    if credit_value <= 0:
        credit_value = _SMX_Decimal("0.005")

    retail_cost = supplier_cost * (_SMX_Decimal("1") + markup / _SMX_Decimal("100"))
    credits = 0 if retail_cost <= 0 else int(
        (retail_cost / credit_value).to_integral_value(rounding=_SMX_ROUND_CEILING)
    )

    return {
        "eventType": event_type,
        "unit": unit,
        "quantity": float(quantity_decimal),
        "supplierCostUsd": float(supplier_cost),
        "supplierCostUsdExact": format(supplier_cost, "f"),
        "retailCostUsd": float(retail_cost),
        "retailCostUsdExact": format(retail_cost, "f"),
        "credits": credits,
        "rateSnapshot": {
            "fixedCostUsd": float(fixed),
            "costPerUnitUsd": float(per_unit),
            "retailMarkupPercent": float(markup),
            "retailUsdPerCredit": float(credit_value),
            "retailValuePerCreditUsd": float(credit_value),
        },
    }


def calculate_metered_usage(event_type, quantity=1):
    return calculate_event_charge(event_type, quantity)


def estimate_provider_cost_for_event(event_type, quantity=1.0):
    return float(calculate_event_charge(event_type, quantity)["supplierCostUsd"])
# <<< SMX_SAFE_PRICING_CORE_REPAIR <<<

# >>> SMX_PRICING_COMPAT_ALIASES >>>
# Compatibility aliases for acceptance scripts and older billing code.
def event_economics(event_type, quantity=1):
    charge = calculate_event_charge(event_type, quantity)

    supplier_exact = charge.get("supplierCostUsdExact", charge.get("supplierCostUsd", 0))
    retail_exact = charge.get("retailCostUsdExact", charge.get("retailCostUsd", 0))

    try:
        supplier_decimal = _smx_decimal(supplier_exact, "0")
    except Exception:
        supplier_decimal = supplier_exact

    try:
        retail_decimal = _smx_decimal(retail_exact, "0")
    except Exception:
        retail_decimal = retail_exact

    result = dict(charge)
    result.update(
        {
            "supplier_cost_usd": supplier_decimal,
            "retail_cost_usd": retail_decimal,
            "credit_count": int(charge.get("credits") or 0),
            "credits_charged": int(charge.get("credits") or 0),
            "quantity": charge.get("quantity", quantity),
        }
    )
    return result


def supplier_cost_usd(event_type, quantity=1):
    charge = calculate_event_charge(event_type, quantity)
    return _smx_decimal(charge.get("supplierCostUsdExact", charge.get("supplierCostUsd", 0)), "0")


def retail_cost_usd(event_type, quantity=1):
    charge = calculate_event_charge(event_type, quantity)
    return _smx_decimal(charge.get("retailCostUsdExact", charge.get("retailCostUsd", 0)), "0")


def credits_for_event(event_type, quantity=1):
    return int(calculate_event_charge(event_type, quantity).get("credits") or 0)
# <<< SMX_PRICING_COMPAT_ALIASES <<<

# >>> SMX_LEGACY_EVENT_NAME_ALIASES >>>
# Compatibility for older acceptance scripts and old event naming.
_SMX_ORIGINAL_CALCULATE_EVENT_CHARGE_FOR_ALIASES = calculate_event_charge

_SMX_EVENT_NAME_ALIASES = {
    "narration.generated.characters": "narration.generated",
    "script.narration.generated.characters": "narration.generated",
    "voice.preview.generated.characters": "voice.preview.generated",
    "preview.generated.characters": "voice.preview.generated",
    "voice.clone.succeeded.count": "voice.clone.succeeded",
    "voice.enrollment.succeeded": "voice.clone.succeeded",
    "voice.enrollment.succeeded.count": "voice.clone.succeeded",
}


def _smx_normalise_event_type(event_type):
    key = str(event_type or "").strip()
    return _SMX_EVENT_NAME_ALIASES.get(key, key)


def calculate_event_charge(event_type, quantity=1):
    return _SMX_ORIGINAL_CALCULATE_EVENT_CHARGE_FOR_ALIASES(
        _smx_normalise_event_type(event_type),
        quantity,
    )


def calculate_metered_usage(event_type, quantity=1):
    return calculate_event_charge(event_type, quantity)


def estimate_provider_cost_for_event(event_type, quantity=1.0):
    return float(calculate_event_charge(event_type, quantity)["supplierCostUsd"])


def event_economics(event_type, quantity=1):
    charge = calculate_event_charge(event_type, quantity)

    supplier_exact = charge.get("supplierCostUsdExact", charge.get("supplierCostUsd", 0))
    retail_exact = charge.get("retailCostUsdExact", charge.get("retailCostUsd", 0))

    result = dict(charge)
    result.update(
        {
            "supplier_cost_usd": _smx_decimal(supplier_exact, "0"),
            "retail_cost_usd": _smx_decimal(retail_exact, "0"),
            "credit_count": int(charge.get("credits") or 0),
            "credits_charged": int(charge.get("credits") or 0),
            "quantity": charge.get("quantity", quantity),
        }
    )
    return result


def supplier_cost_usd(event_type, quantity=1):
    charge = calculate_event_charge(event_type, quantity)
    return _smx_decimal(
        charge.get("supplierCostUsdExact", charge.get("supplierCostUsd", 0)),
        "0",
    )


def retail_cost_usd(event_type, quantity=1):
    charge = calculate_event_charge(event_type, quantity)
    return _smx_decimal(
        charge.get("retailCostUsdExact", charge.get("retailCostUsd", 0)),
        "0",
    )


def credits_for_event(event_type, quantity=1):
    return int(calculate_event_charge(event_type, quantity).get("credits") or 0)
# <<< SMX_LEGACY_EVENT_NAME_ALIASES <<<

# >>> SMX_COMPOSITE_CLONE_PREVIEW_EVENT >>>
# Composite compatibility event:
# voice.clone.with_preview = one successful Qwen voice enrollment + one standard preview generation.
_SMX_PRE_COMPOSITE_CALCULATE_EVENT_CHARGE = calculate_event_charge

_SMX_COMPOSITE_EVENTS = {
    "voice.clone.with_preview",
    "voice.parameter.saved",
}


def _smx_credit_value_decimal():
    config = get_pricing_config()
    value = config.get("retailUsdPerCredit", config.get("retailValuePerCreditUsd", "0.005"))
    parsed = _smx_decimal(value, "0.005")
    return parsed if parsed > 0 else _SMX_Decimal("0.005")


def _smx_standard_preview_characters():
    config = get_pricing_config()
    supplier = config.get("supplierMetering") if isinstance(config.get("supplierMetering"), dict) else {}

    try:
        value = int(float(supplier.get("standardPreviewCharacters", 103)))
        return max(0, value)
    except Exception:
        return 103


def calculate_event_charge(event_type, quantity=1):
    event_key = _smx_normalise_event_type(event_type)

    if event_key not in _SMX_COMPOSITE_EVENTS:
        return _SMX_PRE_COMPOSITE_CALCULATE_EVENT_CHARGE(event_key, quantity)

    qty = _smx_decimal(quantity, "1")
    if qty <= 0:
        qty = _smx_decimal("1", "1")

    preview_chars = _smx_decimal(_smx_standard_preview_characters(), "103") * qty

    clone = _SMX_PRE_COMPOSITE_CALCULATE_EVENT_CHARGE("voice.clone.succeeded", qty)
    preview = _SMX_PRE_COMPOSITE_CALCULATE_EVENT_CHARGE("voice.preview.generated", preview_chars)

    supplier = _smx_decimal(clone.get("supplierCostUsdExact", clone.get("supplierCostUsd", 0)), "0") + _smx_decimal(preview.get("supplierCostUsdExact", preview.get("supplierCostUsd", 0)), "0")
    retail = _smx_decimal(clone.get("retailCostUsdExact", clone.get("retailCostUsd", 0)), "0") + _smx_decimal(preview.get("retailCostUsdExact", preview.get("retailCostUsd", 0)), "0")

    config = get_pricing_config()
    credit_value = _smx_decimal(
        config.get("retailUsdPerCredit", config.get("retailValuePerCreditUsd")),
        "0.005",
    )
    if credit_value <= 0:
        credit_value = _smx_decimal("0.005", "0.005")

    credits = 0 if retail <= 0 else int(
        (retail / credit_value).to_integral_value(rounding=_SMX_ROUND_CEILING)
    )

    return {
        "eventType": str(event_type or event_key),
        "unit": "event",
        "quantity": float(qty),
        "supplierCostUsd": float(supplier),
        "supplierCostUsdExact": format(supplier, "f"),
        "retailCostUsd": float(retail),
        "retailCostUsdExact": format(retail, "f"),
        "credits": credits,
        "components": {
            "voice.clone.succeeded": clone,
            "voice.preview.generated": preview,
        },
        "rateSnapshot": {
            "standardPreviewCharacters": int(preview_chars / qty) if qty else _smx_standard_preview_characters(),
            "retailUsdPerCredit": float(credit_value),
            "retailValuePerCreditUsd": float(credit_value),
        },
    }


def calculate_metered_usage(event_type, quantity=1):
    return calculate_event_charge(event_type, quantity)


def estimate_provider_cost_for_event(event_type, quantity=1.0):
    return float(calculate_event_charge(event_type, quantity)["supplierCostUsd"])


def event_economics(event_type, quantity=1):
    charge = calculate_event_charge(event_type, quantity)

    result = dict(charge)
    result.update(
        {
            "supplier_cost_usd": _smx_decimal(
                charge.get("supplierCostUsdExact", charge.get("supplierCostUsd", 0)),
                "0",
            ),
            "retail_cost_usd": _smx_decimal(
                charge.get("retailCostUsdExact", charge.get("retailCostUsd", 0)),
                "0",
            ),
            "credit_count": int(charge.get("credits") or 0),
            "credits_charged": int(charge.get("credits") or 0),
        }
    )
    return result


def supplier_cost_usd(event_type, quantity=1):
    charge = calculate_event_charge(event_type, quantity)
    return _smx_decimal(
        charge.get("supplierCostUsdExact", charge.get("supplierCostUsd", 0)),
        "0",
    )


def retail_cost_usd(event_type, quantity=1):
    charge = calculate_event_charge(event_type, quantity)
    return _smx_decimal(
        charge.get("retailCostUsdExact", charge.get("retailCostUsd", 0)),
        "0",
    )


def credits_for_event(event_type, quantity=1):
    return int(calculate_event_charge(event_type, quantity).get("credits") or 0)
# <<< SMX_COMPOSITE_CLONE_PREVIEW_EVENT <<<
