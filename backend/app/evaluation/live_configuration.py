"""Content-addressed live configuration; Phase 2 remains explicitly gated and inactive."""

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar

from app.analyzer.prompts import SEMANTIC_INSPECTION_TASK
from app.baselines.prompts import DIRECT_DECISION_TASK
from app.config import REPOSITORY_ROOT
from app.domain.vocabulary import action_vocabulary_disclosure, output_vocabulary
from app.evaluation.models import DirectDecisionOutput
from app.graph.builder import GRAPH_CONTRACT_CHANGE
from app.graph.models import GRAPH_SCHEMA_VERSION
from app.llm.models import SemanticRiskOutput
from app.llm.responses import SYSTEM_INSTRUCTIONS, TEMPERATURE_HANDLING, _strict_json_schema

ResultT = TypeVar("ResultT")


def content_digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def configuration_material(*, max_output_tokens: int = 25_000) -> dict[str, Any]:
    def source(path: str) -> str:
        return hashlib.sha256((REPOSITORY_ROOT / path).read_bytes()).hexdigest()

    return {
        "model": "gpt-5.5",
        "reasoning_effort": "medium",
        "max_output_tokens": max_output_tokens,
        "final_structured_answer_token_limit": 800,
        "input_character_limit": 16_000,
        "temperature_handling": TEMPERATURE_HANDLING,
        "retry_limit": 2,
        "retry_policy": (
            "transport_and_provider_api_failures_only; schema, citation, graph, persistence, "
            "and synthesis failures are non-retryable and halt the phase"
        ),
        "direct_prompt": DIRECT_DECISION_TASK,
        "semantic_prompt": SEMANTIC_INSPECTION_TASK,
        "system_instructions": SYSTEM_INSTRUCTIONS,
        "direct_schema": _strict_json_schema(DirectDecisionOutput.model_json_schema()),
        "semantic_schema": _strict_json_schema(SemanticRiskOutput.model_json_schema()),
        "direct_validation_schema": DirectDecisionOutput.model_json_schema(),
        "semantic_validation_schema": SemanticRiskOutput.model_json_schema(),
        "serializer": source("backend/app/baselines/direct.py"),
        "semantic_serializer": source("backend/app/llm/serialization.py"),
        "responses_adapter": source("backend/app/llm/responses.py"),
        "direct_prompt_source": source("backend/app/baselines/prompts.py"),
        "semantic_prompt_source": source("backend/app/analyzer/prompts.py"),
        "output_validators": source("backend/app/evaluation/models.py"),
        "semantic_validators": source("backend/app/llm/models.py"),
        "request_aliasing": source("backend/app/llm/serialization.py"),
        "shared_output_vocabulary": output_vocabulary(),
        "action_vocabulary_disclosure": action_vocabulary_disclosure(),
        "action_vocabulary_source": source("backend/app/domain/vocabulary.py"),
        "b2_scoring_contract_source": source("backend/app/evaluation/phase1_b2.py"),
        "scorer": source("backend/app/evaluation/metrics.py"),
        "decision_scoring_policy": "option-a-exact-match-three-represented-reference-classes",
        "graph_contract": {
            "schema_version": GRAPH_SCHEMA_VERSION,
            "change": GRAPH_CONTRACT_CHANGE,
            "occurrence_identity": (
                "raw value, owner, locator, and provenance resolve server-side after "
                "request-local evidence de-aliasing"
            ),
            "citation_contract": (
                "MODEL_FINDING-CITES-DOSSIER_EVIDENCE; MODEL_FINDING-ABOUT-KEYWORD; "
                "DOSSIER_EVIDENCE-OBSERVES-KEYWORD; direct CITES-KEYWORD invalid"
            ),
            "keyword_agreement": (
                "ABOUT must equal the keyword OBSERVED by cited metadata occurrence evidence; "
                "no cross-concept relationship is currently encoded"
            ),
            "rationale": (
                "The B003 manufacturer-metadata citation was correct; graph v1 could not "
                "represent findings about metadata and could fail the Case B family."
            ),
        },
        "graph_enums_source": source("backend/app/domain/enums.py"),
        "graph_models_source": source("backend/app/graph/models.py"),
        "graph_builder_source": source("backend/app/graph/builder.py"),
        "analysis_pipeline_source": source("backend/app/analyzer/service.py"),
        "analysis_repository_source": source("backend/app/analyzer/repository.py"),
        "live_retry_and_summary_source": source("backend/app/evaluation/live_phase1.py"),
        "tokenizer": "tiktoken==0.12.0:o200k_base",
        "input_counting_policy": (
            "Unicode characters: instructions + serialized input + JSON schema"
        ),
    }


def require_development_approval() -> None:
    """Approval is an external author event; neither exporter nor runner can create it."""
    path = REPOSITORY_ROOT / "data/evaluation/phase1-v3-approval.json"
    if not path.is_file():
        raise ValueError(
            "Phase 1 rerun blocked: graph-contract-v2 development configuration awaits its "
            "recorded author-01 approval"
        )
    approval = json.loads(path.read_text(encoding="utf-8"))
    if (
        approval.get("author_id") != "author-01"
        or approval.get("configuration_sha256") != content_digest(configuration_material())
        or approval.get("action_vocabulary_sha256") != content_digest(output_vocabulary())
    ):
        raise ValueError("Phase 1 rerun blocked: author approval or configuration digest mismatch")


def template_digests(material: dict[str, Any]) -> dict[str, str]:
    return {
        key: content_digest(material[key]) for key in (
            "direct_prompt", "semantic_prompt", "system_instructions", "direct_schema",
            "semantic_schema", "serializer", "semantic_serializer",
            "shared_output_vocabulary",
        )
    }


@dataclass(frozen=True)
class HeldOutApprovalGate:
    """No benchmark loading here. Guard every future loader/repetition/dispatch callback."""

    author_id: str
    frozen_prompt_digest: str
    frozen_configuration_digest: str
    max_output_tokens: int

    def guard(self) -> None:
        if self.author_id != "author-01":
            raise ValueError("Held-out execution requires explicit author-01 approval")
        material = configuration_material(max_output_tokens=self.max_output_tokens)
        if content_digest(material) != self.frozen_configuration_digest:
            raise ValueError("Held-out run aborted: frozen configuration digest mismatch")
        if content_digest(template_digests(material)) != self.frozen_prompt_digest:
            raise ValueError("Held-out run aborted: frozen prompt digest mismatch")

    def before_loading(self, loader: Callable[[], ResultT]) -> ResultT:
        self.guard()
        return loader()

    def before_repetition(self, run: Callable[[], ResultT]) -> ResultT:
        self.guard()
        return run()

    def before_dispatch(self, dispatch: Callable[[], ResultT]) -> ResultT:
        self.guard()
        return dispatch()
