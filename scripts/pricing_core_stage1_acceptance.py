from decimal import Decimal
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
