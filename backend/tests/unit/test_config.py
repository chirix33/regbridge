import pytest
from app.config import Settings
from app.domain.enums import LlmMode
from pydantic import SecretStr, ValidationError


def test_default_configuration_is_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("LLM_MODE", "LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL"):
        monkeypatch.delenv(key, raising=False)

    settings = Settings()

    assert settings.llm_mode == LlmMode.FIXTURE
    assert settings.llm_api_key is None


def test_live_configuration_requires_all_provider_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for key in ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL"):
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(ValidationError, match="LLM_BASE_URL, LLM_API_KEY, LLM_MODEL"):
        Settings(llm_mode=LlmMode.LIVE)


def test_secret_is_not_exposed_by_representation() -> None:
    settings = Settings(
        llm_mode=LlmMode.LIVE,
        llm_base_url="https://models.example.test/v1",
        llm_api_key=SecretStr("private-key"),
        llm_model="test-model",
    )

    assert "private-key" not in repr(settings)
