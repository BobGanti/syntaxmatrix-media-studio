from __future__ import annotations

import pathlib

from flask import Response, jsonify, request, send_from_directory

from services.clone_voice_audio_policy import (
    VoiceSourcePolicyError,
    apply_narration_speed_to_file,
    get_max_voice_source_seconds,
    narration_speed_payload,
    normalize_generated_audio_file,
    prepare_voice_source_audio,
    settings_payload,
    set_max_voice_source_seconds,
)
from services.clone_voice_provider import create_voice_parameter, generate_narration_to_file
from services.clone_voice_style import generate_narration_to_file_with_style
from services.auth_context import (
    AuthError,
    auth_context_from_request,
    auth_error_payload,
    require_admin,
    require_workspace_access,
)
from services.customer_workspace import workspace_selector_payload
from services.billing_provider import (
    BillingProviderError,
    BillingWebhookNotReady,
    billing_provider_status_payload,
    process_dev_subscription_simulation,
    process_provider_webhook,
)
from services.billing_usage import (
    QuotaExceededError,
    assert_workspace_can_spend,
    assert_workspace_can_create_custom_voice,
    assert_workspace_can_use_custom_voice,
    custom_voice_entitlement,
    audio_duration_seconds,
    billing_plans_payload,
    estimate_credits,
    estimate_narration_credits_from_text,
    estimate_voice_creation_credits,
    get_workspace_subscription,
    economics_summary,
    pricing_config_payload,
    quota_status,
    record_usage_event,
    set_workspace_plan,
    update_pricing_config,
    usage_summary,
)
from services.clone_voice_system import (
    SYSTEM_PREVIEWS_DIR,
    delete_system_voice,
    list_system_voices_payload,
    load_system_voice_parameter,
    save_system_voice_from_path,
    save_system_voice_from_source,
)
from services.voice_source_ingestion import (
    VoiceSourceUploadError,
    create_system_upload_session,
    create_workspace_upload_session,
    delete_temporary_upload,
    download_completed_upload,
    system_temporary_prefix,
    workspace_temporary_prefix,
)
from services.clone_voice_workspace import (
    MOCK_WORKSPACE_ID,
    STANDARD_VOICE_PREVIEW_TEXT,
    delete_if_exists,
    delete_workspace_voice,
    display_name_from_voice_id,
    generated_audio_path,
    get_workspace,
    list_workspace_voice_parameters,
    list_demo_workspaces,
    load_voice_metadata,
    load_workspace_voice_parameter,
    new_recorded_voice_id,
    normalize_gender,
    relative_to_root,
    save_source_audio,
    save_voice_metadata,
    save_voice_parameter,
    source_limited_path,
    stable_preview_path,
    voice_id_from_source_filename,
    voice_parameter_exists,
    workspace_generated_audio_url,
    workspace_voice_preview_url,
)






# >>> SMX_CUSTOM_VOICE_PLAN_GUARD >>>
def _smx_custom_voice_block_response(workspace_id: str):
    """Return a Flask error response when the active plan cannot create private voices."""
    try:
        subscription = get_workspace_subscription(workspace_id)
        plan_key = str(subscription.get("planKey") or "").strip().lower()
        plan = subscription.get("plan") or {}

        raw_slots = plan.get("maxCustomVoices", plan.get("cloneSlots"))
        if raw_slots is None:
            slots = None
        else:
            try:
                slots = int(float(raw_slots))
            except Exception:
                slots = 0

        blocked = (
            plan_key == "free"
            or bool(plan.get("systemVoicesOnly"))
            or slots == 0
        )

        if blocked:
            return _error(
                "Your Free plan uses system voices only. Upgrade to Starter or higher to create saved custom voices.",
                403,
            )
    except Exception as exc:
        print("[clone_voice_controller] custom voice entitlement check failed:", repr(exc), flush=True)
        return _error("Could not verify voice-cloning entitlement.", 403)

    return None
# <<< SMX_CUSTOM_VOICE_PLAN_GUARD <<<


def _workspace_media_response_from_object_storage(workspace_id: str, category: str, filename: str):
    import mimetypes

    try:
        from services.object_storage import (
            get_object_storage,
            object_key_for_generated_audio,
            object_key_for_voice_preview,
        )

        if category == "generated_audio":
            key = object_key_for_generated_audio(workspace_id, filename)
        elif category == "voice_previews":
            key = object_key_for_voice_preview(workspace_id, filename)
        else:
            return None

        storage = get_object_storage()

        if not storage.exists(key):
            return None

        data = storage.read_bytes(key)
        mimetype = mimetypes.guess_type(filename)[0] or "audio/wav"

        return Response(
            data,
            mimetype=mimetype,
            headers={
                "Cache-Control": "private, max-age=3600",
                "X-SyntaxMatrix-Object-Storage": storage.backend_name,
            },
        )

    except Exception as exc:
        print(
            "[clone_voice_controller] Object storage media read failed:",
            workspace_id,
            category,
            filename,
            repr(exc),
            flush=True,
        )
        return None


def _error(message: str, status: int = 500):
    return jsonify({"ok": False, "message": message, "error": message}), status


def _quota_error_response(exc: QuotaExceededError):
    payload = getattr(exc, "payload", None) or {"message": str(exc)}
    return jsonify({"ok": False, "error": payload.get("message"), **payload}), 402


def _generate_and_normalize(voice_parameter: str, prompt: str, workspace, title: str, narration_speed="normal", narration_style="natural"):
    output_path = generated_audio_path(workspace, title)

    style_info = generate_narration_to_file_with_style(
        voice_parameter,
        prompt,
        output_path,
        narration_style,
    )

    speed_info = narration_speed_payload(narration_speed)
    apply_narration_speed_to_file(output_path, speed_info["key"])

    normalize_generated_audio_file(output_path)

    duration_seconds = audio_duration_seconds(output_path)

    record_usage_event(
        workspace.workspace_id,
        "narration.generated",
        quantity=len(prompt),
        metadata={
            "title": title,
            "submittedCharacters": len(prompt),
            "outputPath": relative_to_root(output_path),
            "durationSeconds": duration_seconds,
            "speed": speed_info.get("key"),
            "style": style_info.get("key"),
            "styleApplied": style_info.get("styleApplied"),
        },
    )

    asset_url = workspace_generated_audio_url(workspace, output_path)

    return output_path, asset_url, speed_info, style_info


def _generate_standard_preview(voice_parameter: str, preview_path):
    print("[clone_voice_controller] Generating standard synthesized voice preview:", preview_path, flush=True)
    generate_narration_to_file(voice_parameter, STANDARD_VOICE_PREVIEW_TEXT, preview_path)
    normalize_generated_audio_file(preview_path)


def _preflight_custom_voice(workspace_id: str, *, replacing: bool = False):
    assert_workspace_can_create_custom_voice(workspace_id, replacing=replacing)
    return assert_workspace_can_spend(
        workspace_id,
        "voice.clone.succeeded",
        estimated_credits=estimate_voice_creation_credits(STANDARD_VOICE_PREVIEW_TEXT),
    )


def _preflight_preview(workspace_id: str):
    return assert_workspace_can_spend(
        workspace_id,
        "voice.preview.generated",
        estimated_credits=estimate_credits(
            "voice.preview.generated",
            len(STANDARD_VOICE_PREVIEW_TEXT),
        ),
    )


def _record_custom_voice_usage(workspace_id: str, voice_id: str, *, parameter_created: bool, preview_created: bool):
    if parameter_created:
        record_usage_event(
            workspace_id,
            "voice.clone.succeeded",
            quantity=1,
            metadata={"voiceId": voice_id},
        )
    if preview_created:
        record_usage_event(
            workspace_id,
            "voice.preview.generated",
            quantity=len(STANDARD_VOICE_PREVIEW_TEXT),
            metadata={
                "voiceId": voice_id,
                "previewText": STANDARD_VOICE_PREVIEW_TEXT,
                "submittedCharacters": len(STANDARD_VOICE_PREVIEW_TEXT),
            },
        )



def _request_origin() -> str:
    return (request.headers.get("Origin") or f"{request.scheme}://{request.host}").rstrip("/")


def _admin_context_or_response():
    try:
        ctx = auth_context_from_request(request)
        require_admin(ctx)
        return ctx, None
    except AuthError as exc:
        return None, (jsonify(auth_error_payload(exc)), exc.status_code)


def _create_workspace_voice_from_path(
    *,
    workspace_id: str,
    source_mode: str,
    source_path: pathlib.Path,
    original_filename: str,
    display_name_input: str,
    gender: str,
) -> dict:
    source_mode = str(source_mode or "upload").strip().lower()
    if source_mode not in {"upload", "record"}:
        raise ValueError("Voice creation only supports upload or record source mode")

    gender = normalize_gender(gender)
    if gender not in {"M", "F"}:
        raise ValueError("Voice gender is required. Choose Male (M) or Female (F).")

    source_path = pathlib.Path(source_path)
    if not source_path.exists() or source_path.stat().st_size <= 0:
        raise ValueError("Voice source audio is missing or empty.")

    is_recording = source_mode == "record"
    workspace = get_workspace(workspace_id)
    voice_id = new_recorded_voice_id() if is_recording else voice_id_from_source_filename(original_filename)
    display_name = display_name_input or display_name_from_voice_id(voice_id)
    preview_path = stable_preview_path(workspace, voice_id)
    limited_source_path = source_limited_path(workspace, voice_id)
    prepared_source = None

    try:
        existing_parameter = voice_parameter_exists(workspace, voice_id)
        parameter_created = False
        preview_created = False

        if is_recording or not existing_parameter:
            _preflight_custom_voice(workspace.workspace_id, replacing=False)
        else:
            assert_workspace_can_use_custom_voice(workspace.workspace_id)

        if existing_parameter and not is_recording:
            voice_parameter, param_path = load_workspace_voice_parameter(workspace, voice_id)
        else:
            prepared_source = prepare_voice_source_audio(
                input_path=source_path,
                output_path=limited_source_path,
            )
            voice_parameter = create_voice_parameter(pathlib.Path(prepared_source["path"]))
            voice_id, param_path = save_voice_parameter(workspace, voice_parameter, voice_id)
            parameter_created = True

        metadata_before = load_voice_metadata(workspace, voice_id)
        preview_is_standard = (
            preview_path.exists()
            and metadata_before.get("previewKind") == "standard_synthesized"
        )

        if is_recording or not preview_is_standard:
            if not parameter_created:
                _preflight_preview(workspace.workspace_id)
            _generate_standard_preview(voice_parameter, preview_path)
            preview_created = True

        metadata, metadata_path = save_voice_metadata(
            workspace,
            voice_id,
            display_name,
            gender,
            source_type="record" if is_recording else "upload",
            parameter_path=param_path,
            preview_path=preview_path,
            parameter_created=parameter_created,
            preview_created=preview_created,
        )

        _record_custom_voice_usage(
            workspace.workspace_id,
            voice_id,
            parameter_created=parameter_created,
            preview_created=preview_created,
        )

        return {
            "ok": True,
            "operation": "create_voice",
            "message": "Voice saved. Select it from My saved voices to generate narration.",
            "sourceType": "record" if is_recording else "upload",
            "workspaceId": workspace.workspace_id,
            "voiceId": voice_id,
            "displayName": metadata["displayName"],
            "gender": metadata["gender"],
            "label": metadata["label"],
            "voiceParamPath": relative_to_root(param_path),
            "voicePreviewPath": relative_to_root(preview_path),
            "voicePreviewUrl": workspace_voice_preview_url(workspace, preview_path),
            "voiceMetadataPath": relative_to_root(metadata_path),
            "previewText": STANDARD_VOICE_PREVIEW_TEXT,
            "parameterCreated": parameter_created,
            "previewCreated": preview_created,
            "maxVoiceSourceSeconds": get_max_voice_source_seconds(),
            "sourceDurationSeconds": prepared_source.get("durationSeconds") if prepared_source else None,
            "sourceTrimmed": bool(prepared_source and prepared_source.get("trimmed")),
            "autoTrimVoiceSource": bool(prepared_source.get("autoTrimEnabled")) if prepared_source else None,
            "rawSourceDeleted": True,
        }
    finally:
        delete_if_exists(limited_source_path)


def _replace_workspace_voice_from_path(
    *,
    workspace_id: str,
    voice_id: str,
    source_path: pathlib.Path,
    original_filename: str,
    display_name_input: str,
    gender_input: str,
) -> dict:
    workspace = get_workspace(workspace_id)
    _, old_param_path = load_workspace_voice_parameter(workspace, voice_id)
    existing = load_voice_metadata(workspace, voice_id)

    display_name = (
        display_name_input
        or existing.get("displayName")
        or display_name_from_voice_id(voice_id)
    ).strip()
    gender = normalize_gender(gender_input or existing.get("gender"))
    if gender not in {"M", "F"}:
        raise ValueError("Voice gender is required. Choose Male (M) or Female (F).")

    _preflight_custom_voice(workspace.workspace_id, replacing=True)
    limited_source_path = source_limited_path(workspace, voice_id)

    try:
        prepared_source = prepare_voice_source_audio(
            input_path=pathlib.Path(source_path),
            output_path=limited_source_path,
        )
        voice_parameter = create_voice_parameter(pathlib.Path(prepared_source["path"]))
        voice_id, param_path = save_voice_parameter(workspace, voice_parameter, voice_id)
        preview_path = stable_preview_path(workspace, voice_id)
        _generate_standard_preview(voice_parameter, preview_path)

        metadata, metadata_path = save_voice_metadata(
            workspace,
            voice_id,
            display_name,
            gender,
            source_type=existing.get("sourceType") or "upload",
            parameter_path=param_path,
            preview_path=preview_path,
            parameter_created=True,
            preview_created=True,
        )

        _record_custom_voice_usage(
            workspace.workspace_id,
            voice_id,
            parameter_created=True,
            preview_created=True,
        )

        return {
            "ok": True,
            "operation": "replace_voice_source",
            "workspaceId": workspace.workspace_id,
            "voiceId": voice_id,
            "displayName": metadata["displayName"],
            "gender": metadata["gender"],
            "label": metadata["label"],
            "voiceParamPath": relative_to_root(param_path),
            "oldVoiceParamPath": relative_to_root(old_param_path),
            "voicePreviewPath": relative_to_root(preview_path),
            "voicePreviewUrl": workspace_voice_preview_url(workspace, preview_path),
            "voiceMetadataPath": relative_to_root(metadata_path),
            "maxVoiceSourceSeconds": get_max_voice_source_seconds(),
            "sourceDurationSeconds": prepared_source.get("durationSeconds"),
            "sourceTrimmed": bool(prepared_source.get("trimmed")),
            "autoTrimVoiceSource": bool(prepared_source.get("autoTrimEnabled")),
            "parameterCreated": True,
            "previewCreated": True,
            "message": "Saved voice source replaced. Parameter and standard preview rebuilt.",
            "originalFilename": original_filename,
        }
    finally:
        delete_if_exists(limited_source_path)


def register_clone_voice_routes(app):

    if "billing_plans" not in app.view_functions:
        @app.get("/api/billing/plans", endpoint="billing_plans")
        def billing_plans():
            return jsonify({
                "ok": True,
                **billing_plans_payload(),
            })

    if "billing_usage_summary" not in app.view_functions:
        @app.get("/api/billing/usage", endpoint="billing_usage_summary")
        def billing_usage():
            workspace_id = request.args.get("workspaceId", MOCK_WORKSPACE_ID)
            month = request.args.get("month")

            return jsonify({
                "ok": True,
                **usage_summary(workspace_id, month),
            })


    if "billing_pricing_config" not in app.view_functions:
        @app.get("/api/billing/pricing-config", endpoint="billing_pricing_config")
        def billing_pricing_config():
            _ctx, auth_response = _admin_context_or_response()
            if auth_response is not None:
                return auth_response
            return jsonify({
                "ok": True,
                **pricing_config_payload(),
            })

    if "billing_pricing_config_update" not in app.view_functions:
        @app.post("/api/billing/pricing-config", endpoint="billing_pricing_config_update")
        def billing_pricing_config_update():
            _ctx, auth_response = _admin_context_or_response()
            if auth_response is not None:
                return auth_response
            data = request.get_json(silent=True) or {}

            try:
                config = update_pricing_config(dict(data))

                return jsonify({
                    "ok": True,
                    **config,
                })

            except Exception as exc:
                return _error(str(exc), 400)

    if "billing_economics" not in app.view_functions:
        @app.get("/api/billing/economics", endpoint="billing_economics")
        def billing_economics():
            workspace_id = request.args.get("workspaceId", MOCK_WORKSPACE_ID)
            month = request.args.get("month")

            return jsonify({
                "ok": True,
                **economics_summary(workspace_id, month),
            })

    if "billing_provider_status" not in app.view_functions:
        @app.get("/api/billing/provider/status", endpoint="billing_provider_status")
        def billing_provider_status():
            return jsonify({
                "ok": True,
                **billing_provider_status_payload(),
            })

    if "billing_dev_simulate_subscription" not in app.view_functions:
        @app.post("/api/billing/dev/simulate-subscription", endpoint="billing_dev_simulate_subscription")
        def billing_dev_simulate_subscription():
            data = request.get_json(silent=True) or request.form

            try:
                result = process_dev_subscription_simulation(dict(data))
                workspace_id = result["event"]["workspaceId"]

                return jsonify({
                    "ok": True,
                    **result,
                    "quota": quota_status(workspace_id),
                })

            except BillingProviderError as exc:
                return _error(str(exc), 400)

            except Exception as exc:
                return _error(str(exc), 500)

    if "billing_provider_webhook" not in app.view_functions:
        @app.post("/api/billing/webhook/<provider>", endpoint="billing_provider_webhook")
        def billing_provider_webhook(provider: str):
            payload = request.get_json(silent=True) or {}

            try:
                result = process_provider_webhook(
                    provider,
                    payload,
                    headers=dict(request.headers),
                )
                workspace_id = result["event"]["workspaceId"]

                return jsonify({
                    "ok": True,
                    **result,
                    "quota": quota_status(workspace_id),
                })

            except BillingWebhookNotReady as exc:
                return _error(str(exc), 501)

            except BillingProviderError as exc:
                return _error(str(exc), 400)

            except Exception as exc:
                return _error(str(exc), 500)

    if "billing_subscription_status" not in app.view_functions:
        @app.get("/api/billing/subscription", endpoint="billing_subscription_status")
        def billing_subscription_status():
            workspace_id = request.args.get("workspaceId", MOCK_WORKSPACE_ID)

            return jsonify({
                "ok": True,
                **quota_status(workspace_id),
            })

    if "billing_free_plan_select" not in app.view_functions:
        @app.post("/api/billing/free-plan", endpoint="billing_free_plan_select")
        def billing_free_plan_select():
            data = request.get_json(silent=True) or request.form
            try:
                ctx = auth_context_from_request(request)
                workspace_id = str(data.get("workspaceId") or ctx.workspace_id or "").strip()
                require_workspace_access(ctx, workspace_id)
                current = get_workspace_subscription(workspace_id)
                has_active_paid = (
                    current.get("planKey") != "free"
                    and str(current.get("status") or "").lower() in {"active", "trialing"}
                    and bool(current.get("stripeSubscriptionId") or current.get("subscriptionId"))
                )
                if has_active_paid:
                    return _error("Use the Stripe billing portal to cancel or change an active paid subscription.", 409)
                subscription = set_workspace_plan(
                    workspace_id,
                    "free",
                    status="active",
                    provider="internal",
                    customer_id=current.get("stripeCustomerId") or current.get("customerId") or "",
                )
                return jsonify({"ok": True, "subscription": subscription, **quota_status(workspace_id)})
            except AuthError as exc:
                return jsonify(auth_error_payload(exc)), exc.status_code
            except Exception as exc:
                return _error(str(exc), 400)

    if "billing_subscription_update" not in app.view_functions:
        @app.post("/api/billing/subscription", endpoint="billing_subscription_update")
        def billing_subscription_update():
            _ctx, auth_response = _admin_context_or_response()
            if auth_response is not None:
                return auth_response
            data = request.get_json(silent=True) or request.form
            workspace_id = data.get("workspaceId") or request.args.get("workspaceId") or MOCK_WORKSPACE_ID
            plan_key = data.get("planKey") or data.get("plan") or "starter"
            status = data.get("status") or "active"

            try:
                subscription = set_workspace_plan(
                    workspace_id,
                    plan_key,
                    status=status,
                    provider=data.get("provider") or "manual",
                    customer_id=data.get("customerId") or "",
                    subscription_id=data.get("subscriptionId") or "",
                )

                return jsonify({
                    "ok": True,
                    "subscription": subscription,
                    **quota_status(workspace_id),
                })

            except Exception as exc:
                return _error(str(exc), 400)

    if "clone_voice_settings" not in app.view_functions:
        @app.get("/api/clone-voice/settings", endpoint="clone_voice_settings")
        def clone_voice_settings():
            payload = settings_payload()
            print("[clone_voice_controller] Settings:", payload, flush=True)
            return jsonify({"ok": True, **payload})

    if "clone_voice_update_settings" not in app.view_functions:
        @app.post("/api/clone-voice/settings", endpoint="clone_voice_update_settings")
        def clone_voice_update_settings():
            data = request.get_json(silent=True) or request.form

            raw_value = (
                data.get("maxVoiceSourceSeconds")
                or data.get("max_voice_source_seconds")
                or data.get("duration")
                or data.get("D")
            )

            if raw_value is None:
                return _error("Missing maxVoiceSourceSeconds", 400)

            try:
                payload = set_max_voice_source_seconds(int(raw_value))
            except Exception as exc:
                return _error(str(exc), 400)

            print("[clone_voice_controller] Updated settings:", payload, flush=True)

            return jsonify({"ok": True, **payload})


    if "clone_voice_workspaces" not in app.view_functions:
        @app.get("/api/clone-voice/workspaces", endpoint="clone_voice_workspaces")
        def clone_voice_workspaces():
            ctx = auth_context_from_request(request)
            payload = workspace_selector_payload(ctx.user_id, ctx.role, ctx.workspace_id)

            return jsonify({
                "ok": True,
                **payload,
            })

    if "clone_voice_workspace_upload_session" not in app.view_functions:
        @app.post("/api/clone-voice/source-uploads/workspace/session", endpoint="clone_voice_workspace_upload_session")
        def clone_voice_workspace_upload_session():
            data = request.get_json(silent=True) or {}
            try:
                workspace_id = str(data.get("workspaceId") or "").strip()
                blocked = _smx_custom_voice_block_response(workspace_id)
                if blocked is not None:
                    return blocked

                ctx = auth_context_from_request(request)
                workspace_id = str(data.get("workspaceId") or ctx.workspace_id or "").strip()
                require_workspace_access(ctx, workspace_id)
                purpose = str(data.get("purpose") or "create").strip().lower()
                assert_workspace_can_create_custom_voice(
                    workspace_id,
                    replacing=purpose == "replace",
                )
                payload = create_workspace_upload_session(
                    workspace_id=data.get("workspaceId"),
                    filename=data.get("filename"),
                    content_type=data.get("contentType"),
                    size_bytes=data.get("sizeBytes"),
                    origin=_request_origin(),
                    user_id=ctx.user_id,
                    purpose=data.get("purpose") or "create",
                )
                return jsonify(payload)
            except QuotaExceededError as exc:
                return _quota_error_response(exc)
            except VoiceSourceUploadError as exc:
                return _error(str(exc), getattr(exc, "status_code", 400))
            except Exception as exc:
                print("[clone_voice_controller] workspace upload session error:", repr(exc), flush=True)
                return _error(str(exc), 500)

    if "clone_voice_workspace_upload_complete" not in app.view_functions:
        @app.post("/api/clone-voice/source-uploads/workspace/complete", endpoint="clone_voice_workspace_upload_complete")
        def clone_voice_workspace_upload_complete():
            data = request.get_json(silent=True) or {}
            workspace_id = str(data.get("workspaceId") or "").strip()
            object_key = str(data.get("objectKey") or "").strip()
            blocked = _smx_custom_voice_block_response(workspace_id)
            if blocked is not None:
                return blocked
            temp_dir = None
            try:
                uploaded, local_path, temp_dir = download_completed_upload(
                    object_key=object_key,
                    expected_prefix=workspace_temporary_prefix(workspace_id),
                    original_filename=data.get("originalFilename") or data.get("filename"),
                    expected_size_bytes=data.get("sizeBytes"),
                )
                payload = _create_workspace_voice_from_path(
                    workspace_id=workspace_id,
                    source_mode=data.get("sourceMode") or "upload",
                    source_path=local_path,
                    original_filename=uploaded.original_filename,
                    display_name_input=str(data.get("voiceDisplayName") or data.get("displayName") or "").strip(),
                    gender=str(data.get("gender") or "").strip(),
                )
                payload["temporaryObjectDeleted"] = True
                return jsonify(payload)
            except QuotaExceededError as exc:
                return _quota_error_response(exc)
            except (VoiceSourceUploadError, VoiceSourcePolicyError, ValueError) as exc:
                return _error(str(exc), getattr(exc, "status_code", 422 if isinstance(exc, VoiceSourcePolicyError) else 400))
            except Exception as exc:
                print("[clone_voice_controller] workspace upload completion error:", repr(exc), flush=True)
                return _error(str(exc), 500)
            finally:
                if temp_dir is not None:
                    temp_dir.cleanup()
                if object_key:
                    delete_temporary_upload(object_key)

    if "clone_voice_workspace_replace_upload_complete" not in app.view_functions:
        @app.post("/api/clone-voice/source-uploads/workspace/replace", endpoint="clone_voice_workspace_replace_upload_complete")
        def clone_voice_workspace_replace_upload_complete():
            data = request.get_json(silent=True) or {}
            workspace_id = str(data.get("workspaceId") or "").strip()
            object_key = str(data.get("objectKey") or "").strip()
            voice_id = str(data.get("voiceId") or "").strip()
            temp_dir = None
            try:
                if not voice_id:
                    return _error("voiceId is required.", 400)
                uploaded, local_path, temp_dir = download_completed_upload(
                    object_key=object_key,
                    expected_prefix=workspace_temporary_prefix(workspace_id),
                    original_filename=data.get("originalFilename") or data.get("filename"),
                    expected_size_bytes=data.get("sizeBytes"),
                )
                payload = _replace_workspace_voice_from_path(
                    workspace_id=workspace_id,
                    voice_id=voice_id,
                    source_path=local_path,
                    original_filename=uploaded.original_filename,
                    display_name_input=str(data.get("displayName") or data.get("voiceDisplayName") or "").strip(),
                    gender_input=str(data.get("gender") or "").strip(),
                )
                payload["temporaryObjectDeleted"] = True
                return jsonify(payload)
            except QuotaExceededError as exc:
                return _quota_error_response(exc)
            except (VoiceSourceUploadError, VoiceSourcePolicyError, ValueError) as exc:
                return _error(str(exc), getattr(exc, "status_code", 422 if isinstance(exc, VoiceSourcePolicyError) else 400))
            except Exception as exc:
                print("[clone_voice_controller] replacement upload completion error:", repr(exc), flush=True)
                return _error(str(exc), 500)
            finally:
                if temp_dir is not None:
                    temp_dir.cleanup()
                if object_key:
                    delete_temporary_upload(object_key)

    if "clone_voice_system_upload_session" not in app.view_functions:
        @app.post("/api/clone-voice/source-uploads/system/session", endpoint="clone_voice_system_upload_session")
        def clone_voice_system_upload_session():
            ctx, auth_response = _admin_context_or_response()
            if auth_response is not None:
                return auth_response
            data = request.get_json(silent=True) or {}
            try:
                return jsonify(create_system_upload_session(
                    filename=data.get("filename"),
                    content_type=data.get("contentType"),
                    size_bytes=data.get("sizeBytes"),
                    origin=_request_origin(),
                    user_id=ctx.user_id,
                ))
            except VoiceSourceUploadError as exc:
                return _error(str(exc), getattr(exc, "status_code", 400))
            except Exception as exc:
                print("[clone_voice_controller] system upload session error:", repr(exc), flush=True)
                return _error(str(exc), 500)

    if "clone_voice_system_upload_complete" not in app.view_functions:
        @app.post("/api/clone-voice/source-uploads/system/complete", endpoint="clone_voice_system_upload_complete")
        def clone_voice_system_upload_complete():
            _ctx, auth_response = _admin_context_or_response()
            if auth_response is not None:
                return auth_response
            data = request.get_json(silent=True) or {}
            object_key = str(data.get("objectKey") or "").strip()
            temp_dir = None
            try:
                uploaded, local_path, temp_dir = download_completed_upload(
                    object_key=object_key,
                    expected_prefix=system_temporary_prefix(),
                    original_filename=data.get("originalFilename") or data.get("filename"),
                    expected_size_bytes=data.get("sizeBytes"),
                )
                payload = save_system_voice_from_path(
                    local_path,
                    original_filename=uploaded.original_filename,
                    display_name=str(data.get("displayName") or "").strip(),
                    gender=normalize_gender(data.get("gender")),
                    replace=bool(data.get("replace")),
                )
                payload["temporaryObjectDeleted"] = True
                return jsonify(payload)
            except FileExistsError as exc:
                return _error(str(exc), 409)
            except (VoiceSourceUploadError, VoiceSourcePolicyError, ValueError) as exc:
                return _error(str(exc), getattr(exc, "status_code", 422 if isinstance(exc, VoiceSourcePolicyError) else 400))
            except Exception as exc:
                print("[clone_voice_controller] system upload completion error:", repr(exc), flush=True)
                return _error(str(exc), 500)
            finally:
                if temp_dir is not None:
                    temp_dir.cleanup()
                if object_key:
                    delete_temporary_upload(object_key)

    if "clone_voice_system_voices" not in app.view_functions:
        @app.get("/api/clone-voice/system-voices", endpoint="clone_voice_system_voices")
        def system_voices():
            voices = list_system_voices_payload()
            print("[clone_voice_controller] System voices:", voices, flush=True)
            return jsonify({"ok": True, "voices": voices})


    if "clone_voice_create_system_voice" not in app.view_functions:
        @app.post("/api/clone-voice/system-voices", endpoint="clone_voice_create_system_voice")
        def create_system_voice():
            _ctx, auth_response = _admin_context_or_response()
            if auth_response is not None:
                return auth_response
            audio_file = request.files.get("audio")
            display_name = (
                request.form.get("displayName", "")
                or request.form.get("voiceDisplayName", "")
                or request.form.get("voiceName", "")
            ).strip()
            gender = normalize_gender(request.form.get("gender"))

            if gender not in {"M", "F"}:
                return _error("Voice gender is required. Choose Male (M) or Female (F).", 400)

            replace_raw = str(request.form.get("replace", "")).strip().lower()
            replace = replace_raw in {"1", "true", "yes", "on", "replace"}

            if audio_file is None or not audio_file.filename:
                return _error("Missing system voice audio source", 400)

            try:
                payload = save_system_voice_from_source(
                    audio_file,
                    display_name=display_name,
                    gender=gender,
                    replace=replace,
                )

                print("[clone_voice_controller] System voice saved:", payload, flush=True)

                return jsonify(payload)

            except FileExistsError as exc:
                return _error(str(exc), 409)

            except Exception as exc:
                print("[clone_voice_controller] create system voice error:", repr(exc), flush=True)
                return _error(str(exc), 500)

    if "clone_voice_delete_system_voice" not in app.view_functions:
        @app.delete("/api/clone-voice/system-voices/<voice_id>", endpoint="clone_voice_delete_system_voice")
        def remove_system_voice(voice_id: str):
            _ctx, auth_response = _admin_context_or_response()
            if auth_response is not None:
                return auth_response
            try:
                payload = delete_system_voice(voice_id)
                print("[clone_voice_controller] System voice deleted:", payload, flush=True)
                return jsonify(payload)

            except Exception as exc:
                print("[clone_voice_controller] delete system voice error:", repr(exc), flush=True)
                return _error(str(exc), 500)

    if "clone_voice_my_voices" not in app.view_functions:
        @app.get("/api/clone-voice/my-voices", endpoint="clone_voice_my_voices")
        def my_voices():
            workspace_id = request.args.get("workspaceId", MOCK_WORKSPACE_ID)
            workspace = get_workspace(workspace_id)
            entitlement = custom_voice_entitlement(workspace.workspace_id)
            stored_voices = list_workspace_voice_parameters(workspace)
            voices = stored_voices if entitlement.get("allowed") and not entitlement.get("systemVoicesOnly") else []

            print("[clone_voice_controller] My saved voices:", voices, flush=True)

            return jsonify({
                "ok": True,
                "workspaceId": workspace.workspace_id,
                "voices": voices,
                "customVoiceEntitlement": entitlement,
                "lockedVoiceCount": max(0, len(stored_voices) - len(voices)),
            })


    if "clone_voice_delete_my_voice" not in app.view_functions:
        @app.delete("/api/clone-voice/my-voices/<voice_id>", endpoint="clone_voice_delete_my_voice")
        def delete_my_voice(voice_id: str):
            data = request.get_json(silent=True) or {}
            workspace_id = (
                request.args.get("workspaceId")
                or data.get("workspaceId")
                or MOCK_WORKSPACE_ID
            )

            try:
                workspace = get_workspace(workspace_id)
                payload = delete_workspace_voice(workspace, voice_id)

                print("[clone_voice_controller] Saved voice deleted:", payload, flush=True)

                return jsonify({
                    **payload,
                    "workspaceId": workspace.workspace_id,
                })

            except Exception as exc:
                print("[clone_voice_controller] delete saved voice error:", repr(exc), flush=True)
                return _error(str(exc), 500)


    if "clone_voice_create_workspace_voice" not in app.view_functions:
        @app.post("/api/clone-voice/voices/from-source", endpoint="clone_voice_create_workspace_voice")
        def create_workspace_voice():
            workspace_id = request.form.get("workspaceId", MOCK_WORKSPACE_ID)
            source_mode = request.form.get("sourceMode", "upload").strip().lower()
            audio_file = request.files.get("audio")

            display_name_input = (
                request.form.get("voiceDisplayName", "")
                or request.form.get("displayName", "")
                or request.form.get("voiceName", "")
            ).strip()

            gender = normalize_gender(request.form.get("gender"))

            if gender not in {"M", "F"}:
                return _error("Voice gender is required. Choose Male (M) or Female (F).", 400)

            print("\n" + "=" * 100, flush=True)
            print("[clone_voice_controller] CREATE WORKSPACE VOICE ONLY", flush=True)
            print("workspaceId:", repr(workspace_id), flush=True)
            print("sourceMode:", repr(source_mode), flush=True)
            print("displayName:", repr(display_name_input), flush=True)
            print("gender:", repr(gender), flush=True)
            if audio_file:
                print("audio.filename:", repr(audio_file.filename), flush=True)
                print("audio.mimetype:", repr(audio_file.mimetype), flush=True)
            print("=" * 100 + "\n", flush=True)

            if source_mode not in {"upload", "record"}:
                return _error("Voice creation only supports upload or record source mode", 400)

            if audio_file is None or not audio_file.filename:
                return _error("Missing uploaded or recorded audio file under field name 'audio'", 400)

            is_recording = source_mode == "record"
            workspace = get_workspace(workspace_id)

            raw_source_path = None
            limited_source_path = None

            try:
                if is_recording:
                    voice_id = new_recorded_voice_id()
                else:
                    voice_id = voice_id_from_source_filename(audio_file.filename)

                display_name = display_name_input or display_name_from_voice_id(voice_id)
                preview_path = stable_preview_path(workspace, voice_id)
                max_seconds = get_max_voice_source_seconds()

                raw_source_path = save_source_audio(audio_file, workspace)

                existing_parameter = voice_parameter_exists(workspace, voice_id)
                parameter_created = False
                preview_created = False

                if is_recording or not existing_parameter:
                    try:
                        _preflight_custom_voice(workspace.workspace_id, replacing=False)
                    except QuotaExceededError as exc:
                        return _quota_error_response(exc)
                else:
                    try:
                        assert_workspace_can_use_custom_voice(workspace.workspace_id)
                    except QuotaExceededError as exc:
                        return _quota_error_response(exc)

                if existing_parameter and not is_recording:
                    print("[clone_voice_controller] Uploaded voice already exists. Reusing parameter:", voice_id, flush=True)
                    voice_parameter, param_path = load_workspace_voice_parameter(workspace, voice_id)
                else:
                    limited_source_path = source_limited_path(workspace, voice_id)

                    prepared_source = prepare_voice_source_audio(
                        input_path=raw_source_path,
                        output_path=limited_source_path,
                    )
                    voice_parameter = create_voice_parameter(pathlib.Path(prepared_source["path"]))
                    voice_id, param_path = save_voice_parameter(workspace, voice_parameter, voice_id)
                    parameter_created = True

                metadata_before = load_voice_metadata(workspace, voice_id)
                preview_is_standard = (
                    preview_path.exists()
                    and metadata_before.get("previewKind") == "standard_synthesized"
                )

                if is_recording or not preview_is_standard:
                    if not parameter_created:
                        try:
                            _preflight_preview(workspace.workspace_id)
                        except QuotaExceededError as exc:
                            return _quota_error_response(exc)
                    _generate_standard_preview(voice_parameter, preview_path)
                    preview_created = True
                else:
                    print("[clone_voice_controller] Standard preview already exists. Reusing:", preview_path, flush=True)

                metadata, metadata_path = save_voice_metadata(
                    workspace,
                    voice_id,
                    display_name,
                    gender,
                    source_type="record" if is_recording else "upload",
                    parameter_path=param_path,
                    preview_path=preview_path,
                    parameter_created=parameter_created,
                    preview_created=preview_created,
                )

                _record_custom_voice_usage(
                    workspace.workspace_id,
                    voice_id,
                    parameter_created=parameter_created,
                    preview_created=preview_created,
                )

                return jsonify({
                    "ok": True,
                    "operation": "create_voice",
                    "message": "Voice saved. Select it from My saved voices to generate narration.",
                    "sourceType": "record" if is_recording else "upload",
                    "workspaceId": workspace.workspace_id,
                    "voiceId": voice_id,
                    "displayName": metadata["displayName"],
                    "gender": metadata["gender"],
                    "label": metadata["label"],
                    "voiceParamPath": relative_to_root(param_path),
                    "voicePreviewPath": relative_to_root(preview_path),
                    "voicePreviewUrl": workspace_voice_preview_url(workspace, preview_path),
                    "voiceMetadataPath": relative_to_root(metadata_path),
                    "previewText": STANDARD_VOICE_PREVIEW_TEXT,
                    "parameterCreated": parameter_created,
                    "previewCreated": preview_created,
                    "maxVoiceSourceSeconds": max_seconds,
                    "rawSourceDeleted": True,
                })

            except VoiceSourcePolicyError as exc:
                return _error(str(exc), getattr(exc, "status_code", 422))
            except Exception as exc:
                print("[clone_voice_controller] create workspace voice error:", repr(exc), flush=True)
                return _error(str(exc), 500)

            finally:
                delete_if_exists(raw_source_path)
                delete_if_exists(limited_source_path)


    if "clone_voice_update_my_voice" not in app.view_functions:
        @app.patch("/api/clone-voice/my-voices/<voice_id>", endpoint="clone_voice_update_my_voice")
        def update_my_voice(voice_id: str):
            data = request.get_json(silent=True) or request.form
            workspace_id = (
                request.args.get("workspaceId")
                or data.get("workspaceId")
                or MOCK_WORKSPACE_ID
            )

            try:
                workspace = get_workspace(workspace_id)

                # Ensure voice exists.
                _, param_path = load_workspace_voice_parameter(workspace, voice_id)
                existing = load_voice_metadata(workspace, voice_id)

                display_name = (
                    data.get("displayName")
                    or data.get("voiceDisplayName")
                    or existing.get("displayName")
                    or display_name_from_voice_id(voice_id)
                ).strip()

                gender = normalize_gender(data.get("gender") or existing.get("gender"))

                if gender not in {"M", "F"}:
                    return _error("Voice gender is required. Choose Male (M) or Female (F).", 400)

                preview_path = stable_preview_path(workspace, voice_id)

                metadata, metadata_path = save_voice_metadata(
                    workspace,
                    voice_id,
                    display_name,
                    gender,
                    source_type=existing.get("sourceType") or "upload",
                    parameter_path=param_path,
                    preview_path=preview_path,
                    parameter_created=bool(existing.get("parameterCreated")),
                    preview_created=bool(existing.get("previewCreated")),
                )

                payload = {
                    "ok": True,
                    "operation": "update_voice_metadata",
                    "workspaceId": workspace.workspace_id,
                    "voiceId": voice_id,
                    "displayName": metadata["displayName"],
                    "gender": metadata["gender"],
                    "label": metadata["label"],
                    "voiceParamPath": relative_to_root(param_path),
                    "voicePreviewPath": relative_to_root(preview_path) if preview_path.exists() else "",
                    "voicePreviewUrl": workspace_voice_preview_url(workspace, preview_path) if preview_path.exists() else "",
                    "voiceMetadataPath": relative_to_root(metadata_path),
                    "message": "Saved voice details updated.",
                }

                print("[clone_voice_controller] Saved voice metadata updated:", payload, flush=True)

                return jsonify(payload)

            except Exception as exc:
                print("[clone_voice_controller] update saved voice error:", repr(exc), flush=True)
                return _error(str(exc), 500)

    if "clone_voice_replace_my_voice_source" not in app.view_functions:
        @app.post("/api/clone-voice/my-voices/<voice_id>/replace-source", endpoint="clone_voice_replace_my_voice_source")
        def replace_my_voice_source(voice_id: str):
            workspace_id = request.form.get("workspaceId", MOCK_WORKSPACE_ID)
            audio_file = request.files.get("audio")

            if audio_file is None or not audio_file.filename:
                return _error("Missing replacement audio file under field name 'audio'", 400)

            workspace = get_workspace(workspace_id)
            raw_source_path = None
            limited_source_path = None

            try:
                # Ensure voice exists before replacing.
                _, old_param_path = load_workspace_voice_parameter(workspace, voice_id)
                existing = load_voice_metadata(workspace, voice_id)

                display_name = (
                    request.form.get("displayName", "")
                    or request.form.get("voiceDisplayName", "")
                    or existing.get("displayName")
                    or display_name_from_voice_id(voice_id)
                ).strip()

                gender = normalize_gender(request.form.get("gender") or existing.get("gender"))

                if gender not in {"M", "F"}:
                    return _error("Voice gender is required. Choose Male (M) or Female (F).", 400)

                # replace voice source quota preflight
                try:
                    _preflight_custom_voice(workspace.workspace_id, replacing=True)
                except QuotaExceededError as exc:
                    return _quota_error_response(exc)

                max_seconds = get_max_voice_source_seconds()
                raw_source_path = save_source_audio(audio_file, workspace)
                limited_source_path = source_limited_path(workspace, voice_id)

                prepared_source = prepare_voice_source_audio(
                    input_path=raw_source_path,
                    output_path=limited_source_path,
                )
                voice_parameter = create_voice_parameter(pathlib.Path(prepared_source["path"]))
                voice_id, param_path = save_voice_parameter(workspace, voice_parameter, voice_id)

                preview_path = stable_preview_path(workspace, voice_id)
                _generate_standard_preview(voice_parameter, preview_path)

                metadata, metadata_path = save_voice_metadata(
                    workspace,
                    voice_id,
                    display_name,
                    gender,
                    source_type=existing.get("sourceType") or "upload",
                    parameter_path=param_path,
                    preview_path=preview_path,
                    parameter_created=True,
                    preview_created=True,
                )

                _record_custom_voice_usage(
                    workspace.workspace_id,
                    voice_id,
                    parameter_created=True,
                    preview_created=True,
                )

                payload = {
                    "ok": True,
                    "operation": "replace_voice_source",
                    "workspaceId": workspace.workspace_id,
                    "voiceId": voice_id,
                    "displayName": metadata["displayName"],
                    "gender": metadata["gender"],
                    "label": metadata["label"],
                    "voiceParamPath": relative_to_root(param_path),
                    "oldVoiceParamPath": relative_to_root(old_param_path),
                    "voicePreviewPath": relative_to_root(preview_path),
                    "voicePreviewUrl": workspace_voice_preview_url(workspace, preview_path),
                    "voiceMetadataPath": relative_to_root(metadata_path),
                    "maxVoiceSourceSeconds": max_seconds,
                    "parameterCreated": True,
                    "previewCreated": True,
                    "message": "Saved voice source replaced. Parameter and standard preview rebuilt.",
                }

                print("[clone_voice_controller] Saved voice source replaced:", payload, flush=True)

                return jsonify(payload)

            except VoiceSourcePolicyError as exc:
                return _error(str(exc), getattr(exc, "status_code", 422))
            except Exception as exc:
                print("[clone_voice_controller] replace saved voice source error:", repr(exc), flush=True)
                return _error(str(exc), 500)

            finally:
                delete_if_exists(raw_source_path)
                delete_if_exists(limited_source_path)

    if "clone_voice_from_source" not in app.view_functions:
        @app.post("/api/clone-voice/from-source", endpoint="clone_voice_from_source")
        def from_source():
            return _error(
                "Deprecated route. Use POST /api/clone-voice/voices/from-source to save a voice, then POST /api/clone-voice/from-saved or /api/clone-voice/from-system to generate narration.",
                410,
            )

    if "clone_voice_from_saved" not in app.view_functions:
        @app.post("/api/clone-voice/from-saved", endpoint="clone_voice_from_saved")
        def from_saved():
            title = request.form.get("title", "").strip()
            prompt = request.form.get("prompt", "").strip()
            voice_id = request.form.get("voiceId", "").strip()
            workspace_id = request.form.get("workspaceId", MOCK_WORKSPACE_ID)
            narration_speed = request.form.get("narrationSpeed", "normal").strip()
            narration_style = request.form.get("narrationStyle", "natural").strip()

            if not title:
                return _error("Missing narration title", 400)

            if not prompt:
                return _error("Missing prompt", 400)

            if not voice_id:
                return _error("Missing voiceId", 400)

            try:
                workspace = get_workspace(workspace_id)
                assert_workspace_can_use_custom_voice(workspace.workspace_id)
                voice_parameter, param_path = load_workspace_voice_parameter(workspace, voice_id)
                metadata = load_voice_metadata(workspace, voice_id)

                estimated_credits = estimate_narration_credits_from_text(prompt, narration_speed)

                try:
                    assert_workspace_can_spend(
                        workspace.workspace_id,
                        "narration.generated",
                        estimated_credits=estimated_credits,
                    )
                except QuotaExceededError as exc:
                    return _quota_error_response(exc)

                output_path, asset_url, speed_info, style_info = _generate_and_normalize(voice_parameter, prompt, workspace, title, narration_speed, narration_style)

                return jsonify({
                    "ok": True,
                    "sourceType": "saved",
                    "workspaceId": workspace.workspace_id,
                    "voiceId": voice_id,
                    "displayName": metadata.get("displayName"),
                    "gender": metadata.get("gender"),
                    "label": metadata.get("label"),
                    "voiceParamPath": relative_to_root(param_path),
                    "assetUrl": asset_url,
                    "audioUrl": asset_url,
                    "outputPath": relative_to_root(output_path),
                    "narrationTitle": title,
                    "volumeNormalized": True,
                    "narrationSpeed": speed_info["key"],
                    "narrationSpeedLabel": speed_info["label"],
                    "narrationSpeedMultiplier": speed_info["multiplier"],
                    "narrationSpeedDisplay": speed_info["display"],
                    "narrationStyle": style_info["key"],
                    "narrationStyleLabel": style_info["label"],
                    "narrationStyleDisplay": style_info["display"],
                    "narrationStyleApplied": style_info["styleApplied"],
                    "narrationStyleReason": style_info["styleReason"],
                })

            except QuotaExceededError as exc:
                return _quota_error_response(exc)
            except Exception as exc:
                print("[clone_voice_controller] from-saved error:", repr(exc), flush=True)
                return _error(str(exc), 500)

    if "clone_voice_from_system" not in app.view_functions:
        @app.post("/api/clone-voice/from-system", endpoint="clone_voice_from_system")
        def from_system():
            title = request.form.get("title", "").strip()
            prompt = request.form.get("prompt", "").strip()
            voice_id = request.form.get("voiceId", "").strip()
            workspace_id = request.form.get("workspaceId", MOCK_WORKSPACE_ID)
            narration_speed = request.form.get("narrationSpeed", "normal").strip()
            narration_style = request.form.get("narrationStyle", "natural").strip()

            if not title:
                return _error("Missing narration title", 400)

            if not prompt:
                return _error("Missing prompt", 400)

            if not voice_id:
                return _error("Missing voiceId", 400)

            try:
                workspace = get_workspace(workspace_id)
                voice_parameter, param_path = load_system_voice_parameter(voice_id)

                estimated_credits = estimate_narration_credits_from_text(prompt, narration_speed)

                try:
                    assert_workspace_can_spend(
                        workspace.workspace_id,
                        "narration.generated",
                        estimated_credits=estimated_credits,
                    )
                except QuotaExceededError as exc:
                    return _quota_error_response(exc)

                output_path, asset_url, speed_info, style_info = _generate_and_normalize(voice_parameter, prompt, workspace, title, narration_speed, narration_style)

                return jsonify({
                    "ok": True,
                    "sourceType": "system",
                    "workspaceId": workspace.workspace_id,
                    "voiceId": voice_id,
                    "systemVoiceParamPath": relative_to_root(param_path),
                    "assetUrl": asset_url,
                    "audioUrl": asset_url,
                    "outputPath": relative_to_root(output_path),
                    "narrationTitle": title,
                    "volumeNormalized": True,
                    "narrationSpeed": speed_info["key"],
                    "narrationSpeedLabel": speed_info["label"],
                    "narrationSpeedMultiplier": speed_info["multiplier"],
                    "narrationSpeedDisplay": speed_info["display"],
                    "narrationStyle": style_info["key"],
                    "narrationStyleLabel": style_info["label"],
                    "narrationStyleDisplay": style_info["display"],
                    "narrationStyleApplied": style_info["styleApplied"],
                    "narrationStyleReason": style_info["styleReason"],
                })

            except Exception as exc:
                print("[clone_voice_controller] from-system error:", repr(exc), flush=True)
                return _error(str(exc), 500)

    if "clone_voice_workspace_audio" not in app.view_functions:
        @app.get("/media/workspaces/<workspace_id>/generated_audio/<path:filename>", endpoint="clone_voice_workspace_audio")
        def workspace_audio(workspace_id: str, filename: str):
            workspace = get_workspace(workspace_id)
            object_response = _workspace_media_response_from_object_storage(
                workspace.workspace_id,
                "generated_audio",
                filename,
            )

            if object_response is not None:
                return object_response

            return send_from_directory(workspace.generated_audio_dir, filename)

    if "clone_voice_workspace_preview" not in app.view_functions:
        @app.get("/media/workspaces/<workspace_id>/voice_previews/<path:filename>", endpoint="clone_voice_workspace_preview")
        def workspace_preview(workspace_id: str, filename: str):
            workspace = get_workspace(workspace_id)
            object_response = _workspace_media_response_from_object_storage(
                workspace.workspace_id,
                "voice_previews",
                filename,
            )

            if object_response is not None:
                return object_response

            return send_from_directory(workspace.voice_previews_dir, filename)

    if "clone_voice_preview_audio" not in app.view_functions:
        @app.get("/media/voices/previews/<path:filename>", endpoint="clone_voice_preview_audio")
        def preview_audio(filename: str):
            try:
                from services.object_storage import get_object_storage, object_key_for_system_voice_preview
                storage = get_object_storage()
                key = object_key_for_system_voice_preview(filename)
                if storage.exists(key):
                    return Response(
                        storage.read_bytes(key),
                        mimetype="audio/wav",
                        headers={
                            "Cache-Control": "private, max-age=3600",
                            "X-SyntaxMatrix-Object-Storage": storage.backend_name,
                        },
                    )
            except Exception as exc:
                print("[clone_voice_controller] System preview object read failed:", repr(exc), flush=True)
            return send_from_directory(SYSTEM_PREVIEWS_DIR, filename)
