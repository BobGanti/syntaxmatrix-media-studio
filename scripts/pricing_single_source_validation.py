from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]

ALLOWED_FILES = {
    "billing/pricing_config.json",
    "services/billing_pricing.py",
}

ALLOWED_PREFIXES = {
    "docs/",
    "reports/",
    "patches/",
}

SCAN_FILES = [
    "services/admin_client_lifecycle.py",
    "services/stripe_webhooks.py",
    "services/stripe_checkout.py",
    "services/billing_usage.py",
    "services/subscription_enforcement.py",
    "frontend/clone_voice/plans.js",
    "frontend/clone_voice/billing.js",
    "frontend/clone_voice/client_usage.js",
    "frontend/clone_voice/admin.js",
    "app.py",
]

FORBIDDEN_PATTERNS = [
    ("hardcoded_eur_9", re.compile(r"€\s*9\b")),
    ("hardcoded_eur_29", re.compile(r"€\s*29\b")),
    ("hardcoded_eur_99", re.compile(r"€\s*99\b")),
    ("hardcoded_usd_9", re.compile(r"\$\s*9\b")),
    ("hardcoded_usd_29", re.compile(r"\$\s*29\b")),
    ("hardcoded_usd_99", re.compile(r"\$\s*99\b")),
    ("hardcoded_amount_map_900", re.compile(r"\b900\s*:\s*[\"']starter[\"']")),
    ("hardcoded_amount_map_2900", re.compile(r"\b2900\s*:\s*[\"']pro[\"']")),
    ("hardcoded_amount_map_9900", re.compile(r"\b9900\s*:\s*[\"']business[\"']")),
    ("webhook_default_starter", re.compile(r"metadata\.get\([\"']planKey[\"']\)\s+or\s+metadata\.get\([\"']plan[\"']\)\s+or\s+[\"']starter[\"']")),
    ("frontend_non_empty_fallback_plans", re.compile(r"const\s+FALLBACK_PLANS\s*=\s*\[\s*\{", re.S)),
]

def rel(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")

def allowed(path: Path) -> bool:
    rp = rel(path)

    if rp in ALLOWED_FILES:
        return True

    return any(rp.startswith(prefix) for prefix in ALLOWED_PREFIXES)

def main() -> int:
    failures: list[str] = []

    for file in SCAN_FILES:
        path = ROOT / file

        if not path.exists() or allowed(path):
            continue

        text = path.read_text(encoding="utf-8", errors="ignore")

        for name, pattern in FORBIDDEN_PATTERNS:
            if pattern.search(text):
                failures.append(f"{file}: {name}")

    if failures:
        print("PRICING_SINGLE_SOURCE_VALIDATION: FAILED")
        for item in failures:
            print(" -", item)
        return 1

    print("PRICING_SINGLE_SOURCE_VALIDATION: PASSED")
    return 0

# >>> SMX_STAGE2_STRIPE_MAP_GUARDRAIL >>>
def validate_stripe_price_map_provider_ids_only() -> list[str]:
    import json

    failures: list[str] = []
    path = ROOT / "billing" / "stripe_price_map.json"

    if not path.exists():
        failures.append("billing/stripe_price_map.json: missing")
        return failures

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        failures.append(f"billing/stripe_price_map.json: invalid JSON: {exc}")
        return failures

    forbidden_keys = {
        "unitAmount",
        "unit_amount",
        "amount",
        "monthlyPrice",
        "monthly_price",
        "weeklyCredits",
        "weekly_credits",
        "monthlyCredits",
        "monthly_credits",
        "cloneSlots",
        "clone_slots",
        "maxCustomVoices",
        "retailValuePerCreditUsd",
        "retailUsdPerCredit",
        "retailMarkupPercent",
        "voiceCloneCostUsd",
        "ttsCostPer10000CharactersUsd",
        "ttsCostUsdPer10000Characters",
    }

    allowed_top_keys = {"stripeMode", "freePlanHandledBy", "plans"}
    allowed_plan_record_keys = {"priceId"}

    def walk(node, path_label):
        if isinstance(node, dict):
            for key, value in node.items():
                if key in forbidden_keys:
                    failures.append(f"billing/stripe_price_map.json:{path_label}.{key}: forbidden business value key")

                walk(value, f"{path_label}.{key}")

    walk(data, "$")

    extra_top = set(data.keys()) - allowed_top_keys

    if extra_top:
        failures.append(
            "billing/stripe_price_map.json: unexpected top-level keys: "
            + ", ".join(sorted(extra_top))
        )

    plans = data.get("plans")

    if not isinstance(plans, dict):
        failures.append("billing/stripe_price_map.json: plans must be an object")
        return failures

    for plan_key, record in plans.items():
        if not isinstance(record, dict):
            failures.append(f"billing/stripe_price_map.json: plans.{plan_key} must be an object")
            continue

        extra = set(record.keys()) - allowed_plan_record_keys

        if extra:
            failures.append(
                f"billing/stripe_price_map.json: plans.{plan_key} has non-provider keys: "
                + ", ".join(sorted(extra))
            )

        price_id = str(record.get("priceId") or "").strip()

        if not price_id.startswith("price_"):
            failures.append(f"billing/stripe_price_map.json: plans.{plan_key}.priceId must start with price_")

    raw = path.read_text(encoding="utf-8")

    for forbidden in [
        '"unitAmount"',
        '"monthlyPrice"',
        '"monthlyCredits"',
        '"weeklyCredits"',
        '"cloneSlots"',
        ': 900',
        ': 2900',
        ': 9900',
        '€9',
        '€29',
        '€99',
    ]:
        if forbidden in raw:
            failures.append(f"billing/stripe_price_map.json contains forbidden literal {forbidden}")

    return failures


_original_main = main


def main() -> int:
    failures = validate_stripe_price_map_provider_ids_only()

    original_failures: list[str] = []

    for file in SCAN_FILES:
        path = ROOT / file

        if not path.exists() or allowed(path):
            continue

        text = path.read_text(encoding="utf-8", errors="ignore")

        for name, pattern in FORBIDDEN_PATTERNS:
            if pattern.search(text):
                original_failures.append(f"{file}: {name}")

    failures.extend(original_failures)

    if failures:
        print("PRICING_SINGLE_SOURCE_VALIDATION: FAILED")
        for item in failures:
            print(" -", item)
        return 1

    print("PRICING_SINGLE_SOURCE_VALIDATION: PASSED")
    return 0
# <<< SMX_STAGE2_STRIPE_MAP_GUARDRAIL >>>


if __name__ == "__main__":
    raise SystemExit(main())
