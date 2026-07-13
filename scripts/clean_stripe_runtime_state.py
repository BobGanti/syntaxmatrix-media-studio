from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

STRIPE_WEBHOOK_EVENT_LOG = ROOT / "billing" / "stripe_webhook_events.jsonl"
STRIPE_PROCESSED_EVENTS = ROOT / "billing" / "stripe_processed_events.json"


def clean_stripe_runtime_state(print_summary: bool = True) -> dict[str, int]:
    STRIPE_WEBHOOK_EVENT_LOG.parent.mkdir(parents=True, exist_ok=True)
    STRIPE_PROCESSED_EVENTS.parent.mkdir(parents=True, exist_ok=True)

    previous_log_bytes = STRIPE_WEBHOOK_EVENT_LOG.stat().st_size if STRIPE_WEBHOOK_EVENT_LOG.exists() else 0
    previous_processed_bytes = STRIPE_PROCESSED_EVENTS.stat().st_size if STRIPE_PROCESSED_EVENTS.exists() else 0

    STRIPE_WEBHOOK_EVENT_LOG.write_text("", encoding="utf-8")
    STRIPE_PROCESSED_EVENTS.write_text("[]\n", encoding="utf-8")

    result = {
        "previousWebhookLogBytes": previous_log_bytes,
        "previousProcessedEventsBytes": previous_processed_bytes,
        "currentWebhookLogBytes": 0,
        "currentProcessedEventsBytes": len("[]\n".encode("utf-8")),
    }

    if print_summary:
        print("Cleared Stripe runtime state.")
        print("Previous webhook log bytes:", previous_log_bytes)
        print("Previous processed-events bytes:", previous_processed_bytes)
        print("Current webhook log bytes:", 0)
        print("Current processed-events bytes:", len("[]\n".encode("utf-8")))

    return result


if __name__ == "__main__":
    clean_stripe_runtime_state(print_summary=True)
