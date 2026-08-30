import hashlib
import json
import time
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.domain.models import ModelRunRecord
from app.llm.models import ModelCompletion, ModelRequest

ModelOutput = TypeVar("ModelOutput", bound=BaseModel)


class OpenAICompatibleModelError(RuntimeError):
    """A redacted live-model transport, protocol, or validation failure."""


class OpenAICompatibleModel:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float,
        transport_retries: int = 1,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.transport_retries = transport_retries
        self.transport = transport

    async def complete(
        self, request: ModelRequest, output_type: type[ModelOutput]
    ) -> ModelCompletion[ModelOutput]:
        request_json = request.model_dump(mode="json")
        digest = hashlib.sha256(
            json.dumps(request_json, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        payload = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Return only the requested JSON schema. Cite supplied evidence IDs for "
                        "every finding. Abstain rather than invent evidence or regulatory rules."
                    ),
                },
                {"role": "user", "content": json.dumps(request_json, sort_keys=True)},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": output_type.__name__,
                    "strict": True,
                    "schema": output_type.model_json_schema(),
                },
            },
        }
        started = time.perf_counter()
        response: httpx.Response | None = None
        async with httpx.AsyncClient(
            timeout=self.timeout_seconds, transport=self.transport
        ) as client:
            for attempt in range(self.transport_retries + 1):
                try:
                    response = await client.post(
                        f"{self.base_url}/chat/completions",
                        headers={"Authorization": f"Bearer {self.api_key}"},
                        json=payload,
                    )
                    break
                except (httpx.ConnectError, httpx.TimeoutException) as error:
                    if attempt >= self.transport_retries:
                        raise OpenAICompatibleModelError(
                            f"live model transport failed: {type(error).__name__}"
                        ) from error
        if response is None:
            raise OpenAICompatibleModelError("live model returned no response")
        try:
            response.raise_for_status()
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise TypeError("message content is not a JSON string")
            result = output_type.model_validate_json(content)
        except (
            httpx.HTTPStatusError,
            KeyError,
            IndexError,
            TypeError,
            ValueError,
            ValidationError,
        ) as error:
            raise OpenAICompatibleModelError(
                f"live model response was invalid: {type(error).__name__}"
            ) from error
        usage = body.get("usage", {})
        return ModelCompletion(
            output=result,
            run=ModelRunRecord(
                mode="live",
                status="abstained" if getattr(result, "abstained", False) else "completed",
                prompt_template_version=request.prompt_template_version,
                model_name=self.model,
                request_digest=digest,
                input_tokens=usage.get("prompt_tokens"),
                output_tokens=usage.get("completion_tokens"),
                latency_ms=(time.perf_counter() - started) * 1000,
            ),
        )
