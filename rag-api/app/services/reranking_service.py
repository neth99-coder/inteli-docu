from __future__ import annotations

from functools import lru_cache
from typing import Any

from sentence_transformers import CrossEncoder

from app.config import Settings, get_settings


class RerankingService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.model = get_reranker_model()

    def rerank(self, question: str, candidates: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
        if not candidates:
            return []

        pairs = [(question, candidate.get("content", "")) for candidate in candidates]
        scores = self.model.predict(
            pairs,
            batch_size=self.settings.reranker_batch_size,
            show_progress_bar=False,
        )

        rescored: list[dict[str, Any]] = []
        for item, score in zip(candidates, scores, strict=False):
            updated_item = dict(item)
            updated_item["score"] = float(score)
            rescored.append(updated_item)

        return sorted(rescored, key=lambda candidate: candidate["score"], reverse=True)[:limit]


@lru_cache
def get_reranker_model() -> CrossEncoder:
    settings: Settings = get_settings()
    return CrossEncoder(settings.default_reranker_model)
