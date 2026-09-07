from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        enable_decoding=False,
        extra="ignore",
    )

    app_name: str = "txtai-partitioned-knowledge-base-mvp"
    app_env: str = "development"
    app_host: str = "127.0.0.1"
    app_port: int = Field(default=8001, ge=1, le=65535)
    serve_frontend: bool = False
    frontend_dist_dir: Path = Path("./frontend/dist")

    data_root: Path = Path("./data")
    raw_root: Path = Path("./data/raw")
    staging_root: Path = Path("./data/staging")
    hierarchical_index_root: Path = Path("./data/indexes-hierarchical")
    fixture_root: Path = Path("./data/fixtures")
    metadata_database_url: str = "sqlite+aiosqlite:///./data/metadata/knowledge.db"

    embedding_model: str = "Qwen/Qwen3-Embedding-0.6B"
    retrieval_top_k: int = Field(default=5, ge=1, le=100)
    retrieval_min_score: float = Field(default=0.5, ge=0, le=1)
    hierarchical_document_beam_width: int = Field(default=3, ge=1, le=10)
    hierarchical_section_beam_width: int = Field(default=2, ge=1, le=10)
    hierarchical_leaf_candidate_limit: int = Field(default=100, ge=1, le=500)
    max_upload_size_mb: int = Field(default=25, ge=1, le=200)
    allowed_file_types: tuple[str, ...] = ("pdf", "docx", "txt", "md")
    chunk_target_tokens: int = Field(default=550, ge=1)
    chunk_min_tokens: int = Field(default=100, ge=1)
    chunk_max_tokens: int = Field(default=700, ge=1)
    chunk_overlap_tokens: int = Field(default=75, ge=0)

    llm_provider: Literal["openai_compatible"] = "openai_compatible"
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    router_llm_model: str = ""
    answer_llm_model: str = ""
    llm_timeout_seconds: float = Field(default=30, ge=1, le=120)
    llm_data_mode: Literal["local", "remote"] = "remote"
    max_question_length: int = Field(default=2000, ge=1)
    router_retry_count: int = Field(default=1, ge=0, le=1)
    composite_max_partitions: int = Field(default=2, ge=2, le=2)
    composite_top_k_per_partition: int = Field(default=3, ge=1, le=20)
    answer_mode: Literal["llm", "extractive"] = "llm"
    web_search_enabled: bool = False
    web_search_provider: Literal["tavily"] = "tavily"
    web_search_base_url: str = "https://api.tavily.com/search"
    web_search_api_key: str = ""
    web_search_timeout_seconds: float = Field(default=60, ge=1, le=120)
    web_search_max_results: int = Field(default=5, ge=1, le=5)
    log_level: str = "INFO"
    cors_origins: tuple[str, ...] = (
        "http://localhost:5174",
        "http://127.0.0.1:5174",
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
        if self.hierarchical_leaf_candidate_limit < self.retrieval_top_k:
            raise ValueError(
                "hierarchical_leaf_candidate_limit must be >= retrieval_top_k"
            )
        return self

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    @property
    def resolved_router_llm_model(self) -> str:
        return self.router_llm_model or self.llm_model

    @property
    def resolved_answer_llm_model(self) -> str:
        return self.answer_llm_model or self.llm_model

    @property
    def llm_transport_configured(self) -> bool:
        return bool(self.llm_base_url and self.llm_api_key)

    @property
    def router_configured(self) -> bool:
        return self.llm_transport_configured and bool(self.resolved_router_llm_model)

    @property
    def answer_configured(self) -> bool:
        return (
            self.answer_mode == "llm"
            and self.llm_transport_configured
            and bool(self.resolved_answer_llm_model)
        )

    @property
    def web_search_configured(self) -> bool:
        return bool(
            self.web_search_enabled
            and self.web_search_base_url
            and self.web_search_api_key
        )

    def ensure_directories(self) -> None:
        for path in (
            self.data_root,
            self.raw_root,
            self.staging_root,
            self.fixture_root,
            self.hierarchical_index_root,
            self.data_root / "metadata",
        ):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
