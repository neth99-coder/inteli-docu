from fastapi import HTTPException, status

from app.db.repositories import JobRepository
from app.schemas.common import CurrentUser


class JobService:
    def __init__(self) -> None:
        self.job_repository = JobRepository()

    def get_job(self, *, job_id: str, current_user: CurrentUser) -> dict:
        job = self.job_repository.get_job(job_id, current_user.user_id)
        if not job:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
        return job

