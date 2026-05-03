from fastapi import Depends

from app.core.auth import decode_supabase_jwt, require_bearer_token
from app.schemas.common import CurrentUser


def get_current_user(token: str = Depends(require_bearer_token)) -> CurrentUser:
    payload = decode_supabase_jwt(token)
    return CurrentUser(
        user_id=payload["sub"],
        email=payload.get("email"),
        raw_token=token,
    )

