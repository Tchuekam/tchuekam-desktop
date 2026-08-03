"""
Service métier de gestion sécurisée du téléversement de fichiers.
"""

import os
import re
import uuid
from typing import Optional, Tuple
from fastapi import UploadFile
from sqlalchemy.orm import Session

from tchuekam_backend.core.config import settings
from tchuekam_backend.core.exceptions import FileUploadError, NotFoundError
from tchuekam_backend.domain.models import FileRecord
from tchuekam_backend.repositories.file_repository import FileRepository


class FileService:
    """Service d'upload, de validation et de suppression sécurisée des fichiers."""

    def __init__(self, db: Session):
        self.db = db
        self.repo = FileRepository(db)
        self.upload_dir = os.path.abspath(settings.UPLOAD_DIR)

        if not os.path.exists(self.upload_dir):
            os.makedirs(self.upload_dir, exist_ok=True)

    def _sanitize_filename(self, filename: str) -> str:
        """Sanitizes an incoming filename to avoid path traversal and injection attacks."""
        # Strip path info
        filename = os.path.basename(filename)
        # Remove null bytes or non-printable chars
        filename = re.sub(r'[\x00-\x1f\x7f]', '', filename)
        # Replace spaces and special characters
        filename = re.sub(r'[^\w\.-]', '_', filename)
        return filename or "unnamed_file"

    def validate_file(self, file: UploadFile, content: bytes) -> None:
        """Validates uploaded file size, extensions, and content safety."""
        # 1. Size Validation
        if len(content) > settings.MAX_UPLOAD_SIZE_BYTES:
            max_mb = settings.MAX_UPLOAD_SIZE_BYTES / (1024 * 1024)
            raise FileUploadError(
                f"La taille du fichier dépasse la limite autorisée de {max_mb:.1f} MB."
            )

        if len(content) == 0:
            raise FileUploadError("Le fichier téléversé est vide.")

        original_name = file.filename or "file"
        sanitized_name = self._sanitize_filename(original_name)
        ext = os.path.splitext(sanitized_name)[1].lower()

        # 2. Extension Blacklist
        if ext in settings.DISALLOWED_EXTENSIONS:
            raise FileUploadError(
                f"L'extension '{ext}' n'est pas autorisée pour des raisons de sécurité."
            )

        # 3. MIME Type Validation
        content_type = file.content_type or "application/octet-stream"
        if settings.ALLOWED_MIME_TYPES and content_type not in settings.ALLOWED_MIME_TYPES:
            raise FileUploadError(
                f"Le type de contenu '{content_type}' n'est pas autorisé."
            )

    async def upload_file(self, file: UploadFile, uploaded_by_id: Optional[str] = None) -> FileRecord:
        """Processes, validates, stores, and records an uploaded file."""
        content = await file.read()
        self.validate_file(file, content)

        original_filename = self._sanitize_filename(file.filename or "file")
        ext = os.path.splitext(original_filename)[1].lower()
        unique_filename = f"{uuid.uuid4().hex}{ext}"
        storage_path = os.path.join(self.upload_dir, unique_filename)

        # Write safely to disk
        with open(storage_path, "wb") as f:
            f.write(content)

        file_record = self.repo.create(
            filename=unique_filename,
            original_filename=original_filename,
            mime_type=file.content_type or "application/octet-stream",
            file_size_bytes=len(content),
            storage_path=storage_path,
            uploaded_by_id=uploaded_by_id,
        )

        return file_record

    def get_file(self, file_id: str) -> FileRecord:
        record = self.repo.get_by_id(file_id)
        if not record:
            raise NotFoundError("Fichier introuvable.")
        return record

    def delete_file(self, file_id: str) -> bool:
        record = self.get_file(file_id)
        if os.path.exists(record.storage_path):
            try:
                os.remove(record.storage_path)
            except OSError:
                pass
        return self.repo.delete(file_id)
