from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from postgrest.exceptions import APIError
from storage3.exceptions import StorageApiError

from app.config import get_settings
from app.db import get_supabase
from app.schemas import (
    AskPageQuestionRequest,
    AskPageQuestionResponse,
    DocumentListItem,
    PageDetail,
    PageListItem,
    UpdatePageAnnotationsRequest,
    UploadResponse,
)
from app.services.llm import (
    LlmRateLimitError,
    LlmServiceError,
    NO_ACCOUNTING_SUMMARY,
    answer_page_question,
    generate_page_summary,
    is_reference_page,
)
from app.services.pdf import extract_pages_from_pdf

settings = get_settings()

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def ensure_storage_bucket() -> None:
    supabase = get_supabase()

    try:
        supabase.storage.get_bucket(settings.supabase_storage_bucket)
    except StorageApiError as exc:
        if getattr(exc, "status", None) != 404:
            raise HTTPException(status_code=500, detail="Failed to access Supabase Storage.") from exc

        try:
            supabase.storage.create_bucket(
                settings.supabase_storage_bucket,
                options={"public": False},
            )
        except StorageApiError as create_exc:
            raise HTTPException(
                status_code=500,
                detail=(
                    "Supabase Storage bucket is missing and could not be created automatically. "
                    "Create the bucket named "
                    f"'{settings.supabase_storage_bucket}' and try again."
                ),
            ) from create_exc


def get_document_storage_path(document_id: str) -> str:
    return f"{document_id}/original.pdf"


def resolve_document_storage_path(document_id: str) -> str | None:
    supabase = get_supabase()
    preferred_path = get_document_storage_path(document_id)

    try:
        supabase.storage.from_(settings.supabase_storage_bucket).create_signed_url(
            preferred_path,
            60,
        )
        return preferred_path
    except StorageApiError:
        pass

    try:
        stored_files = supabase.storage.from_(settings.supabase_storage_bucket).list(document_id)
    except StorageApiError:
        return None

    for item in stored_files:
        file_name = item.get("name")
        if isinstance(file_name, str) and file_name.lower().endswith(".pdf"):
            return f"{document_id}/{file_name}"

    return None


def get_adjacent_page_context(document_id: str, page_number: int) -> tuple[str | None, str | None]:
    supabase = get_supabase()
    response = (
        supabase.table("pages")
        .select("page_number, content")
        .eq("document_id", document_id)
        .gte("page_number", max(page_number - 1, 1))
        .lte("page_number", page_number + 1)
        .order("page_number")
        .execute()
    )

    previous_page_text: str | None = None
    next_page_text: str | None = None

    for item in response.data or []:
        neighbor_number = item.get("page_number")
        if neighbor_number == page_number - 1:
            previous_page_text = item.get("content")
        elif neighbor_number == page_number + 1:
            next_page_text = item.get("content")

    return previous_page_text, next_page_text


def is_missing_annotations_column(error: APIError) -> bool:
    return (
        isinstance(error, APIError)
        and getattr(error, "code", None) == "42703"
        and "annotations" in str(error)
    )


def get_page_record(page_id: str) -> dict:
    supabase = get_supabase()

    try:
        response = (
            supabase.table("pages")
            .select("id, document_id, page_number, content, summary, annotations, created_at")
            .eq("id", page_id)
            .limit(1)
            .execute()
        )
        data = response.data or []
        if not data:
            raise HTTPException(status_code=404, detail="Page not found.")
        return data[0]
    except APIError as exc:
        if not is_missing_annotations_column(exc):
            raise

    fallback_response = (
        supabase.table("pages")
        .select("id, document_id, page_number, content, summary, created_at")
        .eq("id", page_id)
        .limit(1)
        .execute()
    )
    fallback_data = fallback_response.data or []
    if not fallback_data:
        raise HTTPException(status_code=404, detail="Page not found.")

    page = fallback_data[0]
    page["annotations"] = []
    return page


async def generate_and_store_page_summary(page_id: str) -> None:
    supabase = get_supabase()

    latest_page = get_page_record(page_id)
    if latest_page.get("summary"):
        return

    if is_reference_page(latest_page.get("content", "")):
        (
            supabase.table("pages")
            .update({"summary": NO_ACCOUNTING_SUMMARY})
            .eq("id", page_id)
            .execute()
        )
        return

    previous_page_text, _next_page_text = get_adjacent_page_context(
        latest_page["document_id"],
        latest_page["page_number"],
    )
    summary = await generate_page_summary(
        current_page_text=latest_page.get("content", ""),
        previous_page_text=previous_page_text,
    )
    (
        supabase.table("pages")
        .update({"summary": summary})
        .eq("id", page_id)
        .execute()
    )


async def regenerate_page_summary(page_id: str) -> dict:
    supabase = get_supabase()
    page = get_page_record(page_id)

    if is_reference_page(page.get("content", "")):
        summary = NO_ACCOUNTING_SUMMARY
    else:
        previous_page_text, _next_page_text = get_adjacent_page_context(
            page["document_id"],
            page["page_number"],
        )
        summary = await generate_page_summary(
            current_page_text=page.get("content", ""),
            previous_page_text=previous_page_text,
        )

    (
        supabase.table("pages")
        .update({"summary": summary})
        .eq("id", page_id)
        .execute()
    )

    updated_page = get_page_record(page_id)
    updated_page["summary"] = summary
    return updated_page


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/documents", response_model=list[DocumentListItem])
def list_documents() -> list[DocumentListItem]:
    supabase = get_supabase()
    response = (
        supabase.table("documents")
        .select("id, name, created_at")
        .order("created_at", desc=True)
        .execute()
    )
    return response.data or []


@app.post("/upload", response_model=UploadResponse)
async def upload_document(file: UploadFile = File(...)) -> UploadResponse:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF uploads are supported.")

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="The uploaded PDF is empty.")

    try:
        pages = extract_pages_from_pdf(file_bytes)
    except Exception as exc:  # pragma: no cover - parser failure path
        raise HTTPException(status_code=400, detail="Unable to parse PDF.") from exc

    if not pages:
        raise HTTPException(status_code=400, detail="No pages were extracted from the PDF.")

    ensure_storage_bucket()

    supabase = get_supabase()

    document_insert = (
        supabase.table("documents")
        .insert({"name": file.filename})
        .execute()
    )
    document = document_insert.data[0]
    document_id = document["id"]

    extension = Path(file.filename).suffix or ".pdf"
    if extension.lower() != ".pdf":
        extension = ".pdf"
    storage_path = get_document_storage_path(document_id)
    try:
        storage_result = supabase.storage.from_(settings.supabase_storage_bucket).upload(
            path=storage_path,
            file=file_bytes,
            file_options={"content-type": "application/pdf", "upsert": "false"},
        )
    except StorageApiError as exc:
        supabase.table("documents").delete().eq("id", document_id).execute()
        raise HTTPException(status_code=500, detail="Failed to store the uploaded PDF.") from exc

    if getattr(storage_result, "error", None):
        supabase.table("documents").delete().eq("id", document_id).execute()
        raise HTTPException(status_code=500, detail="Failed to store the uploaded PDF.")

    page_rows = [
        {
            "document_id": document_id,
            "page_number": index + 1,
            "content": content,
        }
        for index, content in enumerate(pages)
    ]

    try:
        supabase.table("pages").insert(page_rows).execute()
    except Exception as exc:
        try:
            supabase.storage.from_(settings.supabase_storage_bucket).remove([storage_path])
        except Exception:
            pass
        supabase.table("documents").delete().eq("id", document_id).execute()
        raise HTTPException(status_code=500, detail="Failed to store extracted pages.") from exc

    return UploadResponse(
        document_id=document_id,
        name=file.filename,
        page_count=len(page_rows),
    )


@app.get("/document/{document_id}/pages", response_model=list[PageListItem])
def list_document_pages(document_id: str) -> list[PageListItem]:
    supabase = get_supabase()

    document_response = (
        supabase.table("documents")
        .select("id")
        .eq("id", document_id)
        .limit(1)
        .execute()
    )
    if not document_response.data:
        raise HTTPException(status_code=404, detail="Document not found.")

    response = (
        supabase.table("pages")
        .select("id, page_number, summary, created_at")
        .eq("document_id", document_id)
        .order("page_number")
        .execute()
    )
    return response.data or []


@app.get("/document/{document_id}/file-url")
def get_document_file_url(document_id: str) -> dict[str, str]:
    supabase = get_supabase()

    document_response = (
        supabase.table("documents")
        .select("id")
        .eq("id", document_id)
        .limit(1)
        .execute()
    )
    if not document_response.data:
        raise HTTPException(status_code=404, detail="Document not found.")

    storage_path = resolve_document_storage_path(document_id)
    if not storage_path:
        raise HTTPException(status_code=404, detail="Stored PDF file not found for this document.")

    try:
        signed = supabase.storage.from_(settings.supabase_storage_bucket).create_signed_url(
            storage_path,
            60 * 60,
        )
    except StorageApiError as exc:
        raise HTTPException(status_code=500, detail="Failed to create a file preview URL.") from exc

    signed_url = signed.get("signedURL")
    if not signed_url:
        raise HTTPException(status_code=500, detail="Failed to create a file preview URL.")

    return {"url": signed_url}


@app.delete("/document/{document_id}")
def delete_document(document_id: str) -> dict[str, str]:
    supabase = get_supabase()
    document_response = (
        supabase.table("documents")
        .select("id")
        .eq("id", document_id)
        .limit(1)
        .execute()
    )
    if not document_response.data:
        raise HTTPException(status_code=404, detail="Document not found.")

    storage_paths: list[str] = []

    try:
        stored_files = supabase.storage.from_(settings.supabase_storage_bucket).list(document_id)
        for item in stored_files:
            file_name = item.get("name")
            if isinstance(file_name, str) and file_name:
                storage_paths.append(f"{document_id}/{file_name}")
    except StorageApiError:
        storage_paths = []

    if storage_paths:
        try:
            supabase.storage.from_(settings.supabase_storage_bucket).remove(storage_paths)
        except StorageApiError as exc:
            raise HTTPException(status_code=500, detail="Failed to delete the stored PDF.") from exc

    try:
        supabase.table("documents").delete().eq("id", document_id).execute()
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Failed to delete the document record.") from exc

    return {"status": "deleted"}


@app.get("/page/{page_id}", response_model=PageDetail)
async def get_page(page_id: str, background_tasks: BackgroundTasks) -> PageDetail:
    supabase = get_supabase()
    page = get_page_record(page_id)

    if is_reference_page(page.get("content", "")):
        if page.get("summary") != NO_ACCOUNTING_SUMMARY:
            (
                supabase.table("pages")
                .update({"summary": NO_ACCOUNTING_SUMMARY})
                .eq("id", page_id)
                .execute()
            )
            page["summary"] = NO_ACCOUNTING_SUMMARY
        else:
            page["summary"] = NO_ACCOUNTING_SUMMARY
    elif not page.get("summary"):
        background_tasks.add_task(generate_and_store_page_summary, page_id)

    storage_path = resolve_document_storage_path(page["document_id"])
    if not storage_path:
        page["document_file_url"] = None
        return page

    try:
        signed = supabase.storage.from_(settings.supabase_storage_bucket).create_signed_url(
            storage_path,
            60 * 60,
        )
        page["document_file_url"] = signed.get("signedURL")
    except StorageApiError:
        page["document_file_url"] = None

    return page


@app.put("/page/{page_id}/annotations", response_model=PageDetail)
def update_page_annotations(page_id: str, payload: UpdatePageAnnotationsRequest) -> PageDetail:
    supabase = get_supabase()
    try:
        response = (
            supabase.table("pages")
            .update({"annotations": [item.model_dump(mode="json") for item in payload.annotations]})
            .eq("id", page_id)
            .execute()
        )
    except APIError as exc:
        if is_missing_annotations_column(exc):
            raise HTTPException(
                status_code=503,
                detail=(
                    "Annotations are not enabled in the database yet. "
                    "Run the Supabase schema update to add the 'annotations' column to 'pages'."
                ),
            ) from exc
        raise

    if not response.data:
        raise HTTPException(status_code=404, detail="Page not found.")

    page = get_page_record(page_id)

    storage_path = resolve_document_storage_path(page["document_id"])
    if not storage_path:
        page["document_file_url"] = None
        return page

    try:
        signed = supabase.storage.from_(settings.supabase_storage_bucket).create_signed_url(
            storage_path,
            60 * 60,
        )
        page["document_file_url"] = signed.get("signedURL")
    except StorageApiError:
        page["document_file_url"] = None

    return page


@app.post("/page/{page_id}/regenerate-summary", response_model=PageDetail)
async def regenerate_summary_for_page(page_id: str) -> PageDetail:
    page = await regenerate_page_summary(page_id)

    storage_path = resolve_document_storage_path(page["document_id"])
    if not storage_path:
        page["document_file_url"] = None
        return page

    try:
        signed = get_supabase().storage.from_(settings.supabase_storage_bucket).create_signed_url(
            storage_path,
            60 * 60,
        )
        page["document_file_url"] = signed.get("signedURL")
    except StorageApiError:
        page["document_file_url"] = None

    return page


@app.post("/page/{page_id}/ask", response_model=AskPageQuestionResponse)
async def ask_question_for_page(page_id: str, payload: AskPageQuestionRequest) -> AskPageQuestionResponse:
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Enter a question for this page.")

    page = get_page_record(page_id)
    previous_page_text, next_page_text = get_adjacent_page_context(
        page["document_id"],
        page["page_number"],
    )
    try:
        answer = await answer_page_question(
            question=question,
            current_page_text=page.get("content", ""),
            previous_page_text=previous_page_text,
            next_page_text=next_page_text,
        )
    except LlmRateLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except LlmServiceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return AskPageQuestionResponse(answer=answer)
