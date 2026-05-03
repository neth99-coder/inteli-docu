from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from app.config import get_settings
from app.core.queue import dequeue_job
from app.db.repositories import ChunkRepository, DocumentRepository, JobRepository
from app.db.supabase_client import get_supabase_admin_client
from app.services.chunking_service import ChunkingService
from app.services.embedding_service import EmbeddingService
from app.services.extraction_service import ExtractionService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def update_job(job_id: str, **payload: object) -> None:
    JobRepository().update_job(job_id, payload)


def process_job(payload: dict) -> None:
    settings = get_settings()
    job_id = payload["job_id"]
    document_id = payload["document_id"]
    user_id = payload["user_id"]
    storage_path = payload["storage_path"]
    file_name = payload["file_name"]
    file_type = payload["file_type"]

    document_repository = DocumentRepository()
    chunk_repository = ChunkRepository()
    extraction_service = ExtractionService()
    chunking_service = ChunkingService()
    embedding_service = EmbeddingService()
    supabase = get_supabase_admin_client()

    update_job(job_id, status="extracting", current_step="extracting", progress=10)
    document_repository.update_document_status(document_id, "processing")

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir) / file_name
        file_bytes = supabase.storage.from_(settings.supabase_storage_bucket).download(storage_path)
        temp_path.write_bytes(file_bytes)

        elements = extraction_service.extract(temp_path, file_type)
        update_job(
            job_id,
            current_step="chunking",
            status="chunking",
            progress=40,
            total_pages=len({element.get("page_number") for element in elements}),
            processed_pages=len({element.get("page_number") for element in elements}),
        )

        chunks = chunking_service.chunk_elements(elements)
        embeddings = embedding_service.embed_chunks(chunk["content"] for chunk in chunks)
        update_job(
            job_id,
            current_step="embedding",
            status="embedding",
            progress=70,
            total_chunks=len(chunks),
            embedded_chunks=len(chunks),
        )

        rows = []
        for chunk, embedding in zip(chunks, embeddings, strict=False):
            rows.append(
                {
                    "document_id": document_id,
                    "user_id": user_id,
                    "chunk_index": chunk["chunk_index"],
                    "content": chunk["content"],
                    "page_number": chunk["page_number"],
                    "section_title": chunk["section_title"],
                    "has_image": chunk["has_image"],
                    "has_table": chunk["has_table"],
                    "image_summary": chunk["image_summary"],
                    "table_summary": chunk["table_summary"],
                    "metadata": chunk["metadata"],
                    "embedding": embedding,
                }
            )

        update_job(job_id, current_step="storing", status="storing", progress=90)
        chunk_repository.insert_chunks(rows)

    page_numbers = {chunk["page_number"] for chunk in chunks if chunk.get("page_number") is not None}
    document_repository.update_document_status(document_id, "completed", page_count=len(page_numbers))
    update_job(job_id, current_step="completed", status="completed", progress=100)


def main() -> None:
    logger.info("document worker started")
    while True:
        payload = dequeue_job(timeout_seconds=5)
        if not payload:
            continue

        try:
            process_job(payload)
        except Exception as exc:
            logger.exception("document processing failed")
            update_job(
                payload["job_id"],
                status="failed",
                current_step="failed",
                error_message=str(exc),
            )
            DocumentRepository().update_document_status(payload["document_id"], "failed")


if __name__ == "__main__":
    main()
