from __future__ import annotations

import os
from typing import Any


def _clean(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


def persistence_backend() -> str:
    backend = _clean(os.getenv("PERSISTENCE_BACKEND"), "json").lower()

    if backend not in {"json", "postgres"}:
        return "json"

    return backend


def database_url_configured() -> bool:
    url = _clean(os.getenv("DATABASE_URL"))
    return bool(url and not url.startswith("replace"))


def postgres_driver_status() -> dict[str, Any]:
    try:
        import psycopg  # type: ignore

        return {
            "installed": True,
            "driver": "psycopg",
            "version": getattr(psycopg, "__version__", ""),
        }
    except Exception as exc:
        return {
            "installed": False,
            "driver": "psycopg",
            "error": str(exc),
            "install": "pip install psycopg[binary]",
        }


def persistence_status_payload() -> dict[str, Any]:
    backend = persistence_backend()
    db_configured = database_url_configured()
    driver = postgres_driver_status()

    ready_for_postgres = backend == "postgres" and db_configured and driver["installed"]

    warnings = []

    if backend == "json":
        warnings.append("JSON runtime storage is active. This is acceptable for local development only.")

    if backend == "postgres" and not db_configured:
        warnings.append("PERSISTENCE_BACKEND=postgres but DATABASE_URL is not configured.")

    if backend == "postgres" and not driver["installed"]:
        warnings.append("PERSISTENCE_BACKEND=postgres but psycopg is not installed.")

    return {
        "backend": backend,
        "databaseUrlConfigured": db_configured,
        "postgresDriver": driver,
        "readyForPostgres": ready_for_postgres,
        "schemaFile": "sql/postgres_schema.sql",
        "initCommand": "python scripts/init_postgres_schema.py",
        "cloudRunReady": ready_for_postgres,
        "warnings": warnings,
    }
