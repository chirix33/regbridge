from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import date
from typing import Any, TypeVar, cast

from pydantic import BaseModel

from app.analyzer.service import AnalysisService
from app.config import REPOSITORY_ROOT, Settings
from app.domain.enums import (
    ApplicationType,
    Authority,
    Center,
    LlmMode,
    ManufacturerPartitioning,
    MetadataMigrationIntent,
    ReuseOperation,
    ScenarioMode,
    StandardVersion,
)
from app.domain.models import MetadataPlan, ModelRunRecord, TargetContext
from app.graph.models import PRODUCT_GRAPH_SCHEMA_VERSION
from app.llm.models import ModelCompletion, ModelRequest, SemanticRiskOutput
from app.parsers.public322 import parse_public_profile_zip
from app.product.models_registry import ModelProfileRegistry, ProductFixtureModel
from app.product.services import CaptureRepository, _execution_record, canonical_digest
from app.rules.registry import MetadataRuleRegistry, RuleRegistry
from app.standards.operational import OperationalStatusRegistry

OutputT = TypeVar("OutputT", bound=BaseModel)
PACKAGE = (
    REPOSITORY_ROOT
    / "data"
    / "demo-dossiers"
    / "m4-2"
    / "regbridge-m4-2-public-standards.zip"
)
PROTECTED_MANIFEST = (
    REPOSITORY_ROOT / "data" / "product" / "m4-2-2" / "protected-artifacts.json"
)
DIAGNOSTIC_RECORD = (
    REPOSITORY_ROOT / "data" / "product" / "m4-2-2" / "diagnostic-adjudication.json"
)


def _tree_digest(relative: str) -> tuple[int, str]:
    root = REPOSITORY_ROOT / relative
    digest = hashlib.sha256()
    files = sorted(path for path in root.rglob("*") if path.is_file())
    for path in files:
        digest.update(path.relative_to(REPOSITORY_ROOT).as_posix().encode())
        digest.update(path.read_bytes())
    return len(files), digest.hexdigest()


def verify_protected() -> dict[str, dict[str, object]]:
    expected = json.loads(PROTECTED_MANIFEST.read_text(encoding="utf-8"))
    result: dict[str, dict[str, object]] = {}
    for relative, record in expected["trees"].items():
        count, digest = _tree_digest(relative)
        if count != record["file_count"] or digest != record["sha256"]:
            raise RuntimeError(f"M4.2.2 protected artifact tree changed: {relative}")
        result[relative] = {
            "file_count": count,
            "pre_sha256": digest,
            "post_sha256": digest,
        }
    for relative, expected_digest in expected["files"].items():
        digest = hashlib.sha256((REPOSITORY_ROOT / relative).read_bytes()).hexdigest()
        if digest != expected_digest:
            raise RuntimeError(f"M4.2.2 protected artifact file changed: {relative}")
        result[relative] = {
            "file_count": 1,
            "pre_sha256": digest,
            "post_sha256": digest,
        }
    return result


def _target() -> TargetContext:
    return TargetContext(
        authority=Authority.FDA,
        center=Center.CDER,
        application_type=ApplicationType.NDA,
        source_standard=StandardVersion.ECTD_3_2_2,
        target_standard=StandardVersion.ECTD_4_0,
        analysis_date=date(2026, 9, 4),
        reuse_operation=ReuseOperation.REFERENCE_EXISTING_CONTENT,
        standards_snapshot_id="fda-cder-demo-v1",
        scenario_mode=ScenarioMode.PROSPECTIVE_FORWARD_COMPATIBILITY,
        metadata_plan=MetadataPlan(
            intent=MetadataMigrationIntent.PRESERVE_EXISTING_LIFECYCLE,
            manufacturer_partitioning=ManufacturerPartitioning.UNKNOWN,
        ),
    )


class VerificationAbstentionModel:
    last_attempts: tuple[object, ...] = ()

    async def complete(
        self, request: ModelRequest, output_type: type[OutputT]
    ) -> ModelCompletion[OutputT]:
        output = SemanticRiskOutput(
            fixture_version="1.0.0",
            abstained=True,
            abstain_reason="insufficient bounded evidence",
            findings=(),
            confidence=0,
        )
        return ModelCompletion(
            output=output_type.model_validate(output.model_dump()),
            run=ModelRunRecord(
                mode="fixture",
                status="abstained",
                prompt_template_version=request.prompt_template_version,
                model_name="m4.2.2-verification-abstention",
                request_digest=hashlib.sha256(request.model_dump_json().encode()).hexdigest(),
                latency_ms=0,
            ),
        )


async def _run_path(model_factory: Any) -> tuple[list[dict[str, object]], str]:
    inventory = parse_public_profile_zip(PACKAGE.read_bytes())
    settings = Settings(llm_mode=LlmMode.FIXTURE)
    profile = ModelProfileRegistry(settings).require("gpt-5.5")
    records: list[dict[str, object]] = []
    digest_records: list[dict[str, object]] = []
    for leaf in inventory.leaves:
        model = model_factory()
        capture = CaptureRepository()
        result = await AnalysisService(
            model=model,
            repository=cast(Any, capture),
            settings=settings,
        ).analyze_async(inventory, leaf.id, _target())
        if capture.neighborhood is None:
            raise RuntimeError("M4.2.2 verification graph was not persisted")
        execution = _execution_record(profile, result, model)
        records.append(
            {
                "title": result.source_artifact.title,
                "decision": result.decision.value,
                "repair": result.repair.type,
                "human_approval_required": result.human_approval_required,
                "model_status": execution.status,
                "execution_mode": execution.execution_mode,
                "actual_adapter": execution.adapter_type,
                "decision_basis": result.decision_basis,
                "limitation_count": sum(
                    node.type.value == "analysis_limitation"
                    for node in capture.neighborhood.nodes
                ),
                "model_finding_count": sum(
                    node.type.value == "model_finding" for node in capture.neighborhood.nodes
                ),
            }
        )
        digest_records.append(
            {
                "result": result.model_dump(
                    mode="json",
                    exclude={
                        "trace": {"__all__": {"occurred_at"}},
                        "model_run": {"latency_ms"},
                    },
                ),
                "graph": capture.neighborhood.model_dump(mode="json"),
                "execution": execution.model_dump(mode="json", exclude={"latency_ms"}),
            }
        )
    return records, canonical_digest(digest_records)


def _assert_outcomes(
    records: list[dict[str, object]], expected: dict[str, tuple[str, str, str]]
) -> None:
    by_title = {str(record["title"]): record for record in records}
    if set(by_title) != set(expected):
        raise RuntimeError("M4.2.2 package document set changed")
    for title, (decision, repair, status) in expected.items():
        observed = by_title[title]
        if (
            observed["decision"] != decision
            or observed["repair"] != repair
            or observed["model_status"] != status
        ):
            raise RuntimeError(f"M4.2.2 outcome mismatch: {title}")


def verify_behavior() -> dict[str, object]:
    fixture_records, fixture_digest = asyncio.run(_run_path(ProductFixtureModel))
    abstention_records, abstention_digest = asyncio.run(
        _run_path(VerificationAbstentionModel)
    )
    _assert_outcomes(
        fixture_records,
        {
            "Synthetic molecular structure": (
                "REUSE_WITH_NEW_CONTEXT",
                "CREATE_NEW_CONTEXT_GROUP_AND_SUSPEND_LEGACY_CONTENT",
                "completed",
            ),
            "Synthetic lifecycle metadata context": (
                "REUSE_AS_LEGACY_REFERENCE",
                "PRESERVE_EXACT_CONTEXT_GROUP_KEYWORDS",
                "completed",
            ),
            "Synthetic applicant responsibility statement": (
                "HUMAN_REGULATORY_REVIEW",
                "HUMAN_VERIFY_STALE_CONTENT",
                "completed",
            ),
        },
    )
    _assert_outcomes(
        abstention_records,
        {
            "Synthetic molecular structure": (
                "REUSE_WITH_NEW_CONTEXT",
                "CREATE_NEW_CONTEXT_GROUP_AND_SUSPEND_LEGACY_CONTENT",
                "abstained",
            ),
            "Synthetic lifecycle metadata context": (
                "HUMAN_REGULATORY_REVIEW",
                "COMPLETE_DOCUMENT_INSPECTION",
                "abstained",
            ),
            "Synthetic applicant responsibility statement": (
                "HUMAN_REGULATORY_REVIEW",
                "COMPLETE_DOCUMENT_INSPECTION",
                "abstained",
            ),
        },
    )
    if any(record["limitation_count"] != 1 for record in abstention_records):
        raise RuntimeError("M4.2.2 abstention path lacks an analysis limitation")
    if any(record["model_finding_count"] != 0 for record in abstention_records):
        raise RuntimeError("M4.2.2 abstention path fabricated a model finding")
    diagnostic = json.loads(DIAGNOSTIC_RECORD.read_text(encoding="utf-8"))
    if diagnostic["m4_2_2_runtime_digests"] != {
        "clean_fixture_result_sha256": fixture_digest,
        "valid_abstention_result_sha256": abstention_digest,
    }:
        raise RuntimeError("M4.2.2 diagnostic runtime digests differ from verification")
    return {
        "clean_fixture": fixture_records,
        "valid_abstention": abstention_records,
        "clean_fixture_result_sha256": fixture_digest,
        "valid_abstention_result_sha256": abstention_digest,
    }


def verify_execution_modes() -> dict[str, object]:
    fixture = ModelProfileRegistry(Settings(llm_mode=LlmMode.FIXTURE)).require("gpt-5.5")
    disabled = ModelProfileRegistry(Settings(llm_mode=LlmMode.DISABLED)).catalog().models[0]
    if fixture.actual_adapter_type != "fixture" or fixture.network_required:
        raise RuntimeError("fixture model disclosure is inconsistent")
    if disabled.availability != "disabled" or disabled.actual_adapter_type is not None:
        raise RuntimeError("disabled model profile exposes an execution adapter")
    return {
        "fixture": fixture.model_dump(mode="json"),
        "disabled": disabled.model_dump(mode="json"),
    }


def verify_governance() -> dict[str, object]:
    heading_rules = RuleRegistry().load()
    metadata_rules = MetadataRuleRegistry().load()
    if any(rule.expert_validated for rule in heading_rules) or any(
        rule.expert_validated for rule in metadata_rules
    ):
        raise RuntimeError("M4.2.2 rule unexpectedly became expert validated")
    operational = OperationalStatusRegistry().load().status.value
    if operational != "not_operational":
        raise RuntimeError("M4.2.2 operational status changed")
    return {
        "operational_status": operational,
        "expert_validated": False,
        "rule_count": len(heading_rules) + len(metadata_rules),
    }


def main() -> None:
    package_sha256 = hashlib.sha256(PACKAGE.read_bytes()).hexdigest()
    if package_sha256 != (
        "4d236d51694b1c15d37ad92b9d0074b97a15075cde86cb96c393b9f87ce3e6e4"
    ):
        raise RuntimeError("historical M4.2 package bytes changed")
    report = {
        "package_sha256": package_sha256,
        "product_graph_schema_version": PRODUCT_GRAPH_SCHEMA_VERSION,
        "diagnostic_record_sha256": hashlib.sha256(DIAGNOSTIC_RECORD.read_bytes()).hexdigest(),
        "protected_artifacts": verify_protected(),
        "governance": verify_governance(),
        "execution_modes": verify_execution_modes(),
        "behavior": verify_behavior(),
    }
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
