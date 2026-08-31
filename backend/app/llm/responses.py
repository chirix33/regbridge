import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.domain.models import ModelRunRecord
from app.llm.models import ModelCompletion, ModelRequest
from app.llm.serialization import UUID_PATTERN, serialize_semantic_request

ModelOutput = TypeVar("ModelOutput", bound=BaseModel)
SYSTEM_INSTRUCTIONS = (
    "Return only the requested JSON schema. Cite supplied evidence IDs for every finding. "
    "Abstain rather than invent evidence or regulatory rules."
)


class LiveModelInvalidOutput(RuntimeError):
    """A redacted live-model failure that must not be mapped into a decision class."""


TEMPERATURE_HANDLING = "unsupported_by_endpoint_parameter"


@dataclass(frozen=True)
class ResponsesAttempt:
    attempt_index: int
    request_digest: str
    status: str
    cause: str | None
    http_status: int | None
    error_type: str | None
    error_code: str | None
    error_param: str | None
    model_requested: str
    model_reported: str | None
    temperature_handling: str
    reasoning_effort: str
    max_output_tokens: int
    input_tokens: int | None
    cached_input_tokens: int | None
    final_answer_tokens: int | None
    reasoning_tokens: int | None
    total_output_tokens: int | None
    finish_reason: str | None
    response_status: str | None
    latency_ms: float
    ceiling_hit: bool
    response_id: str | None
    final_json_text: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "attempt_index": self.attempt_index,
            "request_digest": self.request_digest,
            "status": self.status,
            "cause": self.cause,
            "http_status": self.http_status,
            "error_type": self.error_type,
            "error_code": self.error_code,
            "error_param": self.error_param,
            "model_requested": self.model_requested,
            "model_reported": self.model_reported,
            "temperature_handling": self.temperature_handling,
            "reasoning_effort": self.reasoning_effort,
            "max_output_tokens": self.max_output_tokens,
            "input_tokens": self.input_tokens,
            "cached_input_tokens": self.cached_input_tokens,
            "final_answer_tokens": self.final_answer_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "total_output_tokens": self.total_output_tokens,
            "finish_reason": self.finish_reason,
            "response_status": self.response_status,
            "latency_ms": self.latency_ms,
            "ceiling_hit": self.ceiling_hit,
            "response_id": self.response_id,
            "final_json_text": self.final_json_text,
        }


class ResponsesStructuredModel:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float,
        reasoning_effort: str = "medium",
        max_output_tokens: int = 25_000,
        count_final_tokens: Callable[[str], int],
        final_answer_token_limit: int = 800,
        input_character_limit: int = 16_000,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.reasoning_effort = reasoning_effort
        self.max_output_tokens = max_output_tokens
        self.count_final_tokens = count_final_tokens
        self.final_answer_token_limit = final_answer_token_limit
        self.input_character_limit = input_character_limit
        self.transport = transport
        self.last_attempts: tuple[ResponsesAttempt, ...] = ()

    async def complete(
        self, request: ModelRequest, output_type: type[ModelOutput]
    ) -> ModelCompletion[ModelOutput]:
        packet = serialize_semantic_request(request)
        completion = await self.complete_text(
            input_text=packet.serialized,
            output_type=output_type,
            prompt_template_version=request.prompt_template_version,
        )
        supplied_ids = set(packet.alias_to_evidence_id)
        cited_ids = {
            evidence_id for finding in getattr(completion.output, "findings", ())
            for evidence_id in finding.evidence_ids
        }
        if cited_ids - supplied_ids:
            self.last_attempts = tuple(
                replace(item, status="failed", cause="unsupported_citation")
                for item in self.last_attempts
            )
            raise LiveModelInvalidOutput("unsupported_citation")
        translated = completion.output.model_dump()
        for finding in translated.get("findings", ()):
            finding["evidence_ids"] = tuple(
                packet.alias_to_evidence_id[item] for item in finding["evidence_ids"]
            )
        return ModelCompletion(output=output_type.model_validate(translated), run=completion.run)

    async def complete_text(
        self,
        *,
        input_text: str,
        output_type: type[ModelOutput],
        prompt_template_version: str,
    ) -> ModelCompletion[ModelOutput]:
        self.last_attempts = ()
        digest = hashlib.sha256(input_text.encode("utf-8")).hexdigest()
        schema = _strict_json_schema(output_type.model_json_schema())
        model_facing_characters = len(
            SYSTEM_INSTRUCTIONS + input_text + json.dumps(schema, sort_keys=True)
        )
        payload = {
            "model": self.model,
            "instructions": SYSTEM_INSTRUCTIONS,
            "input": input_text,
            "reasoning": {"effort": self.reasoning_effort},
            "max_output_tokens": self.max_output_tokens,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": output_type.__name__,
                    "strict": True,
                    "schema": schema,
                }
            },
        }
        started = time.perf_counter()
        response: httpx.Response | None = None
        final_tokens: int | None = None
        text: str | None = None
        failure_class = "api_failure"
        try:
            if model_facing_characters > self.input_character_limit:
                failure_class = "input_character_limit"
                raise LiveModelInvalidOutput("model-facing input character limit exceeded")
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds, transport=self.transport
            ) as client:
                response = await client.post(
                    f"{self.base_url}/responses",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=payload,
                )
            response.raise_for_status()
            failure_class = "invalid_response_envelope"
            body = response.json()
            body["_http_status"] = response.status_code
            failure_class = "refusal"
            if any(
                content.get("type") == "refusal"
                for item in body.get("output", []) if isinstance(item, dict)
                for content in item.get("content", []) if isinstance(content, dict)
            ):
                raise LiveModelInvalidOutput("provider refusal")
            failure_class = "incomplete_response"
            if body.get("status") != "completed":
                raise LiveModelInvalidOutput("response did not complete")
            failure_class = "missing_final_json"
            text = _response_text(body)
            if not text:
                raise LiveModelInvalidOutput("response contained no final JSON text")
            final_tokens = self.count_final_tokens(text)
            failure_class = "final_answer_token_limit"
            if final_tokens > self.final_answer_token_limit:
                raise LiveModelInvalidOutput("final JSON text exceeded 800 tokens")
            failure_class = "schema_validation"
            output = output_type.model_validate_json(text)
            failure_class = "unsupported_identifier"
            if UUID_PATTERN.search(text):
                raise LiveModelInvalidOutput("model output contains an unsupported UUID")
            attempt = _attempt_from_body(
                attempt_index=1,
                request_digest=digest,
                body=body,
                model_requested=self.model,
                reasoning_effort=self.reasoning_effort,
                max_output_tokens=self.max_output_tokens,
                final_answer_tokens=final_tokens,
                latency_ms=(time.perf_counter() - started) * 1000,
                status="completed",
                cause=None,
                final_json_text=text,
            )
            self.last_attempts = (attempt,)
            return ModelCompletion(
                output=output,
                run=ModelRunRecord(
                    mode="live",
                    status="abstained" if getattr(output, "abstained", False) else "completed",
                    prompt_template_version=prompt_template_version,
                    model_name=attempt.model_reported or self.model,
                    request_digest=digest,
                    input_tokens=attempt.input_tokens,
                    output_tokens=attempt.total_output_tokens,
                    latency_ms=attempt.latency_ms,
                ),
            )
        except (
            httpx.HTTPError,
            KeyError,
            IndexError,
            TypeError,
            ValueError,
            ValidationError,
            LiveModelInvalidOutput,
        ) as error:
            body = _safe_json(response)
            if response is not None:
                body["_http_status"] = response.status_code
            attempt = _attempt_from_body(
                attempt_index=1,
                request_digest=digest,
                body=body,
                model_requested=self.model,
                reasoning_effort=self.reasoning_effort,
                max_output_tokens=self.max_output_tokens,
                final_answer_tokens=final_tokens,
                latency_ms=(time.perf_counter() - started) * 1000,
                status="failed",
                cause=failure_class,
                final_json_text=text,
            )
            self.last_attempts = (attempt,)
            message = f"live response invalid: {failure_class}"
            raise LiveModelInvalidOutput(message) from error


def _safe_json(response: httpx.Response | None) -> dict[str, Any]:
    if response is None:
        return {}
    try:
        body = response.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def _response_text(body: dict[str, Any]) -> str:
    if isinstance(body.get("output_text"), str):
        return str(body["output_text"])
    texts: list[str] = []
    for item in body.get("output", []):
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []):
            if isinstance(content, dict) and isinstance(content.get("text"), str):
                texts.append(str(content["text"]))
    return "".join(texts)


def _strict_json_schema(schema: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(schema)

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            node.pop("default", None)
            properties = node.get("properties")
            if isinstance(properties, dict):
                node["required"] = sorted(properties)
                node.setdefault("additionalProperties", False)
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for item in node:
                visit(item)

    visit(normalized)
    return normalized


def _usage_value(body: dict[str, Any], *path: str) -> int | None:
    value: Any = body
    for key in path:
        if not isinstance(value, dict) or key not in value:
            return None
        value = value[key]
    return value if isinstance(value, int) else None


def _attempt_from_body(
    *,
    attempt_index: int,
    request_digest: str,
    body: dict[str, Any],
    model_requested: str,
    reasoning_effort: str,
    max_output_tokens: int,
    final_answer_tokens: int | None,
    latency_ms: float,
    status: str,
    cause: str | None,
    final_json_text: str | None = None,
) -> ResponsesAttempt:
    raw_usage = body.get("usage")
    usage: dict[str, Any] = raw_usage if isinstance(raw_usage, dict) else {}
    raw_output_details = usage.get("output_tokens_details")
    details: dict[str, Any] = raw_output_details if isinstance(raw_output_details, dict) else {}
    raw_input_details = usage.get("input_tokens_details")
    input_details: dict[str, Any] = (
        raw_input_details if isinstance(raw_input_details, dict) else {}
    )
    raw_incomplete = body.get("incomplete_details")
    incomplete = raw_incomplete if isinstance(raw_incomplete, dict) else {}
    finish_reason = incomplete.get("reason") if isinstance(incomplete.get("reason"), str) else None
    response_status = body.get("status") if isinstance(body.get("status"), str) else None
    output_tokens = _usage_value(body, "usage", "output_tokens")
    raw_error = body.get("error")
    error: dict[str, Any] = raw_error if isinstance(raw_error, dict) else {}
    return ResponsesAttempt(
        attempt_index=attempt_index,
        request_digest=request_digest,
        status=status,
        cause=cause,
        http_status=body.get("_http_status") if isinstance(body.get("_http_status"), int) else None,
        error_type=error.get("type") if isinstance(error.get("type"), str) else None,
        error_code=error.get("code") if isinstance(error.get("code"), str) else None,
        error_param=error.get("param") if isinstance(error.get("param"), str) else None,
        model_requested=model_requested,
        model_reported=body.get("model") if isinstance(body.get("model"), str) else None,
        temperature_handling=TEMPERATURE_HANDLING,
        reasoning_effort=reasoning_effort,
        max_output_tokens=max_output_tokens,
        input_tokens=_usage_value(body, "usage", "input_tokens"),
        cached_input_tokens=input_details.get("cached_tokens")
        if isinstance(input_details.get("cached_tokens"), int)
        else None,
        final_answer_tokens=final_answer_tokens,
        reasoning_tokens=details.get("reasoning_tokens")
        if isinstance(details.get("reasoning_tokens"), int)
        else None,
        total_output_tokens=output_tokens,
        finish_reason=finish_reason,
        response_status=response_status,
        latency_ms=latency_ms,
        ceiling_hit=response_status == "incomplete" and finish_reason == "max_output_tokens",
        response_id=body.get("id") if isinstance(body.get("id"), str) else None,
        final_json_text=final_json_text,
    )
