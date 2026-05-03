from typing import Any

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    question: str
    document_ids: list[str]
    top_k: int = Field(default=10, ge=1, le=50)
    use_multi_query: bool = True
    use_hybrid_search: bool = True
    use_reranking: bool = True
    include_sources: bool = True
    session_id: str | None = None


class QuerySource(BaseModel):
    document_id: str
    chunk_id: str
    page_number: int | None = None
    score: float
    content_preview: str


class RetrievalDebug(BaseModel):
    multi_query_used: bool
    hybrid_search_used: bool
    reranking_used: bool
    generated_queries: list[str] = Field(default_factory=list)
    retrieval_metadata: dict[str, Any] = Field(default_factory=dict)


class QueryResponse(BaseModel):
    answer: str
    sources: list[QuerySource] = []
    retrieval_debug: RetrievalDebug
