"""
Image Studio Service
====================

Core service managing TchueKAM Image Studio assets, synchronized model catalog,
and multi-provider dispatch (FAL.ai primary, MuAPI optional).

Provides:
- Shared generation history and asset management across Chat and Image Studio.
- Multi-tenant / workspace isolation.
- Synchronized model discovery with capabilities.
- Safe error normalization without mock/fake data.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from hermes_constants import get_hermes_home

logger = logging.getLogger(__name__)

_lock = threading.Lock()


def get_image_studio_dir() -> Path:
    """Return the Image Studio cache directory, creating it if needed."""
    d = get_hermes_home() / "cache" / "image_studio"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_image_studio_assets_dir() -> Path:
    """Return the directory where local asset binaries are cached."""
    d = get_image_studio_dir() / "assets"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _library_path() -> Path:
    return get_image_studio_dir() / "library.json"


def _load_library_raw() -> List[Dict[str, Any]]:
    p = _library_path()
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
        except Exception as exc:
            logger.warning("Failed to parse image studio library.json: %s", exc)
    return []


def _save_library_raw(items: List[Dict[str, Any]]) -> None:
    """Atomically persist the library. Raises on failure — a registration must
    never report success when nothing was written."""
    p = _library_path()
    temp_path = p.with_suffix(".tmp")
    try:
        temp_path.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")
        temp_path.replace(p)
    except Exception as exc:
        logger.error("Failed to write image studio library.json: %s", exc)
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def register_asset(
    url: str,
    prompt: str,
    provider: str,
    model: str,
    studio_type: str = "image",
    parameters: Optional[Dict[str, Any]] = None,
    dimensions: Optional[Dict[str, int]] = None,
    duration: Optional[float] = None,
    mime_type: Optional[str] = None,
    local_path: Optional[str] = None,
    user_id: str = "default",
    workspace_id: str = "default",
    conversation_id: Optional[str] = None,
    job_id: Optional[str] = None,
    status: str = "completed",
    tags: Optional[List[str]] = None,
    favorite: bool = False,
    asset_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Register a generated asset into the shared generation history.

    A ``completed`` asset must actually be retrievable: it needs a ``url`` or an
    existing ``local_path``. An id that already belongs to another workspace is
    never overwritten.
    """
    if status == "completed":
        has_local = bool(local_path) and os.path.isfile(local_path)
        if not (url or "").strip() and not has_local:
            raise ValueError("Cannot register a completed asset without a url or an existing local file.")

    if not asset_id:
        asset_id = str(uuid.uuid4())

    if not mime_type:
        if studio_type in ("video", "i2v", "t2v"):
            mime_type = "video/mp4"
        elif studio_type == "audio":
            mime_type = "audio/mpeg"
        else:
            mime_type = "image/png"

    created_at = int(time.time() * 1000)

    asset_record: Dict[str, Any] = {
        "id": asset_id,
        "userId": user_id or "default",
        "workspaceId": workspace_id or "default",
        "conversationId": conversation_id,
        "studioType": studio_type,
        "provider": provider.lower() if provider else "fal",
        "model": model,
        "prompt": prompt or "",
        "parameters": parameters or {},
        "createdAt": created_at,
        "url": url,
        "localPath": local_path,
        "mimeType": mime_type,
        "dimensions": dimensions or {},
        "duration": duration,
        "status": status,
        "jobId": job_id,
        "tags": tags or [],
        "favorite": favorite,
    }

    with _lock:
        items = _load_library_raw()
        # Prepend new item (chronological descending)
        existing_idx = next((i for i, x in enumerate(items) if x.get("id") == asset_id), None)
        if existing_idx is not None:
            if _ws(items[existing_idx].get("workspaceId")) != _ws(workspace_id):
                raise PermissionError("Asset id already exists in another workspace.")
            # Preserve original creation timestamp on update
            asset_record["createdAt"] = items[existing_idx].get("createdAt", created_at)
            if not asset_record.get("localPath"):
                asset_record["localPath"] = items[existing_idx].get("localPath")
            items[existing_idx] = asset_record
        else:
            items.insert(0, asset_record)

        _save_library_raw(items)

    logger.info("Registered studio asset: id=%s provider=%s model=%s type=%s", asset_id, provider, model, studio_type)
    return asset_record


def _ws(workspace_id: Optional[str]) -> str:
    """Normalise a workspace id. Omitted/blank means the ``default`` workspace,
    never "all workspaces"."""
    return (workspace_id or "").strip() or "default"


def list_assets(
    studio_type: Optional[str] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    search: Optional[str] = None,
    workspace_id: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """List assets with filtering, workspace scoping, and pagination.

    Scoping is strict: only assets whose ``workspaceId`` equals the requested
    workspace (``default`` when omitted) are ever returned.
    """
    with _lock:
        items = _load_library_raw()

    wanted_ws = _ws(workspace_id)
    items = [x for x in items if _ws(x.get("workspaceId")) == wanted_ws]

    if studio_type:
        st_lc = studio_type.lower()
        if st_lc == "image":
            items = [x for x in items if x.get("studioType") in ("image", "i2i", "t2i", "cinema", "design-agent")]
        elif st_lc == "video":
            items = [x for x in items if x.get("studioType") in ("video", "t2v", "i2v", "vibe-motion", "clipping", "lipsync", "body-swap")]
        elif st_lc == "audio":
            items = [x for x in items if x.get("studioType") == "audio"]
        else:
            items = [x for x in items if x.get("studioType") == st_lc]

    if provider:
        p_lc = provider.lower()
        items = [x for x in items if x.get("provider", "").lower() == p_lc]

    if model:
        m_lc = model.lower()
        items = [x for x in items if m_lc in x.get("model", "").lower()]

    if search:
        s_lc = search.lower().strip()
        items = [
            x for x in items
            if s_lc in x.get("prompt", "").lower()
            or s_lc in x.get("model", "").lower()
            or any(s_lc in tag.lower() for tag in x.get("tags", []))
        ]

    # Chronological sort: newest first
    items.sort(key=lambda x: x.get("createdAt", 0), reverse=True)

    return items[offset : offset + limit]


def get_asset(asset_id: str, workspace_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Retrieve a single asset by ID, scoped to a workspace.

    Returns ``None`` both when the asset does not exist and when it belongs to
    another workspace, so callers cannot probe for foreign asset ids.
    """
    with _lock:
        items = _load_library_raw()
    wanted_ws = _ws(workspace_id)
    return next(
        (x for x in items if x.get("id") == asset_id and _ws(x.get("workspaceId")) == wanted_ws),
        None,
    )


def delete_asset(asset_id: str, workspace_id: Optional[str] = None) -> bool:
    """Delete an asset by ID. Only assets in the caller's workspace can be deleted."""
    wanted_ws = _ws(workspace_id)
    with _lock:
        items = _load_library_raw()
        target = next(
            (x for x in items if x.get("id") == asset_id and _ws(x.get("workspaceId")) == wanted_ws),
            None,
        )
        if not target:
            return False

        filtered = [x for x in items if x.get("id") != asset_id]
        _save_library_raw(filtered)

    # Clean up the cached binary only if it lives inside the studio assets dir
    # (never delete a file we do not own, e.g. a shared images cache entry).
    local_path = target.get("localPath")
    if local_path and os.path.exists(local_path):
        try:
            assets_root = get_image_studio_assets_dir().resolve()
            if Path(local_path).resolve().is_relative_to(assets_root):
                os.remove(local_path)
        except Exception as exc:
            logger.debug("Failed to remove cached asset file %s: %s", local_path, exc)

    return True


_MAX_DATA_URL_BYTES = 25 * 1024 * 1024
_MIME_EXT = {
    "image/png": "png", "image/jpeg": "jpg", "image/webp": "webp", "image/gif": "gif",
    "video/mp4": "mp4", "video/webm": "webm", "audio/mpeg": "mp3", "audio/wav": "wav",
}


def materialize_asset(asset_id: str, workspace_id: Optional[str] = None) -> Optional[Path]:
    """Ensure the asset's bytes exist as a local file and return its path.

    Needed by consumers that only accept filesystem paths (chat ``image.attach``).
    Handles existing local files, ``data:`` URLs and remote http(s) URLs (the
    latter only if they pass the shared SSRF guard). Raises ``ValueError`` if
    the asset cannot be fetched; returns ``None`` if it does not exist in the
    caller's workspace.
    """
    import re

    asset = get_asset(asset_id, workspace_id)
    if not asset:
        return None

    existing = asset.get("localPath")
    if existing and os.path.isfile(existing):
        return Path(existing)

    url = asset.get("url") or ""
    dest_dir = get_image_studio_assets_dir()
    mime = asset.get("mimeType") or "image/png"

    if url.startswith("data:"):
        m = re.match(r"data:([\w/+.-]+);base64,(.*)$", url, re.DOTALL)
        if not m:
            raise ValueError("Unsupported data URL encoding for asset.")
        mime = m.group(1)
        raw = base64.b64decode(m.group(2))
        if len(raw) > _MAX_DATA_URL_BYTES:
            raise ValueError("Asset exceeds the maximum supported size.")
        path = dest_dir / f"{asset_id}.{_MIME_EXT.get(mime, 'bin')}"
        path.write_bytes(raw)
    elif url.startswith(("http://", "https://")):
        from tools.url_safety import is_safe_url
        if not is_safe_url(url):
            raise ValueError("Asset URL was blocked by the URL safety policy.")
        from agent.image_gen_provider import save_url_image
        downloaded = save_url_image(url, prefix=f"studio_{asset_id[:8]}", max_bytes=_MAX_DATA_URL_BYTES)
        path = dest_dir / f"{asset_id}{downloaded.suffix}"
        downloaded.replace(path)
    else:
        raise ValueError("Asset has no retrievable location.")

    # Persist the local path so restarts and later calls reuse the file.
    with _lock:
        items = _load_library_raw()
        for x in items:
            if x.get("id") == asset_id:
                x["localPath"] = str(path)
                break
        _save_library_raw(items)
    return path


def read_asset_data_url(asset_id: str, workspace_id: Optional[str] = None) -> Optional[Dict[str, str]]:
    """Return ``{"dataUrl", "mimeType"}`` for a locally stored asset (workspace-scoped)."""
    path = materialize_asset(asset_id, workspace_id)
    if path is None:
        return None
    asset = get_asset(asset_id, workspace_id) or {}
    mime = asset.get("mimeType") or "image/png"
    return {
        "dataUrl": f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}",
        "mimeType": mime,
    }


# ---------------------------------------------------------------------------
# Synchronized Model Catalog & Providers
# ---------------------------------------------------------------------------

def get_providers_info() -> List[Dict[str, Any]]:
    """Return configured status and capabilities for all supported providers."""
    from hermes_cli.config import load_config
    cfg = load_config() if isinstance(load_config(), dict) else {}
    image_gen_cfg = cfg.get("image_gen", {}) if isinstance(cfg.get("image_gen"), dict) else {}
    configured_provider = (image_gen_cfg.get("provider") or "fal").lower().strip()

    fal_key = os.getenv("FAL_KEY", "").strip()
    muapi_key = os.getenv("MUAPI_KEY", "").strip()

    # Check managed FAL gateway
    has_fal = bool(fal_key)
    if not has_fal:
        try:
            from tools.tool_backend_helpers import fal_key_is_configured
            has_fal = fal_key_is_configured()
        except Exception:
            pass

    return [
        {
            "id": "fal",
            "name": "FAL.ai",
            "isPrimary": True,
            "configured": has_fal,
            "active": (configured_provider == "fal"),
            "description": "Primary high-performance generative AI infrastructure (FLUX 2, Nano Banana, Veo 3.1, LTX 2.3, Recraft)",
            "capabilities": {
                "textToImage": True,
                "imageToImage": True,
                "imageEdit": True,
                "upscaling": True,
                "textToVideo": True,
                "imageToVideo": True,
                "audio": True,
                "clipping": False,
                "lipsync": False,
                "recast": False,
                "workflows": False,
            },
        },
        {
            "id": "muapi",
            "name": "MuAPI",
            "isPrimary": False,
            "configured": bool(muapi_key),
            "active": (configured_provider == "muapi"),
            "description": "Optional creative provider with specialized community studios (LipSync, BodySwap, Workflows)",
            "capabilities": {
                "textToImage": True,
                "imageToImage": True,
                "imageEdit": True,
                "upscaling": True,
                "textToVideo": True,
                "imageToVideo": True,
                "audio": True,
                "clipping": True,
                "lipsync": True,
                "recast": True,
                "workflows": True,
            },
        },
    ]


def get_synchronized_model_catalog() -> Dict[str, Any]:
    """Return authoritative synchronized model catalog including FAL.ai and MuAPI models."""
    from tools.image_generation_tool import FAL_MODELS
    from plugins.video_gen.fal import FAL_FAMILIES

    image_models: List[Dict[str, Any]] = []
    for model_id, meta in FAL_MODELS.items():
        image_models.append({
            "id": model_id,
            "name": meta.get("display", model_id),
            "provider": "fal",
            "providerName": "FAL.ai",
            "category": "image",
            "capabilities": ["text-to-image", "image-to-image"],
            "speed": meta.get("speed", ""),
            "strengths": meta.get("strengths", ""),
            "price": meta.get("price", ""),
            "aspectRatios": ["16:9", "1:1", "9:16", "4:3", "3:4"],
            "defaultAspectRatio": "16:9",
        })

    video_models: List[Dict[str, Any]] = []
    for family_id, meta in FAL_FAMILIES.items():
        video_models.append({
            "id": family_id,
            "name": meta.get("display", family_id),
            "provider": "fal",
            "providerName": "FAL.ai",
            "category": "video",
            "capabilities": ["text-to-video", "image-to-video"],
            "speed": meta.get("speed", ""),
            "strengths": meta.get("strengths", ""),
            "price": meta.get("price", ""),
            "resolutions": list(meta.get("resolutions") or ["720p", "1080p"]),
            "durations": list(meta.get("durations") or [5, 10]),
            "audioSupported": bool(meta.get("audio", False)),
        })

    return {
        "providers": get_providers_info(),
        "imageModels": image_models,
        "videoModels": video_models,
    }



# ---------------------------------------------------------------------------
# Generation job lifecycle
# ---------------------------------------------------------------------------
#
# REQUESTED -> VALIDATING -> SUBMITTED -> PROCESSING -> COMPLETED | FAILED | CANCELLED
#
# Jobs are persisted to ``jobs.json`` so state survives navigation and restarts.
# A job is only COMPLETED when its asset has actually been registered.
# Non-terminal jobs left behind by a previous process are failed on first use
# ("interrupted"), and non-terminal jobs older than JOB_TIMEOUT_S are failed
# ("timed out") so nothing stays in a loading state forever.

JOB_STATES = ("REQUESTED", "VALIDATING", "SUBMITTED", "PROCESSING", "COMPLETED", "FAILED", "CANCELLED")
JOB_TERMINAL = frozenset({"COMPLETED", "FAILED", "CANCELLED"})
_JOB_TRANSITIONS = {
    "REQUESTED": {"VALIDATING", "FAILED", "CANCELLED"},
    "VALIDATING": {"SUBMITTED", "FAILED", "CANCELLED"},
    "SUBMITTED": {"PROCESSING", "COMPLETED", "FAILED", "CANCELLED"},
    "PROCESSING": {"COMPLETED", "FAILED", "CANCELLED"},
}
JOB_TIMEOUT_S = 15 * 60
_BOOT_ID = uuid.uuid4().hex
_recovered = False


def _jobs_path() -> Path:
    return get_image_studio_dir() / "jobs.json"


def _load_jobs_raw() -> List[Dict[str, Any]]:
    p = _jobs_path()
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
        except Exception as exc:
            logger.warning("Failed to parse image studio jobs.json: %s", exc)
    return []


def _save_jobs_raw(jobs: List[Dict[str, Any]]) -> None:
    p = _jobs_path()
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(jobs[:500], indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)


def _fail_stale(jobs: List[Dict[str, Any]]) -> bool:
    """Fail orphaned/timed-out non-terminal jobs in place. Returns True if changed."""
    global _recovered
    changed = False
    now = int(time.time() * 1000)
    first_pass = not _recovered
    for j in jobs:
        if j.get("state") in JOB_TERMINAL:
            continue
        if first_pass and j.get("bootId") != _BOOT_ID:
            j.update(state="FAILED", error="Generation was interrupted by an application restart.",
                     errorType="interrupted", updatedAt=now)
            changed = True
        elif now - int(j.get("updatedAt") or j.get("createdAt") or now) > JOB_TIMEOUT_S * 1000:
            j.update(state="FAILED", error="Generation timed out.", errorType="timeout", updatedAt=now)
            changed = True
    _recovered = True
    return changed


def create_job(
    kind: str,
    request: Dict[str, Any],
    workspace_id: Optional[str] = None,
    client_request_id: Optional[str] = None,
) -> Tuple[Dict[str, Any], bool]:
    """Create a job (state REQUESTED). Returns ``(job, created)``.

    If ``client_request_id`` matches a job already known in this workspace, that
    job is returned with ``created=False`` so duplicate submissions (double
    click, retry after a dropped response) never trigger a second generation.
    """
    ws = _ws(workspace_id)
    with _lock:
        jobs = _load_jobs_raw()
        if _fail_stale(jobs):
            _save_jobs_raw(jobs)
        if client_request_id:
            dup = next(
                (j for j in jobs if j.get("clientRequestId") == client_request_id and _ws(j.get("workspaceId")) == ws),
                None,
            )
            if dup:
                return dup, False
        now = int(time.time() * 1000)
        job = {
            "id": str(uuid.uuid4()),
            "kind": kind,
            "state": "REQUESTED",
            "workspaceId": ws,
            "clientRequestId": client_request_id,
            "bootId": _BOOT_ID,
            "request": {k: v for k, v in request.items() if k not in ("apiKey", "api_key")},
            "assetIds": [],
            "error": None,
            "errorType": None,
            "createdAt": now,
            "updatedAt": now,
        }
        jobs.insert(0, job)
        _save_jobs_raw(jobs)
        return job, True


def update_job(job_id: str, state: str, **fields: Any) -> Optional[Dict[str, Any]]:
    """Move a job to ``state`` if the transition is legal; terminal states are final."""
    if state not in JOB_STATES:
        raise ValueError(f"Unknown job state: {state}")
    with _lock:
        jobs = _load_jobs_raw()
        job = next((j for j in jobs if j.get("id") == job_id), None)
        if not job:
            return None
        current = job.get("state")
        if current in JOB_TERMINAL:
            return job  # never resurrect or overwrite a finished job
        if state != current and state not in _JOB_TRANSITIONS.get(current, set()):
            raise ValueError(f"Illegal job transition {current} -> {state}")
        job.update(fields)
        job["state"] = state
        job["updatedAt"] = int(time.time() * 1000)
        _save_jobs_raw(jobs)
        return job


def get_job(job_id: str, workspace_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    ws = _ws(workspace_id)
    with _lock:
        jobs = _load_jobs_raw()
        if _fail_stale(jobs):
            _save_jobs_raw(jobs)
    return next((j for j in jobs if j.get("id") == job_id and _ws(j.get("workspaceId")) == ws), None)


def cancel_job(job_id: str, workspace_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Mark a job CANCELLED. A provider call already in flight cannot be aborted,
    but its result is discarded and never registered as an asset."""
    if not get_job(job_id, workspace_id):
        return None
    return update_job(job_id, "CANCELLED", error="Cancelled by user.", errorType="cancelled")


def normalize_provider_error(exc_or_msg: Any) -> Tuple[str, str]:
    """Map a provider exception/message to ``(error_type, safe_message)``.

    The message never contains credentials: key-looking tokens are redacted.
    """
    import re

    raw = str(exc_or_msg) or exc_or_msg.__class__.__name__
    low = raw.lower()
    if "401" in low or "403" in low or "unauthorized" in low or "forbidden" in low or "invalid api key" in low:
        etype, msg = "auth_invalid_credentials", "The provider rejected the API key. Check it in Settings."
    elif "429" in low or "rate limit" in low or "quota" in low or "insufficient" in low:
        etype, msg = "quota_or_rate_limited", "The provider rate limit or quota was reached. Try again later or check your balance."
    elif isinstance(exc_or_msg, TimeoutError) or "timed out" in low or "timeout" in low:
        etype, msg = "timeout", "The provider timed out. Nothing was generated; you can retry."
    elif isinstance(exc_or_msg, ConnectionError) or "connection" in low or "network" in low or "dns" in low:
        etype, msg = "network_error", "Could not reach the provider. Check your connection and retry."
    else:
        etype, msg = "generation_failed", raw
    msg = re.sub(r"(?i)(key|token|secret|bearer)[\s:=]+[A-Za-z0-9._\-:]{12,}", r"\1 [redacted]", msg)
    return etype, msg[:500]


def execute_generation(
    job_id: str,
    provider: Any,
    prompt: str,
    *,
    model: Optional[str] = None,
    parameters: Optional[Dict[str, Any]] = None,
    workspace_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
    studio_type: str = "image",
) -> Dict[str, Any]:
    """Drive one generation job through its lifecycle and register the asset.

    Synchronous (call it from a worker thread). Returns
    ``{"job": ..., "asset": ... | None}``. The asset exists only when the job
    ended COMPLETED; every other outcome leaves no asset behind.
    """
    params = dict(parameters or {})

    def _fail(etype: str, msg: str) -> Dict[str, Any]:
        job = update_job(job_id, "FAILED", error=msg, errorType=etype)
        return {"job": job, "asset": None}

    update_job(job_id, "VALIDATING")
    if not (prompt or "").strip():
        return _fail("validation_error", "A prompt is required.")
    if provider is None:
        return _fail("provider_unavailable", "The selected provider is not available.")
    if not provider.is_available():
        return _fail("auth_missing_credentials",
                     f"Provider '{provider.name}' is not configured. Add its API key in Settings.")

    update_job(job_id, "SUBMITTED", provider=provider.name, model=model)
    update_job(job_id, "PROCESSING")
    try:
        kwargs = {"aspect_ratio": params.get("aspectRatio") or params.get("aspect_ratio") or "16:9"}
        if model:
            kwargs["model"] = model
        res = provider.generate(prompt=prompt, **kwargs)
    except Exception as exc:  # provider SDKs raise many types
        etype, msg = normalize_provider_error(exc)
        logger.warning("Generation job %s failed (%s)", job_id, etype)
        return _fail(etype, msg)

    # Cancelled while the provider call was in flight: discard the result.
    current = get_job(job_id, workspace_id)
    if current and current.get("state") == "CANCELLED":
        return {"job": current, "asset": None}

    if not isinstance(res, dict) or not res.get("success"):
        etype, msg = normalize_provider_error((res or {}).get("error") or "Image generation failed.")
        return _fail((res or {}).get("error_type") or etype, msg)

    location = res.get("image")
    if not location:
        return _fail("empty_result", "The provider finished without returning an asset.")

    is_local = isinstance(location, str) and not location.startswith(("http://", "https://", "data:")) \
        and os.path.isfile(location)
    try:
        asset = register_asset(
            url="" if is_local else location,
            local_path=location if is_local else None,
            prompt=prompt,
            provider=provider.name,
            model=model or (provider.default_model() if callable(getattr(provider, "default_model", None)) else None) or "default",
            studio_type=studio_type,
            parameters=params,
            workspace_id=workspace_id or "default",
            conversation_id=conversation_id,
            job_id=job_id,
            status="completed",
        )
    except Exception as exc:
        logger.error("Could not register asset for job %s: %s", job_id, exc)
        return _fail("storage_failed", "The image was generated but could not be saved to history.")

    job = update_job(job_id, "COMPLETED", assetIds=[asset["id"]])
    return {"job": job, "asset": asset}
