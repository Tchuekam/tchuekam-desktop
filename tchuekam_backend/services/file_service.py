"""
Service métier de gestion sécurisée du téléversement de fichiers.
"""

import os
import re
import uuid
from typing import Optional
from fastapi import UploadFile
from sqlalchemy.orm import Session

from tchuekam_backend.core.config import settings
from tchuekam_backend.core.exceptions import FileUploadError, NotFoundError
from tchuekam_backend.domain.models import FileRecord
from tchuekam_backend.repositories.file_repository import FileRepository

_ALLOWED_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".gif",
    ".pdf",
    ".doc",
    ".docx",
    ".txt",
    ".csv",
}

_CHUNK_SIZE = 65_536


class FileService:
    """Service d'upload, de validation et de suppression sécurisée des fichiers."""

    def __init__(self, db: Session):
        self.db = db
        self.repo = FileRepository(db)
        self.upload_dir = os.path.abspath(settings.UPLOAD_DIR)

    def _sanitize_filename(self, filename: str) -> str:
        """Sanitizes an incoming filename to avoid path traversal and injection attacks."""
        filename = os.path.basename(filename)
        filename = re.sub(r'[\x00-\x1f\x7f]', '', filename)
        filename = re.sub(r'[^\w\.-]', '_', filename)
        return filename or "unnamed_file"

    def _validate_magic_bytes(self, ext: str, content_type: str, content: bytes) -> None:
        if ext in {".jpg", ".jpeg"} or content_type == "image/jpeg":
            if not content.startswith(b"\xff\xd8\xff"):
                raise FileUploadError("Contenu JPEG invalide (signature magique non conforme).")
        elif ext == ".png" or content_type == "image/png":
            if not content.startswith(b"\x89PNG\r\n\x1a\n"):
                raise FileUploadError("Contenu PNG invalide (signature magique non conforme).")
        elif ext == ".gif" or content_type == "image/gif":
            if not content.startswith((b"GIF87a", b"GIF89a")):
                raise FileUploadError("Contenu GIF invalide (signature magique non conforme).")
        elif ext == ".webp" or content_type == "image/webp":
            if not (len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP"):
                raise FileUploadError("Contenu WEBP invalide (signature magique non conforme).")
        elif ext == ".pdf" or content_type == "application/pdf":
            if not content.lstrip().startswith(b"%PDF-"):
                raise FileUploadError("Contenu PDF invalide (signature magique non conforme).")

    def validate_file(self, file: UploadFile, content: bytes) -> None:
        """Validates uploaded file size, extensions, magic bytes, and content safety."""
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

        if ext in settings.DISALLOWED_EXTENSIONS:
            raise FileUploadError(
                f"L'extension '{ext}' n'est pas autorisée pour des raisons de sécurité."
            )

        if ext not in _ALLOWED_EXTENSIONS:
            raise FileUploadError(
                f"L'extension '{ext}' n'est pas autorisée."
            )

        content_type = (file.content_type or "application/octet-stream").split(";")[0].strip().lower()
        if settings.ALLOWED_MIME_TYPES and content_type not in settings.ALLOWED_MIME_TYPES:
            raise FileUploadError(
                f"Le type de contenu '{content_type}' n'est pas autorisé."
            )

        self._validate_magic_bytes(ext, content_type, content)

    def ensure_safe_storage_path(self, record: FileRecord) -> str:
        """Verifies the stored file path remains strictly confined within upload_dir."""
        real_dir = os.path.realpath(self.upload_dir)
        real_path = os.path.realpath(record.storage_path)
        if not (real_path == real_dir or real_path.startswith(real_dir + os.sep)):
            raise NotFoundError("Fichier introuvable.")
        return real_path

    async def upload_file(self, file: UploadFile, uploaded_by_id: Optional[str] = None) -> FileRecord:
        """Processes, validates in bounded chunks, stores, and records an uploaded file."""
        chunks = []
        total_bytes = 0
        max_bytes = settings.MAX_UPLOAD_SIZE_BYTES

        while True:
            chunk = await file.read(_CHUNK_SIZE)
            if not chunk:
                break
            total_bytes += len(chunk)
            if total_bytes > max_bytes:
                max_mb = max_bytes / (1024 * 1024)
                raise FileUploadError(
                    f"La taille du fichier dépasse la limite autorisée de {max_mb:.1f} MB."
                )
            chunks.append(chunk)

        content = b"".join(chunks)
        self.validate_file(file, content)

        if not os.path.exists(self.upload_dir):
            os.makedirs(self.upload_dir, exist_ok=True)

        original_filename = self._sanitize_filename(file.filename or "file")
        ext = os.path.splitext(original_filename)[1].lower()
        unique_filename = f"{uuid.uuid4().hex}{ext}"
        storage_path = os.path.join(self.upload_dir, unique_filename)

        with open(storage_path, "wb") as f:
            f.write(content)

        file_record = self.repo.create(
            filename=unique_filename,
            original_filename=original_filename,
            mime_type=(file.content_type or "application/octet-stream").split(";")[0].strip(),
            file_size_bytes=len(content),
            storage_path=storage_path,
            uploaded_by_id=uploaded_by_id,
        )

        return file_record

    def get_file(self, file_id: str, requester_id: str) -> FileRecord:
        """Charge un fichier en appliquant le contrôle de propriété."""
        if not requester_id:
            raise NotFoundError("Fichier introuvable.")
        record = self.repo.get_by_id(file_id)
        if not record:
            raise NotFoundError("Fichier introuvable.")
        if record.uploaded_by_id is None or record.uploaded_by_id != requester_id:
            raise NotFoundError("Fichier introuvable.")
        return record

    def delete_file(self, file_id: str, requester_id: str) -> bool:
        record = self.get_file(file_id, requester_id=requester_id)
        safe_path = self.ensure_safe_storage_path(record)
        if os.path.exists(safe_path):
            try:
                os.remove(safe_path)
            except OSError:
                pass
        return self.repo.delete(file_id)
