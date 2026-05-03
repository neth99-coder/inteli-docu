from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class DocumentResponse(BaseModel):
    id: str
    user_id: str
    file_name: str
    file_type: str
    storage_path: str
    status: str
    page_count: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class DocumentChunkResponse(BaseModel):
    id: str
    document_id: str
    user_id: str
    chunk_index: int
    content: str
    page_number: int | None = None
    section_title: str | None = None
    has_image: bool = False
    has_table: bool = False
    image_summary: str | None = None
    table_summary: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class UploadResponse(BaseModel):
    document_id: str
    job_id: str
    status: str
