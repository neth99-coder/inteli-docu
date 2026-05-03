from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = Field(default="RAG API", alias="APP_NAME")
    app_env: str = Field(default="development", alias="APP_ENV")
    api_prefix: str = Field(default="", alias="API_PREFIX")
    frontend_origin: str = Field(default="http://localhost:3000", alias="FRONTEND_ORIGIN")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    supabase_url: str = Field(alias="SUPABASE_URL")
    supabase_anon_key: str = Field(alias="SUPABASE_ANON_KEY")
    supabase_service_role_key: str = Field(alias="SUPABASE_SERVICE_ROLE_KEY")
    supabase_jwt_secret: str = Field(alias="SUPABASE_JWT_SECRET")
    supabase_storage_bucket: str = Field(default="documents", alias="SUPABASE_STORAGE_BUCKET")

    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    queue_name: str = Field(default="document-processing", alias="QUEUE_NAME")

    default_embedding_model: str = Field(
        default="BAAI/bge-small-en-v1.5",
        alias="DEFAULT_EMBEDDING_MODEL",
    )
    default_embedding_dimension: int = Field(default=384, alias="DEFAULT_EMBEDDING_DIMENSION")
    default_reranker_model: str = Field(
        default="BAAI/bge-reranker-base",
        alias="DEFAULT_RERANKER_MODEL",
    )
    llm_provider: str = Field(default="openrouter", alias="LLM_PROVIDER")
    llm_api_key: str = Field(default="", alias="LLM_API_KEY")
    llm_model: str = Field(default="meta-llama/llama-3.1-8b-instruct", alias="LLM_MODEL")

    unstructured_api_key: str | None = Field(default=None, alias="UNSTRUCTURED_API_KEY")
    unstructured_api_url: str = Field(
        default="https://api.unstructuredapp.io/general/v0/general",
        alias="UNSTRUCTURED_API_URL",
    )
    llama_parse_api_key: str | None = Field(default=None, alias="LLAMA_PARSE_API_KEY")
    embedding_batch_size: int = Field(default=16, alias="EMBEDDING_BATCH_SIZE")
    reranker_batch_size: int = Field(default=16, alias="RERANKER_BATCH_SIZE")
    max_upload_size_mb: int = Field(default=50, alias="MAX_UPLOAD_SIZE_MB")
    max_top_k: int = Field(default=20, alias="MAX_TOP_K")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
