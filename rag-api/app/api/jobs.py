from fastapi import APIRouter, Depends

from app.core.dependencies import get_current_user
from app.schemas.common import CurrentUser
from app.schemas.jobs import JobResponse
from app.services.job_service import JobService

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}", response_model=JobResponse)
def get_job(job_id: str, current_user: CurrentUser = Depends(get_current_user)) -> JobResponse:
    service = JobService()
    return JobResponse.model_validate(service.get_job(job_id=job_id, current_user=current_user))

