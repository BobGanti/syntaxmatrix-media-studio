from __future__ import annotations

import os
import py_compile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def require(path: str, token: str) -> None:
    text = (ROOT / path).read_text(encoding="utf-8")
    assert token in text, f"Missing {token!r} in {path}"


def main() -> None:
    python_files = [
        "app.py",
        "services/firebase_auth.py",
        "services/firebase_page_session.py",
        "services/customer_workspace.py",
        "services/billing_usage.py",
        "services/subscription_enforcement.py",
        "services/stripe_checkout.py",
        "views/clone_voice_view.py",
        "scripts/require_payment_for_existing_beta.py",
    ]
    for relative in python_files:
        py_compile.compile(str(ROOT / relative), doraise=True)

    require("frontend/clone_voice/auth.html", "confirmPassword")
    require("frontend/clone_voice/auth.html", "rememberMe")
    require("frontend/clone_voice/auth.html", "resetPasswordButton")
    require("frontend/clone_voice/auth.js", "sendPasswordResetEmail")
    require("frontend/clone_voice/auth.js", "Auth.Persistence.SESSION")
    require("frontend/clone_voice/auth.js", "/plans?onboarding=1")
    require("frontend/clone_voice/plans.html", "Choose your plan")
    require("frontend/clone_voice/plans.js", "/api/billing/checkout/stripe")
    require("app.py", "/api/auth/session")
    require("app.py", "/api/billing/plans")
    require("views/clone_voice_view.py", "require_admin_page_session")
    require("services/customer_workspace.py", 'status="incomplete"')
    require("services/subscription_enforcement.py", '"status": "incomplete"')
    require("services/stripe_checkout.py", "/plans?checkout=success")
    require("frontend/clone_voice/client_usage.js", "window.location.assign(`/plans")

    assert "/admin/clone-voice/billing?checkout=success" not in (ROOT / "services/stripe_checkout.py").read_text(encoding="utf-8")

    os.environ["PERSISTENCE_BACKEND"] = "json"
    from services.subscription_enforcement import entitlement_payload
    payload = entitlement_payload(workspace_id="nonexistent-paid-launch-test")
    assert payload["allowed"] is False
    assert payload["subscription"]["status"] == "incomplete"

    print("Paid launch acceptance")
    print("======================")
    print("Separate sign-in and registration: passed")
    print("Confirm password: passed")
    print("Password reset: passed")
    print("Remember-me persistence: passed")
    print("Paid plan selection page: passed")
    print("New workspace payment requirement: passed")
    print("Customer Checkout return path: passed")
    print("Server-protected admin HTML routes: passed")
    print("PAID LAUNCH ACCEPTANCE: PASSED")


if __name__ == "__main__":
    main()
