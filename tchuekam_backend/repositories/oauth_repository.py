"""
Dépôt de données pour la gestion des comptes OAuth sociaux (Google, GitHub, Apple, Microsoft, Facebook).
"""

from typing import Optional
from sqlalchemy.orm import Session
from tchuekam_backend.domain.models import OAuthAccount


class OAuthRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_provider_user_id(self, provider: str, provider_user_id: str) -> Optional[OAuthAccount]:
        return (
            self.db.query(OAuthAccount)
            .filter(
                OAuthAccount.provider == provider.lower(),
                OAuthAccount.provider_user_id == str(provider_user_id),
            )
            .first()
        )

    def link_oauth_account(
        self,
        user_id: str,
        provider: str,
        provider_user_id: str,
        email: Optional[str] = None,
        access_token: Optional[str] = None,
    ) -> OAuthAccount:
        account = OAuthAccount(
            user_id=user_id,
            provider=provider.lower(),
            provider_user_id=str(provider_user_id),
            email=email,
            access_token=access_token,
        )
        self.db.add(account)
        self.db.commit()
        self.db.refresh(account)
        return account
