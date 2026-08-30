import hashlib
from datetime import UTC, datetime

from app.domain.enums import Decision, ScenarioMode, Severity, TraceStepKind
from app.domain.models import (
    AnalysisResult,
    Finding,
    RepairAction,
    SourceArtifact,
    TargetContext,
    TraceStep,
)
from app.graph.builder import build_neighborhood
from app.graph.models import GraphNeighborhood
from app.parsers.models import ApplicationInventory
from app.rules.engine import applicable_heading_rule
from app.rules.registry import RuleRegistry
from app.standards.evidence import EvidenceRegistry
from app.standards.operational import OperationalStatusRegistry

SCENARIO_DISCLOSURE = (
    "Prospective forward-compatibility research scenario; FDA forward compatibility is "
    "currently not operational. Results are author-adjudicated for a controlled demonstration "
    "and are not regulatory-expert validated."
)


class AnalysisService:
    def __init__(self) -> None:
        self.rules = RuleRegistry().load()
        self.evidence = {span.id: span for span in EvidenceRegistry().load()}
        self.operational = OperationalStatusRegistry().load()
        self._results: dict[str, AnalysisResult] = {}
        self._graphs: dict[str, GraphNeighborhood] = {}

    def analyze(
        self,
        inventory: ApplicationInventory,
        leaf_id: str,
        target: TargetContext,
    ) -> AnalysisResult:
        try:
            leaf = next(item for item in inventory.leaves if item.id == leaf_id)
        except StopIteration as error:
            raise ValueError(f"unknown leaf identifier: {leaf_id}") from error
        rule = applicable_heading_rule(leaf, target, self.rules)
        analysis_id = self._analysis_id(inventory, leaf.id, target)
        occurred_at = datetime.now(UTC)
        artifact = SourceArtifact(
            id=f"artifact-{leaf.id}",
            title=leaf.title,
            source_standard=inventory.source_standard,
            source_leaf_id=leaf.id,
            source_heading=leaf.heading,
            source_locator=leaf.source_locator,
            content_type=leaf.content_type,
            file_sha256=leaf.file_sha256,
        )
        if target.scenario_mode == ScenarioMode.CURRENT_OPERATIONAL:
            result = AnalysisResult(
                id=analysis_id,
                source_artifact=artifact,
                target_context=target,
                operational_status=self.operational.status,
                scenario_disclosure=SCENARIO_DISCLOSURE,
                decision=Decision.HUMAN_REGULATORY_REVIEW,
                severity=Severity.UNRESOLVED,
                triggered_rule_ids=(),
                findings=(),
                evidence=(),
                rationale=(
                    "FDA forward compatibility is not operational in the selected current-"
                    "operational mode, so the prospective M1 mapping rule was not executed."
                ),
                repair=RepairAction(
                    type="WAIT_FOR_OPERATIONAL_AVAILABILITY",
                    description=(
                        "Do not apply the prospective rule to an operational submission; retain "
                        "human regulatory review until FDA makes the capability operational."
                    ),
                ),
                confidence=0.0,
                unresolved_uncertainty=(
                    "Operational forward-compatibility processing is unavailable.",
                ),
                human_approval_required=True,
                trace=(
                    TraceStep(
                        sequence=1,
                        kind=TraceStepKind.DETERMINISTIC,
                        component="operational-mode-guard",
                        summary=(
                            "Bypassed prospective rules because operational status is "
                            "not_operational."
                        ),
                        occurred_at=occurred_at,
                    ),
                ),
            )
        elif rule:
            evidence = tuple(self.evidence[evidence_id] for evidence_id in rule.evidence_ids)
            mapped_heading = rule.explicit_heading_mapping[leaf.heading]
            result = AnalysisResult(
                id=analysis_id,
                source_artifact=artifact,
                target_context=target,
                operational_status=self.operational.status,
                scenario_disclosure=SCENARIO_DISCLOSURE,
                decision=rule.decision,
                severity=rule.severity,
                triggered_rule_ids=(rule.id,),
                findings=(
                    Finding(
                        id=f"finding-{leaf.id}-removed-heading",
                        rule_id=rule.id,
                        severity=rule.severity,
                        rationale=(
                            f"Legacy heading {leaf.heading} is explicitly removed and mapped to "
                            f"{mapped_heading} for this controlled prospective scenario."
                        ),
                        evidence_ids=rule.evidence_ids,
                        source=TraceStepKind.DETERMINISTIC,
                    ),
                ),
                evidence=evidence,
                rationale=(
                    f"The physical document remains reusable by identifier, but its legacy "
                    f"{leaf.heading} placement cannot be retained. Use a new {mapped_heading} "
                    "context group and suspend the legacy context."
                ),
                repair=RepairAction(
                    type=rule.repair_type,
                    description=rule.repair_description,
                    evidence_ids=rule.evidence_ids,
                ),
                confidence=1.0,
                unresolved_uncertainty=(),
                human_approval_required=True,
                trace=(
                    TraceStep(
                        sequence=1,
                        kind=TraceStepKind.DETERMINISTIC,
                        component="ectd-322-parser",
                        summary=f"Parsed leaf {leaf.id} beneath {leaf.heading}.",
                        occurred_at=occurred_at,
                    ),
                    TraceStep(
                        sequence=2,
                        kind=TraceStepKind.DETERMINISTIC,
                        component="explicit-heading-rule-engine",
                        summary=(
                            f"Matched the author-adjudicated explicit mapping to {mapped_heading}."
                        ),
                        evidence_ids=rule.evidence_ids,
                        occurred_at=occurred_at,
                    ),
                    TraceStep(
                        sequence=3,
                        kind=TraceStepKind.SYNTHESIS,
                        component="decision-precedence",
                        summary=f"Emitted {rule.decision.value}; no model-assisted step ran.",
                        evidence_ids=rule.evidence_ids,
                        occurred_at=occurred_at,
                    ),
                ),
            )
        elif leaf.heading in self.rules[0].verified_available_target_headings:
            evidence = (self.evidence["ev-ctoc-321-remains"],)
            result = AnalysisResult(
                id=analysis_id,
                source_artifact=artifact,
                target_context=target,
                operational_status=self.operational.status,
                scenario_disclosure=SCENARIO_DISCLOSURE,
                decision=Decision.REUSE_AS_LEGACY_REFERENCE,
                severity=Severity.INFORMATIONAL,
                triggered_rule_ids=(),
                findings=(),
                evidence=evidence,
                rationale=(
                    "The parsed legacy placement is 3.2.S.1, which remains available in the "
                    "selected target hierarchy; the removed-subheading rule does not trigger."
                ),
                repair=RepairAction(
                    type="NO_HEADING_REPAIR",
                    description="No heading relocation is supported or required by the M1 rule.",
                    evidence_ids=("ev-ctoc-321-remains",),
                ),
                confidence=1.0,
                unresolved_uncertainty=(),
                human_approval_required=False,
                trace=(
                    TraceStep(
                        sequence=1,
                        kind=TraceStepKind.DETERMINISTIC,
                        component="explicit-heading-rule-engine",
                        summary=(
                            "Confirmed exact available heading 3.2.S.1; no removed-heading "
                            "rule matched."
                        ),
                        evidence_ids=("ev-ctoc-321-remains",),
                        occurred_at=occurred_at,
                    ),
                ),
            )
        else:
            evidence = (
                self.evidence["ev-ctoc-321-remains"],
                self.evidence["ev-ctoc-3211-3213-removed"],
            )
            evidence_ids = tuple(item.id for item in evidence)
            result = AnalysisResult(
                id=analysis_id,
                source_artifact=artifact,
                target_context=target,
                operational_status=self.operational.status,
                scenario_disclosure=SCENARIO_DISCLOSURE,
                decision=Decision.HUMAN_REGULATORY_REVIEW,
                severity=Severity.UNRESOLVED,
                triggered_rule_ids=(),
                findings=(
                    Finding(
                        id=f"finding-{leaf.id}-unmapped-heading",
                        severity=Severity.UNRESOLVED,
                        rationale=(
                            f"Heading {leaf.heading} is neither the verified available heading nor "
                            "one of the three explicitly adjudicated removed headings."
                        ),
                        evidence_ids=evidence_ids,
                        source=TraceStepKind.DETERMINISTIC,
                    ),
                ),
                evidence=evidence,
                rationale=(
                    "No generic nearest-parent inference is permitted; mapping is unresolved."
                ),
                repair=RepairAction(
                    type="AUTHOR_REVIEW_HEADING_MAPPING",
                    description=(
                        "Verify and adjudicate exact official evidence before adding a mapping."
                    ),
                    evidence_ids=evidence_ids,
                ),
                confidence=0.0,
                unresolved_uncertainty=(
                    f"No source-supported mapping is encoded for {leaf.heading}.",
                ),
                human_approval_required=True,
                trace=(
                    TraceStep(
                        sequence=1,
                        kind=TraceStepKind.DETERMINISTIC,
                        component="explicit-heading-rule-engine",
                        summary=(
                            "Abstained because no exact mapping exists; no parent inference "
                            "was attempted."
                        ),
                        evidence_ids=evidence_ids,
                        occurred_at=occurred_at,
                    ),
                ),
            )
        self._results[result.id] = result
        self._graphs[result.id] = build_neighborhood(result, self.rules[0])
        return result

    def get(self, analysis_id: str) -> AnalysisResult:
        try:
            return self._results[analysis_id]
        except KeyError as error:
            raise KeyError(f"analysis not found: {analysis_id}") from error

    def graph(self, analysis_id: str) -> GraphNeighborhood:
        try:
            return self._graphs[analysis_id]
        except KeyError as error:
            raise KeyError(f"analysis graph not found: {analysis_id}") from error

    @staticmethod
    def _analysis_id(
        inventory: ApplicationInventory,
        leaf_id: str,
        target: TargetContext,
    ) -> str:
        payload = "|".join(
            (
                inventory.package_sha256,
                leaf_id,
                target.model_dump_json(),
            )
        )
        return f"analysis-{hashlib.sha256(payload.encode()).hexdigest()[:16]}"
