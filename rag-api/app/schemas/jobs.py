from datetime import datetime

from pydantic import BaseModel


class JobResponse(BaseModel):
    id: str
    document_id: str
    user_id: str
    status: str
    current_step: str | None = None
    progress: int = 0
    total_pages: int = 0
    processed_pages: int = 0
    total_chunks: int = 0
    embedded_chunks: int = 0
    error_message: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

