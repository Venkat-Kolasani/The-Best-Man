from __future__ import annotations

import cognee
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    llm_api_key: str = ""
    llm_provider: str = "gemini"
    llm_model: str = "gemini/gemini-3.1-flash-lite"
    embedding_provider: str = "gemini"
    embedding_model: str = "gemini/gemini-embedding-001"
    embedding_dimensions: int = 3072
    github_token: str = ""
    cognee_db_path: str = "data/cognee"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()

_cognee_initialized = False
_BACKEND_DIR = Path(__file__).resolve().parent.parent


def initialize_cognee() -> None:
    """Apply this app's configured provider, model, and key to Cognee."""
    global _cognee_initialized

    if _cognee_initialized:
        return

    cognee_root = (_BACKEND_DIR / settings.cognee_db_path).resolve()
    cognee.config.system_root_directory(str(cognee_root))
    cognee.config.data_root_directory(str((cognee_root / "data").resolve()))
    cognee.config.set_llm_provider(settings.llm_provider)
    cognee.config.set_llm_model(settings.llm_model)
    cognee.config.set_llm_api_key(settings.llm_api_key)
    cognee.config.set_embedding_provider(settings.embedding_provider)
    cognee.config.set_embedding_model(settings.embedding_model)
    cognee.config.set_embedding_dimensions(settings.embedding_dimensions)
    cognee.config.set_embedding_api_key(settings.llm_api_key)
    _cognee_initialized = True
