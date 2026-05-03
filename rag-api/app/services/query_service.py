from app.config import get_settings
from app.db.repositories import ChatRepository
from app.schemas.common import CurrentUser
from app.schemas.query import QueryRequest, QueryResponse, RetrievalDebug
from app.services.llm_service import LlmService
from app.services.reranking_service import RerankingService
from app.services.retrieval_service import RetrievalService


class QueryService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.retrieval_service = RetrievalService()
        self.reranking_service = RerankingService()
        self.llm_service = LlmService()
        self.chat_repository = ChatRepository()

    def answer(self, *, current_user: CurrentUser, request: QueryRequest) -> QueryResponse:
        top_k = min(request.top_k, self.settings.max_top_k)
        candidates, retrieval_metadata = self.retrieval_service.retrieve(
            user_id=current_user.user_id,
            document_ids=request.document_ids,
            question=request.question,
            top_k=top_k,
            use_multi_query=request.use_multi_query,
            use_hybrid_search=request.use_hybrid_search,
        )

        selected_chunks = candidates
        if request.use_reranking:
            selected_chunks = self.reranking_service.rerank(request.question, candidates, top_k)
        else:
            selected_chunks = candidates[:top_k]

        answer = self.llm_service.answer_question(question=request.question, chunks=selected_chunks)
        sources = self.llm_service.build_source_payload(selected_chunks) if request.include_sources else []

        if request.session_id:
            self.chat_repository.save_message(
                session_id=request.session_id,
                user_id=current_user.user_id,
                role="user",
                content=request.question,
            )
            self.chat_repository.save_message(
                session_id=request.session_id,
                user_id=current_user.user_id,
                role="assistant",
                content=answer,
                metadata={"sources": sources},
            )

        return QueryResponse(
            answer=answer,
            sources=sources,
            retrieval_debug=RetrievalDebug(
                multi_query_used=request.use_multi_query,
                hybrid_search_used=request.use_hybrid_search,
                reranking_used=request.use_reranking,
                generated_queries=retrieval_metadata["queries"],
                retrieval_metadata={
                    "query_stats": retrieval_metadata["query_stats"],
                    "merge_strategy": retrieval_metadata["merge_strategy"],
                },
            ),
        )

