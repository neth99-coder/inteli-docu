from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel


class PageAnnotation(BaseModel):
    id: str
    type: Literal["highlight", "note"]
    x: float
    y: float
    width: float
    height: float
    text: Optional[str] = None
    created_at: datetime


class DocumentListItem(BaseModel):
    id: UUID
    name: str
    created_at: datetime


class PageListItem(BaseModel):
    id: UUID
    page_number: int
    summary: Optional[str] = None
    created_at: datetime


class PageDetail(BaseModel):
    id: UUID
    document_id: UUID
    page_number: int
    content: str
    summary: Optional[str] = None
    annotations: list[PageAnnotation] = []
    document_file_url: Optional[str] = None
    created_at: datetime


class UploadResponse(BaseModel):
    document_id: UUID
    name: str
    page_count: int


class UpdatePageAnnotationsRequest(BaseModel):
    annotations: list[PageAnnotation]


class AskPageQuestionRequest(BaseModel):
    question: str


class AskPageQuestionResponse(BaseModel):
    answer: str
