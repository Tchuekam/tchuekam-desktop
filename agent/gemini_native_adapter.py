"""OpenAI-compatible facade over Google AI Studio's native Gemini API.

Hermes keeps ``api_mode='chat_completions'`` for the ``gemini`` provider so the
main agent loop can keep using its existing OpenAI-shaped message flow.
This adapter is the transport shim that converts those OpenAI-style
``messages[]`` / ``tools[]`` requests into Gemini's native
``models/{model}:generateContent`` schema and converts the responses back.

Why this exists
---------------
Google's OpenAI-compatible endpoint has been brittle for Hermes's multi-turn
agent/tool loop (auth churn, tool-call replay quirks, thought-signature
requirements).  The native Gemini API is the canonical path and avoids the
OpenAI-compat layer entirely.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import time
import uuid
from types import SimpleNamespace
from typing import Any, Dict, Iterator, List, Optional

import httpx

from agent.gemini_schema import sanitize_gemini_tool_parameters

logger = logging.getLogger(__name__)

DEFAULT_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


def is_native_gemini_base_url(base_url: str) -> bool:
    """Return True when the endpoint speaks Gemini's native REST API."""
    normalized = str(base_url or "").strip().rstrip("/").lower()
    if not normalized:
        return False
    if "generativelanguage.googleapis.com" not in normalized:
        return False
    return not normalized.endswith("/openai")


def probe_gemini_tier(
    api_key: str,
    base_url: str = DEFAULT_GEMINI_BASE_URL,
    *,
    model: str = "gemini-2.5-flash",
    timeout: float = 10.0,
) -> str:
    """Probe a Google AI Studio API key and return its tier.

    Returns one of:

    - ``"free"``    -- key is on the free tier (unusable with Hermes)
    - ``"paid"``    -- key is on a paid tier
    - ``"unknown"`` -- probe failed; callers should proceed without blocking.
    """
    key = (api_key or "").strip()
    if not key:
        return "unknown"

    normalized_base = str(base_url or DEFAULT_GEMINI_BASE_URL).strip().rstrip("/")
    if not normalized_base:
        normalized_base = DEFAULT_GEMINI_BASE_URL
    if normalized_base.lower().endswith("/openai"):
        normalized_base = normalized_base[: -len("/openai")]

    url = f"{normalized_base}/models/{model}:generateContent"
    payload = {
        "contents": [{"role": "user", "parts": [{"text": "hi"}]}],
        "generationConfig": {"maxOutputTokens": 1},
    }

    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(
                url,
                params={"key": key},
                json=payload,
                headers={"Content-Type": "application/json"},
            )
    except Exception as exc:
        logger.debug("probe_gemini_tier: network error: %s", exc)
        return "unknown"

    headers_lower = {k.lower(): v for k, v in resp.headers.items()}
    rpd_header = headers_lower.get("x-ratelimit-limit-requests-per-day")
    if rpd_header:
        try:
            rpd_val = int(rpd_header)
        except (TypeError, ValueError):
            rpd_val = None
        # Published free-tier daily caps (Dec 2025):
        #   gemini-2.5-pro: 100, gemini-2.5-flash: 250, flash-lite: 1000
        # Tier 1 starts at ~1500+ for Flash. We treat <= 1000 as free.
        if rpd_val is not None and rpd_val <= 1000:
            return "free"
        if rpd_val is not None and rpd_val > 1000:
            return "paid"

    if resp.status_code == 429:
        body_text = ""
        try:
            body_text = resp.text or ""
        except Exception:
            body_text = ""
        if "free_tier" in body_text.lower():
            return "free"
        return "paid"

    if 200 <= resp.status_code < 300:
        return "paid"

    return "unknown"


def is_free_tier_quota_error(error_message: str) -> bool:
    """Return True when a Gemini 429 message indicates free-tier exhaustion."""
    if not error_message:
        return False
    return "free_tier" in error_message.lower()


_FREE_TIER_GUIDANCE = (
    "\n\nYour Google API key is on the free tier (<= 250 requests/day for "
    "gemini-2.5-flash). Hermes typically makes 3-10 API calls per user turn, "
    "so the free tier is exhausted in a handful of messages and cannot sustain "
    "an agent session. Enable billing on your Google Cloud project and "
    "regenerate the key in a billing-enabled project: "
    "https://aistudio.google.com/apikey"
)


class GeminiAPIError(Exception):
    """Error shape compatible with Hermes retry/error classification."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "gemini_api_error",
        status_code: Optional[int] = None,
        response: Optional[httpx.Response] = None,
        retry_after: Optional[float] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.response = response
        self.retry_after = retry_after
        self.details = details or {}


def _coerce_content_to_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        pieces: List[str] = []
        for part in content:
            if isinstance(part, str):
                pieces.append(part)
            elif isinstance(part, dict) and part.get("type") == "text":
                text = part.get("text")
                if isinstance(text, str):
                    pieces.append(text)
        return "\n".join(pieces)
    return str(content)


def _extract_multimodal_parts(content: Any) -> List[Dict[str, Any]]:
    if not isinstance(content, list):
        text = _coerce_content_to_text(content)
        return [{"text": text}] if text else []

    parts: List[Dict[str, Any]] = []
    for item in content:
        if isinstance(item, str):
            parts.append({"text": item})
            continue
        if not isinstance(item, dict):
            continue
        ptype = item.get("type")
        if ptype == "text":
            text = item.get("text")
            if isinstance(text, str) and text:
                parts.append({"text": text})
        elif ptype == "image_url":
            url = ((item.get("image_url") or {}).get("url") or "")
            if not isinstance(url, str) or not url.startswith("data:"):
                continue
            try:
                header, encoded = url.split(",", 1)
                mime = header.split(":", 1)[1].split(";", 1)[0]
                raw = base64.b64decode(encoded)
            except Exception:
                continue
            parts.append(
                {
                    "inlineData": {
                        "mimeType": mime,
                        "data": base64.b64encode(raw).decode("ascii"),
                    }
                }
            )
    return parts


def _tool_call_extra_signature(tool_call: Dict[str, Any]) -> Optional[str]:
    extra = tool_call.get("extra_content") or {}
    if not isinstance(extra, dict):
        return None
    google = extra.get("google") or extra.get("thought_signature")
    if isinstance(google, dict):
        sig = google.get("thought_signature") or google.get("thoughtSignature")
        return str(sig) if isinstance(sig, str) and sig else None
    if isinstance(google, str) and google:
        return google
    return None


def _translate_tool_call_to_gemini(tool_call: Dict[str, Any]) -> Dict[str, Any]:
    fn = tool_call.get("function") or {}
    args_raw = fn.get("arguments", "")
    try:
        args = json.loads(args_raw) if isinstance(args_raw, str) and args_raw else {}
    except json.JSONDecodeError:
        args = {"_raw": args_raw}
    if not isinstance(args, dict):
        args = {"_value": args}

    part: Dict[str, Any] = {
        "functionCall": {
            "name": str(fn.get("name") or ""),
            "args": args,
        }
    }
    thought_signature = _tool_call_extra_signature(tool_call)
    if thought_signature:
        part["thoughtSignature"] = thought_signature
    return part


def _translate_tool_result_to_gemini(
    message: Dict[str, Any],
    tool_name_by_call_id: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    tool_name_by_call_id = tool_name_by_call_id or {}
    tool_call_id = str(message.get("tool_call_id") or "")
    name = str(
        message.get("name")
        or tool_name_by_call_id.get(tool_call_id)
        or tool_call_id
        or "tool"
    )
    content = _coerce_content_to_text(message.get("content"))
    try:
        parsed = json.loads(content) if content.strip().startswith(("{", "[")) else None
    except json.JSONDecodeError:
        parsed = None
    response = parsed if isinstance(parsed, dict) else {"output": content}
    return {
        "functionResponse": {
            "name": name,
            "response": response,
        }
    }


def _append_or_merge_gemini_content(
    contents: List[Dict[str, Any]],
    role: str,
    parts: List[Dict[str, Any]],
) -> None:
    if not parts:
        return
    if contents and contents[-1].get("role") == role and isinstance(contents[-1].get("parts"), list):
        contents[-1]["parts"].extend(parts)
    else:
        contents.append({"role": role, "parts": list(parts)})


def _build_gemini_contents(messages: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    system_text_parts: List[str] = []
    contents: List[Dict[str, Any]] = []
    tool_name_by_call_id: Dict[str, str] = {}

    for msg in messages:
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role") or "user")

        if role == "system":
            system_text_parts.append(_coerce_content_to_text(msg.get("content")))
            continue

        if role in {"tool", "function"}:
            _append_or_merge_gemini_content(
                contents,
                "user",
                [
                    _translate_tool_result_to_gemini(
                        msg,
                        tool_name_by_call_id=tool_name_by_call_id,
                    )
                ],
            )
            continue

        gemini_role = "model" if role == "assistant" else "user"
        parts: List[Dict[str, Any]] = []

        content_parts = _extract_multimodal_parts(msg.get("content"))
        parts.extend(content_parts)

        tool_calls = msg.get("tool_calls") or []
        if isinstance(tool_calls, list):
            for tool_call in tool_calls:
                if isinstance(tool_call, dict):
                    tool_call_id = str(tool_call.get("id") or tool_call.get("call_id") or "")
                    tool_name = str(((tool_call.get("function") or {}).get("name") or ""))
                    if tool_call_id and tool_name:
                        tool_name_by_call_id[tool_call_id] = tool_name
                    parts.append(_translate_tool_call_to_gemini(tool_call))

        if parts:
            _append_or_merge_gemini_content(contents, gemini_role, parts)

    system_instruction = None
    joined_system = "\n".join(part for part in system_text_parts if part).strip()
    if joined_system:
        system_instruction = {"parts": [{"text": joined_system}]}
    return contents, system_instruction


def _translate_tools_to_gemini(tools: Any) -> List[Dict[str, Any]]:
    if not isinstance(tools, list):
        return []
    declarations: List[Dict[str, Any]] = []
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        fn = tool.get("function") or {}
        if not isinstance(fn, dict):
            continue
        name = fn.get("name")
        if not isinstance(name, str) or not name:
            continue
        decl: Dict[str, Any] = {"name": name}
        description = fn.get("description")
        if isinstance(description, str) and description:
            decl["description"] = description
        parameters = fn.get("parameters")
        if isinstance(parameters, dict):
            decl["parameters"] = sanitize_gemini_tool_parameters(parameters)
        declarations.append(decl)
    return [{"functionDeclarations": declarations}] if declarations else []


def _translate_tool_choice_to_gemini(tool_choice: Any) -> Optional[Dict[str, Any]]:
    if tool_choice is None:
        return None
    if isinstance(tool_choice, str):
        if tool_choice == "auto":
            return {"functionCallingConfig": {"mode": "AUTO"}}
        if tool_choice == "required":
            return {"functionCallingConfig": {"mode": "ANY"}}
        if tool_choice == "none":
            return {"functionCallingConfig": {"mode": "NONE"}}
    if isinstance(tool_choice, dict):
        fn = tool_choice.get("function") or {}
        name = fn.get("name")
        if isinstance(name, str) and name:
            return {"functionCallingConfig": {"mode": "ANY", "allowedFunctionNames": [name]}}
    return None


def _normalize_thinking_config(config: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(config, dict) or not config:
        return None
    budget = config.get("thinkingBudget", config.get("thinking_budget"))
    include = config.get("includeThoughts", config.get("include_thoughts"))
    level = config.get("thinkingLevel", config.get("thinking_level"))
    normalized: Dict[str, Any] = {}
    if isinstance(budget, (int, float)):
        normalized["thinkingBudget"] = int(budget)
    if isinstance(include, bool):
        normalized["includeThoughts"] = include
    if isinstance(level, str) and level.strip():
        normalized["thinkingLevel"] = level.strip().lower()
    return normalized or None


def build_gemini_request(
    *,
    messages: List[Dict[str, Any]],
    tools: Any = None,
    tool_choice: Any = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    top_p: Optional[float] = None,
    stop: Any = None,
    thinking_config: Any = None,
) -> Dict[str, Any]:
    contents, system_instruction = _build_gemini_contents(messages)
    request: Dict[str, Any] = {"contents": contents}
    if system_instruction:
        request["systemInstruction"] = system_instruction

    gemini_tools = _translate_tools_to_gemini(tools)
    if gemini_tools:
        request["tools"] = gemini_tools

    tool_config = _translate_tool_choice_to_gemini(tool_choice)
    if tool_config:
        request["toolConfig"] = tool_config

    generation_config: Dict[str, Any] = {}
    if temperature is not None:
        generation_config["temperature"] = temperature
    if max_tokens is not None:
        generation_config["maxOutputTokens"] = max_tokens
    if top_p is not None:
        generation_config["topP"] = top_p
    if stop:
        generation_config["stopSequences"] = stop if isinstance(stop, list) else [str(stop)]
    normalized_thinking = _normalize_thinking_config(thinking_config)
    if normalized_thinking:
        generation_config["thinkingConfig"] = normalized_thinking
    if generation_config:
        request["generationConfig"] = generation_config

    return request


def _map_gemini_finish_reason(reason: str) -> str:
    mapping = {
        "STOP": "stop",
        "MAX_TOKENS": "length",
        "SAFETY": "content_filter",
        "RECITATION": "content_filter",
        "OTHER": "stop",
    }
    return mapping.get(str(reason or "").upper(), "stop")


def _tool_call_extra_from_part(part: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    sig = part.get("thoughtSignature")
    if isinstance(sig, str) and sig:
        return {"google": {"thought_signature": sig}}
    return None


def _empty_response(model: str) -> SimpleNamespace:
    message = SimpleNamespace(
        role="assistant",
        content="",
        tool_calls=None,
        reasoning=None,
        reasoning_content=None,
        reasoning_details=None,
    )
    choice = SimpleNamespace(index=0, message=message, finish_reason="stop")
    usage = SimpleNamespace(
        prompt_tokens=0,
        completion_tokens=0,
        total_tokens=0,
        prompt_tokens_details=SimpleNamespace(cached_tokens=0),
    )
    return SimpleNamespace(
        id=f"chatcmpl-{uuid.uuid4().hex[:12]}",
        object="chat.completion",
        created=int(time.time()),
        model=model,
        choices=[choice],
        usage=usage,
    )


def translate_gemini_response(resp: Dict[str, Any], model: str) -> SimpleNamespace:
    candidates = resp.get("candidates") or []
    if not isinstance(candidates, list) or not candidates:
        return _empty_response(model)

    cand = candidates[0] if isinstance(candidates[0], dict) else {}
    content_obj = cand.get("content") if isinstance(cand, dict) else {}
    parts = content_obj.get("parts") if isinstance(content_obj, dict) else []

    text_pieces: List[str] = []
    reasoning_pieces: List[str] = []
    tool_calls: List[SimpleNamespace] = []

    for index, part in enumerate(parts or []):
        if not isinstance(part, dict):
