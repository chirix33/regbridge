from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from typing import TypeVar, cast

import tiktoken
from pydantic import BaseModel

from app.config import Settings
from app.domain.enums import LlmMode, Severity
from app.domain.models import DossierEvidence, ModelRunRecord
from app.llm.models import ModelCompletion, ModelRequest, SemanticFinding, SemanticRiskOutput
from app.llm.protocol import StructuredModel
from app.llm.responses import ResponsesStructuredModel
from app.product.models import ModelAvailability, ModelCatalog, ModelProfile

OutputT = TypeVar("OutputT", bound=BaseModel)


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _token_counter(model_name: str) -> Callable[[str], int]:
    try:
        encoding = tiktoken.encoding_for_model(model_name)
    except KeyError:
        encoding = tiktoken.get_encoding("o200k_base")
    return lambda text: len(encoding.encode(text))


class ProductFixtureModel:
    """Internal network-free semantic component driven only by supplied dossier evidence."""

    async def complete(
        self, request: ModelRequest, output_type: type[OutputT]
    ) -> ModelCompletion[OutputT]:
        started = time.perf_counter()
        applicant = str(request.context.get("parsed_applicant_name") or "").casefold()
        findings: list[SemanticFinding] = []
        for item in request.evidence:
            if not isinstance(item, DossierEvidence) or item.kind != "text":
                continue
            text = item.text.casefold()
            if "responsible applicant" in text and applicant and applicant not in text:
                findings.append(
                    SemanticFinding(
                        id=f"finding-{item.artifact_id}-applicant",
                        basis="observation",
                        summary=(
                            "The document's responsible-applicant wording differs from parsed "
                            "regional metadata."
                        ),
                        severity=Severity.HIGH,
                        evidence_ids=(item.id,),
                        category="applicant_name_mismatch",
                    )
                )
        output = SemanticRiskOutput(
            fixture_version="1.0.0",
            abstained=False,
            abstain_reason=None,
            findings=tuple(findings),
            confidence=0.95 if findings else 0.9,
        )
        digest = hashlib.sha256(request.model_dump_json().encode()).hexdigest()
        run = ModelRunRecord(
            mode="fixture",
            status="completed",
            prompt_template_version=request.prompt_template_version,
            model_name="internal-package-derived-fixture",
            request_digest=digest,
            input_tokens=(len(request.model_dump_json()) + 3) // 4,
            output_tokens=(len(output.model_dump_json()) + 3) // 4,
            latency_ms=(time.perf_counter() - started) * 1000,
        )
        return ModelCompletion(output=output_type.model_validate(output.model_dump()), run=run)


class ModelProfileRegistry:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _gpt_profile(self) -> ModelProfile:
        live_valid = bool(
            self.settings.llm_base_url and self.settings.llm_api_key and self.settings.llm_model
        )
        fixture_valid = self.settings.llm_mode == LlmMode.FIXTURE
        availability: ModelAvailability = (
            "available" if live_valid or fixture_valid else "misconfigured"
        )
        configured = self.settings.llm_model or "gpt-5.5"
        configuration = {
            "profile": "gpt-5.5",
            "adapter": "responses",
            "model": configured,
            "reasoning_effort": self.settings.product_reasoning_effort,
            "max_output_tokens": self.settings.product_max_output_tokens,
            "final_answer_token_limit": self.settings.product_final_answer_token_limit,
            "input_character_limit": self.settings.product_input_character_limit,
            "temperature_handling": "unsupported_by_endpoint_parameter",
            "execution_mode": self.settings.llm_mode.value,
        }
        return ModelProfile(
            model_id="gpt-5.5",
            display_name="GPT-5.5",
            availability=availability,
            disabled_reason=None
            if availability == "available"
            else "Server-side GPT-5.5 configuration is incomplete.",
            adapter_type="responses",
            configured_model_name=configured,
            structured_output_capability="validated",
            reasoning_capability=True,
            configuration_digest=_digest(configuration),
            network_required=self.settings.llm_mode == LlmMode.LIVE,
        )

    def _qwen_profile(self) -> ModelProfile:
        configuration = {
            "profile": "qwen3.6-local",
            "adapter": "chat_completions",
            "configured_model": self.settings.qwen_model,
            "structured_output_validated": self.settings.qwen_structured_output_validated,
            "temperature_capability": "optional",
        }
        return ModelProfile(
            model_id="qwen3.6-local",
            display_name="Qwen 3.6 local — coming soon",
            subtitle="27B Dense / 35B-A3B",
            availability="coming_soon",
            disabled_reason=(
                "Endpoint and structured-output behavior have not been separately validated."
            ),
            adapter_type="chat_completions",
            configured_model_name=self.settings.qwen_model,
            structured_output_capability="unvalidated",
            reasoning_capability=True,
            configuration_digest=_digest(configuration),
            network_required=True,
        )

    def catalog(self) -> ModelCatalog:
        return ModelCatalog(
            default_model_id="gpt-5.5", models=(self._gpt_profile(), self._qwen_profile())
        )

    def require(self, model_id: str) -> ModelProfile:
        profiles = {profile.model_id: profile for profile in self.catalog().models}
        profile = profiles.get(model_id)
        if profile is None:
            raise KeyError("unknown model profile")
        if profile.availability != "available":
            raise ValueError(profile.disabled_reason or "model profile is unavailable")
        return profile

    def create(self, model_id: str) -> StructuredModel:
        profile = self.require(model_id)
        if profile.model_id != "gpt-5.5":
            raise ValueError("model profile adapter has not been activated")
        if self.settings.llm_mode == LlmMode.FIXTURE:
            return ProductFixtureModel()
        return ResponsesStructuredModel(
            base_url=cast(str, self.settings.llm_base_url),
            api_key=cast(
                str,
                self.settings.llm_api_key.get_secret_value() if self.settings.llm_api_key else None,
            ),
            model=cast(str, self.settings.llm_model),
            timeout_seconds=self.settings.llm_timeout_seconds,
            reasoning_effort=self.settings.product_reasoning_effort,
            max_output_tokens=self.settings.product_max_output_tokens,
            count_final_tokens=_token_counter(profile.configured_model_name or "gpt-5.5"),
            final_answer_token_limit=self.settings.product_final_answer_token_limit,
            input_character_limit=self.settings.product_input_character_limit,
        )
