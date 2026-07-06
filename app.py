from __future__ import annotations

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

    # Friendly SPA-style fallback.
    return send_from_directory(FRONTEND_DIR, "index.html")

@app.errorhandler(413)
def upload_too_large(_exc):
    return _json_error("Upload is too large. Increase the max upload MB setting if needed.", 413)

@app.errorhandler(Exception)
def unhandled(exc):
    traceback.print_exc()
    return _json_error(str(exc), 500)

if __name__ == "__main__":
    print("SyntaxMatrix Media Studio Flask")
    print(f"Open: http://{HOST}:{PORT}")
    print("Edit → Image upload contract: multipart field name 'image' repeated in Image 1 → Image 2 → Image 3 order")
    app.run(host=HOST, port=PORT, debug=os.getenv("FLASK_DEBUG", "0") == "1")
