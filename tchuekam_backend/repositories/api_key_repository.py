"""
Dépôt de données pour les Clés API hachées (SHA256).
"""

import json
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy.orm import Session
from tchuekam_backend.domain.models import ApiKey


class ApiKeyRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        org_id: str,
        user_id: str,
        name: str,
        key_hash: str,
        prefix: str,
        scopes: List[str],
        expires_at: Optional[datetime] = None,
    ) -> ApiKey:
        api_key = ApiKey(
            org_id=org_id,
            user_id=user_id,
            name=name,
            key_hash=key_hash,
            prefix=prefix,
            scopes_json=json.dumps(scopes),
            expires_at=expires_at,
        )
        self.db.add(api_key)
        self.db.commit()
        self.db.refresh(api_key)
        return api_key

    def get_by_key_hash(self, key_hash: str) -> Optional[ApiKey]:
        return self.db.query(ApiKey).filter(ApiKey.key_hash == key_hash).first()

    def list_by_org(self, org_id: str) -> List[ApiKey]:
        return self.db.query(ApiKey).filter(ApiKey.org_id == org_id).all()

    def list_by_user(self, user_id: str) -> List[ApiKey]:
        return self.db.query(ApiKey).filter(ApiKey.user_id == user_id).all()

    def revoke(self, key_id: str) -> bool:
        key = self.db.query(ApiKey).filter(ApiKey.id == key_id).first()
        if not key:
            return False
        self.db.delete(key)
        self.db.commit()
        return True

    def touch_last_used(self, key_id: str) -> None:
        key = self.db.query(ApiKey).filter(ApiKey.id == key_id).first()
        if key:
            key.last_used_at = datetime.now(timezone.utc)
            self.db.commit()
