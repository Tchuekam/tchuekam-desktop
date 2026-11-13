"""MuAPI image generation backend.

Wraps MuAPI models as an :class:`ImageGenProvider` implementation.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional
import urllib.request
import urllib.error

from agent.image_gen_provider import (
    DEFAULT_ASPECT_RATIO,
    ImageGenProvider,
    error_response,
    resolve_aspect_ratio,
    save_url_image,
    success_response,
)

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "flux-schnell"

_MODELS: Dict[str, Dict[str, Any]] = {
    "flux-schnell": {
        "display": "FLUX Schnell (MuAPI)",
        "speed": "~3s",
        "strengths": "Fast iteration, versatile styles",
        "endpoint": "flux-schnell",
    },
    "flux-dev": {
        "display": "FLUX Dev (MuAPI)",
        "speed": "~8s",
        "strengths": "High detail, quality text",
        "endpoint": "flux-dev",
    },
    "nano-banana": {
        "display": "Nano Banana (MuAPI)",
        "speed": "~5s",
        "strengths": "Vibrant illustration and photorealism",
        "endpoint": "nano-banana",
    },
}


class MuapiImageGenProvider(ImageGenProvider):
    """MuAPI image generation backend."""

    @property
    def name(self) -> str:
        return "muapi"

    @property
    def display_name(self) -> str:
        return "MuAPI"

    def is_available(self) -> bool:
        return bool(os.getenv("MUAPI_KEY", "").strip())

    def list_models(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": mid,
                "display": meta["display"],
                "speed": meta["speed"],
                "strengths": meta["strengths"],
            }
            for mid, meta in _MODELS.items()
        ]

    def default_model(self) -> Optional[str]:
        return DEFAULT_MODEL

    def get_setup_schema(self) -> Dict[str, Any]:
        return {
            "name": "MuAPI",
            "badge": "optional",
            "tag": "Creative studio model provider",
            "env_vars": [
                {
                    "key": "MUAPI_KEY",
                    "prompt": "MuAPI API key",
                    "url": "https://muapi.ai",
                },
            ],
        }

    def generate(
        self,
        prompt: str,
        aspect_ratio: str = DEFAULT_ASPECT_RATIO,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        api_key = os.getenv("MUAPI_KEY", "").strip()
        if not api_key:
            return error_response(
                "MUAPI_KEY is not configured. Please set your MuAPI key in Settings.",
                error_type="auth_missing_credentials",
                provider=self.name,
                prompt=prompt,
                aspect_ratio=aspect_ratio,
            )

        model_id = kwargs.get("model") or DEFAULT_MODEL
        endpoint = _MODELS.get(model_id, {}).get("endpoint", model_id)

        ratio_map = {
            "landscape": "16:9",
            "square": "1:1",
            "portrait": "9:16",
        }
        mapped_ratio = ratio_map.get(aspect_ratio, aspect_ratio)

        payload = {
            "prompt": prompt,
            "aspect_ratio": mapped_ratio,
        }

        base_url = "https://api.muapi.ai/api/v1"
        submit_url = f"{base_url}/{endpoint}"

        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "User-Agent": "TchueKAM-ImageStudio/1.0",
        }

        try:
            req = urllib.request.Request(
                submit_url,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            request_id = data.get("request_id") or data.get("id")
            if not request_id and data.get("url"):
                saved_path = save_url_image(data["url"], prefix="muapi")
                return success_response(
                    image=str(saved_path),
                    model=model_id,
                    prompt=prompt,
                    aspect_ratio=aspect_ratio,
                    provider=self.name,
                )

            if not request_id:
                return error_response(
                    "Unexpected response structure from MuAPI",
                    error_type="provider_contract",
                    provider=self.name,
                    prompt=prompt,
                    aspect_ratio=aspect_ratio,
                )

            # Poll for result
            poll_url = f"{base_url}/predictions/{request_id}/result"
            for _ in range(60):
                time.sleep(2)
                try:
                    p_req = urllib.request.Request(poll_url, headers=headers, method="GET")
                    with urllib.request.urlopen(p_req, timeout=15) as p_resp:
                        poll_data = json.loads(p_resp.read().decode("utf-8"))
                        status = (poll_data.get("status") or "").lower()
                        if status in ("completed", "succeeded", "success"):
                            out_url = (
                                (poll_data.get("outputs") or [None])[0]
                                or poll_data.get("url")
                                or (poll_data.get("output") or {}).get("url")
                            )
                            if out_url:
                                saved = save_url_image(out_url, prefix="muapi")
                                return success_response(
                                    image=str(saved),
                                    model=model_id,
                                    prompt=prompt,
                                    aspect_ratio=aspect_ratio,
                                    provider=self.name,
                                )
                            break
                        if status in ("failed", "error"):
                            return error_response(
                                poll_data.get("error") or "MuAPI generation failed",
                                error_type="generation_failed",
                                provider=self.name,
                                prompt=prompt,
                                aspect_ratio=aspect_ratio,
                            )
                except urllib.error.HTTPError as he:
                    if he.code in (401, 403):
                        return error_response(
                            "MuAPI authentication rejected. Please check your API key.",
                            error_type="auth_invalid_credentials",
                            provider=self.name,
                            prompt=prompt,
                            aspect_ratio=aspect_ratio,
                        )
                    continue

            return error_response(
                "MuAPI generation timed out after polling",
                error_type="timeout",
                provider=self.name,
                prompt=prompt,
                aspect_ratio=aspect_ratio,
            )

        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                return error_response(
                    "MuAPI authentication failed. Please verify your API key.",
                    error_type="auth_invalid_credentials",
                    provider=self.name,
                    prompt=prompt,
                    aspect_ratio=aspect_ratio,
                )
            return error_response(
                f"MuAPI HTTP error ({e.code}): {e.reason}",
                error_type="http_error",
                provider=self.name,
                prompt=prompt,
                aspect_ratio=aspect_ratio,
            )
        except Exception as e:
            return error_response(
                f"MuAPI error: {str(e)}",
                error_type="provider_exception",
                provider=self.name,
                prompt=prompt,
                aspect_ratio=aspect_ratio,
            )


def register(ctx) -> None:
    """Register MuapiImageGenProvider into the agent image gen registry."""
    ctx.register_image_gen_provider(MuapiImageGenProvider())

