from fastapi import APIRouter, Depends

from app.core.dependencies import get_current_user
from app.schemas.common import CurrentUser
from app.schemas.query import QueryRequest, QueryResponse
from app.services.query_service import QueryService

router = APIRouter(prefix="/query", tags=["query"])


@router.post("", response_model=QueryResponse)
def query_documents(
    request: QueryRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> QueryResponse:
    service = QueryService()
    return service.answer(current_user=current_user, request=request)

