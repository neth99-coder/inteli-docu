from __future__ import annotations

from pathlib import Path
import sys

from postgrest.exceptions import APIError
from storage3.exceptions import StorageApiError

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import get_settings
from app.db import get_supabase
from app.services.document_storage import (
    ensure_storage_bucket,
    normalize_user_id,
    resolve_document_storage_path,
    upload_document_bytes,
)


def is_missing_user_id_column(error: APIError) -> bool:
    return (
        isinstance(error, APIError)
        and getattr(error, "code", None) == "42703"
        and "user_id" in str(error)
    )


def get_documents() -> list[dict]:
    supabase = get_supabase()

    try:
        response = (
            supabase.table("documents")
            .select("id, name, user_id")
            .order("created_at", desc=False)
            .execute()
        )
        return response.data or []
    except APIError as exc:
        if not is_missing_user_id_column(exc):
            raise

    fallback = (
        supabase.table("documents")
        .select("id, name")
        .order("created_at", desc=False)
        .execute()
    )
    settings = get_settings()
    return [
        {
            **document,
            "user_id": settings.default_user_id,
        }
        for document in (fallback.data or [])
    ]


def migrate_document(document: dict) -> str:
    settings = get_settings()
    supabase = get_supabase()
    document_id = document["id"]
    user_id = normalize_user_id(document.get("user_id"))
    location = resolve_document_storage_path(document_id, user_id)

    if not location:
        return f"skip {document_id}: no source PDF found"

    if location["kind"] == "s3":
        return f"skip {document_id}: already in s3"

    try:
        file_bytes = supabase.storage.from_(settings.legacy_supabase_storage_bucket).download(location["path"])
    except StorageApiError as exc:
        return f"error {document_id}: failed to download legacy file ({exc})"

    upload_document_bytes(document_id=document_id, user_id=user_id, file_bytes=file_bytes)
    return f"migrated {document_id} -> {user_id}/files/{document_id}/original.pdf"


def main() -> None:
    ensure_storage_bucket()
    documents = get_documents()

    if not documents:
        print("No documents found.")
        return

    print(f"Found {len(documents)} documents.")
    for document in documents:
        print(migrate_document(document))


if __name__ == "__main__":
    main()
