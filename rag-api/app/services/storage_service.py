from fastapi import UploadFile

from app.config import get_settings
from app.db.supabase_client import get_supabase_admin_client


class StorageService:
    def __init__(self) -> None:
        self.client = get_supabase_admin_client()
        self.settings = get_settings()

    def upload_document(self, *, document_id: str, upload_file: UploadFile) -> str:
        storage_path = f"{document_id}/{upload_file.filename}"
        file_bytes = upload_file.file.read()
        self.client.storage.from_(self.settings.supabase_storage_bucket).upload(
            storage_path,
            file_bytes,
            {"content-type": upload_file.content_type or "application/octet-stream"},
        )
        return storage_path

    def delete_document(self, storage_path: str) -> None:
        self.client.storage.from_(self.settings.supabase_storage_bucket).remove([storage_path])

