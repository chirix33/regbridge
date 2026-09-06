import asyncio
import hashlib
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import tiktoken

from app.analyzer.prompts import SEMANTIC_INSPECTION_PROMPT_VERSION, SEMANTIC_INSPECTION_TASK
from app.analyzer.repairs import complete_document_inspection_action
from app.analyzer.repository import AnalysisRepository
from app.config import Settings, get_settings
from app.domain.enums import (
    Decision,
    EnforcementMode,
    ManufacturerPartitioning,
    MetadataMigrationIntent,
    ReuseOperation,
    ScenarioMode,
    Severity,
    TraceStepKind,
    VerificationBasis,
)
from app.domain.models import (
    AnalysisResult,
    DossierEvidence,
    Finding,
    ModelRunRecord,
    RepairAction,
    RuntimeRepairAction,
    SourceArtifact,
    TargetContext,
    TraceStep,
)
from app.domain.vocabulary import ActionCode
from app.graph.builder import build_neighborhood
from app.graph.models import GraphNeighborhood
from app.llm import DisabledModel, FixtureModel
from app.llm.models import ModelRequest, SemanticRiskOutput
from app.llm.protocol import StructuredModel
from app.llm.responses import LiveModelInvalidOutput, ResponsesStructuredModel
from app.parsers.models import ApplicationInventory, ParsedLeaf
from app.rules.engine import applicable_heading_rule
from app.rules.models import MetadataRule
from app.rules.registry import MetadataRuleRegistry, RuleRegistry
from app.standards.evidence import EvidenceRegistry
from app.standards.operational import OperationalStatusRegistry
from app.standards.registry import StandardsRegistry

SCENARIO_DISCLOSURE = (
    "Prospective forward-compatibility research scenario; FDA forward compatibility is "
    "currently not operational. Results are author-adjudicated for a controlled demonstration "
    "and are not regulatory-expert validated."
)
PROMPT_VERSION = SEMANTIC_INSPECTION_PROMPT_VERSION


class AnalysisPipelineError(RuntimeError):
    """A non-retryable failure after inference, with an auditable pipeline stage."""

    def __init__(self, stage: str, cause: Exception) -> None:
        self.stage = stage
        self.cause_type = type(cause).__name__
        super().__init__(f"{stage}:{self.cause_type}")


def _configured_model(settings: Settings) -> StructuredModel:
    if settings.llm_mode.value == "disabled":
        return DisabledModel()
    if settings.llm_mode.value == "live":
        return ResponsesStructuredModel(
            base_url=cast(str, settings.llm_base_url),
            api_key=cast(
                str, settings.llm_api_key.get_secret_value() if settings.llm_api_key else None
            ),
            model=cast(str, settings.llm_model),
            timeout_seconds=settings.llm_timeout_seconds,
            reasoning_effort=settings.product_reasoning_effort,
            max_output_tokens=settings.product_max_output_tokens,
            count_final_tokens=_token_counter(cast(str, settings.llm_model)),
            final_answer_token_limit=settings.product_final_answer_token_limit,
            input_character_limit=settings.product_input_character_limit,
        )
    return FixtureModel()


def _token_counter(model_name: str) -> Callable[[str], int]:
    try:
        encoding = tiktoken.encoding_for_model(model_name)
    except KeyError:
        encoding = tiktoken.get_encoding("o200k_base")
    return lambda text: len(encoding.encode(text))


class AnalysisService:
    def __init__(
        self,
        *,
        model: StructuredModel | None = None,
        repository: AnalysisRepository | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.heading_rules = RuleRegistry().load()
        self.metadata_rules = MetadataRuleRegistry().load()
        self.metadata_by_predicate = {rule.predicate_type: rule for rule in self.metadata_rules}
        self.evidence = {span.id: span for span in EvidenceRegistry().load()}
        self.operational = OperationalStatusRegistry().load()
        self.snapshot_id = StandardsRegistry().load().snapshot_id
        self.model = model or _configured_model(self.settings)
        self.repository = repository or AnalysisRepository(
            Path(self.settings.reg_bridge_database_path)
        )

    def analyze(
        self,
        inventory: ApplicationInventory,
        leaf_id: str,
        target: TargetContext,
    ) -> AnalysisResult:
        return asyncio.run(self.analyze_async(inventory, leaf_id, target))

    async def analyze_async(
        self,
        inventory: ApplicationInventory,
        leaf_id: str,
        target: TargetContext,
    ) -> AnalysisResult:
        leaf = self._leaf(inventory, leaf_id)
        self._validate_target(inventory, target)
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
            result = self._current_operational_result(analysis_id, artifact, target, occurred_at)
            return self._persist(result)

        dossier_evidence = self._dossier_evidence(artifact.id, leaf)
        findings: list[Finding] = []
        regulatory_ids: set[str] = set()
        triggered: list[str] = []
        heading_rule = applicable_heading_rule(leaf, target, self.heading_rules)
        unresolved_reason: str | None = None
        unresolved_source: str | None = None
        if leaf.policy_coverage_status == "OUTSIDE_ENCODED_POLICY_COVERAGE":
            unresolved_reason = leaf.policy_coverage_basis
            unresolved_source = "deterministic_policy"
        elif leaf.policy_coverage_status == "INSUFFICIENT_APPLICATION_HISTORY":
            unresolved_reason = leaf.policy_coverage_basis
            unresolved_source = "deterministic_policy"
        elif leaf.policy_coverage_status == "DOCUMENT_INSPECTION_INCOMPLETE":
            unresolved_reason = leaf.policy_coverage_basis
            unresolved_source = "deterministic_policy"
        deterministic_decision: Decision | None = None
        deterministic_repair: RepairAction | None = None
        deterministic_severity = Severity.INFORMATIONAL

        if heading_rule:
            triggered.append(heading_rule.id)
            regulatory_ids.update(heading_rule.evidence_ids)
            mapped_heading = heading_rule.explicit_heading_mapping[leaf.heading]
            findings.append(
                Finding(
                    id=f"{leaf.id}-removed-heading",
                    rule_id=heading_rule.id,
                    severity=heading_rule.severity,
                    rationale=(
                        f"Legacy heading {leaf.heading} is explicitly mapped to {mapped_heading} "
                        "for this controlled prospective scenario."
                    ),
                    evidence_ids=heading_rule.evidence_ids,
                    source=TraceStepKind.DETERMINISTIC,
                    verification_basis=heading_rule.verification_basis,
                    enforcement_mode=heading_rule.enforcement_mode,
                )
            )
            deterministic_decision = heading_rule.decision
            deterministic_severity = heading_rule.severity
            deterministic_repair = RepairAction(
                type=cast(ActionCode, heading_rule.repair_type),
                description=heading_rule.repair_description,
                evidence_ids=heading_rule.evidence_ids,
            )
        elif leaf.heading != "3.2.S.1":
            unresolved_reason = (
                "No generic nearest-parent inference is permitted; no source-supported mapping "
                f"is encoded for {leaf.heading}."
            )
            unresolved_source = "deterministic_policy"

        if target.reuse_operation == ReuseOperation.CREATE_NEW_TARGET_ARTIFACT:
            unresolved_reason = (
                "The approved identifier-reuse rules do not cover creation of a new target "
                "artifact."
            )
            unresolved_source = "deterministic_policy"
            regulatory_ids.update(("ev-ctoc-321-remains", "ev-ctoc-3211-3213-removed"))
            findings.append(
                Finding(
                    id=f"{leaf.id}-unmapped-heading",
                    severity=Severity.UNRESOLVED,
                    rationale=(
                        f"Heading {leaf.heading} is outside the exact approved mapping; no "
                        "nearest-parent inference was attempted."
                    ),
                    evidence_ids=("ev-ctoc-321-remains", "ev-ctoc-3211-3213-removed"),
                    source=TraceStepKind.DETERMINISTIC,
                    verification_basis=VerificationBasis.MECHANICAL_DERIVATION,
                    enforcement_mode=EnforcementMode.HARD,
                )
            )

        manufacturer = next((item for item in leaf.keywords if item.name == "manufacturer"), None)
        manufacturer_all = manufacturer is not None and manufacturer.normalized_value == "all"
        if manufacturer_all:
            advisory = self.metadata_by_predicate["discouraged-manufacturer-value"]
            self._append_rule_finding(
                findings,
                triggered,
                regulatory_ids,
                advisory,
                leaf,
                'The legacy manufacturer value normalizes to "all". FDA guidance describes '
                "that general value as not recommended when differentiation is unnecessary; "
                "this is an advisory, not a noncompliance finding.",
            )
            plan = target.metadata_plan
            if plan is None or plan.intent == MetadataMigrationIntent.UNSPECIFIED:
                unresolved_reason = "Metadata migration intent is not declared."
                unresolved_source = "deterministic_policy"
            elif plan.intent == MetadataMigrationIntent.PRESERVE_EXISTING_LIFECYCLE:
                preserve = self.metadata_by_predicate["preserve-existing-lifecycle"]
                self._append_rule_finding(
                    findings,
                    triggered,
                    regulatory_ids,
                    preserve,
                    leaf,
                    "Preservation intent is explicit and the existing manufacturer keyword is "
                    "retained exactly. Controlled eligibility still depends on deterministic "
                    "checks and author-verified hyperlink relevance.",
                )
                deterministic_decision = preserve.decision
                deterministic_severity = max(
                    deterministic_severity, preserve.severity, key=self._severity_rank
                )
                deterministic_repair = self._rule_repair(preserve)
            elif plan.intent == MetadataMigrationIntent.NORMALIZE_METADATA:
                if plan.manufacturer_partitioning == ManufacturerPartitioning.UNKNOWN:
                    unresolved_reason = "Manufacturer partitioning need is not declared."
                    unresolved_source = "deterministic_policy"
                else:
                    normalize = self.metadata_by_predicate["normalize-manufacturer-metadata"]
                    self._append_rule_finding(
                        findings,
                        triggered,
                        regulatory_ids,
                        normalize,
                        leaf,
                        (
                            "Normalization intent is explicit. The optional manufacturer keyword "
                            "will be omitted because partitioning is unnecessary."
                            if plan.manufacturer_partitioning
                            == ManufacturerPartitioning.UNNECESSARY
                            else "Normalization intent and a stable distinguishing manufacturer "
                            "value are explicit."
                        ),
                    )
                    deterministic_decision = normalize.decision
                    deterministic_severity = max(
                        deterministic_severity, normalize.severity, key=self._severity_rank
                    )
                    deterministic_repair = self._rule_repair(normalize)

        model_output, model_run = await self._semantic_inspection(
            inventory, target, dossier_evidence
        )
        if model_output.abstained:
            reason_category, status_detail = self._abstention_disclosure(
                model_output.abstain_reason
            )
            model_run = model_run.model_copy(
                update={
                    "status": "abstained",
                    "reason_category": reason_category,
                    "status_detail": status_detail,
                }
            )
        supplied_ids = {item.id for item in dossier_evidence}
        semantic_risk = False
        unsupported = {
            evidence_id
            for semantic in model_output.findings
            for evidence_id in semantic.evidence_ids
            if evidence_id not in supplied_ids
        }
        if unsupported:
            raise AnalysisPipelineError(
                "semantic_validation",
                ValueError("model cited evidence outside its request packet"),
            )
        for semantic in model_output.findings:
            findings.append(
                Finding(
                    id=semantic.id,
                    severity=semantic.severity,
                    rationale=semantic.summary,
                    evidence_ids=semantic.evidence_ids,
                    source=TraceStepKind.MODEL_ASSISTED,
                    verification_basis=VerificationBasis.SEMANTIC_INFERENCE,
                    enforcement_mode=EnforcementMode.SEMANTIC_SIGNAL,
                )
            )
            if semantic.category != "benign_historical_reference":
                semantic_risk = True

        hyperlinks_verified = not leaf.hyperlinks or all(
            link.author_verified_relevant and link.target_exists is not False
            for link in leaf.hyperlinks
        )
        semantic_required = inventory.fixture_id is None or inventory.fixture_id.startswith(
            "case-c-"
        )
        inspection_incomplete = semantic_required and (
            leaf.extraction_status != "completed" or model_output.abstained
        )
        hard_structural_decision = bool(
            heading_rule
            and heading_rule.enforcement_mode == EnforcementMode.HARD
            and deterministic_decision is not None
            and deterministic_repair is not None
        )
        if leaf.hyperlinks and not hyperlinks_verified:
            unresolved_reason = (
                "One or more hyperlinks lack author-verified target-context relevance."
            )
            regulatory_ids.add("ev-tcg-hyperlinks-relevant-to-context")
            gate = self.metadata_by_predicate["hyperlink-relevance-gate"]
            self._append_rule_finding(
                findings,
                triggered,
                regulatory_ids,
                gate,
                leaf,
                "Document reuse eligibility is unresolved because hyperlink relevance has not "
                "been author-verified for this controlled fixture.",
            )
            unresolved_source = "deterministic_policy"
        elif inspection_incomplete and unresolved_reason is None:
            unresolved_reason = (
                model_run.status_detail or "Required semantic inspection is incomplete."
            )
            unresolved_source = "abstention_gate"
        elif semantic_risk and unresolved_reason is None:
            unresolved_reason = (
                "Supported stale or ambiguous dossier evidence requires human review."
            )
            unresolved_source = "semantic_finding"

        uncertainty: tuple[str, ...]
        repair: RepairAction | RuntimeRepairAction
        if hard_structural_decision:
            decision = cast(Decision, deterministic_decision)
            severity = deterministic_severity
            repair = cast(RepairAction, deterministic_repair)
            uncertainty = (unresolved_reason,) if unresolved_reason else ()
            confidence = 0.0 if unresolved_reason else min(1.0, model_output.confidence)
            human_required = True
            decision_basis = "deterministic_hard_rule"
        elif unresolved_reason:
            decision = Decision.HUMAN_REGULATORY_REVIEW
            severity = Severity.UNRESOLVED
            if leaf.hyperlinks and not hyperlinks_verified:
                repair = RepairAction(
                    type="VERIFY_HYPERLINK_RELEVANCE",
                    description=(
                        "Have a human verify every hyperlink against the selected target context; "
                        "update or remove stale references before relying on reuse eligibility."
                    ),
                    evidence_ids=("ev-tcg-hyperlinks-relevant-to-context",),
                )
            elif target.reuse_operation == ReuseOperation.CREATE_NEW_TARGET_ARTIFACT:
                repair = RepairAction(
                    type="SELECT_SUPPORTED_REUSE_OPERATION",
                    description=(
                        "Select identifier-based reuse for this controlled rule or obtain human "
                        "review for new-artifact creation outside the approved rule scope."
                    ),
                )
            elif (
                manufacturer_all
                and target.metadata_plan is not None
                and target.metadata_plan.intent == MetadataMigrationIntent.NORMALIZE_METADATA
                and target.metadata_plan.manufacturer_partitioning
                == ManufacturerPartitioning.UNKNOWN
            ):
                repair = RepairAction(
                    type="DECLARE_MANUFACTURER_PARTITIONING",
                    description=(
                        "Declare whether manufacturer partitioning is required and, when "
                        "required, provide a stable distinguishing manufacturer value."
                    ),
                    evidence_ids=("ev-m4-manufacturer-general-values",),
                )
                regulatory_ids.add("ev-m4-manufacturer-general-values")
            elif manufacturer_all and (
                target.metadata_plan is None
                or target.metadata_plan.intent == MetadataMigrationIntent.UNSPECIFIED
            ):
                repair = RepairAction(
                    type="DECLARE_METADATA_MIGRATION_INTENT",
                    description=(
                        "Declare whether to preserve exact lifecycle keywords or normalize the "
                        "manufacturer metadata; RegBridge will not choose between them."
                    ),
                    evidence_ids=("ev-m4-manufacturer-general-values",),
                )
                regulatory_ids.add("ev-m4-manufacturer-general-values")
            elif unresolved_source == "abstention_gate":
                repair = complete_document_inspection_action()
            elif semantic_risk:
                repair = RepairAction(
                    type="HUMAN_VERIFY_STALE_CONTENT",
                    description=(
                        "Review the cited text and hyperlinks against the target heading, "
                        "applicant, and context; update the content only after that review."
                    ),
                )
            else:
                repair = RepairAction(
                    type="AUTHOR_REVIEW_HEADING_MAPPING",
                    description="Adjudicate exact official evidence before adding a new mapping.",
                    evidence_ids=tuple(sorted(regulatory_ids)),
                )
            uncertainty = (unresolved_reason,)
            confidence = 0.0
            human_required = True
            decision_basis = (
                unresolved_source
                if unresolved_source in {"semantic_finding", "abstention_gate"}
                else "deterministic_policy"
            )
        else:
            decision = deterministic_decision or Decision.REUSE_AS_LEGACY_REFERENCE
            severity = deterministic_severity
            repair = deterministic_repair or RepairAction(
                type="NO_MATERIAL_REPAIR",
                description=(
                    "No material structural, metadata, or semantic repair was identified within "
                    "the controlled evidence packet."
                ),
            )
            uncertainty = ()
            confidence = min(1.0, model_output.confidence)
            human_required = decision != Decision.REUSE_AS_LEGACY_REFERENCE
            decision_basis = "deterministic_policy"

        all_evidence = (
            tuple(self.evidence[item] for item in sorted(regulatory_ids)) + dossier_evidence
        )
        trace = (
            TraceStep(
                sequence=1,
                kind=TraceStepKind.DETERMINISTIC,
                component="ectd-322-parser",
                summary=(
                    f"Parsed {leaf.id} beneath {leaf.heading}; extracted {leaf.text_span_count} "
                    f"text spans and {leaf.hyperlink_count} hyperlinks; policy coverage "
                    f"{leaf.policy_coverage_status}."
                ),
                occurred_at=occurred_at,
            ),
            TraceStep(
                sequence=2,
                kind=TraceStepKind.DETERMINISTIC,
                component="typed-rule-engine",
                summary=(
                    f"Evaluated {len(self.heading_rules) + len(self.metadata_rules)} scoped rules."
                ),
                evidence_ids=tuple(sorted(regulatory_ids)),
                occurred_at=occurred_at,
            ),
            TraceStep(
                sequence=3,
                kind=TraceStepKind.MODEL_ASSISTED,
                component="semantic-inspection",
                summary=(
                    f"Semantic inspection {model_run.status}; {len(model_output.findings)} "
                    f"validated findings; reason category "
                    f"{model_run.reason_category or 'none'}."
                ),
                evidence_ids=tuple(
                    sorted(
                        {
                            evidence_id
                            for item in model_output.findings
                            for evidence_id in item.evidence_ids
                        }
                    )
                ),
                occurred_at=occurred_at,
            ),
            TraceStep(
                sequence=4,
                kind=TraceStepKind.SYNTHESIS,
                component="decision-synthesizer",
                summary=(
                    f"Applied {decision_basis.replace('_', ' ')} precedence and produced "
                    f"{decision.value}."
                ),
                occurred_at=occurred_at,
            ),
        )
        result = AnalysisResult(
            id=analysis_id,
            source_artifact=artifact,
            target_context=target,
            operational_status=self.operational.status,
            scenario_disclosure=SCENARIO_DISCLOSURE,
            decision=decision,
            severity=severity,
            triggered_rule_ids=tuple(triggered),
            findings=tuple(findings),
            evidence=all_evidence,
            rationale=self._rationale(
                decision,
                manufacturer_all,
                unresolved_reason,
                decision_basis,
                model_run.status == "abstained",
            ),
            repair=repair,
            confidence=confidence,
            unresolved_uncertainty=uncertainty,
            human_approval_required=human_required,
            decision_basis=decision_basis,
            trace=trace,
            model_run=model_run,
        )
        return self._persist(result)

    def get(self, analysis_id: str) -> AnalysisResult:
        return self.repository.get(analysis_id)

    def graph(self, analysis_id: str) -> GraphNeighborhood:
        return self.repository.graph(analysis_id)

    def _persist(self, result: AnalysisResult) -> AnalysisResult:
        try:
            graph = build_neighborhood(result)
        except Exception as error:
            raise AnalysisPipelineError("graph", error) from error
        try:
            self.repository.save(result, graph)
        except Exception as error:
            raise AnalysisPipelineError("persistence", error) from error
        return result

    @staticmethod
    def _leaf(inventory: ApplicationInventory, leaf_id: str) -> ParsedLeaf:
        try:
            return next(item for item in inventory.leaves if item.id == leaf_id)
        except StopIteration as error:
            raise ValueError(f"unknown leaf identifier: {leaf_id}") from error

    def _validate_target(self, inventory: ApplicationInventory, target: TargetContext) -> None:
        if target.standards_snapshot_id != self.snapshot_id:
            raise ValueError("target standards snapshot does not match the active snapshot")
        if target.source_standard != inventory.source_standard:
            raise ValueError("target source standard differs from parsed inventory")
        if target.authority.value != "FDA" or target.center.value != "CDER":
            raise ValueError("target is outside the FDA/CDER demonstration scope")
        if target.application_type.value != "NDA":
            raise ValueError("application type is outside the M2 demonstration scope")

    @staticmethod
    def _dossier_evidence(artifact_id: str, leaf: ParsedLeaf) -> tuple[DossierEvidence, ...]:
        evidence: list[DossierEvidence] = []
        for keyword in leaf.keywords:
            evidence.append(
                DossierEvidence(
                    id=f"{leaf.id}-metadata-{keyword.name}",
                    artifact_id=artifact_id,
                    kind="metadata",
                    locator=keyword.source_locator,
                    text=f"{keyword.name}={keyword.raw_value}",
                    file_sha256=leaf.file_sha256,
                )
            )
        for span in leaf.text_spans:
            evidence.append(
                DossierEvidence(
                    id=span.id,
                    artifact_id=artifact_id,
                    kind="text",
                    locator=span.locator,
                    text=span.text,
                    file_sha256=leaf.file_sha256,
                )
            )
        for link in leaf.hyperlinks:
            status = "author-verified relevant" if link.author_verified_relevant else "unverified"
            evidence.append(
                DossierEvidence(
                    id=link.id,
                    artifact_id=artifact_id,
                    kind="hyperlink",
                    locator=link.locator,
                    text=(
                        f"{link.target_type} target={link.target}; "
                        f"target_exists={link.target_exists}; "
                        f"fixture_relevance={status}"
                    ),
                    file_sha256=leaf.file_sha256,
                )
            )
        return tuple(evidence)

    async def _semantic_inspection(
        self,
        inventory: ApplicationInventory,
        target: TargetContext,
        evidence: tuple[DossierEvidence, ...],
    ) -> tuple[SemanticRiskOutput, ModelRunRecord]:
        fixture_id = inventory.fixture_id or "uncontrolled-upload"
        request = ModelRequest(
            fixture_lookup_key=fixture_id,
            task=SEMANTIC_INSPECTION_TASK,
            context={
                "authority": target.authority.value,
                "center": target.center.value,
                "target_standard": target.target_standard.value,
                "application_type": target.application_type.value,
                "analysis_date": target.analysis_date.isoformat(),
                "parsed_applicant_name": inventory.applicant_name,
            },
            evidence=evidence,
            prompt_template_version=PROMPT_VERSION,
        )
        try:
            completion = await self.model.complete(request, SemanticRiskOutput)
            return completion.output, completion.run
        except LiveModelInvalidOutput:
            # Retry policy and terminal publication are owned by the product/evaluation runner.
            raise
        except Exception as error:
            raise AnalysisPipelineError("semantic_processing", error) from error

    @staticmethod
    def _abstention_disclosure(reason: str | None) -> tuple[str, str]:
        normalized = " ".join((reason or "").split()).casefold()
        if "disabled" in normalized or "omitted" in normalized:
            return "semantic_model_disabled", "Semantic inspection was deliberately disabled."
        if "extract" in normalized or "document" in normalized:
            return (
                "document_inspection_incomplete",
                "Document extraction or bounded semantic inspection was incomplete.",
            )
        return (
            "insufficient_bounded_evidence",
            "The model abstained because the bounded evidence did not support a semantic "
            "conclusion.",
        )

    @staticmethod
    def _append_rule_finding(
        findings: list[Finding],
        triggered: list[str],
        evidence_ids: set[str],
        rule: MetadataRule,
        leaf: ParsedLeaf,
        rationale: str,
    ) -> None:
        triggered.append(rule.id)
        evidence_ids.update(rule.evidence_ids)
        findings.append(
            Finding(
                id=f"{leaf.id}-{rule.id.lower()}",
                rule_id=rule.id,
                severity=rule.severity,
                rationale=rationale,
                evidence_ids=rule.evidence_ids,
                source=TraceStepKind.DETERMINISTIC,
                verification_basis=rule.verification_basis,
                enforcement_mode=rule.enforcement_mode,
            )
        )

    @staticmethod
    def _rule_repair(rule: MetadataRule) -> RepairAction:
        return RepairAction(
            type=cast(ActionCode, rule.repair_type),
            description=cast(str, rule.repair_description),
            evidence_ids=rule.evidence_ids,
        )

    @staticmethod
    def _severity_rank(severity: Severity) -> int:
        return {
            Severity.INFORMATIONAL: 0,
            Severity.LOW: 1,
            Severity.MEDIUM: 2,
            Severity.HIGH: 3,
            Severity.BLOCKING: 4,
            Severity.UNRESOLVED: 5,
        }[severity]

    @staticmethod
    def _rationale(
        decision: Decision,
        manufacturer_all: bool,
        unresolved_reason: str | None,
        decision_basis: str,
        model_abstained: bool,
    ) -> str:
        if decision_basis == "deterministic_hard_rule" and unresolved_reason:
            return (
                "The author-adjudicated hard structural mapping and its required context-group "
                "action remain in force. Semantic inspection is incomplete, so the document is "
                f"not semantically cleared: {unresolved_reason}"
            )
        if model_abstained and unresolved_reason:
            return (
                "Semantic inspection is incomplete and produced no substantive finding. "
                f"RegBridge therefore requires bounded human review: {unresolved_reason}"
            )
        if unresolved_reason:
            return f"RegBridge requires human review: {unresolved_reason}"
        if decision == Decision.REUSE_WITH_NEW_CONTEXT and manufacturer_all:
            return (
                "Explicit normalization intent changes the context-group keyword. Create a new "
                "context group and suspend the old one; reuse the unchanged document by identifier."
            )
        if decision == Decision.REUSE_AS_LEGACY_REFERENCE and manufacturer_all:
            return (
                "Exact lifecycle preservation and controlled hyperlink eligibility permit legacy "
                'reference reuse, while the nonbinding manufacturer="all" advisory remains visible.'
            )
        if decision == Decision.REUSE_WITH_NEW_CONTEXT:
            return "An author-adjudicated structural rule requires a new target context group."
        return "No material risk was found in the completed controlled evidence packet."

    def _current_operational_result(
        self,
        analysis_id: str,
        artifact: SourceArtifact,
        target: TargetContext,
        occurred_at: datetime,
    ) -> AnalysisResult:
        return AnalysisResult(
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
                "FDA forward compatibility is not operational in current-operational mode, so "
                "prospective M1/M2 rules and semantic inspection were not executed."
            ),
            repair=RepairAction(
                type="WAIT_FOR_OPERATIONAL_AVAILABILITY",
                description=(
                    "Do not apply prospective rules to an operational submission; retain human "
                    "review until FDA makes the capability operational."
                ),
            ),
            confidence=0,
            unresolved_uncertainty=("Operational forward compatibility is unavailable.",),
            human_approval_required=True,
            decision_basis="operational_guard",
            trace=(
                TraceStep(
                    sequence=1,
                    kind=TraceStepKind.DETERMINISTIC,
                    component="operational-mode-guard",
                    summary="Bypassed all prospective rules and semantic inspection.",
                    occurred_at=occurred_at,
                ),
            ),
            model_run=ModelRunRecord(
                mode=self.settings.llm_mode.value,
                status="not_applicable",
                prompt_template_version=PROMPT_VERSION,
                model_name=self.settings.llm_model,
                latency_ms=0,
            ),
        )

    @staticmethod
    def _analysis_id(inventory: ApplicationInventory, leaf_id: str, target: TargetContext) -> str:
        payload = "|".join((inventory.package_sha256, leaf_id, target.model_dump_json()))
        return f"analysis-{hashlib.sha256(payload.encode()).hexdigest()[:16]}"
