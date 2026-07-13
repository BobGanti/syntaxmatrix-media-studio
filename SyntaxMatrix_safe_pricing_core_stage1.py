from __future__ import annotations

import datetime as dt
import json
import py_compile
import shutil
from decimal import Decimal, ROUND_CEILING
from pathlib import Path

ROOT = Path.cwd()
STAMP = dt.datetime.now().strftime('%Y%m%d_%H%M%S')
BACKUP = ROOT / 'patches' / 'backups' / f'pricing_core_stage1_{STAMP}'

PRICING_JSON = ROOT / 'billing' / 'pricing_config.json'
PRICING_PY = ROOT / 'services' / 'billing_pricing.py'
ACCEPTANCE = ROOT / 'scripts' / 'pricing_core_stage1_acceptance.py'


def stop(message: str) -> None:
    raise SystemExit(f'PRICING CORE STAGE 1 STOPPED: {message}')


def backup(path: Path) -> None:
    if not path.exists():
        stop(f'Missing required file: {path.relative_to(ROOT)}')
    target = BACKUP / path.relative_to(ROOT)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)


for path in (PRICING_JSON, PRICING_PY):
    backup(path)

try:
    current = json.loads(PRICING_JSON.read_text(encoding='utf-8'))
except Exception as exc:
    stop(f'Could not read billing/pricing_config.json: {exc}')

if not isinstance(current, dict):
    stop('billing/pricing_config.json must contain a JSON object')

plans = []
seen = set()
for raw in current.get('plans') or []:
    if not isinstance(raw, dict):
        continue
    key = str(raw.get('key') or '').strip().lower()
    if not key or key in seen:
        continue
    seen.add(key)
    row = dict(raw)
    row['key'] = key
    if key == 'starter':
        row.setdefault('maxCustomVoices', 1)
        row.setdefault('systemVoicesOnly', False)
        row.setdefault('creditPeriod', 'month')
        row.setdefault('enabled', True)
    elif key == 'pro':
        row.setdefault('maxCustomVoices', 3)
        row.setdefault('systemVoicesOnly', False)
        row.setdefault('creditPeriod', 'month')
        row.setdefault('enabled', True)
    elif key == 'business':
        row.setdefault('maxCustomVoices', 10)
        row.setdefault('systemVoicesOnly', False)
        row.setdefault('creditPeriod', 'month')
        row.setdefault('enabled', True)
    elif key == 'enterprise':
        row.setdefault('maxCustomVoices', None)
        row.setdefault('systemVoicesOnly', False)
        row.setdefault('creditPeriod', 'month')
        row.setdefault('enabled', True)
    plans.append(row)

free_plan = {
    'key': 'free',
    'label': 'Free',
    'monthlyPrice': 0.0,
    'monthlyCredits': None,
    'weeklyCredits': 10,
    'description': 'Try narration with system voices. Custom voice cloning is not included.',
    'maxCustomVoices': 0,
    'systemVoicesOnly': True,
    'creditPeriod': 'week',
    'enabled': True,
}

plans = [p for p in plans if p.get('key') != 'free']
plans.insert(0, free_plan)

current['plans'] = plans
current['supplierCurrency'] = 'USD'
current['retailMarkupPercent'] = 100.0
current['retailValuePerCreditUsd'] = 0.005
current['supplierMetering'] = {
    'voiceCloneCostUsd': 0.01,
    'ttsCostUsdPer10000Characters': 0.115,
    'standardPreviewCharacters': 103,
}
current['freePlan'] = {
    'enabled': True,
    'weeklyCredits': 10,
    'resetWeekday': 0,
    'resetHourUtc': 0,
    'resetTimezone': 'UTC',
    'rollover': False,
    'maxCustomVoices': 0,
    'systemVoicesOnly': True,
}

PRICING_JSON.write_text(json.dumps(current, indent=2) + '\n', encoding='utf-8')

module = r'''from __future__ import annotations

import copy
import json
import pathlib
from decimal import Decimal, ROUND_CEILING
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parent.parent
BILLING_DIR = ROOT / "billing"
PRICING_CONFIG_PATH = BILLING_DIR / "pricing_config.json"


DEFAULT_PRICING_CONFIG = {
    "currency": "EUR",
    "supplierCurrency": "USD",
    "retailMarkupPercent": 100.0,
    "retailValuePerCreditUsd": 0.005,
    "supplierMetering": {
        "voiceCloneCostUsd": 0.01,
        "ttsCostUsdPer10000Characters": 0.115,
        "standardPreviewCharacters": 103,
    },
    "freePlan": {
        "enabled": True,
        "weeklyCredits": 10,
        "resetWeekday": 0,
        "resetHourUtc": 0,
        "resetTimezone": "UTC",
        "rollover": False,
        "maxCustomVoices": 0,
        "systemVoicesOnly": True,
    },
    "plans": [
        {
            "key": "free",
            "label": "Free",
            "monthlyPrice": 0.0,
            "monthlyCredits": None,
            "weeklyCredits": 10,
            "description": "Try narration with system voices. Custom voice cloning is not included.",
            "maxCustomVoices": 0,
            "systemVoicesOnly": True,
            "creditPeriod": "week",
            "enabled": True,
        },
        {
            "key": "starter",
            "label": "Starter",
            "monthlyPrice": 9.0,
            "monthlyCredits": 1000,
            "description": "Small team / early usage plan.",
            "maxCustomVoices": 1,
            "systemVoicesOnly": False,
            "creditPeriod": "month",
            "enabled": True,
        },
        {
            "key": "pro",
            "label": "Pro",
            "monthlyPrice": 29.0,
            "monthlyCredits": 5000,
            "description": "Regular narration and voice generation.",
            "maxCustomVoices": 3,
            "systemVoicesOnly": False,
            "creditPeriod": "month",
            "enabled": True,
        },
        {
            "key": "business",
            "label": "Business",
            "monthlyPrice": 99.0,
            "monthlyCredits": 20000,
            "description": "Higher usage with multiple workspaces and users.",
            "maxCustomVoices": 10,
            "systemVoicesOnly": False,
            "creditPeriod": "month",
            "enabled": True,
        },
        {
            "key": "enterprise",
            "label": "Enterprise",
            "monthlyPrice": 0.0,
            "monthlyCredits": None,
            "description": "Contract pricing, limits, and governance.",
            "maxCustomVoices": None,
            "systemVoicesOnly": False,
            "creditPeriod": "month",
            "enabled": True,
        },
    ],
    # Legacy rules remain during Stage 1 so no live metering path changes yet.
    "creditRules": [
        {
            "eventType": "voice.parameter.saved",
            "unit": "event",
            "creditsPerUnit": 25,
            "minimumCredits": 25,
            "description": "Legacy rule retained until the supplier meter is wired.",
        },
        {
            "eventType": "narration.generated",
            "unit": "second",
            "creditsPerUnit": 1,
            "minimumCredits": 1,
            "description": "Legacy rule retained until character metering is wired.",
        },
    ],
    "providerCostRules": [
        {
            "eventType": "voice.parameter.saved",
            "unit": "event",
            "fixedCost": 0.50,
            "costPerUnit": 0.0,
            "description": "Legacy estimate retained until the supplier meter is wired.",
        },
        {
            "eventType": "narration.generated",
            "unit": "second",
            "fixedCost": 0.0,
            "costPerUnit": 0.004,
            "description": "Legacy estimate retained until character metering is wired.",
        },
    ],
}


def _ensure_dir() -> None:
    BILLING_DIR.mkdir(parents=True, exist_ok=True)


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        parsed = float(value)
        return parsed if parsed >= 0 else fallback
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
        return max(0, parsed)
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
    defaults = {
        "free": (0, True, "week"),
        "starter": (1, False, "month"),
        "pro": (3, False, "month"),
        "business": (10, False, "month"),
        "enterprise": (None, False, "month"),
    }
    slots, system_only, period = defaults.get(key, (0, False, "month"))
    return {
        "key": key,
        "label": _safe_text(raw.get("label"), key.title()),
        "monthlyPrice": _safe_float(raw.get("monthlyPrice"), 0.0),
        "monthlyCredits": _safe_int_or_none(raw.get("monthlyCredits")),
        "weeklyCredits": _safe_int_or_none(raw.get("weeklyCredits")),
        "description": _safe_text(raw.get("description")),
        "maxCustomVoices": _safe_int_or_none(raw.get("maxCustomVoices")) if raw.get("maxCustomVoices") is not None else slots,
        "systemVoicesOnly": _safe_bool(raw.get("systemVoicesOnly"), system_only),
        "creditPeriod": _safe_text(raw.get("creditPeriod"), period).lower(),
        "enabled": _safe_bool(raw.get("enabled"), True),
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
        for key in (
            "currency", "supplierCurrency", "retailMarkupPercent",
            "retailValuePerCreditUsd", "supplierMetering", "freePlan",
            "plans", "creditRules", "providerCostRules",
        ):
            if key in raw:
                source[key] = copy.deepcopy(raw[key])

    supplier = dict(DEFAULT_PRICING_CONFIG["supplierMetering"])
    if isinstance(source.get("supplierMetering"), dict):
        supplier.update(source["supplierMetering"])

    free_plan = dict(DEFAULT_PRICING_CONFIG["freePlan"])
    if isinstance(source.get("freePlan"), dict):
        free_plan.update(source["freePlan"])

    return {
        "currency": _safe_text(source.get("currency"), "EUR").upper(),
        "supplierCurrency": _safe_text(source.get("supplierCurrency"), "USD").upper(),
        "retailMarkupPercent": _safe_float(source.get("retailMarkupPercent"), 100.0),
        "retailValuePerCreditUsd": _safe_float(source.get("retailValuePerCreditUsd"), 0.005),
        "supplierMetering": {
            "voiceCloneCostUsd": _safe_float(supplier.get("voiceCloneCostUsd"), 0.01),
            "ttsCostUsdPer10000Characters": _safe_float(supplier.get("ttsCostUsdPer10000Characters"), 0.115),
            "standardPreviewCharacters": int(_safe_float(supplier.get("standardPreviewCharacters"), 103)),
        },
        "freePlan": {
            "enabled": _safe_bool(free_plan.get("enabled"), True),
            "weeklyCredits": int(_safe_float(free_plan.get("weeklyCredits"), 10)),
            "resetWeekday": int(_safe_float(free_plan.get("resetWeekday"), 0)) % 7,
            "resetHourUtc": int(_safe_float(free_plan.get("resetHourUtc"), 0)) % 24,
            "resetTimezone": _safe_text(free_plan.get("resetTimezone"), "UTC"),
            "rollover": _safe_bool(free_plan.get("rollover"), False),
            "maxCustomVoices": int(_safe_float(free_plan.get("maxCustomVoices"), 0)),
            "systemVoicesOnly": _safe_bool(free_plan.get("systemVoicesOnly"), True),
        },
        "plans": [_normalise_plan(item) for item in (source.get("plans") or DEFAULT_PRICING_CONFIG["plans"])],
        "creditRules": [_normalise_credit_rule(item) for item in (source.get("creditRules") or DEFAULT_PRICING_CONFIG["creditRules"])],
        "providerCostRules": [_normalise_provider_cost_rule(item) for item in (source.get("providerCostRules") or DEFAULT_PRICING_CONFIG["providerCostRules"])],
    }


def ensure_pricing_config() -> pathlib.Path:
    _ensure_dir()
    if not PRICING_CONFIG_PATH.exists():
        PRICING_CONFIG_PATH.write_text(json.dumps(DEFAULT_PRICING_CONFIG, indent=2), encoding="utf-8")
    return PRICING_CONFIG_PATH


def get_pricing_config() -> dict[str, Any]:
    ensure_pricing_config()
    try:
        raw = json.loads(PRICING_CONFIG_PATH.read_text(encoding="utf-8"))
        config = normalise_pricing_config(raw if isinstance(raw, dict) else {})
    except Exception as exc:
        print("[billing_pricing] Could not read pricing config:", repr(exc), flush=True)
        config = normalise_pricing_config(DEFAULT_PRICING_CONFIG)
    return {**config, "configPath": str(PRICING_CONFIG_PATH.relative_to(ROOT)).replace("\\", "/")}


def save_pricing_config(raw: dict[str, Any]) -> dict[str, Any]:
    config = normalise_pricing_config(raw)
    _ensure_dir()
    PRICING_CONFIG_PATH.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return get_pricing_config()


def get_billing_plan_map() -> dict[str, dict[str, Any]]:
    return {plan["key"]: plan for plan in get_pricing_config()["plans"]}


def get_credit_rule_map() -> dict[str, dict[str, Any]]:
    return {rule["eventType"]: rule for rule in get_pricing_config()["creditRules"]}


def get_provider_cost_rule_map() -> dict[str, dict[str, Any]]:
    return {rule["eventType"]: rule for rule in get_pricing_config()["providerCostRules"]}


def supplier_cost_usd(event_type: str, quantity: int | float = 1) -> Decimal:
    config = get_pricing_config()
    rates = config["supplierMetering"]
    event_type = _safe_text(event_type).lower()
    qty = Decimal(str(max(0.0, float(quantity or 0))))
    clone = Decimal(str(rates["voiceCloneCostUsd"]))
    per_char = Decimal(str(rates["ttsCostUsdPer10000Characters"])) / Decimal("10000")
    if event_type == "voice.clone.succeeded":
        return (clone * qty).quantize(Decimal("0.0000001"))
    if event_type in {"voice.preview.generated", "narration.generated.characters"}:
        return (per_char * qty).quantize(Decimal("0.0000001"))
    if event_type == "voice.clone.with_preview":
        preview_chars = Decimal(str(rates["standardPreviewCharacters"]))
        return (clone * qty + per_char * preview_chars * qty).quantize(Decimal("0.0000001"))
    return Decimal("0")


def event_economics(event_type: str, quantity: int | float = 1) -> dict[str, Any]:
    config = get_pricing_config()
    supplier = supplier_cost_usd(event_type, quantity)
    markup = Decimal(str(config["retailMarkupPercent"]))
    credit_value = Decimal(str(config["retailValuePerCreditUsd"]))
    retail = (supplier * (Decimal("1") + markup / Decimal("100"))).quantize(Decimal("0.0000001"))
    credits = 0
    if supplier > 0 and credit_value > 0:
        credits = int((retail / credit_value).to_integral_value(rounding=ROUND_CEILING))
    return {
        "eventType": event_type,
        "quantity": float(quantity),
        "supplierCostUsd": float(supplier),
        "retailCostUsd": float(retail),
        "retailMarkupPercent": float(markup),
        "retailValuePerCreditUsd": float(credit_value),
        "credits": credits,
    }


def estimate_provider_cost_for_event(event_type: str, quantity: float = 1.0) -> float:
    # Preserve the existing live estimate during Stage 1. The next guarded
    # stage will switch actual usage events to event_economics().
    rule = get_provider_cost_rule_map().get(event_type)
    if not rule:
        return 0.0
    try:
        quantity = max(0.0, float(quantity))
    except Exception:
        quantity = 1.0
    return round(float(rule.get("fixedCost") or 0.0) + quantity * float(rule.get("costPerUnit") or 0.0), 6)
'''

PRICING_PY.write_text(module, encoding='utf-8')

acceptance = r'''from decimal import Decimal
from services.billing_pricing import event_economics, get_billing_plan_map, get_pricing_config, supplier_cost_usd

config = get_pricing_config()
plans = get_billing_plan_map()

assert config["supplierCurrency"] == "USD"
assert Decimal(str(config["retailValuePerCreditUsd"])) == Decimal("0.005")
assert Decimal(str(config["retailMarkupPercent"])) == Decimal("100.0")
assert plans["free"]["weeklyCredits"] == 10
assert plans["free"]["maxCustomVoices"] == 0
assert plans["free"]["systemVoicesOnly"] is True
assert plans["starter"]["maxCustomVoices"] == 1
assert plans["pro"]["maxCustomVoices"] == 3
assert plans["business"]["maxCustomVoices"] == 10
assert supplier_cost_usd("voice.clone.succeeded", 1) == Decimal("0.0100000")
assert supplier_cost_usd("voice.preview.generated", 103) == Decimal("0.0011845")
assert supplier_cost_usd("narration.generated.characters", 10000) == Decimal("0.1150000")
assert event_economics("voice.clone.with_preview", 1)["credits"] == 5
assert event_economics("narration.generated.characters", 10000)["credits"] == 46
print("PRICING CORE STAGE 1: PASSED")
'''
ACCEPTANCE.parent.mkdir(parents=True, exist_ok=True)
ACCEPTANCE.write_text(acceptance, encoding='utf-8')

py_compile.compile(str(PRICING_PY), doraise=True)
py_compile.compile(str(ACCEPTANCE), doraise=True)

print(f'Backup: {BACKUP.relative_to(ROOT)}')
print('PRICING CORE STAGE 1 PATCH: APPLIED')
