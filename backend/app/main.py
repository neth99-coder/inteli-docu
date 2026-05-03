from fastapi import BackgroundTasks, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from postgrest.exceptions import APIError

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
from app.services.auth import get_authenticated_user
from app.services.document_storage import (
    create_document_download_url,
    delete_document_file,
    ensure_storage_bucket,
    normalize_user_id,
    upload_document_bytes,
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


def is_missing_user_id_column(error: APIError) -> bool:
    return (
        isinstance(error, APIError)
        and getattr(error, "code", None) == "42703"
        and "user_id" in str(error)
    )


def get_document_record(document_id: str, user_id: str | None = None) -> dict:
    supabase = get_supabase()
    normalized_user_id = normalize_user_id(user_id)

    try:
        query = (
            supabase.table("documents")
            .select("id, name, created_at, user_id")
            .eq("id", document_id)
        )
        if normalized_user_id:
            query = query.eq("user_id", normalized_user_id)
        response = query.limit(1).execute()
        data = response.data or []
        if data:
            return data[0]
        raise HTTPException(status_code=404, detail="Document not found.")
    except APIError as exc:
        if not is_missing_user_id_column(exc):
            raise

    fallback_response = (
        supabase.table("documents")
        .select("id, name, created_at")
        .eq("id", document_id)
        .limit(1)
        .execute()
    )
    fallback_data = fallback_response.data or []
    if not fallback_data:
        raise HTTPException(status_code=404, detail="Document not found.")

    document = fallback_data[0]
    document["user_id"] = settings.default_user_id
    if normalized_user_id != document["user_id"]:
        raise HTTPException(status_code=404, detail="Document not found.")
    return document


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


def get_page_record_for_user(page_id: str, user_id: str | None) -> tuple[dict, str]:
    page = get_page_record(page_id)
    document = get_document_record(page["document_id"], user_id)
    return page, normalize_user_id(document.get("user_id"))


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
def list_documents(
    authorization: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
) -> list[DocumentListItem]:
    supabase = get_supabase()
    user_id = get_authenticated_user(authorization, x_user_id).app_user_id

    try:
        response = (
            supabase.table("documents")
            .select("id, name, created_at, user_id")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .execute()
        )
        return response.data or []
    except APIError as exc:
        if not is_missing_user_id_column(exc):
            raise

    if user_id != settings.default_user_id:
        return []

    fallback_response = (
        supabase.table("documents")
        .select("id, name, created_at")
        .order("created_at", desc=True)
        .execute()
    )
    return fallback_response.data or []


@app.post("/upload", response_model=UploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    authorization: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
) -> UploadResponse:
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

    try:
        ensure_storage_bucket()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    supabase = get_supabase()
    user_id = get_authenticated_user(authorization, x_user_id).app_user_id

    try:
        document_insert = (
            supabase.table("documents")
            .insert({"name": file.filename, "user_id": user_id})
            .execute()
        )
        document = document_insert.data[0]
    except APIError as exc:
        if not is_missing_user_id_column(exc):
            raise
        document_insert = (
            supabase.table("documents")
            .insert({"name": file.filename})
            .execute()
        )
        document = document_insert.data[0]
        document["user_id"] = user_id

    document_id = document["id"]

    try:
        upload_document_bytes(document_id=document_id, user_id=user_id, file_bytes=file_bytes)
    except Exception as exc:
        supabase.table("documents").delete().eq("id", document_id).execute()
        raise HTTPException(status_code=500, detail="Failed to store the uploaded PDF.") from exc

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
            delete_document_file(document_id=document_id, user_id=user_id)
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
def list_document_pages(
    document_id: str,
    authorization: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
) -> list[PageListItem]:
    supabase = get_supabase()
    user_id = get_authenticated_user(authorization, x_user_id).app_user_id
    get_document_record(document_id, user_id)

    response = (
        supabase.table("pages")
        .select("id, page_number, summary, created_at")
        .eq("document_id", document_id)
        .order("page_number")
        .execute()
    )
    return response.data or []


@app.get("/document/{document_id}/file-url")
def get_document_file_url(
    document_id: str,
    authorization: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
) -> dict[str, str]:
    user_id = get_authenticated_user(authorization, x_user_id).app_user_id
    document = get_document_record(document_id, user_id)
    signed_url = create_document_download_url(
        document_id=document_id,
        user_id=document.get("user_id"),
        expires_in=60 * 60,
    )
    if not signed_url:
        raise HTTPException(status_code=404, detail="Stored PDF file not found for this document.")

    return {"url": signed_url}


@app.delete("/document/{document_id}")
def delete_document(
    document_id: str,
    authorization: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
) -> dict[str, str]:
    supabase = get_supabase()
    user_id = get_authenticated_user(authorization, x_user_id).app_user_id
    document = get_document_record(document_id, user_id)

    try:
        delete_document_file(document_id=document_id, user_id=document.get("user_id"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Failed to delete the stored PDF.") from exc

    try:
        supabase.table("documents").delete().eq("id", document_id).execute()
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Failed to delete the document record.") from exc

    return {"status": "deleted"}


@app.get("/page/{page_id}", response_model=PageDetail)
async def get_page(
    page_id: str,
    background_tasks: BackgroundTasks,
    authorization: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
) -> PageDetail:
    supabase = get_supabase()
    user_id = get_authenticated_user(authorization, x_user_id).app_user_id
    page, document_user_id = get_page_record_for_user(page_id, user_id)

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

    page["document_file_url"] = create_document_download_url(
        document_id=page["document_id"],
        user_id=document_user_id,
        expires_in=60 * 60,
    )

    return page


@app.put("/page/{page_id}/annotations", response_model=PageDetail)
def update_page_annotations(
    page_id: str,
    payload: UpdatePageAnnotationsRequest,
    authorization: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
) -> PageDetail:
    supabase = get_supabase()
    user_id = get_authenticated_user(authorization, x_user_id).app_user_id
    _page, document_user_id = get_page_record_for_user(page_id, user_id)
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
    page["document_file_url"] = create_document_download_url(
        document_id=page["document_id"],
        user_id=document_user_id,
        expires_in=60 * 60,
    )

    return page


@app.post("/page/{page_id}/regenerate-summary", response_model=PageDetail)
async def regenerate_summary_for_page(
    page_id: str,
    authorization: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
) -> PageDetail:
    user_id = get_authenticated_user(authorization, x_user_id).app_user_id
    _page, document_user_id = get_page_record_for_user(page_id, user_id)
    page = await regenerate_page_summary(page_id)
    page["document_file_url"] = create_document_download_url(
        document_id=page["document_id"],
        user_id=document_user_id,
        expires_in=60 * 60,
    )

    return page


@app.post("/page/{page_id}/ask", response_model=AskPageQuestionResponse)
async def ask_question_for_page(
    page_id: str,
    payload: AskPageQuestionRequest,
    authorization: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
) -> AskPageQuestionResponse:
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Enter a question for this page.")

    user_id = get_authenticated_user(authorization, x_user_id).app_user_id
    page, _document_user_id = get_page_record_for_user(page_id, user_id)
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
