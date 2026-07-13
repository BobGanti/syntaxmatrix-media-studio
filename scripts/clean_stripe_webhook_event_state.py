from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEBHOOK_EVENT_LOG = ROOT / "billing" / "stripe_webhook_events.jsonl"


def clean_stripe_webhook_event_state(print_summary: bool = True) -> dict[str, int]:
    WEBHOOK_EVENT_LOG.parent.mkdir(parents=True, exist_ok=True)

    previous_size = WEBHOOK_EVENT_LOG.stat().st_size if WEBHOOK_EVENT_LOG.exists() else 0
    WEBHOOK_EVENT_LOG.write_text("", encoding="utf-8")

    result = {
        "previousBytes": previous_size,
        "currentBytes": 0,
    }

    if print_summary:
        print("Cleared Stripe webhook event runtime log.")
        print("Previous bytes:", previous_size)
        print("Current bytes:", 0)

    return result


if __name__ == "__main__":
    clean_stripe_webhook_event_state(print_summary=True)
