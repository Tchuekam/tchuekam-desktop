"""
Couche d'accès aux données pour les fichiers téléversés.
"""

from typing import List, Optional
from sqlalchemy.orm import Session
from tchuekam_backend.domain.models import FileRecord


class FileRepository:
    """Gestion des opérations en base de données pour FileRecord."""

    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        filename: str,
        original_filename: str,
        mime_type: str,
        file_size_bytes: int,
        storage_path: str,
        uploaded_by_id: Optional[str] = None,
    ) -> FileRecord:
        record = FileRecord(
            filename=filename,
            original_filename=original_filename,
            mime_type=mime_type,
            file_size_bytes=file_size_bytes,
            storage_path=storage_path,
            uploaded_by_id=uploaded_by_id,
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def get_by_id(self, file_id: str) -> Optional[FileRecord]:
        return self.db.query(FileRecord).filter(FileRecord.id == file_id).first()

    def list_by_user(self, user_id: str, limit: int = 50, offset: int = 0) -> List[FileRecord]:
        return (
            self.db.query(FileRecord)
            .filter(FileRecord.uploaded_by_id == user_id)
            .order_by(FileRecord.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    def delete(self, file_id: str) -> bool:
        record = self.get_by_id(file_id)
        if record:
            self.db.delete(record)
            self.db.commit()
            return True
        return False
