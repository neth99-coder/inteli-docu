from __future__ import annotations

import argparse
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
    get_document_storage_path,
    normalize_user_id,
    resolve_document_storage_path,
    upload_document_bytes,
)


def parse_args() -> argparse.Namespace:
    settings = get_settings()
    parser = argparse.ArgumentParser(
        description="Create or reuse a Supabase auth user, back up legacy PDFs, and upload them to S3."
    )
    parser.add_argument("--email", required=True, help="Supabase auth email for the existing user.")
    parser.add_argument("--password", required=True, help="Supabase auth password for the existing user.")
    parser.add_argument(
        "--app-user-id",
        default=settings.default_user_id,
        help="Stable workspace user id used in document ownership and S3 paths.",
    )
    parser.add_argument(
        "--backup-dir",
        default="backups/existing-user",
        help="Directory where legacy PDFs should be backed up before S3 upload.",
    )
    return parser.parse_args()


def ensure_auth_user(email: str, password: str, app_user_id: str) -> None:
    supabase = get_supabase()
    users = supabase.auth.admin.list_users()

    for user in users:
        if getattr(user, "email", None) == email:
            supabase.auth.admin.update_user_by_id(
                getattr(user, "id"),
                {
                    "password": password,
                    "user_metadata": {"app_user_id": app_user_id},
                    "email_confirm": True,
                },
            )
            print(f"Reused existing auth user: {email}")
            return

    supabase.auth.admin.create_user(
        {
            "email": email,
            "password": password,
            "email_confirm": True,
            "user_metadata": {"app_user_id": app_user_id},
        }
    )
    print(f"Created auth user: {email}")


def update_document_ownership(app_user_id: str) -> None:
    supabase = get_supabase()
    settings = get_settings()

    try:
        response = (
            supabase.table("documents")
            .select("id, user_id")
            .execute()
        )
    except APIError as exc:
        raise RuntimeError(
            "The documents.user_id column is missing. Run the latest Supabase schema first."
        ) from exc

    documents = response.data or []
    updated = 0
    for document in documents:
        current_user_id = document.get("user_id")
        if current_user_id in {None, "", "default", settings.default_user_id}:
            (
                supabase.table("documents")
                .update({"user_id": app_user_id})
                .eq("id", document["id"])
                .execute()
            )
            updated += 1

    print(f"Updated document ownership for {updated} document(s).")


def backup_and_upload_documents(app_user_id: str, backup_dir: Path) -> None:
    supabase = get_supabase()
    settings = get_settings()

    response = (
        supabase.table("documents")
        .select("id, name, user_id")
        .eq("user_id", app_user_id)
        .order("created_at", desc=False)
        .execute()
    )
    documents = response.data or []
    if not documents:
        print("No documents found for this user.")
        return

    backup_dir.mkdir(parents=True, exist_ok=True)
    migrated = 0

    for document in documents:
        document_id = document["id"]
        resolved = resolve_document_storage_path(document_id, app_user_id)
        if not resolved:
            print(f"skip {document_id}: no stored PDF found")
            continue

        if resolved["kind"] == "s3":
            print(f"skip {document_id}: already in S3 at {get_document_storage_path(document_id, app_user_id)}")
            continue

        try:
            file_bytes = supabase.storage.from_(settings.legacy_supabase_storage_bucket).download(resolved["path"])
        except StorageApiError as exc:
            print(f"error {document_id}: failed to download from Supabase Storage ({exc})")
            continue

        backup_path = backup_dir / app_user_id / document_id / "original.pdf"
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        backup_path.write_bytes(file_bytes)

        upload_document_bytes(document_id=document_id, user_id=app_user_id, file_bytes=file_bytes)
        migrated += 1
        print(
            "migrated "
            f"{document_id}: backup={backup_path} "
            f"s3={get_document_storage_path(document_id, app_user_id)}"
        )

    print(f"Backed up and uploaded {migrated} document(s).")


def main() -> None:
    args = parse_args()
    app_user_id = normalize_user_id(args.app_user_id)
    backup_dir = Path(args.backup_dir)

    ensure_storage_bucket()
    ensure_auth_user(args.email, args.password, app_user_id)
    update_document_ownership(app_user_id)
    backup_and_upload_documents(app_user_id, backup_dir)


if __name__ == "__main__":
    main()
