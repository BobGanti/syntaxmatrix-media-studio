from __future__ import annotations

import os
import py_compile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    os.environ["OBJECT_STORAGE_BACKEND"] = "local"
    os.environ["PERSISTENCE_BACKEND"] = "json"

    for relative in [
        "services/billing_pricing.py",
        "services/billing_usage.py",
        "services/subscription_enforcement.py",
        "services/customer_workspace.py",
        "services/clone_voice_workspace.py",
        "services/stripe_webhooks.py",
        "services/stripe_checkout.py",
        "controllers/clone_voice_controller.py",
    ]:
        py_compile.compile(str(ROOT / relative), doraise=True)

    from services.billing_pricing import calculate_event_pricing, get_pricing_config
    from services.billing_usage import estimate_voice_creation_credits, estimate_narration_credits_from_text
    from services.clone_voice_workspace import STANDARD_VOICE_PREVIEW_TEXT

    config = get_pricing_config()
    plans = {p["key"]: p for p in config["plans"]}
    assert config["metering"]["voiceCloneCostUsd"] == 0.01
    assert config["metering"]["ttsCostPer10000CharactersUsd"] == 0.115
    assert config["metering"]["retailMarkupPercent"] == 100.0
    assert config["metering"]["retailValuePerCreditUsd"] == 0.005
    assert plans["free"]["weeklyCredits"] == 10
    assert plans["free"]["cloneSlots"] == 0
    assert plans["free"]["systemVoicesOnly"] is True
    assert plans["starter"]["cloneSlots"] == 1
    assert plans["pro"]["cloneSlots"] == 3
    assert plans["business"]["cloneSlots"] == 10

    clone = calculate_event_pricing("voice.clone.succeeded", 1)
    preview = calculate_event_pricing("voice.preview.generated", len(STANDARD_VOICE_PREVIEW_TEXT))
    narration = calculate_event_pricing("narration.generated", 10000)

    assert clone["supplierCostUsdExact"] == "0.0100000000"
    assert clone["credits"] == 4
    assert preview["credits"] == 1
    assert narration["supplierCostUsdExact"] == "0.1150000000"
    assert narration["credits"] == 46
    assert estimate_voice_creation_credits(STANDARD_VOICE_PREVIEW_TEXT) == 5
    assert estimate_narration_credits_from_text("x" * 10000) == 46

    # Normalisation must preserve the hard Free-plan restriction even if an
    # invalid admin payload attempts to enable private cloning.
    from services.billing_pricing import normalise_pricing_config
    invalid_free = normalise_pricing_config({
        **config,
        "plans": [
            {**item, "cloneSlots": 99, "systemVoicesOnly": False}
            if item["key"] == "free" else item
            for item in config["plans"]
        ],
    })
    invalid_free_plan = next(item for item in invalid_free["plans"] if item["key"] == "free")
    assert invalid_free_plan["cloneSlots"] == 0
    assert invalid_free_plan["systemVoicesOnly"] is True

    # Economics must use the complete active period rather than only the
    # last 50 events returned for UI display. Patch the data readers so this
    # runtime check never writes a test subscription or usage record.
    from services import billing_usage
    original_usage_summary = billing_usage.usage_summary
    original_events_for_contract = billing_usage._events_for_contract
    try:
        billing_usage.usage_summary = lambda workspace_id, month=None: {
            "workspaceId": workspace_id,
            "month": "2026-07",
            "plan": plans["free"],
            "subscription": {"planKey": "free", "status": "active"},
            "events": [],
        }
        billing_usage._events_for_contract = lambda workspace_id, contract: []
        economics = billing_usage.economics_summary("pricing_acceptance_empty_workspace")
        assert economics["estimatedProviderCostUsd"] == 0
    finally:
        billing_usage.usage_summary = original_usage_summary
        billing_usage._events_for_contract = original_events_for_contract

    controller = (ROOT / "controllers/clone_voice_controller.py").read_text(encoding="utf-8")
    assert "assert_workspace_can_create_custom_voice" in controller
    assert "assert_workspace_can_use_custom_voice" in controller
    assert '"voice.preview.generated"' in controller
    assert 'quantity=len(prompt)' in controller
    assert "def _preflight_preview" in controller
    assert "estimate_credits," in controller
    assert "/api/billing/free-plan" in controller

    plans_js = (ROOT / "frontend/clone_voice/plans.js").read_text(encoding="utf-8")
    # Stage 2: plan labels/buttons must come from the runtime plan catalogue/API,
    # not from a hardcoded frontend fallback catalogue.
    assert "const FALLBACK_PLANS = []" in plans_js or "FALLBACK_PLANS=[]" in plans_js.replace(" ", "")
    assert "SMX_PLAN_CATALOGUE_REQUIRED" in plans_js

    for forbidden in ["€9", "€29", "€99", "$9", "$29", "$99"]:
        assert forbidden not in plans_js
    assert "/api/billing/free-plan" in plans_js

    print("PRICING + FREE PLAN ACCEPTANCE: PASSED")
    print("Clone supplier cost: $0.01")
    print("Preview + clone default charge: 5 credits")
    print("10,000 narration characters: 46 credits")
    print("Clone slots: Free 0 / Starter 1 / Pro 3 / Business 10")


if __name__ == "__main__":
    main()


# >>> SMX_STAGE2_FREE_PLAN_FRONTEND_SOURCE_TEST >>>
def _smx_stage2_validate_frontend_plan_source() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    plans_js = (root / "frontend" / "clone_voice" / "plans.js").read_text(encoding="utf-8", errors="ignore")

    compact = plans_js.replace(" ", "").replace("\n", "")

    assert "constFALLBACK_PLANS=[]" in compact or "FALLBACK_PLANS=[]" in compact
    assert "SMX_PLAN_CATALOGUE_REQUIRED" in plans_js

    for forbidden in ["€9", "€29", "€99", "$9", "$29", "$99"]:
        assert forbidden not in plans_js
# <<< SMX_STAGE2_FREE_PLAN_FRONTEND_SOURCE_TEST >>>
