import os
from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.domain.enums import LlmMode

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPOSITORY_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    reg_bridge_env: str = "development"
    reg_bridge_host: str = "127.0.0.1"
    reg_bridge_port: int = Field(default=8000, ge=1, le=65535)
    reg_bridge_database_path: Path = REPOSITORY_ROOT / "results" / "regbridge.sqlite3"
    reg_bridge_database_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("REG_BRIDGE_DATABASE_URL", "DATABASE_URL"),
    )
    reg_bridge_cors_origins: list[str] = [
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ]
    reg_bridge_cors_origin_regex: str | None = None

    llm_mode: LlmMode = LlmMode.FIXTURE
    llm_base_url: str | None = None
    llm_api_key: SecretStr | None = None
    llm_model: str | None = None
    llm_timeout_seconds: float = Field(default=60.0, gt=0, le=300)
    product_inventory_capacity: int = Field(default=12, ge=1, le=100)
    product_inventory_ttl_seconds: int = Field(default=3600, ge=60, le=86400)
    product_job_capacity: int = Field(default=24, ge=1, le=200)
    product_job_ttl_seconds: int = Field(default=7200, ge=60, le=86400)
    product_reasoning_effort: str = "medium"
    product_max_output_tokens: int = Field(default=4000, ge=800, le=25000)
    product_final_answer_token_limit: int = Field(default=800, ge=100, le=4000)
    product_input_character_limit: int = Field(default=16000, ge=4000, le=100000)
    qwen_base_url: str | None = None
    qwen_api_key: SecretStr | None = None
    qwen_model: str | None = None
    qwen_timeout_seconds: float = Field(default=60.0, gt=0, le=300)
    qwen_structured_output_validated: bool = False

    @field_validator("llm_mode", mode="before")
    @classmethod
    def normalize_legacy_live_mode(cls, value: object) -> object:
        # Earlier local configurations used `llm` for the live adapter. Keep those private
        # configurations usable while exposing only the canonical enum through the API.
        return "live" if value == "llm" else value

    @field_validator("reg_bridge_database_url", mode="before")
    @classmethod
    def empty_database_url_to_none(cls, value: object) -> object:
        if value == "":
            return None
        return value

    @model_validator(mode="after")
    def apply_vercel_cors_preview_regex(self) -> "Settings":
        if self.reg_bridge_cors_origin_regex is None and os.environ.get("VERCEL"):
            self.reg_bridge_cors_origin_regex = r"https://.*\.vercel\.app"
        return self

    @model_validator(mode="after")
    def validate_live_model_configuration(self) -> "Settings":
        if self.llm_mode == LlmMode.LIVE:
            missing = [
                name
                for name, value in (
                    ("LLM_BASE_URL", self.llm_base_url),
                    ("LLM_API_KEY", self.llm_api_key),
                    ("LLM_MODEL", self.llm_model),
                )
                if value is None or value == ""
            ]
            if missing:
                raise ValueError(f"live model mode requires: {', '.join(missing)}")
        return self

    @property
    def uses_postgres(self) -> bool:
        return bool(self.reg_bridge_database_url)

    @property
    def resolved_database_url(self) -> str:
        if self.reg_bridge_database_url is None:
            raise RuntimeError("Postgres URL is not configured")
        return self.reg_bridge_database_url


@lru_cache
def get_settings() -> Settings:
    return Settings()
