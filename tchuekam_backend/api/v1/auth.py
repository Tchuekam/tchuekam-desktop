"""
Endpoints REST pour l'Authentification et la Gestion des Jetons.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from tchuekam_backend.core.config import settings
from tchuekam_backend.core.database import get_db
from tchuekam_backend.domain.schemas import (
    ForgotPasswordSchema,
    RefreshTokenRequestSchema,
    ResetPasswordSchema,
    SignInSchema,
    SignUpSchema,
    TokenResponseSchema,
)
from tchuekam_backend.services.auth_service import AuthService
from tchuekam_backend.services.user_service import UserService
from tchuekam_backend.services.security_service import SecurityService
from tchuekam_backend.api.dependencies import get_current_user_with_token

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/signup", status_code=status.HTTP_201_CREATED)
def signup(payload: SignUpSchema, request: Request, db: Session = Depends(get_db)):
    auth_service = AuthService(db)
    user_service = UserService(db)
    client_ip = request.client.host if request.client else None

    success, msg, data = auth_service.sign_up(
        email=payload.email,
        password=payload.password,
        full_name=payload.full_name,
        ip_address=client_ip,
    )
    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)

    # Génération du jeton de vérification d'email
    verify_token = user_service.create_email_verification_token(data["user_id"])
    response = {
        "message": msg,
        "user_id": data["user_id"],
        "email": data["email"],
    }
    # Même raisonnement que pour /forgot-password : renvoyer le jeton de
    # vérification revient à se vérifier soi-même sans jamais prouver qu'on
    # contrôle l'adresse indiquée.
    if settings.EXPOSE_SENSITIVE_TOKENS:
        response["verification_token"] = verify_token
    return response


@router.post("/signin", response_model=TokenResponseSchema)
def signin(payload: SignInSchema, request: Request, db: Session = Depends(get_db)):
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    
    security_service = SecurityService(db)
    allowed, remaining = security_service.check_brute_force_login(client_ip or "127.0.0.1", payload.email)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Trop de tentatives de connexion échouées. Veuillez ré-essayer dans 5 minutes.",
        )

    auth_service = AuthService(db)
    success, msg, token_data = auth_service.sign_in(
        email=payload.email,
        password=payload.password,
        device_name=payload.device_name,
        device_type=payload.device_type,
        ip_address=client_ip,
        user_agent=user_agent,
    )

    if not success or not token_data:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=msg)

    security_service.reset_brute_force_counter(client_ip or "127.0.0.1", payload.email)
    return token_data


@router.post("/refresh", response_model=TokenResponseSchema)
def refresh_token(payload: RefreshTokenRequestSchema, request: Request, db: Session = Depends(get_db)):
    auth_service = AuthService(db)
    client_ip = request.client.host if request.client else None
    success, msg, token_data = auth_service.refresh_access_token(payload.refresh_token, ip_address=client_ip)
    if not success or not token_data:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=msg)
    return token_data


@router.post("/logout")
def logout(user_tuple=Depends(get_current_user_with_token), db: Session = Depends(get_db)):
    user, jti, session_id = user_tuple
    auth_service = AuthService(db)
    auth_service.logout_session(session_id=session_id, jti=jti, user_id=user.id)
    return {"message": "Déconnexion réussie."}


@router.post("/logout-all")
def logout_all_devices(user_tuple=Depends(get_current_user_with_token), db: Session = Depends(get_db)):
    user, jti, session_id = user_tuple
    auth_service = AuthService(db)
    count = auth_service.logout_all(user_id=user.id, jti=jti)
    return {"message": f"Déconnexion réussie de {count} appareil(s)."}


@router.get("/verify-email")
def verify_email(token: str, db: Session = Depends(get_db)):
    user_service = UserService(db)
    success, msg = user_service.verify_email_token(token)
    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    return {"message": msg}


@router.post("/forgot-password")
def forgot_password(payload: ForgotPasswordSchema, db: Session = Depends(get_db)):
    user_service = UserService(db)
    success, msg, raw_token = user_service.create_password_reset_token(payload.email)

    # Réponse volontairement identique que l'adresse existe ou non : le
    # contraire fournirait un oracle d'énumération des comptes.
    response = {
        "message": "Si un compte existe pour cette adresse, un e-mail de "
                   "réinitialisation vient d'être envoyé.",
    }
    # Le jeton n'est jamais renvoyé en production : il constitue à lui seul la
    # preuve de possession de la boîte e-mail. L'exposer permettait à un
    # anonyme connaissant l'adresse de s'emparer du compte en trois requêtes.
    if raw_token and settings.EXPOSE_SENSITIVE_TOKENS:
        response["reset_token"] = raw_token
    return response


@router.post("/reset-password")
def reset_password(payload: ResetPasswordSchema, db: Session = Depends(get_db)):
    user_service = UserService(db)
    success, msg = user_service.reset_password(payload.token, payload.new_password)
    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    return {"message": msg}
