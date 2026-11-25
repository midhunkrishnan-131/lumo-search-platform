"""Environment-based configuration for the LUMO backend."""

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]
_ALLOWED_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


class Settings(BaseSettings):
    """Runtime settings loaded from the environment and an optional .env file."""

    app_name: str = "LUMO"
    app_version: str = "0.1.0"
    environment: str = "development"
    database_url: str = ""
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    api_auth_token: str = ""
    rate_limit_per_minute: int = 240

    # Crawler Configuration (Phase 3)
    crawler_user_agent: str = "LUMOBot/1.0 (+http://127.0.0.1:8000/bot)"
    crawler_max_depth: int = 2
    crawler_max_pages: int = 100
    crawler_concurrency: int = 2
    crawler_per_domain_concurrency: int = 1
    crawler_crawl_delay: float = 1.0
    crawler_max_response_size: int = 2 * 1024 * 1024  # 2 MB
    crawler_request_timeout: float = 20.0

    # Semantic Search Configuration (Phase 6)
    embedding_model_name: str = "all-MiniLM-L6-v2"
    embedding_dimension: int = 384
    chunk_size: int = 500
    chunk_overlap: int = 50
    embedding_batch_size: int = 16
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection_name: str = "lumo_documents"
    qdrant_storage_path: str = "./qdrant_storage"
    semantic_search_limit: int = 10

    # Hybrid Search Configuration (Phase 7)
    hybrid_rrf_k: int = 60
    hybrid_classic_depth: int = 25
    hybrid_semantic_depth: int = 25

    # AI Search & RAG Configuration (Phase 8)
    gemini_api_key: str = ""
    gemini_model: str = "gemini-1.5-flash"
    grok_api_key: str = ""
    grok_model: str = "grok-beta"
    ai_primary_provider: str = "gemini"
    ai_fallback_provider: str = ""
    ollama_enabled: bool = False
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3"
    local_only_ai: bool = False
    local_ai_max_context_chars: int = 12000
    local_ai_concurrency_limit: int = 1
    ai_request_timeout: float = 30.0
    ai_max_context_documents: int = 8
    ai_max_context_tokens: int = 4000

    # Autonomous Research Agent Configuration (Phase 9)
    research_max_iterations: int = 3
    research_max_queries: int = 12
    research_max_sources: int = 30
    research_max_chunks_per_query: int = 4
    research_max_duration_seconds: float = 120.0
    research_max_ai_calls: int = 10

    # Download Guardian Configuration (Phase 10)
    guardian_max_file_size_bytes: int = 25 * 1024 * 1024  # 25 MB max upload
    guardian_max_redirects: int = 5
    guardian_request_timeout: float = 5.0
    guardian_max_response_size_bytes: int = 512 * 1024  # 512 KB headers/preview
    guardian_virustotal_api_key: str = ""
    guardian_virustotal_base_url: str = "https://www.virustotal.com/api/v3"
    guardian_virustotal_timeout: float = 5.0
    guardian_history_limit: int = 100

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        env_ignore_empty=False,
    )

    @field_validator("app_name", "app_version")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Value must not be empty.")
        return cleaned

    @field_validator("environment")
    @classmethod
    def normalize_environment(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if not cleaned:
            raise ValueError("ENVIRONMENT must not be empty.")
        return cleaned

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        cleaned = value.strip().upper()
        if cleaned not in _ALLOWED_LOG_LEVELS:
            allowed = ", ".join(sorted(_ALLOWED_LOG_LEVELS))
            raise ValueError(f"LOG_LEVEL must be one of: {allowed}.")
        return cleaned

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            return ""
        if not (cleaned.startswith("postgresql+psycopg://") or cleaned.startswith("sqlite")):
            raise ValueError(
                "DATABASE_URL must start with postgresql+psycopg:// "
                "or be left empty until PostgreSQL is configured."
            )
        return cleaned

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def cors_origin_list(self) -> list[str]:
        origins: list[str] = []
        for item in self.cors_origins.split(","):
            origin = item.strip().rstrip("/")
            if not origin:
                continue
            if origin == "*" or "*" in origin:
                raise ValueError(
                    "Wildcard CORS is not allowed. Set CORS_ORIGINS to explicit "
                    "http:// or https:// origins."
                )
            if not (origin.startswith("http://") or origin.startswith("https://")):
                raise ValueError(
                    "Each CORS origin must start with http:// or https://."
                )
            origins.append(origin)
        return origins

    @model_validator(mode="after")
    def require_explicit_cors(self) -> "Settings":
        if not self.cors_origin_list:
            raise ValueError(
                "CORS_ORIGINS must include at least one http:// or https:// origin."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings object."""
    return Settings()
