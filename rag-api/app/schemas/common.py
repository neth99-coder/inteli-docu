from pydantic import BaseModel


class CurrentUser(BaseModel):
    user_id: str
    email: str | None = None
    raw_token: str

