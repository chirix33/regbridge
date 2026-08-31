import json

import httpx
import pytest
from app.llm.models import ModelRequest, SemanticRiskOutput
from app.llm.openai_compatible import OpenAICompatibleModel, OpenAICompatibleModelError


def request() -> ModelRequest:
    return ModelRequest(
        fixture_lookup_key="live-test",
        task="Inspect only supplied evidence.",
        context={"target": "eCTD-4.0"},
        evidence=(),
        prompt_template_version="1.0.0",
    )


@pytest.mark.asyncio
async def test_openai_compatible_adapter_uses_deterministic_structured_request() -> None:
    observed: dict[str, object] = {}

    async def handler(http_request: httpx.Request) -> httpx.Response:
        observed.update(json.loads(http_request.content))
        output = SemanticRiskOutput(
            fixture_version="1.0.0",
            abstained=False,
            abstain_reason=None,
            findings=(),
            confidence=1,
        )
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": output.model_dump_json()}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 8},
            },
        )

    model = OpenAICompatibleModel(
        base_url="https://model.example/v1",
        api_key="secret-not-recorded",
        model="test-model",
        timeout_seconds=2,
        transport=httpx.MockTransport(handler),
    )
    completion = await model.complete(request(), SemanticRiskOutput)
    assert completion.output.confidence == 1
    assert completion.run.input_tokens == 12
    assert completion.run.output_tokens == 8
    assert observed["temperature"] == 0
    assert observed["response_format"]["type"] == "json_schema"  # type: ignore[index]
    user_payload = json.loads(observed["messages"][1]["content"])  # type: ignore[index]
    assert "fixture_lookup_key" not in user_payload
    assert "live-test" not in json.dumps(user_payload)


@pytest.mark.asyncio
async def test_openai_compatible_adapter_rejects_malformed_json_without_reprompting() -> None:
    calls = 0

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"choices": [{"message": {"content": "not-json"}}]})

    model = OpenAICompatibleModel(
        base_url="https://model.example/v1",
        api_key="secret",
        model="test-model",
        timeout_seconds=2,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(OpenAICompatibleModelError, match="response was invalid"):
        await model.complete(request(), SemanticRiskOutput)
    assert calls == 1
