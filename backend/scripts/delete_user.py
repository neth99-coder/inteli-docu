from __future__ import annotations

import argparse
from pathlib import Path
import sys

from storage3.exceptions import StorageApiError

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db import get_supabase
from app.services.document_storage import (
    delete_document_file,
    ensure_storage_bucket,
    normalize_user_id,
    resolve_document_storage_path,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Delete a user's Supabase auth account and/or their app documents. "
            "Runs in preview mode unless --confirm is provided."
        )
    )
    parser.add_argument("--email", help="Supabase auth email to delete.")
    parser.add_argument("--app-user-id", help="Workspace user id used in documents.user_id and S3 paths.")
    parser.add_argument(
        "--delete-documents",
        action="store_true",
        help="Delete the user's documents, pages, and stored PDF files.",
    )
    parser.add_argument(
        "--delete-auth-user",
        action="store_true",
        help="Delete the user's Supabase auth account.",
    )
    parser.add_argument(
        "--soft-delete-auth",
        action="store_true",
        help="Soft-delete the Supabase auth account instead of hard-deleting it.",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Actually perform the deletion. Without this flag, the script only previews actions.",
    )
    return parser.parse_args()


def get_auth_user_by_email(email: str | None):
    if not email:
        return None

    for user in get_supabase().auth.admin.list_users():
        if getattr(user, "email", None) == email:
            return user
    return None


def get_documents_for_user(app_user_id: str | None) -> list[dict]:
    if not app_user_id:
        return []

    response = (
        get_supabase().table("documents")
        .select("id, name, user_id")
        .eq("user_id", app_user_id)
        .order("created_at", desc=False)
        .execute()
    )
    return response.data or []


def preview(auth_user, app_user_id: str | None, documents: list[dict], args: argparse.Namespace) -> None:
    print("Preview mode. No changes will be made unless you re-run with --confirm.")
    print(f"delete_auth_user={args.delete_auth_user}")
    print(f"delete_documents={args.delete_documents}")
    print(f"soft_delete_auth={args.soft_delete_auth}")
    print(f"email={args.email or '-'}")
    print(f"app_user_id={app_user_id or '-'}")

    if args.delete_auth_user:
        if auth_user is None:
            print("auth_user: not found")
        else:
            print(f"auth_user: found id={getattr(auth_user, 'id', '-')}")

    if args.delete_documents:
        print(f"documents_found={len(documents)}")
        for document in documents:
            location = resolve_document_storage_path(document["id"], app_user_id)
            location_text = f"{location['kind']}:{location['path']}" if location else "missing"
            print(f"- {document['id']} | {document['name']} | {location_text}")


def delete_documents(app_user_id: str, documents: list[dict]) -> None:
    if not documents:
        print("No documents to delete.")
        return

    ensure_storage_bucket()
    supabase = get_supabase()

    for document in documents:
        document_id = document["id"]
        try:
            delete_document_file(document_id=document_id, user_id=app_user_id)
        except StorageApiError as exc:
            print(f"error deleting file for {document_id}: {exc}")
            continue
        except Exception as exc:
            print(f"error deleting file for {document_id}: {exc}")
            continue

        supabase.table("documents").delete().eq("id", document_id).execute()
        print(f"deleted document {document_id}")


def delete_auth_user(auth_user, should_soft_delete: bool) -> None:
    if auth_user is None:
        print("Auth user not found.")
        return

    get_supabase().auth.admin.delete_user(
        getattr(auth_user, "id"),
        should_soft_delete=should_soft_delete,
    )
    print(f"deleted auth user {getattr(auth_user, 'id')}")


def main() -> None:
    args = parse_args()

    if not args.delete_documents and not args.delete_auth_user:
        raise SystemExit("Choose at least one action: --delete-documents and/or --delete-auth-user")

    app_user_id = normalize_user_id(args.app_user_id) if args.app_user_id else None
    auth_user = get_auth_user_by_email(args.email)

    if not app_user_id and auth_user is not None:
        metadata = getattr(auth_user, "user_metadata", None) or {}
        candidate = metadata.get("app_user_id") if isinstance(metadata, dict) else None
        if isinstance(candidate, str) and candidate.strip():
            app_user_id = normalize_user_id(candidate)
        elif getattr(auth_user, "email", None):
            app_user_id = normalize_user_id(getattr(auth_user, "email"))

    documents = get_documents_for_user(app_user_id)

    if not args.confirm:
        preview(auth_user, app_user_id, documents, args)
        return

    if args.delete_documents:
        if not app_user_id:
            raise SystemExit("An app user id is required to delete documents. Pass --app-user-id or --email.")
        delete_documents(app_user_id, documents)

    if args.delete_auth_user:
        delete_auth_user(auth_user, should_soft_delete=args.soft_delete_auth)


if __name__ == "__main__":
    main()
