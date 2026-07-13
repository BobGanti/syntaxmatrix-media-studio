from __future__ import annotations

import json
import os
import py_compile
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> None:
    py_compile.compile(
        str(
            ROOT
            / "services"
            / "stripe_price_catalog.py"
        ),
        doraise=True,
    )

    price_map = json.loads(
        (
            ROOT
            / "billing"
            / "stripe_price_map.json"
        ).read_text(encoding="utf-8")
    )

    assert price_map.get("stripeMode") == "live", (
        "Local Stripe catalogue must be live "
        "before production deployment"
    )

    mapping = {
        "starter": "STRIPE_PRICE_STARTER",
        "pro": "STRIPE_PRICE_PRO",
        "business": "STRIPE_PRICE_BUSINESS",
    }

    previous_values = {
        name: os.getenv(name)
        for name in mapping.values()
    }

    previous_key = os.getenv(
        "STRIPE_SECRET_KEY"
    )

    try:
        os.environ[
            "STRIPE_SECRET_KEY"
        ] = "sk_live_acceptance_placeholder"

        for plan_key, environment_name in mapping.items():
            price_id = str(
                price_map
                .get("plans", {})
                .get(plan_key, {})
                .get("priceId", "")
            )

            assert price_id.startswith("price_"), (
                f"Missing live Price ID for {plan_key}"
            )

            os.environ[
                environment_name
            ] = price_id

        from services.stripe_price_catalog import (
            get_stripe_price_for_plan,
        )

        for plan_key in mapping:
            record = get_stripe_price_for_plan(
                plan_key
            )

            assert isinstance(record, dict)
            assert str(
                record.get("priceId", "")
            ).startswith("price_")

            assert (
                record.get("source")
                == "cloud_run_environment"
            )
    finally:
        for name, value in previous_values.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

        if previous_key is None:
            os.environ.pop(
                "STRIPE_SECRET_KEY",
                None,
            )
        else:
            os.environ[
                "STRIPE_SECRET_KEY"
            ] = previous_key

    plans_source = (
        ROOT
        / "frontend"
        / "clone_voice"
        / "plans.js"
    ).read_text(encoding="utf-8")

    assert '["free","starter","pro","business"].includes' in plans_source.replace(" ", "")
    assert "/api/billing/free-plan" in plans_source

    deploy_source = (
        ROOT
        / "scripts"
        / "deploy_production_gate1.sh"
    ).read_text(encoding="utf-8")

    assert (
        "STRIPE_PRICE_STARTER="
        "${STRIPE_PRICE_STARTER}"
        in deploy_source
    )

    assert (
        "STRIPE_PRICE_PRO="
        "${STRIPE_PRICE_PRO}"
        in deploy_source
    )

    assert (
        "STRIPE_PRICE_BUSINESS="
        "${STRIPE_PRICE_BUSINESS}"
        in deploy_source
    )

    print(
        "PAID PLAN RUNTIME CATALOG ACCEPTANCE: PASSED"
    )
    print(
        "Existing live Price IDs: passed"
    )
    print(
        "Cloud Run runtime mapping: passed"
    )
    print(
        "Starter/Pro/Business plan filter: passed"
    )


if __name__ == "__main__":
    main()
