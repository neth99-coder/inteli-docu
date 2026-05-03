from typing import Any


class LlmService:
    def answer_question(self, *, question: str, chunks: list[dict[str, Any]]) -> str:
        if not chunks:
            return "I could not find relevant context in the selected documents."

        citations = ", ".join(
            f"page {chunk.get('page_number') or '?'}"
            for chunk in chunks[:3]
        )
        summary = " ".join(chunk.get("content", "")[:240] for chunk in chunks[:3]).strip()
        return f"Based on the retrieved context ({citations}), here is the best answer: {summary}"

    def build_source_payload(self, chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "document_id": chunk["document_id"],
                "chunk_id": chunk["id"],
                "page_number": chunk.get("page_number"),
                "score": float(chunk.get("score", 0.0)),
                "content_preview": chunk.get("content", "")[:220],
            }
            for chunk in chunks
        ]

