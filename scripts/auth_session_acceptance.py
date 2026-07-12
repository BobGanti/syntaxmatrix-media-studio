from __future__ import annotations

import datetime as dt
import importlib
import py_compile
import sys
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> None:
    for relative in (
        "services/firebase_auth.py",
        "services/firebase_page_session.py",
        "app.py",
    ):
        py_compile.compile(
            str(ROOT / relative),
            doraise=True,
        )

    calls = {}

    fake_auth = types.ModuleType(
        "firebase_admin.auth"
    )

    def create_session_cookie(
        token,
        *,
        expires_in,
    ):
        calls["create_token"] = token
        calls["expires_in"] = expires_in
        return "fake-session-cookie"

    def verify_session_cookie(
        cookie,
        *,
        check_revoked=False,
    ):
        calls["verify_cookie"] = cookie
        calls["check_revoked"] = check_revoked

        return {
            "uid": "firebase-user",
            "email": "admin@example.test",
        }

    fake_auth.create_session_cookie = (
        create_session_cookie
    )
    fake_auth.verify_session_cookie = (
        verify_session_cookie
    )

    fake_admin = types.ModuleType(
        "firebase_admin"
    )
    fake_admin._apps = [object()]
    fake_admin.auth = fake_auth
    fake_admin.get_app = lambda: fake_admin._apps[0]

    previous_admin = sys.modules.get(
        "firebase_admin"
    )
    previous_auth = sys.modules.get(
        "firebase_admin.auth"
    )

    sys.modules["firebase_admin"] = fake_admin
    sys.modules["firebase_admin.auth"] = fake_auth

    try:
        module = importlib.import_module(
            "services.firebase_auth"
        )
        module._firebase_app.cache_clear()

        cookie = (
            module.create_firebase_session_cookie(
                "fake-id-token",
                expires_in_seconds=3600,
            )
        )

        decoded = (
            module.verify_firebase_session_cookie(
                cookie
            )
        )
    finally:
        if previous_admin is None:
            sys.modules.pop(
                "firebase_admin",
                None,
            )
        else:
            sys.modules["firebase_admin"] = (
                previous_admin
            )

        if previous_auth is None:
            sys.modules.pop(
                "firebase_admin.auth",
                None,
            )
        else:
            sys.modules[
                "firebase_admin.auth"
            ] = previous_auth

    assert cookie == "fake-session-cookie"
    assert decoded["uid"] == "firebase-user"
    assert calls["create_token"] == "fake-id-token"
    assert calls["expires_in"] == dt.timedelta(
        seconds=3600
    )
    assert (
        calls["verify_cookie"]
        == "fake-session-cookie"
    )
    assert calls["check_revoked"] is False

    page_source = (
        ROOT
        / "services"
        / "firebase_page_session.py"
    ).read_text(encoding="utf-8")

    assert (
        "verify_firebase_session_cookie"
        in page_source
    )

    assert (
        "verify_firebase_id_token(cookie)"
        not in page_source
    )

    app_source = (
        ROOT / "app.py"
    ).read_text(encoding="utf-8")

    assert (
        "create_firebase_session_cookie"
        in app_source
    )

    assert (
        '"/api/auth/session"'
        in app_source
    )

    print("AUTH SESSION ACCEPTANCE: PASSED")
    print(
        "Missing session-cookie helper: fixed"
    )
    print(
        "Correct session-cookie verifier: passed"
    )
    print(
        "Admin page session contract: passed"
    )


if __name__ == "__main__":
    main()
