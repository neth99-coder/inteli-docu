from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException

from app.config import get_settings
from app.db import get_supabase
from app.services.document_storage import normalize_user_id


@dataclass(frozen=True)
class AuthenticatedUser:
    auth_user_id: str | None
    app_user_id: str
    email: str | None
    source: str


def _extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=401, detail="Invalid authorization header.")
    return token.strip()


def _resolve_app_user_id(user: object) -> str:
    user_metadata = getattr(user, "user_metadata", None) or {}
    if isinstance(user_metadata, dict):
        for key in ("app_user_id", "username"):
            value = user_metadata.get(key)
            if isinstance(value, str) and value.strip():
                return normalize_user_id(value)

    email = getattr(user, "email", None)
    if isinstance(email, str) and email.strip():
        return normalize_user_id(email)

    user_id = getattr(user, "id", None)
    if isinstance(user_id, str) and user_id.strip():
        return normalize_user_id(user_id)

    return normalize_user_id(None)


def get_authenticated_user(
    authorization: str | None,
    x_user_id: str | None,
) -> AuthenticatedUser:
    token = _extract_bearer_token(authorization)
    settings = get_settings()

    if token:
        try:
            response = get_supabase().auth.get_user(token)
        except Exception as exc:
            raise HTTPException(status_code=401, detail="Invalid or expired auth token.") from exc

        user = getattr(response, "user", None)
        if user is None:
            raise HTTPException(status_code=401, detail="Invalid or expired auth token.")

        return AuthenticatedUser(
            auth_user_id=getattr(user, "id", None),
            app_user_id=_resolve_app_user_id(user),
            email=getattr(user, "email", None),
            source="supabase-auth",
        )

    if settings.allow_legacy_auth_fallback:
        return AuthenticatedUser(
            auth_user_id=None,
            app_user_id=normalize_user_id(x_user_id),
            email=None,
            source="legacy-fallback",
        )

    raise HTTPException(status_code=401, detail="Authentication is required.")
