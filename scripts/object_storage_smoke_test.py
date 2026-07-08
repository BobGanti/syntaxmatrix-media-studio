from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> None:
    from services.object_storage import get_object_storage, object_storage_status_payload

    storage = get_object_storage()
    key = "smoke/object_storage_smoke_test.txt"
    payload = b"SyntaxMatrix object storage smoke test."

    saved = storage.save_bytes(
        key,
        payload,
        content_type="text/plain",
    )

    exists_after_save = storage.exists(key)
    read_back = storage.read_bytes(key)
    deleted = storage.delete(key)
    exists_after_delete = storage.exists(key)

    ok = (
        exists_after_save
        and read_back == payload
        and deleted
        and not exists_after_delete
    )

    print(json.dumps({
        "ok": ok,
        "saved": saved.to_payload(),
        "existsAfterSave": exists_after_save,
        "readBackBytes": len(read_back),
        "deleted": deleted,
        "existsAfterDelete": exists_after_delete,
        "status": object_storage_status_payload(),
    }, indent=2, default=str))

    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
