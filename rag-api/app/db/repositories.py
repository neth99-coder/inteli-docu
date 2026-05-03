from __future__ import annotations

from typing import Any

from app.db.supabase_client import get_supabase_admin_client


class DocumentRepository:
    def __init__(self) -> None:
        self.client = get_supabase_admin_client()

    def create_document(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = self.client.table("documents").insert(payload).execute()
        return response.data[0]

    def list_documents(self, user_id: str) -> list[dict[str, Any]]:
        response = (
            self.client.table("documents")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .execute()
        )
        return response.data or []

    def get_document(self, document_id: str, user_id: str) -> dict[str, Any] | None:
        response = (
            self.client.table("documents")
            .select("*")
            .eq("id", document_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        rows = response.data or []
        return rows[0] if rows else None

    def delete_document(self, document_id: str, user_id: str) -> None:
        self.client.table("documents").delete().eq("id", document_id).eq("user_id", user_id).execute()

    def update_document_status(self, document_id: str, status: str, **fields: Any) -> None:
        payload = {"status": status, **fields}
        self.client.table("documents").update(payload).eq("id", document_id).execute()


class JobRepository:
    def __init__(self) -> None:
        self.client = get_supabase_admin_client()

    def create_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = self.client.table("document_processing_jobs").insert(payload).execute()
        return response.data[0]

    def get_job(self, job_id: str, user_id: str) -> dict[str, Any] | None:
        response = (
            self.client.table("document_processing_jobs")
            .select("*")
            .eq("id", job_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        rows = response.data or []
        return rows[0] if rows else None

    def update_job(self, job_id: str, payload: dict[str, Any]) -> None:
        self.client.table("document_processing_jobs").update(payload).eq("id", job_id).execute()


class ChunkRepository:
    def __init__(self) -> None:
        self.client = get_supabase_admin_client()

    def list_chunks(self, document_id: str, user_id: str) -> list[dict[str, Any]]:
        response = (
            self.client.table("document_chunks")
            .select("*")
            .eq("document_id", document_id)
            .eq("user_id", user_id)
            .order("chunk_index")
            .execute()
        )
        return response.data or []

    def insert_chunks(self, chunks: list[dict[str, Any]]) -> None:
        if not chunks:
            return
        self.client.table("document_chunks").insert(chunks).execute()

    def hybrid_search(
        self,
        *,
        user_id: str,
        document_ids: list[str],
        query_text: str,
        query_embedding: list[float],
        match_count: int,
    ) -> dict[str, list[dict[str, Any]]]:
        vector_response = self.client.rpc(
            "match_document_chunks",
            {
                "filter_user_id": user_id,
                "filter_document_ids": document_ids,
                "query_embedding": query_embedding,
                "match_count": match_count,
            },
        ).execute()
        keyword_response = self.client.rpc(
            "keyword_search_document_chunks",
            {
                "filter_user_id": user_id,
                "filter_document_ids": document_ids,
                "search_query": query_text,
                "match_count": match_count,
            },
        ).execute()
        return {
            "vector": vector_response.data or [],
            "keyword": keyword_response.data or [],
        }


class ChatRepository:
    def __init__(self) -> None:
        self.client = get_supabase_admin_client()

    def save_message(
        self,
        *,
        session_id: str,
        user_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.client.table("chat_messages").insert(
            {
                "session_id": session_id,
                "user_id": user_id,
                "role": role,
                "content": content,
                "metadata": metadata or {},
            }
        ).execute()

