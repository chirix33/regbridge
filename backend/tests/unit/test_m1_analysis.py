from datetime import date

import pytest
from app.analyzer.service import AnalysisService
from app.domain.models import TargetContext
from app.parsers.ectd322 import FixtureCatalog
from app.rules.models import HeadingRule
from app.rules.registry import APPROVED_M1_MAPPING, RuleRegistry
from pydantic import ValidationError


def target(mode: str = "prospective_forward_compatibility") -> TargetContext:
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
        }
    )


@pytest.mark.parametrize("suffix", ("3211", "3212", "3213"))
def test_each_explicit_removed_heading_maps_only_to_321(suffix: str) -> None:
    inventory = FixtureCatalog().parse(f"case-a-removed-{suffix}")
    result = AnalysisService().analyze(inventory, inventory.leaves[0].id, target())

    assert result.decision.value == "REUSE_WITH_NEW_CONTEXT"
    assert result.repair.type == "CREATE_NEW_CONTEXT_GROUP_AND_SUSPEND_LEGACY_CONTENT"
    assert "Do not resubmit" in result.repair.description
    assert result.operational_status.value == "not_operational"


def test_rule_registry_contains_exact_mapping_and_no_parent_algorithm() -> None:
    rule = RuleRegistry().load()[0]
    assert rule.explicit_heading_mapping == APPROVED_M1_MAPPING
    assert set(rule.explicit_heading_mapping) == {"3.2.S.1.1", "3.2.S.1.2", "3.2.S.1.3"}


def test_clean_negative_does_not_trigger_removed_heading_rule() -> None:
    inventory = FixtureCatalog().parse("case-a-clean-321")
    result = AnalysisService().analyze(inventory, inventory.leaves[0].id, target())
    assert result.decision.value == "REUSE_AS_LEGACY_REFERENCE"
    assert result.triggered_rule_ids == ()


def test_unmapped_heading_abstains_without_nearest_parent_inference() -> None:
    inventory = FixtureCatalog().parse("case-a-ambiguous-3214")
    result = AnalysisService().analyze(inventory, inventory.leaves[0].id, target())
    assert result.decision.value == "HUMAN_REGULATORY_REVIEW"
    assert result.confidence == 0.0
    assert "No generic nearest-parent" in result.rationale


def test_current_operational_mode_bypasses_prospective_rule() -> None:
    inventory = FixtureCatalog().parse("case-a-removed-3211")
    result = AnalysisService().analyze(
        inventory,
        inventory.leaves[0].id,
        target("current_operational"),
    )
    assert result.decision.value == "HUMAN_REGULATORY_REVIEW"
    assert result.triggered_rule_ids == ()
    assert result.operational_status.value == "not_operational"
    assert "not executed" in result.rationale


def test_hard_rule_rejects_candidate_status() -> None:
    payload = RuleRegistry().load()[0].model_dump(mode="json")
    payload["review_status"] = "candidate"
    with pytest.raises(ValidationError, match="author_adjudicated_for_demo"):
        HeadingRule.model_validate(payload)


def test_hard_rule_rejects_author_interpretation() -> None:
    payload = RuleRegistry().load()[0].model_dump(mode="json")
    payload["verification_basis"] = "author_interpretation"
    with pytest.raises(ValidationError, match="direct or mechanical"):
        HeadingRule.model_validate(payload)


def test_graph_is_deterministic_and_contains_only_active_explicit_mapping() -> None:
    inventory = FixtureCatalog().parse("case-a-removed-3211")
    service = AnalysisService()
    first = service.analyze(inventory, inventory.leaves[0].id, target())
    graph_one = service.graph(first.id)
    second = service.analyze(inventory, inventory.leaves[0].id, target())
    graph_two = service.graph(second.id)
    assert graph_one == graph_two
    mappings = [edge for edge in graph_one.edges if edge.type.value == "MAPS_TO"]
    assert len(mappings) == 1
    assert mappings[0].source == "heading-322-32s11"
    assert all(
        edge.review_status is not None and edge.review_status.value == "author_adjudicated_for_demo"
        for edge in mappings
    )
