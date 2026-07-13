from __future__ import annotations

# ---------------------------------------------------------------------
# Local .env loader
# Loads simple KEY=VALUE pairs before services read os.getenv().
# Does not print secrets.
# ---------------------------------------------------------------------
def _load_local_env_file():
    import os
    from pathlib import Path

    env_path = Path(__file__).resolve().parent / ".env"

    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()

        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")

        if key and key not in os.environ:
            os.environ[key] = value


_load_local_env_file()



import base64
import json
import mimetypes
import os
import pathlib
import time
import traceback
from http import HTTPStatus
from typing import Any, Dict, Iterable, Optional, Tuple

from flask import Flask, jsonify, request, send_from_directory, Response, stream_with_context
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    load_dotenv = None

ROOT = pathlib.Path(__file__).resolve().parent
FRONTEND_DIR = ROOT / "frontend"
UPLOADS_DIR = ROOT / "uploads"
GENERATED_DIR = ROOT / "generated"

UPLOADS_IMAGES_DIR = UPLOADS_DIR / "images"
UPLOADS_VOICES_DIR = UPLOADS_DIR / "voices"

for directory in (FRONTEND_DIR, UPLOADS_IMAGES_DIR, UPLOADS_VOICES_DIR, GENERATED_DIR):
    directory.mkdir(parents=True, exist_ok=True)

if load_dotenv:
    load_dotenv(ROOT / ".env")

app = Flask(__name__, static_folder=None)


# ---------------------------------------------------------------------
# WSGI-LEVEL API GUARD: storage status/media audit
# This runs before Flask route fallback handlers.
# ---------------------------------------------------------------------
if "syntaxmatrix_storage_api_wsgi_guard_installed" not in globals():
    syntaxmatrix_storage_api_wsgi_guard_installed = True
    _syntaxmatrix_original_wsgi_app = app.wsgi_app

    def _syntaxmatrix_storage_api_wsgi_guard(environ, start_response):
        path = str(environ.get("PATH_INFO") or "").rstrip("/")

        if path not in {
            "/api/admin/storage/status",
            "/api/admin/storage/media-audit",
        }:
            return _syntaxmatrix_original_wsgi_app(environ, start_response)

        with app.request_context(environ):
            from flask import jsonify, request

            if request.method.upper() != "GET":
                response = jsonify({
                    "ok": False,
                    "error": "Method not allowed.",
                    "endpoint": path,
                })
                response.status_code = 405
                return response(environ, start_response)

            try:
                from services.auth_context import (
                    AuthError,
                    auth_context_from_request,
                    auth_error_payload,
                    require_admin,
                )

                ctx = auth_context_from_request(request)
                require_admin(ctx)

            except AuthError as exc:
                response = jsonify(auth_error_payload(exc))
                response.status_code = exc.status_code
                return response(environ, start_response)

            except Exception as exc:
                response = jsonify({
                    "ok": False,
                    "error": str(exc),
                    "stage": "auth",
                    "endpoint": path,
                })
                response.status_code = 500
                return response(environ, start_response)

            try:
                if path == "/api/admin/storage/status":
                    from services.object_storage import object_storage_status_payload

                    response = jsonify({
                        "ok": True,
                        **object_storage_status_payload(),
                    })
                    return response(environ, start_response)

                from services.object_storage_media_audit import object_storage_media_audit_payload

                response = jsonify({
                    "ok": True,
                    **object_storage_media_audit_payload(),
                })
                return response(environ, start_response)

            except Exception as exc:
                response = jsonify({
                    "ok": False,
                    "error": str(exc),
                    "stage": "payload",
                    "endpoint": path,
                })
                response.status_code = 500
                return response(environ, start_response)

    app.wsgi_app = _syntaxmatrix_storage_api_wsgi_guard



# ---------------------------------------------------------------------
# EARLY API GUARD: storage status/media audit
# Must be registered near app creation, before broad Media Studio fallback.
# ---------------------------------------------------------------------
@app.before_request
def syntaxmatrix_early_storage_api_guard():
    from flask import jsonify, request

    path = request.path.rstrip("/")

    if path not in {
        "/api/admin/storage/status",
        "/api/admin/storage/media-audit",
    }:
        return None

    if request.method.upper() != "GET":
        return jsonify({
            "ok": False,
            "error": "Method not allowed.",
            "endpoint": path,
        }), 405

    from services.auth_context import (
        AuthError,
        auth_context_from_request,
        auth_error_payload,
        require_admin,
    )

    ctx = auth_context_from_request(request)

    try:
        require_admin(ctx)
    except AuthError as exc:
        return jsonify(auth_error_payload(exc)), exc.status_code

    if path == "/api/admin/storage/status":
        from services.object_storage import object_storage_status_payload

        return jsonify({
            "ok": True,
            **object_storage_status_payload(),
        })

    from services.object_storage_media_audit import object_storage_media_audit_payload

    return jsonify({
        "ok": True,
        **object_storage_media_audit_payload(),
    })



# ---------------------------------------------------------------------
# Clone Voice Finance Console hard route guard
# Runs before normal Flask routing so /admin/clone-voice/billing cannot
# fall through to the general Media Studio page.
# ---------------------------------------------------------------------
@app.before_request
def clone_voice_finance_console_before_request_guard():
    from pathlib import Path
    from flask import request, send_from_directory

    if request.path.rstrip("/") == "/admin/clone-voice/billing":
        from services.firebase_page_session import require_admin_page_session

        denied = require_admin_page_session(request)
        if denied is not None:
            return denied

        frontend_dir = Path(__file__).resolve().parent / "frontend" / "clone_voice"
        return send_from_directory(frontend_dir, "billing.html")

    return None


app.config["MAX_CONTENT_LENGTH"] = int(os.getenv("ALIBABA_MEDIA_MAX_UPLOAD_MB", "80")) * 1024 * 1024

HOST = os.getenv("ALIBABA_MEDIA_HOST", "127.0.0.1")
PORT = int(os.getenv("ALIBABA_MEDIA_PORT", "5055"))

def _dry_run() -> bool:
    return os.getenv("ALIBABA_MEDIA_DRY_RUN", "0").lower() in {"1", "true", "yes", "on"}

def _env_config() -> Tuple[str, str, str]:
    api_key = os.getenv("SINGAPORE_API_KEY") or os.getenv("ALIBABA_API_KEY") or ""
    workspace_id = os.getenv("SINGAPORE_WORKSPACE_ID") or os.getenv("ALIBABA_WORKSPACE_ID") or ""

    if not api_key or not workspace_id:
        raise RuntimeError(
            "Missing provider credentials. Add SINGAPORE_API_KEY and SINGAPORE_WORKSPACE_ID "
            "to a .env file in the project root."
        )

    base_http_api_url = f"https://{workspace_id}.ap-southeast-1.maas.aliyuncs.com/api/v1"
    return api_key, workspace_id, base_http_api_url

def _require_dashscope():
    try:
        import dashscope  # type: ignore
        from dashscope import MultiModalConversation, VideoSynthesis  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("dashscope is not installed. Run: pip install -r requirements.txt") from exc

    return dashscope, MultiModalConversation, VideoSynthesis

def _json_error(message: str, status: int = 500, **extra: Any):
    payload = {"ok": False, "message": message, "error": message}
    payload.update(extra)
    return jsonify(payload), status

def _safe_response(response: Any) -> Any:
    try:
        return json.loads(json.dumps(response, default=lambda obj: getattr(obj, "__dict__", str(obj))))
    except Exception:
        return str(response)

def _parse_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}

def _parse_payload() -> Dict[str, Any]:
    """Read JSON fields or multipart form fields without ever decoding image bytes as text."""
    if request.is_json:
        data = request.get_json(silent=True)
        return data if isinstance(data, dict) else {}

    payload: Dict[str, Any] = {}
    for key in request.form:
        values = request.form.getlist(key)
        payload[key] = values if len(values) > 1 else values[0]

    # Convert JSON-ish form fields back into Python objects where useful.
    for key in ("imageNames", "imageLabels", "imageSlots", "images"):
        value = payload.get(key)
        if isinstance(value, str) and value[:1] in {"[", "{"}:
            try:
                payload[key] = json.loads(value)
            except Exception:
                pass

    return payload

def _safe_ext(mime_type: str, fallback: str = ".bin") -> str:
    return mimetypes.guess_extension(mime_type or "") or fallback

def _data_url_to_bytes(data_url: str) -> Tuple[bytes, str]:
    if not isinstance(data_url, str) or not data_url.startswith("data:") or "," not in data_url:
        raise ValueError("Expected a browser data URL such as data:image/png;base64,...")

    header, encoded = data_url.split(",", 1)
    mime_type = header[5:].split(";", 1)[0] or "application/octet-stream"
    return base64.b64decode(encoded), mime_type

def _unique_upload_name(prefix: str, original_name: str, fallback_ext: str = ".bin") -> str:
    safe = secure_filename(original_name or "")
    stem = pathlib.Path(safe).stem or prefix
    ext = pathlib.Path(safe).suffix or fallback_ext
    return f"{prefix}_{int(time.time() * 1000)}_{stem}{ext}"

def _relative_upload_path(path: pathlib.Path) -> str:
    return str(path.relative_to(ROOT)).replace(os.sep, "/")

def _save_file_storage(file: FileStorage, slot: int, subdir: str = "images") -> str:
    target_dir = UPLOADS_DIR / subdir
    target_dir.mkdir(parents=True, exist_ok=True)

    mime_type = file.mimetype or "application/octet-stream"
    fallback_ext = _safe_ext(mime_type, ".bin")
    filename = _unique_upload_name(f"image{slot}", file.filename or f"image{slot}{fallback_ext}", fallback_ext)
    target = target_dir / filename
    file.save(target)
    return _relative_upload_path(target)

def _save_data_url(data_url: str, slot: int, original_name: str = "", subdir: str = "images") -> str:
    raw, mime_type = _data_url_to_bytes(data_url)
    target_dir = UPLOADS_DIR / subdir
    target_dir.mkdir(parents=True, exist_ok=True)

    fallback_ext = _safe_ext(mime_type, ".bin")
    filename = _unique_upload_name(f"image{slot}", original_name or f"image{slot}{fallback_ext}", fallback_ext)
    target = target_dir / filename
    target.write_bytes(raw)
    return _relative_upload_path(target)

def _uploaded_image_files_in_order() -> list[FileStorage]:
    """Return image files in Image 1, Image 2, Image 3 order.

    The frontend sends repeated field name `image`, so Flask reads it with
    request.files.getlist("image"). We also support image1/image2/image3 names.
    """
    files = request.files.getlist("image")
    if files:
        return [file for file in files if file and file.filename]

    ordered: list[FileStorage] = []
    for name in ("image1", "image2", "image3"):
        file = request.files.get(name)
        if file and file.filename:
            ordered.append(file)
    return ordered

def _extract_image_paths(payload: Dict[str, Any], max_images: int = 3) -> list[str]:
    """Save uploaded files/data URLs and return Alibaba-ready root-relative paths.

    The returned list order is the contract:
      index 0 => Image 1
      index 1 => Image 2
      index 2 => Image 3
    """
    saved_paths: list[str] = []

    files = _uploaded_image_files_in_order()
    if files:
        if len(files) > max_images:
            raise ValueError(f"Too many images. Maximum allowed is {max_images}.")
        for index, file in enumerate(files, start=1):
            saved_paths.append(_save_file_storage(file, index, "images"))
        return saved_paths

    images = payload.get("images") or []
    if isinstance(images, str):
        images = [images]
    if not isinstance(images, list):
        images = []

    image_names = payload.get("imageNames") or []
    if isinstance(image_names, str):
        image_names = [image_names]

    if len(images) > max_images:
        raise ValueError(f"Too many images. Maximum allowed is {max_images}.")

    for index, item in enumerate(images, start=1):
        if isinstance(item, str) and item.startswith("data:"):
            original_name = image_names[index - 1] if index - 1 < len(image_names) else f"image{index}.png"
            saved_paths.append(_save_data_url(item, index, original_name, "images"))
        elif isinstance(item, str) and item.strip():
            # Advanced/local caller can pass an existing path or URL directly.
            saved_paths.append(item.strip())

    return saved_paths

def _messages_from_text(prompt: str) -> list[dict[str, Any]]:
    return [{"role": "user", "content": [{"text": prompt}]}]

def _messages_from_images_and_text(image_paths: list[str], prompt: str) -> list[dict[str, Any]]:
    content: list[dict[str, str]] = []
    for image_path in image_paths:
        # This is exactly the Alibaba message structure the user's console script uses.
        content.append({"image": image_path})
    content.append({"text": prompt})
    return [{"role": "user", "content": content}]

def _first_image_from_response_content(content: Iterable[dict[str, Any]]) -> Optional[str]:
    for item in content:
        if isinstance(item, dict) and item.get("image"):
            return str(item["image"])
    return None

def _extract_image_url(response: Any) -> Optional[str]:
    try:
        content = response["output"]["choices"][0]["message"]["content"]
        return _first_image_from_response_content(content)
    except Exception:
        return None

def _video_size(payload: Dict[str, Any]) -> str:
    resolution = str(payload.get("resolution") or "720P").upper()
    if resolution == "1080P":
        return "1920*1080"
    if resolution == "480P":
        return "832*480"
    return "1280*720"

def _duration(payload: Dict[str, Any]) -> int:
    try:
        return int(payload.get("duration") or 5)
    except Exception:
        return 5

@app.after_request
def _add_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
    return response

@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({
        "ok": True,
        "service": "SyntaxMatrix Media Studio",
        "status": "online",
        "dryRun": _dry_run(),
        "expectsUploads": "multipart field name 'image' repeated in Image 1, Image 2, Image 3 order",
    })

@app.route("/api/media/text-to-image", methods=["POST"])
def text_to_image():
    payload = _parse_payload()
    prompt = (payload.get("prompt") or "").strip()
    if not prompt:
        return _json_error("Prompt is required.", 400)

    model = payload.get("model") or "qwen-image-plus-2026-01-09"
    messages = _messages_from_text(prompt)

    if _dry_run():
        return jsonify({"ok": True, "dryRun": True, "imageUrl": "", "requestMessages": messages})

    api_key, _, base_url = _env_config()
    from alibaba import AlibabaImages
    # from src.ali_t2i_gen import t2i

    image_url = AlibabaImages(api_key).text2image(model, messages, base_url)
    # image_url = t2i(messages)
    if not image_url:
        return _json_error("Provider text-to-image did not return an image URL.", 502)

    return jsonify({"ok": True, "imageUrl": image_url, "assetUrl": image_url, "requestMessages": messages})

@app.route("/api/media/edit-to-image", methods=["POST"])
def edit_to_image():
    payload = _parse_payload()
    prompt = (payload.get("prompt") or "").strip()
    if not prompt:
        return _json_error("Prompt is required.", 400)

    try:
        image_paths = _extract_image_paths(payload, max_images=3)
    except ValueError as exc:
        return _json_error(str(exc), 400)

    if not image_paths:
        return _json_error("Upload at least one image. The frontend should send files under multipart field name 'image'.", 400)
    if len(image_paths) > 3:
        return _json_error("Too many images: maximum allowed is 3.", 400)

    model = payload.get("model") or "qwen-image-edit-plus-2025-12-15"
    messages = _messages_from_images_and_text(image_paths, prompt)

    # This is a useful proof point while testing frontend upload order.
    debug_payload = {
        "inputImages": image_paths,
        "requestMessages": messages,
        "imageCount": len(image_paths),
    }

    if _dry_run():
        return jsonify({"ok": True, "dryRun": True, **debug_payload})

    api_key, _, base_url = _env_config()
    from alibaba import AlibabaImages

    content_list = AlibabaImages(api_key).edit2image(model, messages, base_url)
    if not content_list:
        return _json_error("Provider edit-to-image did not return image content.", 502, **debug_payload)

    image_urls = [item.get("image") for item in content_list if isinstance(item, dict) and item.get("image")]
    image_url = image_urls[0] if image_urls else None

    return jsonify({
        "ok": True,
        "imageUrl": image_url,
        "assetUrl": image_url,
        "images": image_urls,
        "rawContent": content_list,
        **debug_payload,
    })

@app.route("/api/media/text-to-video", methods=["POST"])
def text_to_video():
    payload = _parse_payload()
    prompt = (payload.get("prompt") or "").strip()
    if not prompt:
        return _json_error("Prompt is required.", 400)

    model = payload.get("model") or "wan2.6-t2v"

    if _dry_run():
        return jsonify({"ok": True, "dryRun": True, "videoUrl": "", "request": {"model": model, "prompt": prompt}})

    dashscope, _, VideoSynthesis = _require_dashscope()
    api_key, _, base_url = _env_config()
    dashscope.base_http_api_url = base_url

    kwargs: Dict[str, Any] = {
        "api_key": api_key,
        "model": model,
        "prompt": prompt,
        "size": payload.get("size") or _video_size(payload),
        "duration": _duration(payload),
        "negative_prompt": payload.get("negativePrompt") or "",
        "prompt_extend": _parse_bool(payload.get("promptExtend"), True),
        "watermark": _parse_bool(payload.get("watermark"), False),
    }
    if payload.get("seed") not in (None, ""):
        kwargs["seed"] = int(payload["seed"])
    if payload.get("audioUrl"):
        kwargs["audio_url"] = payload["audioUrl"]

    response = VideoSynthesis.call(**kwargs)
    if getattr(response, "status_code", None) not in {HTTPStatus.OK, 200}:
        return _json_error(getattr(response, "message", "Provider text-to-video request failed."), 502, raw=_safe_response(response))

    video_url = getattr(getattr(response, "output", None), "video_url", None)
    if not video_url:
        try:
            video_url = response["output"]["video_url"]
        except Exception:
            video_url = None

    return jsonify({"ok": True, "videoUrl": video_url, "assetUrl": video_url, "raw": _safe_response(response)})

@app.route("/api/media/image-to-video", methods=["POST"])
@app.route("/visiondirector/api/ai/debug-alibaba-i2v", methods=["POST"])
def image_to_video():
    payload = _parse_payload()
    prompt = (payload.get("prompt") or "").strip()
    if not prompt:
        return _json_error("Prompt is required.", 400)

    image_paths = _extract_image_paths(payload, max_images=1)
    image_url = payload.get("imageUrl") or (image_paths[0] if image_paths else None)
    if not image_url:
        return _json_error("Upload one source image or provide imageUrl.", 400)

    model = payload.get("model") or "wan2.6-i2v"

    if _dry_run():
        return jsonify({"ok": True, "dryRun": True, "videoUrl": "", "inputImage": image_url})

    dashscope, _, VideoSynthesis = _require_dashscope()
    api_key, _, base_url = _env_config()
    dashscope.base_http_api_url = base_url

    kwargs: Dict[str, Any] = {
        "api_key": api_key,
        "model": model,
        "prompt": prompt,
        "img_url": image_url,
        "size": payload.get("size") or _video_size(payload),
        "duration": _duration(payload),
        "negative_prompt": payload.get("negativePrompt") or "",
        "prompt_extend": _parse_bool(payload.get("promptExtend"), True),
        "watermark": _parse_bool(payload.get("watermark"), False),
    }
    if payload.get("seed") not in (None, ""):
        kwargs["seed"] = int(payload["seed"])

    response = VideoSynthesis.call(**kwargs)
    if getattr(response, "status_code", None) not in {HTTPStatus.OK, 200}:
        return _json_error(getattr(response, "message", "Provider image-to-video request failed."), 502, raw=_safe_response(response))

    video_url = getattr(getattr(response, "output", None), "video_url", None)
    if not video_url:
        try:
            video_url = response["output"]["video_url"]
        except Exception:
            video_url = None

    return jsonify({"ok": True, "videoUrl": video_url, "assetUrl": video_url, "inputImage": image_url, "raw": _safe_response(response)})

@app.route("/api/download-asset", methods=["GET"])
def download_asset():
    """Download a generated asset from a local path or remote provider URL."""
    asset_url = (request.args.get("url") or "").strip()
    requested_name = secure_filename(request.args.get("filename") or "")

    if not asset_url:
        return _json_error("Missing asset URL.", 400)

    from urllib.parse import urlparse, unquote

    parsed = urlparse(asset_url)

    def choose_filename(content_type: str = "") -> str:
        if requested_name:
            return requested_name
        guessed = secure_filename(unquote(pathlib.PurePosixPath(parsed.path).name or ""))
        if guessed:
            return guessed
        ext = mimetypes.guess_extension((content_type or "").split(";", 1)[0].strip()) or ".bin"
        return f"syntaxmatrix_generated_asset{ext}"

    local_path = asset_url.lstrip("/")
    if not parsed.scheme and local_path.startswith("uploads/"):
        rel = local_path[len("uploads/"):]
        return send_from_directory(UPLOADS_DIR, rel, as_attachment=True, download_name=choose_filename())

    if not parsed.scheme and local_path.startswith("generated/"):
        rel = local_path[len("generated/"):]
        return send_from_directory(GENERATED_DIR, rel, as_attachment=True, download_name=choose_filename())

    if parsed.scheme not in {"http", "https"}:
        return _json_error("Only http(s), uploads/, and generated/ asset URLs can be downloaded.", 400)

    try:
        import requests  # type: ignore
        remote = requests.get(
            asset_url,
            stream=True,
            timeout=(10, 180),
            headers={"User-Agent": "SyntaxMatrixMediaStudio/1.0"},
        )
    except Exception as exc:
        return _json_error(f"Could not reach generated asset URL: {exc}", 502)

    if remote.status_code >= 400:
        details = ""
        try:
            details = remote.text[:500]
        except Exception:
            pass
        remote.close()
        return _json_error(f"Generated asset URL returned HTTP {remote.status_code}.", 502, details=details)

    content_type = remote.headers.get("Content-Type") or "application/octet-stream"
    download_name = choose_filename(content_type)

    def generate():
        try:
            for chunk in remote.iter_content(chunk_size=1024 * 64):
                if chunk:
                    yield chunk
        finally:
            remote.close()

    headers = {
        "Content-Type": content_type,
        "Content-Disposition": f'attachment; filename="{download_name}"',
        "Cache-Control": "no-store",
    }

    if remote.headers.get("Content-Length"):
        headers["Content-Length"] = remote.headers["Content-Length"]

    return Response(stream_with_context(generate()), headers=headers)

@app.route("/uploads/<path:filename>")
def uploaded_file(filename: str):
    return send_from_directory(UPLOADS_DIR, filename)

@app.route("/generated/<path:filename>")
def generated_file(filename: str):
    return send_from_directory(GENERATED_DIR, filename)


# SMX_CLONE_VOICE_CLEAN_START
from views import register_views as _smx_register_views
from controllers.clone_voice_controller import register_clone_voice_routes as _smx_register_clone_voice_routes

_smx_register_views(app)
_smx_register_clone_voice_routes(app)
# SMX_CLONE_VOICE_CLEAN_END

@app.route("/", defaults={"path": "index.html"})
@app.route("/<path:path>")
def frontend(path: str):
    if path in {"", "/"}:
        path = "index.html"

    candidate = FRONTEND_DIR / path
    if candidate.exists() and candidate.is_file():
        return send_from_directory(FRONTEND_DIR, path)

    # API and protected media requests must never fall through to index.html.
    # Returning JSON here prevents the browser from trying to parse HTML as an
    # API response when a route is missing or deployed under the wrong image.
    if path.startswith("api/"):
        return _json_error(f"API endpoint not found: /{path}", 404)

    if path.startswith("media/"):
        return _json_error(f"Media asset not found: /{path}", 404)

    # Friendly SPA-style fallback for browser pages only.
    return send_from_directory(FRONTEND_DIR, "index.html")

@app.errorhandler(413)
def upload_too_large(_exc):
    return _json_error("Upload is too large. Increase the max upload MB setting if needed.", 413)

@app.errorhandler(Exception)
def unhandled(exc):
    from werkzeug.exceptions import HTTPException

    # API callers must never receive an HTML error document. Preserve known HTTP
    # status codes and convert the response to the JSON contract used by the UI.
    if isinstance(exc, HTTPException):
        status_code = int(exc.code or 500)
        message = str(exc.description or exc.name or "Request failed.")
        if request.path.startswith("/api/"):
            return _json_error(message, status_code)
        return exc

    traceback.print_exc()
    return _json_error("The server could not complete the request.", 500)



# ---------------------------------------------------------------------
# Clone Voice Finance Console
# Direct route guard so /admin/clone-voice/billing does not fall through
# to the general Media Studio page.
# ---------------------------------------------------------------------
if "clone_voice_finance_console_page" not in app.view_functions:
    @app.get("/admin/clone-voice/billing", endpoint="clone_voice_finance_console_page")
    def clone_voice_finance_console_page():
        from pathlib import Path
        from flask import request, send_from_directory
        from services.firebase_page_session import require_admin_page_session

        denied = require_admin_page_session(request)
        if denied is not None:
            return denied

        frontend_dir = Path(__file__).resolve().parent / "frontend" / "clone_voice"
        return send_from_directory(frontend_dir, "billing.html")




# ---------------------------------------------------------------------
# SyntaxMatrix Media Studio dev access-control boundary
# ---------------------------------------------------------------------


if "auth_context_status" not in app.view_functions:
    @app.get("/api/auth/context", endpoint="auth_context_status")
    def auth_context_status():
        from flask import jsonify, request
        from services.auth_context import auth_context_from_request

        ctx = auth_context_from_request(request)

        return jsonify({
            "ok": True,
            **ctx.to_payload(),
            "notes": [
                "Development auth boundary is active.",
                "Use DEV_AUTH_ROLE=admin for admin testing.",
                "Use DEV_AUTH_ROLE=client and DEV_AUTH_WORKSPACE_ID=<workspace> for client testing.",
                "Replace services.auth_context with real login/JWT/session auth before production.",
            ],
        })




# ---------------------------------------------------------------------
# Customer / workspace / membership foundation routes
# ---------------------------------------------------------------------
if "account_workspaces" not in app.view_functions:
    @app.get("/api/account/workspaces", endpoint="account_workspaces")
    def account_workspaces():
        from flask import jsonify, request
        from services.auth_context import auth_context_from_request
        from services.customer_workspace import workspace_selector_payload

        ctx = auth_context_from_request(request)
        payload = workspace_selector_payload(ctx.user_id, ctx.role, ctx.workspace_id)

        return jsonify({
            "ok": True,
            **payload,
        })


if "admin_customer_workspace_index" not in app.view_functions:
    @app.get("/api/admin/workspaces", endpoint="admin_customer_workspace_index")
    def admin_customer_workspace_index():
        from flask import jsonify, request
        from services.auth_context import AuthError, auth_context_from_request, auth_error_payload, require_admin
        from services.customer_workspace import list_customers, list_memberships, list_workspaces

        ctx = auth_context_from_request(request)

        try:
            require_admin(ctx)
        except AuthError as exc:
            return jsonify(auth_error_payload(exc)), exc.status_code

        return jsonify({
            "ok": True,
            "customers": list_customers(),
            "workspaces": list_workspaces(),
            "memberships": list_memberships(),
        })


if "admin_customer_create" not in app.view_functions:
    @app.post("/api/admin/customers", endpoint="admin_customer_create")
    def admin_customer_create():
        from flask import jsonify, request
        from services.auth_context import AuthError, auth_context_from_request, auth_error_payload, require_admin
        from services.customer_workspace import create_customer

        ctx = auth_context_from_request(request)

        try:
            require_admin(ctx)
        except AuthError as exc:
            return jsonify(auth_error_payload(exc)), exc.status_code

        data = request.get_json(silent=True) or {}

        try:
            customer = create_customer(
                name=data.get("name"),
                billing_email=data.get("billingEmail") or data.get("billing_email") or "",
                customer_id=data.get("customerId") or data.get("customer_id") or "",
            )
            return jsonify({"ok": True, "customer": customer})
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc), "message": str(exc)}), 400


if "admin_workspace_create" not in app.view_functions:
    @app.post("/api/admin/workspaces", endpoint="admin_workspace_create")
    def admin_workspace_create():
        from flask import jsonify, request
        from services.auth_context import AuthError, auth_context_from_request, auth_error_payload, require_admin
        from services.customer_workspace import create_workspace

        ctx = auth_context_from_request(request)

        try:
            require_admin(ctx)
        except AuthError as exc:
            return jsonify(auth_error_payload(exc)), exc.status_code

        data = request.get_json(silent=True) or {}

        try:
            workspace = create_workspace(
                customer_id=data.get("customerId") or data.get("customer_id"),
                label=data.get("label"),
                workspace_id=data.get("workspaceId") or data.get("workspace_id") or "",
                subscription_owner_user_id=data.get("subscriptionOwnerUserId") or data.get("subscription_owner_user_id") or "",
            )
            return jsonify({"ok": True, "workspace": workspace})
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc), "message": str(exc)}), 400


if "admin_membership_create" not in app.view_functions:
    @app.post("/api/admin/memberships", endpoint="admin_membership_create")
    def admin_membership_create():
        from flask import jsonify, request
        from services.auth_context import AuthError, auth_context_from_request, auth_error_payload, require_admin
        from services.customer_workspace import add_workspace_membership

        ctx = auth_context_from_request(request)

        try:
            require_admin(ctx)
        except AuthError as exc:
            return jsonify(auth_error_payload(exc)), exc.status_code

        data = request.get_json(silent=True) or {}

        try:
            membership = add_workspace_membership(
                user_id=data.get("userId") or data.get("user_id"),
                workspace_id=data.get("workspaceId") or data.get("workspace_id"),
                role=data.get("role") or "member",
            )
            return jsonify({"ok": True, "membership": membership})
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc), "message": str(exc)}), 400




# ---------------------------------------------------------------------
# Stripe Checkout Session creation
# ---------------------------------------------------------------------
if "billing_stripe_checkout_session" not in app.view_functions:
    @app.post("/api/billing/checkout/stripe", endpoint="billing_stripe_checkout_session")
    def billing_stripe_checkout_session():
        from flask import jsonify, request

        from services.auth_context import (
            AuthError,
            auth_context_from_request,
            auth_error_payload,
            require_workspace_access,
        )
        from services.stripe_checkout import (
            StripeCheckoutError,
            StripeCheckoutNotConfigured,
            create_stripe_checkout_session,
        )

        ctx = auth_context_from_request(request)
        data = request.get_json(silent=True) or request.form

        workspace_id = data.get("workspaceId") or ctx.workspace_id
        plan_key = data.get("planKey") or data.get("plan") or "starter"
        customer_email = data.get("customerEmail") or data.get("customer_email") or ""
        success_url = data.get("successUrl") or data.get("success_url") or ""
        cancel_url = data.get("cancelUrl") or data.get("cancel_url") or ""

        try:
            require_workspace_access(ctx, workspace_id)

            payload = create_stripe_checkout_session(
                workspace_id=workspace_id,
                plan_key=plan_key,
                user_id=ctx.user_id,
                customer_email=customer_email,
                success_url=success_url,
                cancel_url=cancel_url,
            )

            return jsonify({
                "ok": True,
                **payload,
            })

        except AuthError as exc:
            return jsonify(auth_error_payload(exc)), exc.status_code

        except StripeCheckoutNotConfigured as exc:
            return jsonify({
                "ok": False,
                "error": str(exc),
                "message": str(exc),
                "provider": "stripe",
                "configured": False,
            }), 501

        except StripeCheckoutError as exc:
            return jsonify({
                "ok": False,
                "error": str(exc),
                "message": str(exc),
                "provider": "stripe",
            }), 400

        except Exception as exc:
            return jsonify({
                "ok": False,
                "error": str(exc),
                "message": str(exc),
                "provider": "stripe",
            }), 500


if "billing_stripe_checkout_status" not in app.view_functions:
    @app.get("/api/billing/checkout/stripe/status", endpoint="billing_stripe_checkout_status")
    def billing_stripe_checkout_status():
        from flask import jsonify
        from services.stripe_checkout import stripe_checkout_status_payload

        return jsonify({
            "ok": True,
            **stripe_checkout_status_payload(),
        })




# ---------------------------------------------------------------------
# Verified Stripe webhook handling
# ---------------------------------------------------------------------


# ---------------------------------------------------------------------
# Verified Stripe webhook endpoint
# ---------------------------------------------------------------------






# ---------------------------------------------------------------------
# Verified Stripe webhook endpoint
# ---------------------------------------------------------------------
@app.before_request
def syntaxmatrix_verified_stripe_webhook_guard():
    from flask import jsonify, request

    if request.path.rstrip("/") != "/api/billing/webhook/stripe":
        return None

    if request.method.upper() != "POST":
        return jsonify({
            "ok": False,
            "error": "Method not allowed. Stripe webhooks must POST to this endpoint.",
            "endpoint": "/api/billing/webhook/stripe",
        }), 405

    from services.stripe_webhooks import (
        StripeWebhookError,
        StripeWebhookNotConfigured,
        StripeWebhookSignatureError,
        verify_and_process_stripe_webhook,
    )

    payload = request.get_data(cache=False, as_text=False)
    signature_header = request.headers.get("Stripe-Signature", "")

    try:
        result = verify_and_process_stripe_webhook(payload, signature_header)

        return jsonify({
            "ok": True,
            "received": True,
            **result,
        }), 200

    except StripeWebhookNotConfigured as exc:
        return jsonify({
            "ok": False,
            "received": False,
            "configured": False,
            "error": str(exc),
            "message": str(exc),
        }), exc.status_code

    except StripeWebhookSignatureError as exc:
        return jsonify({
            "ok": False,
            "received": False,
            "verified": False,
            "error": str(exc),
            "message": str(exc),
        }), exc.status_code

    except StripeWebhookError as exc:
        return jsonify({
            "ok": False,
            "received": False,
            "error": str(exc),
            "message": str(exc),
        }), exc.status_code

    except Exception as exc:
        return jsonify({
            "ok": False,
            "received": False,
            "error": str(exc),
            "message": str(exc),
        }), 500


if "billing_stripe_webhook_status" not in app.view_functions:
    @app.get("/api/billing/webhook/stripe/status", endpoint="billing_stripe_webhook_status")
    def billing_stripe_webhook_status():
        from flask import jsonify
        from services.stripe_webhooks import stripe_webhook_status_payload

        return jsonify({
            "ok": True,
            **stripe_webhook_status_payload(),
        })



# ---------------------------------------------------------------------
# Subscription enforcement for paid Clone Voice product actions
# ---------------------------------------------------------------------
@app.before_request
def syntaxmatrix_subscription_enforcement_guard():
    from flask import jsonify, request

    if not request.path.rstrip("/").startswith("/api/clone-voice/"):
        return None

    from services.auth_context import (
        AuthError,
        auth_context_from_request,
        auth_error_payload,
        require_workspace_access,
    )
    from services.subscription_enforcement import evaluate_flask_request

    ctx = auth_context_from_request(request)

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        data = {}

    workspace_id = (
        request.args.get("workspaceId")
        or request.form.get("workspaceId")
        or data.get("workspaceId")
        or ctx.workspace_id
    )

    try:
        require_workspace_access(ctx, workspace_id)
    except AuthError as exc:
        return jsonify(auth_error_payload(exc)), exc.status_code

    entitlement = evaluate_flask_request(request, ctx)

    if not entitlement.get("enforced"):
        return None

    if entitlement.get("allowed"):
        return None

    return jsonify({
        "ok": False,
        "error": entitlement.get("message"),
        "message": entitlement.get("message"),
        "billingRequired": True,
        "billing": entitlement,
    }), 402


if "billing_entitlement_status" not in app.view_functions:
    @app.get("/api/billing/entitlement", endpoint="billing_entitlement_status")
    def billing_entitlement_status():
        from flask import jsonify, request

        from services.auth_context import (
            AuthError,
            auth_context_from_request,
            auth_error_payload,
            require_workspace_access,
        )
        from services.subscription_enforcement import entitlement_payload

        ctx = auth_context_from_request(request)
        workspace_id = request.args.get("workspaceId") or ctx.workspace_id
        action = request.args.get("action") or "status"
        requested_credits = request.args.get("requestedCredits") or request.args.get("credits") or 0

        try:
            require_workspace_access(ctx, workspace_id)
        except AuthError as exc:
            return jsonify(auth_error_payload(exc)), exc.status_code

        return jsonify({
            "ok": True,
            **entitlement_payload(
                workspace_id=workspace_id,
                action=action,
                requested_credits=requested_credits,
            ),
        })




# ---------------------------------------------------------------------
# Client-safe Stripe billing portal
# ---------------------------------------------------------------------
if "billing_stripe_customer_portal" not in app.view_functions:
    @app.post("/api/billing/portal/stripe", endpoint="billing_stripe_customer_portal")
    def billing_stripe_customer_portal():
        from flask import jsonify, request

        from services.auth_context import (
            AuthError,
            auth_context_from_request,
            auth_error_payload,
            require_workspace_access,
        )
        from services.stripe_customer_portal import (
            StripeCustomerPortalError,
            StripeCustomerPortalMissingCustomer,
            StripeCustomerPortalNotConfigured,
            create_stripe_customer_portal_session,
        )

        ctx = auth_context_from_request(request)
        data = request.get_json(silent=True) or request.form
        workspace_id = data.get("workspaceId") or ctx.workspace_id

        try:
            require_workspace_access(ctx, workspace_id)
            payload = create_stripe_customer_portal_session(workspace_id=workspace_id)

            return jsonify({
                "ok": True,
                **payload,
            })

        except AuthError as exc:
            return jsonify(auth_error_payload(exc)), exc.status_code

        except StripeCustomerPortalMissingCustomer as exc:
            return jsonify({
                "ok": False,
                "provider": "stripe",
                "code": "missing_stripe_customer",
                "error": str(exc),
                "message": str(exc),
            }), 409

        except StripeCustomerPortalNotConfigured as exc:
            return jsonify({
                "ok": False,
                "provider": "stripe",
                "configured": False,
                "error": str(exc),
                "message": str(exc),
            }), 501

        except StripeCustomerPortalError as exc:
            return jsonify({
                "ok": False,
                "provider": "stripe",
                "error": str(exc),
                "message": str(exc),
            }), 400

        except Exception as exc:
            return jsonify({
                "ok": False,
                "provider": "stripe",
                "error": str(exc),
                "message": str(exc),
            }), 500


if "billing_stripe_customer_portal_status" not in app.view_functions:
    @app.get("/api/billing/portal/stripe/status", endpoint="billing_stripe_customer_portal_status")
    def billing_stripe_customer_portal_status():
        from flask import jsonify, request

        from services.auth_context import (
            AuthError,
            auth_context_from_request,
            auth_error_payload,
            require_workspace_access,
        )
        from services.stripe_customer_portal import stripe_customer_portal_status_payload

        ctx = auth_context_from_request(request)
        workspace_id = request.args.get("workspaceId") or ctx.workspace_id

        try:
            require_workspace_access(ctx, workspace_id)
        except AuthError as exc:
            return jsonify(auth_error_payload(exc)), exc.status_code

        return jsonify({
            "ok": True,
            **stripe_customer_portal_status_payload(workspace_id),
        })



# ---------------------------------------------------------------------
# Admin Stripe Product/Price catalog sync
# ---------------------------------------------------------------------
if "billing_stripe_price_catalog_status" not in app.view_functions:
    @app.get("/api/billing/stripe/catalog/status", endpoint="billing_stripe_price_catalog_status")
    def billing_stripe_price_catalog_status():
        from flask import jsonify, request

        from services.auth_context import (
            AuthError,
            auth_context_from_request,
            auth_error_payload,
            require_admin,
        )
        from services.stripe_price_catalog import stripe_price_catalog_status_payload

        ctx = auth_context_from_request(request)

        try:
            require_admin(ctx)
        except AuthError as exc:
            return jsonify(auth_error_payload(exc)), exc.status_code

        return jsonify({
            "ok": True,
            **stripe_price_catalog_status_payload(),
        })


if "billing_stripe_price_catalog_sync" not in app.view_functions:
    @app.post("/api/billing/stripe/catalog/sync", endpoint="billing_stripe_price_catalog_sync")
    def billing_stripe_price_catalog_sync():
        from flask import jsonify, request

        from services.auth_context import (
            AuthError,
            auth_context_from_request,
            auth_error_payload,
            require_admin,
        )
        from services.stripe_price_catalog import (
            StripePriceCatalogError,
            StripePriceCatalogNotConfigured,
            sync_stripe_price_catalog,
        )

        ctx = auth_context_from_request(request)

        try:
            require_admin(ctx)
        except AuthError as exc:
            return jsonify(auth_error_payload(exc)), exc.status_code

        try:
            payload = sync_stripe_price_catalog()

            return jsonify({
                "ok": True,
                **payload,
            })

        except StripePriceCatalogNotConfigured as exc:
            return jsonify({
                "ok": False,
                "provider": "stripe",
                "configured": False,
                "error": str(exc),
                "message": str(exc),
            }), 501

        except StripePriceCatalogError as exc:
            return jsonify({
                "ok": False,
                "provider": "stripe",
                "error": str(exc),
                "message": str(exc),
            }), 400

        except Exception as exc:
            return jsonify({
                "ok": False,
                "provider": "stripe",
                "error": str(exc),
                "message": str(exc),
            }), 500



# ---------------------------------------------------------------------
# Admin persistence status
# ---------------------------------------------------------------------
if "admin_persistence_status" not in app.view_functions:
    @app.get("/api/admin/persistence/status", endpoint="admin_persistence_status")
    def admin_persistence_status():
        from flask import jsonify, request

        from services.auth_context import (
            AuthError,
            auth_context_from_request,
            auth_error_payload,
            require_admin,
        )
        from services.persistence_status import persistence_status_payload

        ctx = auth_context_from_request(request)

        try:
            require_admin(ctx)
        except AuthError as exc:
            return jsonify(auth_error_payload(exc)), exc.status_code

        return jsonify({
            "ok": True,
            **persistence_status_payload(),
        })



# ---------------------------------------------------------------------
# Hard guard for Admin Persistence Status API
# Prevents /api/admin/persistence/status from falling through to Media Studio.
# ---------------------------------------------------------------------
@app.before_request
def syntaxmatrix_persistence_status_before_request_guard():
    from flask import jsonify, request

    if request.path.rstrip("/") != "/api/admin/persistence/status":
        return None

    if request.method.upper() != "GET":
        return jsonify({
            "ok": False,
            "error": "Method not allowed.",
            "endpoint": "/api/admin/persistence/status",
        }), 405

    from services.auth_context import (
        AuthError,
        auth_context_from_request,
        auth_error_payload,
        require_admin,
    )
    from services.persistence_status import persistence_status_payload

    ctx = auth_context_from_request(request)

    try:
        require_admin(ctx)
    except AuthError as exc:
        return jsonify(auth_error_payload(exc)), exc.status_code

    return jsonify({
        "ok": True,
        **persistence_status_payload(),
    })




# ---------------------------------------------------------------------
# Hard guard for Admin Persistence Repository Status API
# ---------------------------------------------------------------------
@app.before_request
def syntaxmatrix_persistence_repository_status_guard():
    from flask import jsonify, request

    if request.path.rstrip("/") != "/api/admin/persistence/repository/status":
        return None

    if request.method.upper() != "GET":
        return jsonify({
            "ok": False,
            "error": "Method not allowed.",
            "endpoint": "/api/admin/persistence/repository/status",
        }), 405

    from services.auth_context import (
        AuthError,
        auth_context_from_request,
        auth_error_payload,
        require_admin,
    )
    from services.persistence_repository import repository_smoke_test

    ctx = auth_context_from_request(request)

    try:
        require_admin(ctx)
    except AuthError as exc:
        return jsonify(auth_error_payload(exc)), exc.status_code

    return jsonify({
        "ok": True,
        **repository_smoke_test(),
    })




# ---------------------------------------------------------------------
# Hard guard for repository wiring status
# ---------------------------------------------------------------------
@app.before_request
def syntaxmatrix_repository_wiring_status_guard():
    from flask import jsonify, request

    if request.path.rstrip("/") != "/api/admin/persistence/wiring/status":
        return None

    if request.method.upper() != "GET":
        return jsonify({
            "ok": False,
            "error": "Method not allowed.",
            "endpoint": "/api/admin/persistence/wiring/status",
        }), 405

    from services.auth_context import (
        AuthError,
        auth_context_from_request,
        auth_error_payload,
        require_admin,
    )
    from services.persistence_repository import get_persistence_repository, repository_smoke_test

    ctx = auth_context_from_request(request)

    try:
        require_admin(ctx)
    except AuthError as exc:
        return jsonify(auth_error_payload(exc)), exc.status_code

    repo = get_persistence_repository()
    smoke = repository_smoke_test()

    return jsonify({
        "ok": True,
        "backend": repo.backend_name,
        "repository": smoke,
        "wired": {
            "subscriptionEnforcementReads": True,
            "usageCreditReads": True,
            "stripeWebhookSubscriptionWrites": True,
            "stripeWebhookProcessedEvents": True,
            "stripeWebhookEventLogging": True,
        },
    })




# ---------------------------------------------------------------------
# Hard guard for persistence migration readiness/status
# ---------------------------------------------------------------------
@app.before_request
def syntaxmatrix_persistence_migration_status_guard():
    from flask import jsonify, request

    if request.path.rstrip("/") != "/api/admin/persistence/migration/status":
        return None

    if request.method.upper() != "GET":
        return jsonify({
            "ok": False,
            "error": "Method not allowed.",
            "endpoint": "/api/admin/persistence/migration/status",
        }), 405

    from services.auth_context import (
        AuthError,
        auth_context_from_request,
        auth_error_payload,
        require_admin,
    )
    from services.persistence_repository import get_persistence_repository, repository_smoke_test
    from services.persistence_status import persistence_status_payload
    from scripts.export_json_persistence_snapshot import build_snapshot

    ctx = auth_context_from_request(request)

    try:
        require_admin(ctx)
    except AuthError as exc:
        return jsonify(auth_error_payload(exc)), exc.status_code

    snapshot = build_snapshot()
    repo = get_persistence_repository()

    return jsonify({
        "ok": True,
        "backend": repo.backend_name,
        "jsonSnapshotCounts": snapshot.get("counts", {}),
        "persistence": persistence_status_payload(),
        "repository": repository_smoke_test(),
        "tools": {
            "exportSnapshot": "python scripts/export_json_persistence_snapshot.py",
            "dryRunMigration": "python scripts/migrate_json_to_postgres.py --dry-run",
            "applyMigration": "python scripts/migrate_json_to_postgres.py --apply --init-schema",
        },
        "migrationApplied": False,
    })




# ---------------------------------------------------------------------
# Hard guard for object storage status
# ---------------------------------------------------------------------
@app.before_request
def syntaxmatrix_object_storage_status_guard():
    from flask import jsonify, request

    if request.path.rstrip("/") != "/api/admin/storage/status":
        return None

    if request.method.upper() != "GET":
        return jsonify({
            "ok": False,
            "error": "Method not allowed.",
            "endpoint": "/api/admin/storage/status",
        }), 405

    from services.auth_context import (
        AuthError,
        auth_context_from_request,
        auth_error_payload,
        require_admin,
    )
    from services.object_storage import object_storage_status_payload

    ctx = auth_context_from_request(request)

    try:
        require_admin(ctx)
    except AuthError as exc:
        return jsonify(auth_error_payload(exc)), exc.status_code

    return jsonify({
        "ok": True,
        **object_storage_status_payload(),
    })




# ---------------------------------------------------------------------
# Hard guard for object storage media audit
# ---------------------------------------------------------------------
@app.before_request
def syntaxmatrix_object_storage_media_audit_guard():
    from flask import jsonify, request

    if request.path.rstrip("/") != "/api/admin/storage/media-audit":
        return None

    if request.method.upper() != "GET":
        return jsonify({
            "ok": False,
            "error": "Method not allowed.",
            "endpoint": "/api/admin/storage/media-audit",
        }), 405

    from services.auth_context import (
        AuthError,
        auth_context_from_request,
        auth_error_payload,
        require_admin,
    )
    from services.object_storage_media_audit import object_storage_media_audit_payload

    ctx = auth_context_from_request(request)

    try:
        require_admin(ctx)
    except AuthError as exc:
        return jsonify(auth_error_payload(exc)), exc.status_code

    return jsonify({
        "ok": True,
        **object_storage_media_audit_payload(),
    })




# ---------------------------------------------------------------------
# WSGI-LEVEL API GUARD: storage media backfill
# ---------------------------------------------------------------------
if "syntaxmatrix_storage_backfill_wsgi_guard_installed" not in globals():
    syntaxmatrix_storage_backfill_wsgi_guard_installed = True
    _syntaxmatrix_storage_backfill_previous_wsgi_app = app.wsgi_app

    def _syntaxmatrix_storage_backfill_wsgi_guard(environ, start_response):
        path = str(environ.get("PATH_INFO") or "").rstrip("/")

        if path != "/api/admin/storage/backfill":
            return _syntaxmatrix_storage_backfill_previous_wsgi_app(environ, start_response)

        with app.request_context(environ):
            from flask import jsonify, request

            if request.method.upper() != "POST":
                response = jsonify({
                    "ok": False,
                    "error": "Method not allowed.",
                    "endpoint": path,
                })
                response.status_code = 405
                return response(environ, start_response)

            try:
                from services.auth_context import (
                    AuthError,
                    auth_context_from_request,
                    auth_error_payload,
                    require_admin,
                )

                ctx = auth_context_from_request(request)
                require_admin(ctx)

            except AuthError as exc:
                response = jsonify(auth_error_payload(exc))
                response.status_code = exc.status_code
                return response(environ, start_response)

            try:
                from scripts.backfill_workspace_media_to_object_storage import backfill_workspace_media

                data = request.get_json(silent=True) or {}
                dry_run = not bool(data.get("apply"))
                payload = backfill_workspace_media(dry_run=dry_run)

                response = jsonify(payload)
                response.status_code = 200 if payload.get("ok") else 500
                return response(environ, start_response)

            except Exception as exc:
                response = jsonify({
                    "ok": False,
                    "error": str(exc),
                    "endpoint": path,
                })
                response.status_code = 500
                return response(environ, start_response)

    app.wsgi_app = _syntaxmatrix_storage_backfill_wsgi_guard


# === STAGE9F2_FIREBASE_FRONTEND_AUTH_START ===
# Firebase browser auth routes. These are public because users must load the
# login/register page before they have an ID token.
if "stage9f2_auth_page" not in app.view_functions:
    @app.get("/auth", endpoint="stage9f2_auth_page")
    @app.get("/auth/", endpoint="stage9f2_auth_page_slash")
    def stage9f2_auth_page():
        from pathlib import Path
        from flask import send_from_directory

        frontend_dir = Path(__file__).resolve().parent / "frontend" / "clone_voice"
        return send_from_directory(frontend_dir, "auth.html")


if "stage9f2_auth_asset" not in app.view_functions:
    @app.get("/<path:asset_name>", endpoint="stage9f2_auth_asset")
    def stage9f2_auth_asset(asset_name: str):
        from pathlib import Path
        from flask import abort, send_from_directory

        allowed = {
            "auth.css",
            "auth.js",
            "auth_bootstrap.js",
        }

        if asset_name not in allowed:
            abort(404)

        frontend_dir = Path(__file__).resolve().parent / "frontend" / "clone_voice"
        return send_from_directory(frontend_dir, asset_name)


if "stage9f2_firebase_config" not in app.view_functions:
    @app.get("/api/auth/firebase-config", endpoint="stage9f2_firebase_config")
    def stage9f2_firebase_config():
        import os
        from flask import jsonify

        def clean(name: str) -> str:
            return str(os.getenv(name) or "").strip()

        firebase_config = {
            "apiKey": clean("FIREBASE_API_KEY"),
            "authDomain": clean("FIREBASE_AUTH_DOMAIN"),
            "projectId": clean("FIREBASE_PROJECT_ID"),
            "appId": clean("FIREBASE_APP_ID"),
        }

        optional_values = {
            "storageBucket": clean("FIREBASE_STORAGE_BUCKET"),
            "messagingSenderId": clean("FIREBASE_MESSAGING_SENDER_ID"),
        }

        for key, value in optional_values.items():
            if value:
                firebase_config[key] = value

        missing = [
            key
            for key, value in firebase_config.items()
            if key in {"apiKey", "authDomain", "projectId", "appId"} and not value
        ]

        if missing:
            return jsonify({
                "ok": False,
                "error": "Firebase browser configuration is incomplete.",
                "message": "Firebase browser configuration is incomplete.",
                "missing": missing,
            }), 500

        return jsonify({
            "ok": True,
            "authProvider": clean("AUTH_PROVIDER") or "dev",
            "firebaseConfig": firebase_config,
        })
# === STAGE9F2_FIREBASE_FRONTEND_AUTH_END ===




# === PAID_LAUNCH_SESSION_AND_PLANS_START ===
if "paid_launch_auth_session_create" not in app.view_functions:
    @app.post("/api/auth/session", endpoint="paid_launch_auth_session_create")
    def paid_launch_auth_session_create():
        from flask import jsonify, make_response, request
        from services.firebase_auth import (
            FirebaseAuthError,
            create_firebase_session_cookie,
            verify_firebase_id_token,
        )
        from services.firebase_page_session import session_cookie_name

        data = request.get_json(silent=True) or {}
        id_token = str(data.get("idToken") or "").strip()
        remember = bool(data.get("remember"))

        if not id_token:
            return jsonify({"ok": False, "error": "idToken is required.", "message": "idToken is required."}), 400

        expires_in = 14 * 24 * 60 * 60 if remember else 12 * 60 * 60

        try:
            decoded = verify_firebase_id_token(id_token)
            cookie = create_firebase_session_cookie(id_token, expires_in_seconds=expires_in)
        except FirebaseAuthError as exc:
            return jsonify({"ok": False, "error": str(exc), "message": str(exc)}), 401

        response = make_response(jsonify({
            "ok": True,
            "email": str(decoded.get("email") or ""),
            "remember": remember,
            "expiresIn": expires_in,
        }))

        forwarded_proto = str(request.headers.get("X-Forwarded-Proto") or "").lower()
        secure_cookie = bool(request.is_secure or forwarded_proto == "https")
        response.set_cookie(
            session_cookie_name(),
            cookie,
            max_age=expires_in,
            httponly=True,
            secure=secure_cookie,
            samesite="Lax",
            path="/",
        )
        return response


if "paid_launch_auth_session_delete" not in app.view_functions:
    @app.delete("/api/auth/session", endpoint="paid_launch_auth_session_delete")
    def paid_launch_auth_session_delete():
        from flask import jsonify, make_response
        from services.firebase_page_session import session_cookie_name

        response = make_response(jsonify({"ok": True}))
        response.delete_cookie(session_cookie_name(), path="/")
        return response


if "paid_launch_plans_page" not in app.view_functions:
    @app.get("/plans", endpoint="paid_launch_plans_page")
    def paid_launch_plans_page():
        from flask import send_from_directory
        frontend_dir = Path(__file__).resolve().parent / "frontend" / "clone_voice"
        return send_from_directory(frontend_dir, "plans.html")


if "paid_launch_billing_plans" not in app.view_functions:
    @app.get("/api/billing/plans", endpoint="paid_launch_billing_plans")
    def paid_launch_billing_plans():
        from flask import jsonify, request
        from services.auth_context import AuthError, auth_context_from_request, auth_error_payload
        from services.billing_pricing import get_pricing_config
        from services.stripe_price_catalog import get_stripe_price_for_plan

        try:
            auth_context_from_request(request)
        except AuthError as exc:
            return jsonify(auth_error_payload(exc)), exc.status_code

        config = get_pricing_config()
        rows = []
        for plan in config.get("plans", []):
            if not isinstance(plan, dict):
                continue
            key = str(plan.get("key") or "").strip().lower()
            if key not in {"starter", "pro", "business"}:
                continue
            rows.append({
                "key": key,
                "label": plan.get("label") or key.title(),
                "monthlyPrice": plan.get("monthlyPrice"),
                "monthlyCredits": plan.get("monthlyCredits"),
                "description": plan.get("description") or "",
                # These are valid customer-selectable paid plans.
                # Stripe Checkout performs the authoritative runtime
                # validation and supports both persistent Price IDs and
                # the existing recurring inline-price fallback.
                "available": bool(
                    key in {"starter", "pro", "business"}
                    and float(plan.get("monthlyPrice") or 0) > 0
                ),
            })

        return jsonify({
            "ok": True,
            "currency": str(config.get("currency") or "EUR").upper(),
            "plans": rows,
        })
# === PAID_LAUNCH_SESSION_AND_PLANS_END ===


# === STAGE9F3_ACCOUNT_ONBOARDING_TENANT_GATE_START ===

def _stage9f3_auth_provider() -> str:
    import os
    return str(os.getenv("AUTH_PROVIDER") or "").strip().lower()


def _stage9f3_firebase_mode() -> bool:
    return _stage9f3_auth_provider() in {"firebase", "identity_platform", "google_identity_platform"}


def _stage9f3_json_response(payload: dict, status: int = 200):
    from flask import jsonify
    return jsonify(payload), status


def _stage9f3_request_workspace_id():
    from flask import request

    value = (
        request.args.get("workspaceId")
        or request.args.get("workspace_id")
        or request.form.get("workspaceId")
        or request.form.get("workspace_id")
    )

    if value:
        return str(value).strip()

    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        data = request.get_json(silent=True)
        if isinstance(data, dict):
            return str(
                data.get("workspaceId")
                or data.get("workspace_id")
                or ""
            ).strip()

    return ""


def _stage9f3_workspace_id_required_path(path: str) -> bool:
    exact = {
        "/api/clone-voice/my-voices",
        "/api/clone-voice/voices/from-source",
        "/api/clone-voice/source-uploads/workspace/session",
        "/api/clone-voice/source-uploads/workspace/complete",
        "/api/clone-voice/source-uploads/workspace/replace",
        "/api/clone-voice/from-saved",
        "/api/clone-voice/from-system",
        "/api/billing/usage",
        "/api/billing/subscription",
        "/api/billing/economics",
        "/api/billing/checkout/stripe",
        "/api/billing/portal/stripe",
        "/api/billing/portal/stripe/status",
    }

    prefixes = (
        "/api/clone-voice/my-voices/",
    )

    return path in exact or any(path.startswith(prefix) for prefix in prefixes)


def _stage9f3_public_path(path: str) -> bool:
    if path in {
        "/auth",
        "/auth/",
        "/auth.css",
        "/auth.js",
        "/auth_bootstrap.js",
        "/api/auth/firebase-config",
        "/api/auth/session",
    }:
        return True

    if path.startswith("/api/billing/webhook/"):
        return True

    if path.startswith("/static/"):
        return True

    return False


if "stage9f3_account_bootstrap" not in app.view_functions:
    @app.post("/api/account/bootstrap", endpoint="stage9f3_account_bootstrap")
    @app.get("/api/account/bootstrap", endpoint="stage9f3_account_bootstrap_get")
    def stage9f3_account_bootstrap():
        from flask import jsonify, request

        from services.auth_context import AuthError, auth_context_from_request, auth_error_payload
        from services.customer_workspace import bootstrap_firebase_user_workspace, workspace_selector_payload

        try:
            ctx = auth_context_from_request(request)
        except AuthError as exc:
            return jsonify(auth_error_payload(exc)), exc.status_code

        if ctx.auth_mode != "firebase":
            return jsonify({
                "ok": False,
                "error": "Firebase authentication is required for account bootstrap.",
                "message": "Firebase authentication is required for account bootstrap.",
                "authMode": ctx.auth_mode,
            }), 403

        result = bootstrap_firebase_user_workspace(
            user_id=ctx.user_id,
            email=getattr(ctx, "email", ""),
            display_name=getattr(ctx, "email", "").split("@")[0] if getattr(ctx, "email", "") else "",
        )

        selector = workspace_selector_payload(ctx.user_id, ctx.role, result["workspace"]["workspaceId"])

        return jsonify({
            "ok": True,
            "created": bool(result.get("created")),
            "user": ctx.to_payload(),
            "customer": result.get("customer"),
            "workspace": result.get("workspace"),
            "membership": result.get("membership"),
            **selector,
        })


@app.before_request
def stage9f3_firebase_tenant_gate():
    from flask import jsonify, request

    if not _stage9f3_firebase_mode():
        return None

    path = request.path or ""

    if _stage9f3_public_path(path):
        return None

    # Only app/API/media workspace traffic is guarded here.
    # HTML pages load first; their fetch calls are protected by this gate.
    guarded = path.startswith("/api/") or path.startswith("/media/workspaces/")
    if not guarded:
        return None

    from services.auth_context import AuthError, auth_context_from_request, auth_error_payload, require_workspace_access

    try:
        ctx = auth_context_from_request(request)
    except AuthError as exc:
        return jsonify(auth_error_payload(exc)), exc.status_code

    # Bootstrap needs identity, but it must work before the user's first workspace exists.
    if path in {"/api/account/bootstrap"}:
        return None

    # Workspace media URLs contain the workspace ID in the path.
    if path.startswith("/media/workspaces/"):
        parts = [part for part in path.split("/") if part]
        workspace_id = parts[2] if len(parts) >= 3 else ""
        try:
            require_workspace_access(ctx, workspace_id)
        except AuthError as exc:
            return jsonify(auth_error_payload(exc)), exc.status_code
        return None

    requested_workspace_id = _stage9f3_request_workspace_id()

    if requested_workspace_id:
        try:
            require_workspace_access(ctx, requested_workspace_id)
        except AuthError as exc:
            return jsonify(auth_error_payload(exc)), exc.status_code
        return None

    if _stage9f3_workspace_id_required_path(path):
        return jsonify({
            "ok": False,
            "error": "workspaceId is required.",
            "message": "workspaceId is required.",
            "authMode": ctx.auth_mode,
            "path": path,
        }), 400

    return None


def stage9f3_clone_voice_workspaces_override():
    from flask import jsonify, request

    from services.auth_context import AuthError, auth_context_from_request, auth_error_payload
    from services.customer_workspace import workspace_selector_payload

    try:
        ctx = auth_context_from_request(request)
    except AuthError as exc:
        return jsonify(auth_error_payload(exc)), exc.status_code

    payload = workspace_selector_payload(ctx.user_id, ctx.role, ctx.workspace_id)

    return jsonify({
        "ok": True,
        "user": ctx.to_payload(),
        **payload,
    })


# Replace the clone-voice workspace selector response with the account-aware selector.
# This avoids trusting the old demo workspace list after Firebase auth is enabled.
if "clone_voice_workspaces" in app.view_functions:
    app.view_functions["clone_voice_workspaces"] = stage9f3_clone_voice_workspaces_override
else:
    app.add_url_rule(
        "/api/clone-voice/workspaces",
        endpoint="clone_voice_workspaces",
        view_func=stage9f3_clone_voice_workspaces_override,
        methods=["GET"],
    )


# Also override /api/account/workspaces if the old route exists.
if "account_workspaces" in app.view_functions:
    app.view_functions["account_workspaces"] = stage9f3_clone_voice_workspaces_override

# === STAGE9F3_ACCOUNT_ONBOARDING_TENANT_GATE_END ===




# === STAGE9F3C_AUTHERROR_GUARD_WRAPPER_START ===
# Hard safety wrapper for older before_request guards that call
# auth_context_from_request(request) directly. In Firebase mode, those calls
# raise AuthError when the Bearer token is missing/invalid. This wrapper makes
# those failures return clean JSON 401/403 instead of Flask 500 errors.
if "stage9f3c_auth_error_handler_registered" not in app.config:
    from flask import jsonify
    from services.auth_context import AuthError, auth_error_payload

    @app.errorhandler(AuthError)
    def stage9f3c_handle_auth_error(exc):
        return jsonify(auth_error_payload(exc)), exc.status_code

    def stage9f3c_wrap_before_request_guard(original_func):
        def wrapped_guard(*args, **kwargs):
            try:
                return original_func(*args, **kwargs)
            except AuthError as exc:
                return jsonify(auth_error_payload(exc)), exc.status_code

        wrapped_guard.__name__ = f"stage9f3c_wrapped_{getattr(original_func, '__name__', 'before_request_guard')}"
        wrapped_guard.__doc__ = getattr(original_func, "__doc__", None)
        return wrapped_guard

    before_funcs = list(app.before_request_funcs.get(None, []))
    wrapped_funcs = []

    for func in before_funcs:
        name = getattr(func, "__name__", "")

        if name == "syntaxmatrix_subscription_enforcement_guard":
            wrapped_funcs.append(stage9f3c_wrap_before_request_guard(func))
        else:
            wrapped_funcs.append(func)

    app.before_request_funcs[None] = wrapped_funcs
    app.config["stage9f3c_auth_error_handler_registered"] = True
# === STAGE9F3C_AUTHERROR_GUARD_WRAPPER_END ===




# === STAGE9G1_HARD_AUTH_ASSET_WSGI_START ===
# Hard WSGI bypass for auth page/assets. Some older catch-all frontend routes
# serve index.html for unknown top-level files, which breaks /auth.css and /auth.js.
# This bypass runs before Flask routing and returns the correct auth files directly.
if "stage9g1_hard_auth_asset_wsgi_installed" not in app.config:
    import mimetypes
    from pathlib import Path

    _stage9g1_original_wsgi_app = app.wsgi_app
    _stage9g1_frontend_dir = Path(__file__).resolve().parent / "frontend" / "clone_voice"

    _stage9g1_auth_files = {
        "/auth": ("auth.html", "text/html; charset=utf-8"),
        "/auth/": ("auth.html", "text/html; charset=utf-8"),
        "/auth.css": ("auth.css", "text/css; charset=utf-8"),
        "/auth.js": ("auth.js", "application/javascript; charset=utf-8"),
        "/auth_bootstrap.js": ("auth_bootstrap.js", "application/javascript; charset=utf-8"),
    }

    def _stage9g1_response(start_response, status, content_type, body: bytes):
        headers = [
            ("Content-Type", content_type),
            ("Content-Length", str(len(body))),
            ("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0"),
            ("Pragma", "no-cache"),
            ("Expires", "0"),
        ]
        start_response(status, headers)
        return [body]

    def _stage9g1_hard_auth_asset_wsgi(environ, start_response):
        path = environ.get("PATH_INFO") or ""

        if path in _stage9g1_auth_files:
            filename, content_type = _stage9g1_auth_files[path]
            file_path = _stage9g1_frontend_dir / filename

            if file_path.exists() and file_path.is_file():
                return _stage9g1_response(
                    start_response,
                    "200 OK",
                    content_type,
                    file_path.read_bytes(),
                )

            body = f"Missing auth asset: {filename}".encode("utf-8")
            return _stage9g1_response(
                start_response,
                "404 Not Found",
                "text/plain; charset=utf-8",
                body,
            )

        return _stage9g1_original_wsgi_app(environ, start_response)

    app.wsgi_app = _stage9g1_hard_auth_asset_wsgi
    app.config["stage9g1_hard_auth_asset_wsgi_installed"] = True
# === STAGE9G1_HARD_AUTH_ASSET_WSGI_END ===




# === STAGE9H1_UPLOAD_LIMIT_AND_413_JSON_START ===
# Cloud/private-beta upload limit. WAV files can be large, so keep this above
# the preview duration limit. This prevents Flask from returning an HTML 413
# page that the frontend then tries to parse as JSON.
if "stage9h1_upload_limit_configured" not in app.config:
    import os
    from flask import jsonify
    from werkzeug.exceptions import RequestEntityTooLarge

    _stage9h1_upload_mb = int(os.getenv("ALIBABA_MEDIA_MAX_UPLOAD_MB", "80"))
    app.config["MAX_CONTENT_LENGTH"] = _stage9h1_upload_mb * 1024 * 1024

    @app.errorhandler(RequestEntityTooLarge)
    def stage9h1_request_entity_too_large(exc):
        return jsonify({
            "ok": False,
            "error": "Uploaded file is too large.",
            "message": f"Uploaded file is too large. Maximum upload size is {_stage9h1_upload_mb} MB.",
            "maxUploadMb": _stage9h1_upload_mb,
        }), 413

    app.config["stage9h1_upload_limit_configured"] = True
# === STAGE9H1_UPLOAD_LIMIT_AND_413_JSON_END ===




# === STAGE9H2_WORKSPACE_DISCOVERY_GUARD_FIX_START ===
# These endpoints are identity-required but workspace-discovery/bootstrap endpoints.
# They must not be blocked by subscription enforcement before a workspace has been selected.
if "stage9h2_workspace_discovery_guard_fix_installed" not in app.config:
    from flask import jsonify, request
    from services.auth_context import AuthError, auth_context_from_request, auth_error_payload

    _stage9h2_original_before_funcs = list(app.before_request_funcs.get(None, []))

    _stage9h2_discovery_paths = {
        "/api/account/bootstrap",
        "/api/account/workspaces",
        "/api/clone-voice/workspaces",
    }

    def _stage9h2_identity_only_workspace_discovery_guard():
        path = request.path or ""

        if path not in _stage9h2_discovery_paths:
            return None

        try:
            # Require a valid Firebase identity, but do not require workspaceId yet.
            auth_context_from_request(request)
            return None
        except AuthError as exc:
            return jsonify(auth_error_payload(exc)), exc.status_code

    def _stage9h2_skip_subscription_guard_for_discovery(original_func):
        def wrapped_guard(*args, **kwargs):
            path = request.path or ""
            if path in _stage9h2_discovery_paths:
                return None
            return original_func(*args, **kwargs)

        wrapped_guard.__name__ = f"stage9h2_wrapped_{getattr(original_func, '__name__', 'guard')}"
        wrapped_guard.__doc__ = getattr(original_func, "__doc__", None)
        return wrapped_guard

    _stage9h2_new_before_funcs = [
        _stage9h2_identity_only_workspace_discovery_guard
    ]

    for func in _stage9h2_original_before_funcs:
        name = getattr(func, "__name__", "")

        # The subscription guard is the one causing workspace discovery to fail.
        if "syntaxmatrix_subscription_enforcement_guard" in name:
            _stage9h2_new_before_funcs.append(_stage9h2_skip_subscription_guard_for_discovery(func))
        elif "stage9f3c_wrapped_syntaxmatrix_subscription_enforcement_guard" in name:
            _stage9h2_new_before_funcs.append(_stage9h2_skip_subscription_guard_for_discovery(func))
        else:
            _stage9h2_new_before_funcs.append(func)

    app.before_request_funcs[None] = _stage9h2_new_before_funcs
    app.config["stage9h2_workspace_discovery_guard_fix_installed"] = True
# === STAGE9H2_WORKSPACE_DISCOVERY_GUARD_FIX_END ===


if __name__ == "__main__":
    print("SyntaxMatrix Media Studio Flask")
    print(f"Open: http://{HOST}:{PORT}")
    print("Edit → Image upload contract: multipart field name 'image' repeated in Image 1 → Image 2 → Image 3 order")
    app.run(host=HOST, port=PORT, debug=os.getenv("FLASK_DEBUG", "0") == "1")
