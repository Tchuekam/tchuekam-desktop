"""
Endpoints REST pour l'Authentification OAuth2 (Google, GitHub, Apple, Microsoft, Facebook).
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from tchuekam_backend.core.database import get_db
from tchuekam_backend.domain.schemas import OAuthAuthorizeResponseSchema, OAuthCallbackSchema, TokenResponseSchema
from tchuekam_backend.services.oauth_service import OAuthService

router = APIRouter(prefix="/oauth", tags=["OAuth & Social Logins"])


@router.get("/{provider}/authorize", response_model=OAuthAuthorizeResponseSchema)
def oauth_authorize(provider: str, redirect_uri: str, state: str = "default_state", db: Session = Depends(get_db)):
    oauth_service = OAuthService(db)
    success, url = oauth_service.get_authorization_url(provider, redirect_uri=redirect_uri, state=state)
    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=url)
    return {"authorization_url": url, "state": state}


@router.post("/{provider}/callback", response_model=TokenResponseSchema)
def oauth_callback(provider: str, payload: OAuthCallbackSchema, request: Request, redirect_uri: str = "http://localhost:3000/oauth/callback", db: Session = Depends(get_db)):
    oauth_service = OAuthService(db)
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    success, msg, token_data = oauth_service.authenticate_via_oauth(
        provider_name=provider,
        code=payload.code,
        redirect_uri=redirect_uri,
        device_name=payload.device_name,
        device_type=payload.device_type,
        ip_address=client_ip,
        user_agent=user_agent,
    )
    if not success or not token_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    return token_data
