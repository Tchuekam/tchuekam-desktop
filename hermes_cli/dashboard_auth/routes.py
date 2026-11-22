"""HTTP routes for the dashboard-auth OAuth round trip.

Mounted at root (no prefix) by ``web_server.py``. The router does not
auto-gate; gating is performed by ``gated_auth_middleware``, which
allowlists everything under ``/auth/*`` and ``/api/auth/providers``.

The routes:

  GET  /login              → server-rendered login page
  GET  /auth/login?provider=N → 302 to IDP, sets PKCE cookie
  GET  /auth/callback?code,state → completes login, sets session cookies
  POST /auth/logout        → clears cookies, best-effort revoke
  GET  /api/auth/providers → list registered providers (login bootstrap)
  GET  /api/auth/me        → current Session as JSON (auth-required)
"""
from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from hermes_cli.dashboard_auth import (
    get_provider,
    list_providers,
)
from hermes_cli.dashboard_auth.audit import AuditEvent, audit_log
from hermes_cli.dashboard_auth.base import (
    InvalidCodeError,
    ProviderError,
)
from hermes_cli.dashboard_auth.cookies import (
    clear_pkce_cookie,
    clear_session_cookies,
    detect_https,
    read_pkce_cookie,
    read_session_cookies,
    set_pkce_cookie,
    set_session_cookies,
)
from hermes_cli.dashboard_auth.login_page import render_login_html

_log = logging.getLogger(__name__)

router = APIRouter()


def _redirect_uri(request: Request) -> str:
    """Reconstruct the absolute callback URL the IDP redirects back to.

    Three resolution tiers:

      1. ``HERMES_DASHBOARD_PUBLIC_URL`` env var or
         ``dashboard.public_url`` in config.yaml — when set, this is
         the complete authority (scheme + host + optional path prefix)
         and we append ``/auth/callback`` verbatim. ``X-Forwarded-Prefix``
         is IGNORED on this code path because the operator has declared
         the public URL — we no longer need to guess from proxy headers,
         and stacking the prefix on top would double-prefix the common
         case where the prefix is already baked into ``public_url``.
         Relief valve for deploys behind reverse proxies whose forwarded
         headers aren't reliable.

      2. ``X-Forwarded-Prefix: /hermes`` (Mission Control deploys) — we
         prepend the prefix to the path FastAPI's ``url_for`` produces
         (it doesn't natively honour this header — it isn't part of the
         Starlette/uvicorn proxy_headers set).

      3. Bare ``request.url_for("auth_callback")`` — under uvicorn's
         ``proxy_headers=True`` this picks up the public https URL from
         ``X-Forwarded-Host`` plus ``X-Forwarded-Proto``. Fly.io's
         default path.
    """
    from urllib.parse import urlparse, urlunparse

    from hermes_cli.dashboard_auth.prefix import (
        prefix_from_request,
        resolve_public_url,
    )

    # Tier 1: operator-declared public URL.
    public_url = resolve_public_url()
    if public_url:
        # ``public_url`` is the complete authority (possibly with a
        # path prefix already baked in). Append the auth callback path
        # verbatim. ``resolve_public_url`` already stripped any trailing
        # slash so we don't produce ``//auth/callback`` double-slashes.
        return f"{public_url}/auth/callback"

    # Tier 2 + 3: reconstruct from the request URL, optionally with
    # X-Forwarded-Prefix layered on top of the path.
    base = str(request.url_for("auth_callback"))
    prefix = prefix_from_request(request)
    if not prefix:
        return base
    parsed = urlparse(base)
    return urlunparse(parsed._replace(path=f"{prefix}{parsed.path}"))


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else ""


def _prefix(request: Request) -> str:
    """Resolve the X-Forwarded-Prefix header for the active request.

    Local indirection so the routes pass a consistent value to the
    cookie helpers (cookie name + Path attribute) and the gate's
    redirect builders (login_url construction). See
    ``hermes_cli.dashboard_auth.prefix`` for the normalisation rules.
    """
    from hermes_cli.dashboard_auth.prefix import prefix_from_request
    return prefix_from_request(request)


# ---------------------------------------------------------------------------
# Public: login page (server-rendered HTML, no SPA bundle)
# ---------------------------------------------------------------------------


@router.get("/login", name="login_page")
async def login_page(request: Request) -> HTMLResponse:
    # Read the ``next=`` query the gate's ``_unauth_response`` set on
    # the redirect URL. Validate against the same same-origin rules the
    # callback applies (defence in depth — the gate already filters,
    # but /login is reachable directly too).
    next_path = _validate_post_login_target(
        request.query_params.get("next", "")
    )
    return HTMLResponse(
        render_login_html(next_path=next_path),
        headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
    )


# ---------------------------------------------------------------------------
# Public: provider list for the login-page bootstrap
# ---------------------------------------------------------------------------


@router.get("/api/auth/providers", name="auth_providers")
async def api_auth_providers() -> Any:
    providers = list_providers()
    if not providers:
        # Q13: fail-closed when zero providers are registered.
        return JSONResponse(
            {"detail": "no auth providers registered"},
            status_code=503,
        )
    return {
        "providers": [
            {"name": p.name, "display_name": p.display_name}
            for p in providers
        ],
    }


# ---------------------------------------------------------------------------
# Public: OAuth round trip
# ---------------------------------------------------------------------------


@router.get("/auth/login", name="auth_login")
async def auth_login(request: Request, provider: str, next: str = ""):
    p = get_provider(provider)
    if p is None:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown provider: {provider!r}",
        )

    try:
        ls = p.start_login(redirect_uri=_redirect_uri(request))
    except ProviderError as e:
        audit_log(
            AuditEvent.LOGIN_FAILURE,
            provider=provider,
            reason="provider_unreachable",
            ip=_client_ip(request),
        )
        raise HTTPException(
            status_code=503,
            detail=f"Provider unreachable: {e}",
        )

    audit_log(
        AuditEvent.LOGIN_START,
        provider=provider,
        ip=_client_ip(request),
    )

    resp = RedirectResponse(url=ls.redirect_url, status_code=302)
    # Pack the provider name into the PKCE cookie so the callback can
    # find it without a separate cookie. Provider may or may not have
    # already included a ``provider=`` segment.
    pkce = ls.cookie_payload.get("hermes_session_pkce", "")
    if "provider=" not in pkce:
        pkce = f"provider={provider};{pkce}" if pkce else f"provider={provider}"
    # Carry ``next=`` through the round trip in the PKCE cookie. Real
    # IDPs only echo back ``code`` + ``state`` on the callback URL, so
    # query-string transport would lose the value — the cookie is the
    # only server-controlled channel that survives. Validate before we
    # store it so an attacker who reaches /auth/login directly with
    # ``next=//evil.example`` can't poison the cookie.
    safe_next = _validate_post_login_target(next)
    if safe_next:
        from urllib.parse import quote
        pkce = f"{pkce};next={quote(safe_next, safe='')}"
    set_pkce_cookie(
        resp, payload=pkce, use_https=detect_https(request),
        prefix=_prefix(request),
    )
    return resp


@router.get("/auth/callback", name="auth_callback")
async def auth_callback(
    request: Request,
    code: str = "",
    state: str = "",
    error: str = "",
    error_description: str = "",
):
    pkce_raw = read_pkce_cookie(request)
    if not pkce_raw:
        audit_log(
            AuditEvent.LOGIN_FAILURE,
            reason="missing_pkce_cookie",
            ip=_client_ip(request),
        )
        raise HTTPException(
            status_code=400,
            detail="Missing PKCE state cookie",
        )

    # Parse ``provider=...;state=...;verifier=...;next=...`` — the
    # ``next`` segment is optional (only present when /auth/login was
    # given a next= query). All keys live in the same flat namespace;
    # ``next`` carries a URL-encoded path so it never contains ``;``.
    parts = dict(
