from uuid import uuid4

from fastapi import HTTPException, UploadFile, status

from app.config import get_settings
from app.core.queue import enqueue_job
from app.db.repositories import DocumentRepository, JobRepository
from app.schemas.common import CurrentUser
from app.services.storage_service import StorageService


class DocumentService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.document_repository = DocumentRepository()
        self.job_repository = JobRepository()
        self.storage_service = StorageService()

    def upload_document(self, *, current_user: CurrentUser, upload_file: UploadFile) -> dict:
        if not upload_file.filename:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing file name.")

        content_type = upload_file.content_type or "application/octet-stream"
        document_id = str(uuid4())
        storage_path = self.storage_service.upload_document(document_id=document_id, upload_file=upload_file)

        document = self.document_repository.create_document(
            {
                "id": document_id,
                "user_id": current_user.user_id,
                "file_name": upload_file.filename,
                "file_type": content_type,
                "storage_path": storage_path,
                "status": "uploaded",
            }
        )

        job = self.job_repository.create_job(
            {
                "document_id": document_id,
                "user_id": current_user.user_id,
                "status": "queued",
                "current_step": "queued",
                "progress": 0,
            }
        )

        enqueue_job(
            {
                "job_id": job["id"],
                "document_id": document_id,
                "user_id": current_user.user_id,
                "storage_path": storage_path,
                "file_type": content_type,
                "file_name": upload_file.filename,
            }
        )

        return {
            "document_id": document["id"],
            "job_id": job["id"],
            "status": job["status"],
        }

    def delete_document(self, *, document_id: str, current_user: CurrentUser) -> None:
        document = self.document_repository.get_document(document_id, current_user.user_id)
        if not document:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

        self.storage_service.delete_document(document["storage_path"])
        self.document_repository.delete_document(document_id, current_user.user_id)
