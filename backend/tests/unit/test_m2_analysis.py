from datetime import date
from pathlib import Path

import pytest
from app.analyzer.repository import AnalysisRepository
from app.analyzer.service import AnalysisService
from app.domain.models import MetadataPlan, TargetContext
from app.evaluation.drafts import load_benchmark_drafts
from app.parsers.ectd322 import FixtureCatalog
from app.rules.registry import MetadataRuleRegistry


def target(
    *,
    intent: str | None = None,
    partitioning: str = "unknown",
    replacement: str | None = None,
    mode: str = "prospective_forward_compatibility",
) -> TargetContext:
    metadata = None
    if intent:
        metadata = MetadataPlan.model_validate(
            {
                "intent": intent,
                "manufacturer_partitioning": partitioning,
                "replacement_manufacturer_value": replacement,
            }
        )
    return TargetContext.model_validate(
        {
            "authority": "FDA",
            "center": "CDER",
            "application_type": "NDA",
            "source_standard": "eCTD-3.2.2",
            "target_standard": "eCTD-4.0",
            "analysis_date": date(2026, 8, 29),
            "reuse_operation": "reference-existing-content",
            "standards_snapshot_id": "fda-cder-demo-v1",
            "scenario_mode": mode,
            "metadata_plan": metadata,
        }
    )


def service(tmp_path: Path) -> AnalysisService:
    return AnalysisService(repository=AnalysisRepository(tmp_path / "analyses.sqlite3"))


def analyze(fixture_id: str, target_context: TargetContext, tmp_path: Path):
    inventory = FixtureCatalog().parse(fixture_id)
    return service(tmp_path).analyze(inventory, inventory.leaves[0].id, target_context)


def test_metadata_rules_match_exact_author_adjudication() -> None:
    rules = {rule.predicate_type: rule for rule in MetadataRuleRegistry().load()}
    assert rules["discouraged-manufacturer-value"].enforcement_mode.value == "advisory"
    assert rules["preserve-existing-lifecycle"].enforcement_mode.value == "hard"
    normalize_decision = rules["normalize-manufacturer-metadata"].decision
    assert normalize_decision is not None
    assert normalize_decision.value == "REUSE_WITH_NEW_CONTEXT"
    assert rules["hyperlink-relevance-gate"].enforcement_mode.value == "semantic_signal"
    assert all(rule.expert_validated is False for rule in rules.values())


def test_canonical_case_b_normalizes_by_new_context_without_resubmitting_file(
    tmp_path: Path,
) -> None:
    result = analyze(
        "case-b-normalize-all",
        target(intent="normalize-metadata", partitioning="unnecessary"),
        tmp_path,
    )
    assert result.decision.value == "REUSE_WITH_NEW_CONTEXT"
    assert result.repair.type == "CREATE_NEW_CONTEXT_GROUP_AND_SUSPEND_OLD"
    assert "identifier" in result.repair.description
    assert "FDA-CDER-M2-DISCOURAGED-MANUFACTURER-ALL-001" in result.triggered_rule_ids
    assert "FDA-CDER-M2-NORMALIZE-MANUFACTURER-003" in result.triggered_rule_ids


def test_preserve_gate_retains_advisory_and_controlled_eligibility(tmp_path: Path) -> None:
    result = analyze(
        "case-b-preserve-all",
        target(intent="preserve-existing-lifecycle"),
        tmp_path,
    )
    assert result.decision.value == "REUSE_AS_LEGACY_REFERENCE"
    assert result.severity.value == "medium"
    assert {finding.enforcement_mode.value for finding in result.findings} == {"advisory", "hard"}
    assert "not FDA acceptance" not in result.rationale.lower()
    assert "controlled" in result.rationale.lower()


def test_missing_metadata_intent_abstains_and_does_not_choose_an_alternative(
    tmp_path: Path,
) -> None:
    result = analyze("case-b-unspecified-all", target(intent="unspecified"), tmp_path)
    assert result.decision.value == "HUMAN_REGULATORY_REVIEW"
    assert result.repair.type == "DECLARE_METADATA_MIGRATION_INTENT"
    assert len(result.unresolved_uncertainty) == 1


@pytest.mark.parametrize(
    ("fixture_id", "decision"),
    (
        ("case-c-stale-heading", "HUMAN_REGULATORY_REVIEW"),
        ("case-c-stale-applicant", "HUMAN_REGULATORY_REVIEW"),
        ("case-c-ambiguous", "HUMAN_REGULATORY_REVIEW"),
        ("case-c-clean", "REUSE_AS_LEGACY_REFERENCE"),
        ("case-c-relevant-link", "REUSE_AS_LEGACY_REFERENCE"),
        ("case-c-irrelevant-link", "HUMAN_REGULATORY_REVIEW"),
    ),
)
def test_case_c_semantic_policy_is_conservative(
    fixture_id: str, decision: str, tmp_path: Path
) -> None:
    result = analyze(fixture_id, target(), tmp_path)
    assert result.decision.value == decision
    assert result.model_run.mode == "fixture"
    assert result.operational_status.value == "not_operational"
    if decision == "HUMAN_REGULATORY_REVIEW":
        assert result.human_approval_required


def test_current_operational_mode_bypasses_all_m2_rules_and_model(tmp_path: Path) -> None:
    result = analyze(
        "case-b-normalize-all",
        target(
            intent="normalize-metadata",
            partitioning="unnecessary",
            mode="current_operational",
        ),
        tmp_path,
    )
    assert result.decision.value == "HUMAN_REGULATORY_REVIEW"
    assert result.triggered_rule_ids == ()
    assert result.model_run.status == "not_applicable"


def test_m2_benchmark_has_exactly_ten_unfrozen_drafts_per_archetype() -> None:
    drafts = load_benchmark_drafts()
    assert len(drafts.cases) == 30
    assert all(case.split == "unassigned" for case in drafts.cases)
    canonical = next(case for case in drafts.cases if case.case_id == "case-b-001")
    assert canonical.reference_decision is not None
    assert canonical.expert_validated is False
    assert sum(case.adjudication_status.value == "candidate" for case in drafts.cases) == 29
