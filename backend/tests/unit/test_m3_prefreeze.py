from datetime import date
from pathlib import Path

import pytest
import yaml
from app.analyzer.repository import AnalysisRepository
from app.analyzer.service import AnalysisService
from app.domain.models import MetadataPlan, TargetContext
from app.evaluation.prefreeze import (
    PREFREEZE_SPEC,
    PrefreezeValidationError,
    build_prefreeze_ledger,
    write_prefreeze_ledger,
)
from app.parsers.ectd322 import FixtureCatalog
from pypdf import PdfReader


def _target(
    *,
    reuse_operation: str = "reference-existing-content",
    intent: str | None = None,
    partitioning: str = "unknown",
) -> TargetContext:
    plan = None
    if intent:
        plan = MetadataPlan.model_validate(
            {
                "intent": intent,
                "manufacturer_partitioning": partitioning,
                "replacement_manufacturer_value": None,
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
            "reuse_operation": reuse_operation,
            "standards_snapshot_id": "fda-cder-demo-v1",
            "scenario_mode": "prospective_forward_compatibility",
            "metadata_plan": plan,
        }
    )


def test_prefreeze_ledger_is_complete_but_cannot_promote() -> None:
    ledger = build_prefreeze_ledger()
    assert len(ledger.cases) == 30
    assert ledger.status == "awaiting-explicit-author-01-approval"
    assert ledger.promotion_permitted is False
    assert ledger.author_adjudication_events_created is False
    assert ledger.expert_validated is False
    assert ledger.validation_summary["test_class_counts"] == {
        "HUMAN_REGULATORY_REVIEW": 4,
        "REUSE_AS_LEGACY_REFERENCE": 4,
        "REUSE_WITH_NEW_CONTEXT": 4,
    }
    assert ledger.validation_summary["test_fixture_family_count"] == 6
    serialized = ledger.model_dump_json()
    assert "author_adjudicated_for_demo" not in serialized
    assert "reviewer_id" not in serialized
    assert "review_event" not in serialized


def test_a005_fingerprint_captures_exact_append_and_predecessor() -> None:
    case = next(item for item in build_prefreeze_ledger().cases if item.case_id == "A005")
    assert case.selected_leaf.operation == "append"
    assert case.selected_leaf.modified_leaf_id == "leaf-a005-predecessor"
    assert case.selected_leaf.predecessor_exists is True
    assert case.selected_leaf.predecessor_operation == "new"
    selected = case.decision_relevant_predicates["selected_leaf"]
    assert selected["operation"] == "append"
    assert selected["modified_leaf_id"] == "leaf-a005-predecessor"
    assert selected["predecessor_exists"] is True


def test_realized_mutations_have_distinct_packages_and_predicates() -> None:
    ledger = build_prefreeze_ledger()
    assert ledger.validation_summary["realized_mutation_count"] == 7
    assert ledger.validation_summary["unique_full_fingerprint_count"] == 30
    assert all(
        case.production_path_validation == "matched-candidate-reference" for case in ledger.cases
    )


def test_all_realized_pdf_files_are_single_page_and_parseable() -> None:
    root = Path(__file__).resolve().parents[3] / "data" / "demo-cases"
    fixture_ids = (
        "case-a-004-replacement-3211",
        "case-a-005-append-3212",
        "case-a-007-valid-replacement-321",
        "case-a-009-unmapped-3215",
        "case-c-007-stale-heading-3212",
        "case-c-008-stale-responsible-applicant",
        "case-c-009-benign-heading-history",
    )
    pdfs = tuple(
        path for fixture in fixture_ids for path in (root / fixture / "documents").glob("*.pdf")
    )
    assert len(pdfs) == 10
    for path in pdfs:
        assert path.read_bytes().startswith(b"%PDF-")
        assert len(PdfReader(path, strict=True).pages) == 1


def test_exact_frozen_split_and_family_assignments() -> None:
    ledger = build_prefreeze_ledger()
    actual = {
        case.case_id: (case.split, case.fixture_family, case.reference_decision.value)
        for case in ledger.cases
    }
    expected_split_family = {
        "A001": ("train", "a-removed-3211-lifecycle"),
        "A002": ("test", "a-removed-3212-lifecycle"),
        "A003": ("development", "a-removed-3213"),
        "A004": ("train", "a-removed-3211-lifecycle"),
        "A005": ("test", "a-removed-3212-lifecycle"),
        "A006": ("test", "a-valid-321-lifecycle"),
        "A007": ("test", "a-valid-321-lifecycle"),
        "A008": ("train", "a-unmapped-heading"),
        "A009": ("train", "a-unmapped-heading"),
        "A010": ("development", "a-operational-guard"),
        "B001": ("test", "b-manufacturer-all-normalization"),
        "B002": ("train", "b-manufacturer-all-preservation"),
        "B003": ("train", "b-manufacturer-all-preservation"),
        "B004": ("test", "b-manufacturer-all-normalization"),
        "B005": ("test", "b-manufacturer-all-normalization"),
        "B006": ("development", "b-specific-manufacturer-scope"),
        "B007": ("development", "b-specific-manufacturer-scope"),
        "B008": ("train", "b-product-keyword-scope"),
        "B009": ("train", "b-manufacturer-all-preservation"),
        "B010": ("test", "b-manufacturer-all-normalization"),
        "C001": ("train", "c-heading-context-contrast"),
        "C002": ("test", "c-applicant-mismatch"),
        "C003": ("development", "c-external-link-operational"),
        "C004": ("test", "c-clean-current"),
        "C005": ("test", "c-relevant-internal-link"),
        "C006": ("train", "c-ambiguous-wording"),
        "C007": ("train", "c-heading-context-contrast"),
        "C008": ("test", "c-applicant-mismatch"),
        "C009": ("train", "c-heading-context-contrast"),
        "C010": ("development", "c-external-link-operational"),
    }
    assert {case_id: value[:2] for case_id, value in actual.items()} == expected_split_family


def test_family_crossing_fails_before_ledger_write(tmp_path: Path) -> None:
    payload = yaml.safe_load(PREFREEZE_SPEC.read_text(encoding="utf-8"))
    a001 = next(item for item in payload["cases"] if item["case_id"] == "A001")
    a003 = next(item for item in payload["cases"] if item["case_id"] == "A003")
    a001["split"], a003["split"] = a003["split"], a001["split"]
    invalid = tmp_path / "crossing.yaml"
    invalid.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    with pytest.raises(PrefreezeValidationError, match="families cross splits"):
        build_prefreeze_ledger(invalid)


def test_prefreeze_outputs_are_reproducible_and_atomic(tmp_path: Path) -> None:
    first_json = tmp_path / "first.json"
    first_md = tmp_path / "first.md"
    second_json = tmp_path / "second.json"
    second_md = tmp_path / "second.md"
    write_prefreeze_ledger(first_json, first_md)
    write_prefreeze_ledger(second_json, second_md)
    assert first_json.read_bytes() == second_json.read_bytes()
    assert first_md.read_bytes() == second_md.read_bytes()
    assert not tuple(tmp_path.glob("*.tmp"))


def test_partitioning_gap_selects_partitioning_action_by_rule_behavior(
    tmp_path: Path,
) -> None:
    inventory = FixtureCatalog().parse("case-b-normalize-all")
    result = AnalysisService(
        repository=AnalysisRepository(tmp_path / "partitioning.sqlite3")
    ).analyze(
        inventory,
        inventory.leaves[0].id,
        _target(intent="normalize-metadata", partitioning="unknown"),
    )
    assert result.decision.value == "HUMAN_REGULATORY_REVIEW"
    assert result.repair.type == "DECLARE_MANUFACTURER_PARTITIONING"


def test_new_artifact_operation_abstains_outside_identifier_reuse_rule(
    tmp_path: Path,
) -> None:
    inventory = FixtureCatalog().parse("case-b-clean-specific")
    result = AnalysisService(repository=AnalysisRepository(tmp_path / "operation.sqlite3")).analyze(
        inventory,
        inventory.leaves[0].id,
        _target(reuse_operation="create-new-target-artifact"),
    )
    assert result.decision.value == "HUMAN_REGULATORY_REVIEW"
    assert result.repair.type == "SELECT_SUPPORTED_REUSE_OPERATION"
