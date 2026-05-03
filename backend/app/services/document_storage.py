from __future__ import annotations

import re
from functools import lru_cache
from typing import Literal, TypedDict

import boto3
from botocore.exceptions import ClientError
from storage3.exceptions import StorageApiError

from app.config import get_settings
from app.db import get_supabase


class DocumentStorageLocation(TypedDict):
    kind: Literal["s3", "supabase"]
    path: str


def normalize_user_id(user_id: str | None) -> str:
    settings = get_settings()
    candidate = (user_id or settings.default_user_id).strip()
    if not candidate:
        candidate = settings.default_user_id
    return candidate


def get_document_storage_path(document_id: str, user_id: str | None) -> str:
    safe_user_id = re.sub(r"[^A-Za-z0-9._@-]+", "_", normalize_user_id(user_id))
    return f"{safe_user_id}/files/{document_id}/original.pdf"


@lru_cache
def get_s3_client():
    settings = get_settings()
    return boto3.client(
        "s3",
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        endpoint_url=settings.aws_s3_endpoint_url,
    )


def ensure_storage_bucket() -> None:
    settings = get_settings()

    try:
        get_s3_client().head_bucket(Bucket=settings.aws_s3_bucket)
    except ClientError as exc:
        raise RuntimeError(f"Failed to access S3 bucket '{settings.aws_s3_bucket}'.") from exc


def upload_document_bytes(document_id: str, user_id: str | None, file_bytes: bytes) -> str:
    settings = get_settings()
    object_key = get_document_storage_path(document_id, user_id)

    get_s3_client().put_object(
        Bucket=settings.aws_s3_bucket,
        Key=object_key,
        Body=file_bytes,
        ContentType="application/pdf",
    )

    return object_key


def delete_document_file(document_id: str, user_id: str | None) -> None:
    location = resolve_document_storage_path(document_id, user_id)
    if not location:
        return

    settings = get_settings()
    if location["kind"] == "s3":
        get_s3_client().delete_object(Bucket=settings.aws_s3_bucket, Key=location["path"])
        return

    get_supabase().storage.from_(settings.legacy_supabase_storage_bucket).remove([location["path"]])


def create_document_download_url(document_id: str, user_id: str | None, expires_in: int) -> str | None:
    location = resolve_document_storage_path(document_id, user_id)
    if not location:
        return None

    settings = get_settings()
    if location["kind"] == "s3":
        return get_s3_client().generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.aws_s3_bucket, "Key": location["path"]},
            ExpiresIn=expires_in,
        )

    signed = get_supabase().storage.from_(settings.legacy_supabase_storage_bucket).create_signed_url(
        location["path"],
        expires_in,
    )
    return signed.get("signedURL")


def resolve_document_storage_path(document_id: str, user_id: str | None) -> DocumentStorageLocation | None:
    s3_path = get_document_storage_path(document_id, user_id)
    settings = get_settings()

    try:
        get_s3_client().head_object(Bucket=settings.aws_s3_bucket, Key=s3_path)
        return {"kind": "s3", "path": s3_path}
    except ClientError:
        pass

    supabase = get_supabase()
    legacy_preferred_path = f"{document_id}/original.pdf"

    try:
        supabase.storage.from_(settings.legacy_supabase_storage_bucket).create_signed_url(
            legacy_preferred_path,
            60,
        )
        return {"kind": "supabase", "path": legacy_preferred_path}
    except StorageApiError:
        pass

    try:
        stored_files = supabase.storage.from_(settings.legacy_supabase_storage_bucket).list(document_id)
    except StorageApiError:
        return None

    for item in stored_files:
        file_name = item.get("name")
        if isinstance(file_name, str) and file_name.lower().endswith(".pdf"):
            return {"kind": "supabase", "path": f"{document_id}/{file_name}"}

    return None
