from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.db.repositories import ChunkRepository
from app.services.embedding_service import EmbeddingService


class RetrievalService:
    def __init__(self) -> None:
        self.embedding_service = EmbeddingService()
        self.chunk_repository = ChunkRepository()

    def build_query_variants(self, question: str, enabled: bool) -> list[str]:
        if not enabled:
            return [question]

        return [
            question,
            f"Summarize the answer to: {question}",
            f"What evidence in the document answers: {question}",
            f"Find the most relevant section for: {question}",
        ]

    def retrieve(
        self,
        *,
        user_id: str,
        document_ids: list[str],
        question: str,
        top_k: int,
        use_multi_query: bool,
        use_hybrid_search: bool,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        queries = self.build_query_variants(question, use_multi_query)
        fused_scores: dict[str, float] = defaultdict(float)
        fused_records: dict[str, dict[str, Any]] = {}
        per_query_counts: list[dict[str, int]] = []

        for query in queries:
            query_embedding = self.embedding_service.embed_query(query)
            if use_hybrid_search:
                results = self.chunk_repository.hybrid_search(
                    user_id=user_id,
                    document_ids=document_ids,
                    query_text=query,
                    query_embedding=query_embedding,
                    match_count=max(top_k * 3, 30),
                )
                ranked_lists = [results["vector"], results["keyword"]]
            else:
                results = self.chunk_repository.hybrid_search(
                    user_id=user_id,
                    document_ids=document_ids,
                    query_text=query,
                    query_embedding=query_embedding,
                    match_count=max(top_k * 3, 30),
                )
                ranked_lists = [results["vector"]]

            per_query_counts.append(
                {
                    "query": query,
                    "vector_hits": len(results["vector"]),
                    "keyword_hits": len(results["keyword"]),
                }
            )

            for ranked_list in ranked_lists:
                for rank, item in enumerate(ranked_list, start=1):
                    chunk_id = item["id"]
                    fused_scores[chunk_id] += 1 / (60 + rank)
                    fused_records[chunk_id] = {
                        **item,
                        "score": fused_scores[chunk_id],
                    }

        ranked_records = sorted(fused_records.values(), key=lambda record: record["score"], reverse=True)
        return ranked_records[: max(top_k * 5, 20)], {
            "queries": queries,
            "query_stats": per_query_counts,
            "merge_strategy": "rrf",
        }

