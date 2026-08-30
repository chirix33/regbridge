from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.domain.enums import LlmMode

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPOSITORY_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    reg_bridge_env: str = "development"
    reg_bridge_host: str = "127.0.0.1"
    reg_bridge_port: int = Field(default=8000, ge=1, le=65535)
    reg_bridge_cors_origins: list[str] = [
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ]

    llm_mode: LlmMode = LlmMode.FIXTURE
    llm_base_url: str | None = None
    llm_api_key: SecretStr | None = None
    llm_model: str | None = None
    llm_timeout_seconds: float = Field(default=60.0, gt=0, le=300)

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
