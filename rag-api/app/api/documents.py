from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.core.dependencies import get_current_user
from app.db.repositories import ChunkRepository, DocumentRepository
from app.schemas.common import CurrentUser
from app.schemas.documents import DocumentChunkResponse, DocumentResponse, UploadResponse
from app.services.document_service import DocumentService

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
def upload_document(
    upload_file: UploadFile = File(...),
    current_user: CurrentUser = Depends(get_current_user),
) -> UploadResponse:
    service = DocumentService()
    return UploadResponse.model_validate(service.upload_document(current_user=current_user, upload_file=upload_file))


@router.get("", response_model=list[DocumentResponse])
def list_documents(current_user: CurrentUser = Depends(get_current_user)) -> list[DocumentResponse]:
    repository = DocumentRepository()
    return [DocumentResponse.model_validate(item) for item in repository.list_documents(current_user.user_id)]


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(document_id: str, current_user: CurrentUser = Depends(get_current_user)) -> DocumentResponse:
    repository = DocumentRepository()
    document = repository.get_document(document_id, current_user.user_id)
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    return DocumentResponse.model_validate(document)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(document_id: str, current_user: CurrentUser = Depends(get_current_user)) -> None:
    service = DocumentService()
    service.delete_document(document_id=document_id, current_user=current_user)
    return None


@router.get("/{document_id}/chunks", response_model=list[DocumentChunkResponse])
def list_document_chunks(
    document_id: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> list[DocumentChunkResponse]:
    repository = ChunkRepository()
    return [
        DocumentChunkResponse.model_validate(item)
        for item in repository.list_chunks(document_id, current_user.user_id)
    ]
