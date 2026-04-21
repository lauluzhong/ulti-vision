"""Application settings loaded from .env via Pydantic BaseSettings.

Fails loudly at import time if any required secret is missing (see CONTEXT D-09).
"""

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Required configuration for every Phase 1 entry point."""

    gemini_api_key: SecretStr = Field(..., alias="GEMINI_API_KEY")
    anthropic_api_key: SecretStr = Field(..., alias="ANTHROPIC_API_KEY")
    langfuse_public_key: SecretStr = Field(..., alias="LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: SecretStr = Field(..., alias="LANGFUSE_SECRET_KEY")
    langfuse_host: str = Field(
        default="https://cloud.langfuse.com", alias="LANGFUSE_HOST"
    )
    database_url: str = Field(..., alias="DATABASE_URL")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a process-wide singleton Settings instance."""
    return Settings()  # type: ignore[call-arg]


# Module-level eager load so missing env vars fail at import time, not at first use.
settings: Settings = get_settings()
