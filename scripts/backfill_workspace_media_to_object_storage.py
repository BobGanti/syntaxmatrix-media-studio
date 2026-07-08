from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def backfill_workspace_media(*, dry_run: bool = True) -> dict[str, Any]:
    from services.clone_voice_workspace import DEMO_WORKSPACES, get_workspace, relative_to_root
    from services.object_storage import (
        get_object_storage,
        object_key_for_generated_audio,
        object_key_for_voice_preview,
    )

    storage = get_object_storage()

    result: dict[str, Any] = {
        "dryRun": dry_run,
        "backend": storage.backend_name,
        "workspaceCount": 0,
        "examined": 0,
        "alreadyMirrored": 0,
        "mirrored": 0,
        "failed": 0,
        "workspaces": [],
    }

    for row in DEMO_WORKSPACES:
        workspace_id = str(row.get("workspaceId") or "").strip()

        if not workspace_id:
            continue

        workspace = get_workspace(workspace_id)
        result["workspaceCount"] += 1

        workspace_result = {
            "workspaceId": workspace.workspace_id,
            "generatedAudio": [],
            "voicePreviews": [],
        }

        categories = [
            (
                "generatedAudio",
                workspace.generated_audio_dir,
                object_key_for_generated_audio,
            ),
            (
                "voicePreviews",
                workspace.voice_previews_dir,
                object_key_for_voice_preview,
            ),
        ]

        for category, directory, key_builder in categories:
            for path in sorted(directory.glob("*")):
                if not path.is_file():
                    continue

                result["examined"] += 1
                key = key_builder(workspace.workspace_id, path.name)

                item = {
                    "filename": path.name,
                    "localPath": relative_to_root(path),
                    "objectKey": key,
                    "action": "",
                    "ok": False,
                    "error": "",
                }

                try:
                    if storage.exists(key):
                        result["alreadyMirrored"] += 1
                        item["action"] = "already_mirrored"
                        item["ok"] = True
                    elif dry_run:
                        item["action"] = "would_mirror"
                        item["ok"] = True
                    else:
                        stored = storage.upload_file(
                            key,
                            path,
                            content_type="audio/wav",
                        )
                        result["mirrored"] += 1
                        item["action"] = "mirrored"
                        item["ok"] = True
                        item["uri"] = stored.uri

                except Exception as exc:
                    result["failed"] += 1
                    item["action"] = "failed"
                    item["ok"] = False
                    item["error"] = str(exc)

                workspace_result[category].append(item)

        result["workspaces"].append(workspace_result)

    result["ok"] = result["failed"] == 0

    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill existing local workspace media into configured object storage."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually mirror missing files. Default is dry-run.",
    )

    args = parser.parse_args()
    payload = backfill_workspace_media(dry_run=not args.apply)

    print(json.dumps(payload, indent=2, default=str))

    if not payload["ok"]:
        raise SystemExit(1)

    if not args.apply:
        print()
        print("Dry run only. To mirror files:")
        print("  python scripts/backfill_workspace_media_to_object_storage.py --apply")


if __name__ == "__main__":
    main()
