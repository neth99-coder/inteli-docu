from functools import lru_cache
import base64
import json

from pydantic import Field
from pydantic_core import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Document Intelligence API"
    api_prefix: str = ""
    frontend_origin: str = "http://localhost:3000"

    supabase_url: str = Field(alias="SUPABASE_URL")
    supabase_service_role_key: str = Field(alias="SUPABASE_SERVICE_ROLE_KEY")
    supabase_storage_bucket: str = Field(default="documents", alias="SUPABASE_STORAGE_BUCKET")

    llm_provider: str = Field(default="gemini", alias="LLM_PROVIDER")

    gemini_api_key: str | None = Field(default=None, alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-3.1-flash-lite", alias="GEMINI_MODEL")
    gemini_fallback_models_raw: str = Field(default="gemini-3.0-flash", alias="GEMINI_FALLBACK_MODELS")

    openrouter_api_key: str | None = Field(default=None, alias="OPENROUTER_API_KEY")
    openrouter_model: str = Field(default="openrouter/free", alias="OPENROUTER_MODEL")
    openrouter_fallback_models_raw: str = Field(default="", alias="OPENROUTER_FALLBACK_MODELS")
    openrouter_site_url: str | None = Field(default=None, alias="OPENROUTER_SITE_URL")
    openrouter_app_name: str = Field(default="Document Intelligence API", alias="OPENROUTER_APP_NAME")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def gemini_fallback_models(self) -> list[str]:
        return [
            model.strip()
            for model in self.gemini_fallback_models_raw.split(",")
            if model.strip()
        ]

    @property
    def openrouter_fallback_models(self) -> list[str]:
        return [
            model.strip()
            for model in self.openrouter_fallback_models_raw.split(",")
            if model.strip()
        ]


def _get_supabase_role(jwt_token: str) -> str | None:
    try:
        parts = jwt_token.split(".")
        if len(parts) < 2:
            return None

        payload = parts[1]
        padding = "=" * (-len(payload) % 4)
        decoded = base64.urlsafe_b64decode(payload + padding)
        data = json.loads(decoded)
        role = data.get("role")
        return role if isinstance(role, str) else None
    except Exception:
        return None


@lru_cache
def get_settings() -> Settings:
    try:
        settings = Settings()
    except ValidationError as exc:
        missing_fields = sorted(error["loc"][0] for error in exc.errors())
        missing_names = ", ".join(missing_fields)
        raise RuntimeError(
            "Missing required backend environment variables: "
            f"{missing_names}. Copy backend/.env.example to backend/.env and fill them in."
        ) from exc

    supabase_role = _get_supabase_role(settings.supabase_service_role_key)
    if supabase_role == "anon":
        raise RuntimeError(
            "SUPABASE_SERVICE_ROLE_KEY is using the anon role. Replace it with the project's "
            "service_role key from Supabase Settings -> API."
        )

    provider = settings.llm_provider.strip().lower()
    if provider not in {"gemini", "openrouter"}:
        raise RuntimeError("LLM_PROVIDER must be either 'gemini' or 'openrouter'.")

    if provider == "gemini" and not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is required when LLM_PROVIDER=gemini.")

    if provider == "openrouter" and not settings.openrouter_api_key:
        raise RuntimeError("OPENROUTER_API_KEY is required when LLM_PROVIDER=openrouter.")

    return settings
