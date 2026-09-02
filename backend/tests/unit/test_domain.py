from datetime import date

import pytest
from app.domain.enums import (
    ApplicationType,
    Authority,
    Center,
    Decision,
    ReuseOperation,
    ScenarioMode,
    StandardVersion,
)
from app.domain.models import AnalysisResult, TargetContext
from pydantic import ValidationError


def valid_analysis_payload() -> dict[str, object]:
    return {
        "id": "analysis-001",
        "source_artifact": {
            "id": "artifact-001",
            "title": "Synthetic legacy quality document",
            "source_standard": "eCTD-3.2.2",
            "source_leaf_id": "leaf-001",
            "source_heading": "3.2.S.1",
            "source_locator": "index.xml / ectd:leaf[1]",
            "content_type": "application/pdf",
            "file_sha256": "a" * 64,
        },
        "target_context": {
            "authority": "FDA",
            "center": "CDER",
            "application_type": "NDA",
            "source_standard": "eCTD-3.2.2",
            "target_standard": "eCTD-4.0",
            "analysis_date": "2026-08-29",
            "reuse_operation": "reference-existing-content",
            "standards_snapshot_id": "fda-cder-demo-v1",
            "scenario_mode": "prospective_forward_compatibility",
        },
        "operational_status": "not_operational",
        "scenario_disclosure": "Controlled prospective research scenario.",
        "expert_validated": False,
        "decision": "REUSE_AS_LEGACY_REFERENCE",
        "severity": "informational",
        "triggered_rule_ids": [],
        "findings": [],
        "evidence": [],
        "rationale": "No material finding in this synthetic contract example.",
        "repair": {
            "type": "NO_MATERIAL_REPAIR",
            "description": "No repair is supported or required.",
            "evidence_ids": [],
        },
        "confidence": 1.0,
        "unresolved_uncertainty": [],
        "human_approval_required": False,
        "trace": [
            {
                "sequence": 1,
                "kind": "synthesis",
                "component": "decision-synthesizer",
                "summary": "Validated the completed analysis contract.",
                "evidence_ids": [],
                "occurred_at": "2026-08-29T00:00:00Z",
            }
        ],
    }


def test_decision_vocabulary_is_closed() -> None:
    assert {decision.value for decision in Decision} == {
        "REUSE_AS_LEGACY_REFERENCE",
        "REUSE_WITH_NEW_CONTEXT",
        "REUSE_AFTER_METADATA_REPAIR",
        "BREAK_LIFECYCLE_AND_RESUBMIT",
        "DO_NOT_REUSE",
        "HUMAN_REGULATORY_REVIEW",
    }


def test_target_context_rejects_same_version_transition() -> None:
    with pytest.raises(ValidationError, match="must differ"):
        TargetContext(
            authority=Authority.FDA,
            center=Center.CDER,
            application_type=ApplicationType.NDA,
            source_standard=StandardVersion.ECTD_4_0,
            target_standard=StandardVersion.ECTD_4_0,
            analysis_date=date(2026, 8, 29),
            reuse_operation=ReuseOperation.REFERENCE_EXISTING_CONTENT,
            standards_snapshot_id="fda-cder-demo-v1",
            scenario_mode=ScenarioMode.PROSPECTIVE_FORWARD_COMPATIBILITY,
        )


def test_target_context_rejects_unknown_application_type() -> None:
    with pytest.raises(ValidationError):
        TargetContext.model_validate(
            {
                "authority": "FDA",
                "center": "CDER",
                "application_type": "BLA",
                "source_standard": "eCTD-3.2.2",
                "target_standard": "eCTD-4.0",
                "analysis_date": "2026-08-29",
                "reuse_operation": "reference-existing-content",
                "standards_snapshot_id": "fda-cder-demo-v1",
                "scenario_mode": "prospective_forward_compatibility",
            }
        )


def test_analysis_contract_captures_source_context_and_trace() -> None:
    analysis = AnalysisResult.model_validate(valid_analysis_payload())

    assert analysis.source_artifact.source_leaf_id == "leaf-001"
    assert analysis.target_context.center == Center.CDER
    assert analysis.trace[0].kind.value == "synthesis"


def test_analysis_contract_rejects_unsupported_evidence_citation() -> None:
    payload = valid_analysis_payload()
    payload["triggered_rule_ids"] = ["FDA-DEMO-001"]
    payload["findings"] = [
        {
            "id": "finding-001",
            "rule_id": "FDA-DEMO-001",
            "severity": "high",
            "rationale": "Synthetic unsupported finding.",
            "evidence_ids": ["missing-evidence"],
            "source": "deterministic",
        }
    ]

    with pytest.raises(ValidationError, match="unknown evidence identifiers"):
        AnalysisResult.model_validate(payload)
