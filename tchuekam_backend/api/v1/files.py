"""
REST API Endpoints pour le téléversement et la gestion des fichiers.
"""

import os
from typing import Dict, Any
from fastapi import APIRouter, Depends, File, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from tchuekam_backend.api.dependencies import get_current_user
from tchuekam_backend.core.database import get_db
from tchuekam_backend.domain.models import User
from tchuekam_backend.domain.schemas import APIResponse, FileRecordResponseSchema
from tchuekam_backend.services.file_service import FileService

router = APIRouter(prefix="/files", tags=["File Management"])


@router.post("/upload", response_model=APIResponse[FileRecordResponseSchema], status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Téléverse un fichier de manière sécurisée avec validation du type, de la taille et suppression du code malveillant."""
    file_service = FileService(db)
    record = await file_service.upload_file(file, uploaded_by_id=current_user.id)
    return APIResponse(
        message="Fichier téléversé avec succès.",
        data=FileRecordResponseSchema.model_validate(record),
    )


@router.get("/{file_id}", response_model=APIResponse[FileRecordResponseSchema])
def get_file_metadata(
    file_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Récupère les métadonnées d'un fichier."""
    file_service = FileService(db)
    record = file_service.get_file(file_id)
    return APIResponse(
        message="Métadonnées du fichier récupérées.",
        data=FileRecordResponseSchema.model_validate(record),
    )


@router.get("/{file_id}/download")
def download_file(
    file_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Télécharge le fichier de manière sécurisée."""
    file_service = FileService(db)
    record = file_service.get_file(file_id)
    return FileResponse(
        path=record.storage_path,
        media_type=record.mime_type,
        filename=record.original_filename,
    )


@router.delete("/{file_id}", response_model=APIResponse[Dict[str, Any]])
def delete_file(
    file_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Supprime un fichier enregistré."""
    file_service = FileService(db)
    file_service.delete_file(file_id)
    return APIResponse(
        message="Fichier supprimé avec succès.",
        data={"file_id": file_id},
    )
