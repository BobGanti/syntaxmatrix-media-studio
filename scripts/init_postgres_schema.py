from __future__ import annotations

import os
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCHEMA = ROOT / "sql" / "postgres_schema.sql"


def clean(value: object, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


def main() -> None:
    database_url = clean(os.getenv("DATABASE_URL"))

    if not database_url or database_url.startswith("replace"):
        raise SystemExit("DATABASE_URL is not configured.")

    if not SCHEMA.exists():
        raise SystemExit(f"Schema file not found: {SCHEMA}")

    try:
        import psycopg  # type: ignore
    except Exception as exc:
        raise SystemExit(f"psycopg is not installed. Run: pip install psycopg[binary]\n{exc}")

    sql = SCHEMA.read_text(encoding="utf-8")

    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()

    print("PostgreSQL schema initialised.")
    print(f"Schema: {SCHEMA.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
