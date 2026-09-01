from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "txtai-partitioned-knowledge-base-mvp"
    app_env: str = "development"
    app_host: str = "127.0.0.1"
    app_port: int = Field(default=8000, ge=1, le=65535)

    data_root: Path = Path("./data")
    raw_root: Path = Path("./data/raw")
    staging_root: Path = Path("./data/staging")
    index_root: Path = Path("./data/indexes")
    fixture_root: Path = Path("./data/fixtures")
    metadata_database_url: str = "sqlite+aiosqlite:///./data/metadata/knowledge.db"

    embedding_model: str = "Qwen/Qwen3-Embedding-0.6B"
    retrieval_top_k: int = Field(default=5, ge=1, le=100)
    max_upload_size_mb: int = Field(default=25, ge=1, le=200)
    allowed_file_types: tuple[str, ...] = ("pdf", "docx", "txt", "md")
    chunk_target_tokens: int = Field(default=550, ge=1)
    chunk_min_tokens: int = Field(default=100, ge=1)
    chunk_max_tokens: int = Field(default=700, ge=1)
    chunk_overlap_tokens: int = Field(default=75, ge=0)

    llm_provider: str = "openai_compatible"
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    llm_data_mode: Literal["local", "remote"] = "remote"
    max_question_length: int = Field(default=2000, ge=1)
    router_retry_count: int = Field(default=1, ge=0, le=3)
    log_level: str = "INFO"
    cors_origins: tuple[str, ...] = (
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    )

    @field_validator("allowed_file_types", "cors_origins", mode="before")
    @classmethod
    def split_csv(cls, value: object) -> object:
        if isinstance(value, str):
            return tuple(item.strip() for item in value.split(",") if item.strip())
        return value

    @model_validator(mode="after")
    def validate_chunk_settings(self) -> "Settings":
        if not self.chunk_min_tokens <= self.chunk_target_tokens <= self.chunk_max_tokens:
            raise ValueError(
                "chunk sizes must satisfy min <= target <= max"
            )
        if self.chunk_overlap_tokens >= self.chunk_max_tokens:
            raise ValueError("chunk overlap must be smaller than chunk max")
        return self

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    def ensure_directories(self) -> None:
        for path in (
            self.data_root,
            self.raw_root,
            self.staging_root,
            self.fixture_root,
            self.index_root,
            self.data_root / "metadata",
        ):
            path.mkdir(parents=True, exist_ok=True)
        for partition in ("finance", "hr", "tech"):
            (self.index_root / partition).mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()

