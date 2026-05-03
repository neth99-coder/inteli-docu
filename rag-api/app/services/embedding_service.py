from __future__ import annotations

from functools import lru_cache
from typing import Iterable

from sentence_transformers import SentenceTransformer

from app.config import Settings, get_settings


class EmbeddingService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.model = get_embedding_model()

    def embed_query(self, query: str) -> list[float]:
        prefixed_query = self._normalize_query(query)
        return self._embed_text(prefixed_query)

    def embed_chunks(self, chunks: Iterable[str]) -> list[list[float]]:
        chunk_list = list(chunks)
        if not chunk_list:
            return []
        embeddings = self.model.encode(
            chunk_list,
            batch_size=self.settings.embedding_batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return embeddings.tolist()

    def _embed_text(self, text: str) -> list[float]:
        embedding = self.model.encode(
            text,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return embedding.tolist()

    def _normalize_query(self, query: str) -> str:
        model_name = self.settings.default_embedding_model.lower()
        if "e5" in model_name:
            return f"query: {query}"
        if "bge" in model_name:
            return f"Represent this sentence for searching relevant passages: {query}"
        return query


@lru_cache
def get_embedding_model() -> SentenceTransformer:
    settings: Settings = get_settings()
    return SentenceTransformer(settings.default_embedding_model)
