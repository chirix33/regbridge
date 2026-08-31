import hashlib
import json
import os
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import Field, model_validator

from app.analyzer.service import AnalysisService
from app.config import REPOSITORY_ROOT, Settings
from app.domain.enums import Decision, LlmMode, ReviewStatus, Severity
from app.domain.models import DomainModel, Sha256, StableId, TargetContext
from app.parsers.ectd322 import FixtureCatalog
from app.parsers.models import ApplicationInventory, ParsedLeaf
from app.rules.registry import MetadataRuleRegistry, RuleRegistry
from app.standards.evidence import EvidenceRegistry

PREFREEZE_SPEC = REPOSITORY_ROOT / "data" / "benchmark" / "m3-prefreeze-spec.yaml"
PREFREEZE_JSON = REPOSITORY_ROOT / "data" / "benchmark" / "pre-freeze-ledger.json"
PREFREEZE_MARKDOWN = REPOSITORY_ROOT / "data" / "benchmark" / "PRE_FREEZE_LEDGER.md"
REALIZED_CASE_IDS = frozenset({"A004", "A005", "A007", "A009", "C007", "C008", "C009"})
REPRESENTED_DECISIONS = frozenset(
    {
        Decision.REUSE_WITH_NEW_CONTEXT,
        Decision.REUSE_AS_LEGACY_REFERENCE,
        Decision.HUMAN_REGULATORY_REVIEW,
    }
)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


class MutationSpec(DomainModel):
    type: StableId
    exact: str = Field(min_length=1)


class CandidateCase(DomainModel):
    case_id: StableId
    archetype: Literal[
        "unavailable-heading",
        "legacy-metadata-tension",
        "stale-content-or-hyperlink",
    ]
    fixture_id: StableId
    source_fixture_id: StableId | None = None
    selected_leaf_id: StableId
    target_context_id: StableId
    fixture_family: StableId
    split: Literal["train", "development", "test"]
    mutation: MutationSpec
    reference_decision: Decision
    reference_severity: Severity
    action: StableId
    action_mode: Literal["required_condition", "suggested_check", "no_action"]
    required_rule_ids: tuple[StableId, ...] = ()
    acceptable_evidence_ids: tuple[StableId, ...] = ()
    human_review_required: bool
    rationale: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_candidate_label(self) -> "CandidateCase":
        if self.reference_decision == Decision.HUMAN_REGULATORY_REVIEW:
            if not self.human_review_required:
                raise ValueError("HUMAN reference labels require human review")
        if self.action_mode == "suggested_check" and (
            self.reference_decision != Decision.HUMAN_REGULATORY_REVIEW
        ):
            raise ValueError("suggested checks are reserved for HUMAN semantic cases")
        return self


class PrefreezeSpec(DomainModel):
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    snapshot_id: StableId
    status: Literal["awaiting-author-approval"]
    author_approval_required: Literal[True]
    author_approval_recorded: Literal[False]
    expert_validated: Literal[False]
    controls: dict[str, Any]
    target_contexts: dict[StableId, TargetContext]
    cases: tuple[CandidateCase, ...] = Field(min_length=30, max_length=30)

    @model_validator(mode="after")
    def validate_identifiers(self) -> "PrefreezeSpec":
        ids = [case.case_id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("candidate case identifiers must be unique")
        unknown_contexts = {case.target_context_id for case in self.cases} - set(
            self.target_contexts
        )
        if unknown_contexts:
            raise ValueError(f"unknown target contexts: {sorted(unknown_contexts)}")
        return self


class InputHashes(DomainModel):
    package_sha256: Sha256
    selected_file_sha256: Sha256
    target_context_sha256: Sha256
    decision_fingerprint_sha256: Sha256
    decision_predicate_sha256: Sha256


class RealizedLeaf(DomainModel):
    id: StableId
    heading: str
    operation: str
    modified_leaf_id: StableId | None
    predecessor_exists: bool
    predecessor_operation: str | None
    title: str
    href: str
    extraction_status: str
    text_span_count: int
    hyperlink_count: int


class LedgerCase(DomainModel):
    case_id: StableId
    archetype: str
    fixture_id: StableId
    source_fixture_id: StableId | None
    selected_leaf: RealizedLeaf
    target_context_id: StableId
    target_context: TargetContext
    fixture_family: StableId
    split: str
    mutation: MutationSpec
    input_hashes: InputHashes
    decision_relevant_predicates: dict[str, Any]
    reference_decision: Decision
    reference_severity: Severity
    action: StableId
    action_mode: str
    required_rule_ids: tuple[StableId, ...]
    acceptable_evidence_ids: tuple[StableId, ...]
    human_review_required: bool
    rationale: str
    label_status: Literal[ReviewStatus.CANDIDATE] = ReviewStatus.CANDIDATE
    expert_validated: Literal[False] = False
    production_path_validation: Literal["matched-candidate-reference"]


class PrefreezeLedger(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    benchmark_version: str
    snapshot_id: StableId
    status: Literal["awaiting-explicit-author-01-approval"]
    promotion_permitted: Literal[False]
    author_adjudication_events_created: Literal[False]
    expert_validated: Literal[False]
    generated_at: Literal["2026-08-30T00:00:00Z"]
    specification_sha256: Sha256
    controls: dict[str, Any]
    validation_summary: dict[str, Any]
    cases: tuple[LedgerCase, ...] = Field(min_length=30, max_length=30)


class PrefreezeValidationError(ValueError):
    """Raised when a candidate benchmark cannot advance to author review."""


def load_prefreeze_spec(path: Path | None = None) -> PrefreezeSpec:
    source = path or PREFREEZE_SPEC
    return PrefreezeSpec.model_validate(yaml.safe_load(source.read_text(encoding="utf-8")))


def _leaf_predicates(
    inventory: ApplicationInventory,
    leaf: ParsedLeaf,
    target: TargetContext,
    *,
    include_input_hashes: bool,
) -> dict[str, Any]:
    predecessor = next(
        (item for item in inventory.leaves if item.id == leaf.modified_leaf_id), None
    )
    predicates: dict[str, Any] = {
        "source_standard": inventory.source_standard.value,
        "application_number": inventory.application_number,
        "submission_type": inventory.submission_type,
        "applicant_name": inventory.applicant_name,
        "has_stf": inventory.has_stf,
        "selected_leaf": {
            "heading": leaf.heading,
            "title": leaf.title,
            "href": leaf.href,
            "operation": leaf.operation.value,
            "modified_leaf_id": leaf.modified_leaf_id,
            "predecessor_exists": predecessor is not None,
            "predecessor_operation": predecessor.operation.value if predecessor else None,
            "predecessor_heading": predecessor.heading if predecessor else None,
            "keywords": [
                {
                    "name": item.name,
                    "raw_value": item.raw_value,
                    "normalized_value": item.normalized_value,
                }
                for item in leaf.keywords
            ],
            "extraction_status": leaf.extraction_status,
            "text_spans": [
                {"page": item.page, "text": item.text, "locator": item.locator}
                for item in leaf.text_spans
            ],
            "hyperlinks": [
                {
                    "page": item.page,
                    "target_type": item.target_type,
                    "target": item.target,
                    "target_exists": item.target_exists,
                    "author_verified_relevant": item.author_verified_relevant,
                }
                for item in leaf.hyperlinks
            ],
        },
        "target_context": target.model_dump(mode="json"),
        "operational_availability": "not_operational",
    }
    if include_input_hashes:
        predicates["package_sha256"] = inventory.package_sha256
        predicates["selected_file_sha256"] = leaf.file_sha256
        if predecessor:
            predicates["predecessor_file_sha256"] = predecessor.file_sha256
    return predicates


def _realized_leaf(inventory: ApplicationInventory, leaf: ParsedLeaf) -> RealizedLeaf:
    predecessor = next(
        (item for item in inventory.leaves if item.id == leaf.modified_leaf_id), None
    )
    return RealizedLeaf(
        id=leaf.id,
        heading=leaf.heading,
        operation=leaf.operation.value,
        modified_leaf_id=leaf.modified_leaf_id,
        predecessor_exists=predecessor is not None,
        predecessor_operation=predecessor.operation.value if predecessor else None,
        title=leaf.title,
        href=leaf.href,
        extraction_status=leaf.extraction_status,
        text_span_count=leaf.text_span_count,
        hyperlink_count=leaf.hyperlink_count,
    )


def _selected_leaf(inventory: ApplicationInventory, leaf_id: str) -> ParsedLeaf:
    try:
        return next(item for item in inventory.leaves if item.id == leaf_id)
    except StopIteration as error:
        raise PrefreezeValidationError(
            f"fixture {inventory.fixture_id} is missing selected leaf {leaf_id}"
        ) from error


def _validate_structure(spec: PrefreezeSpec) -> None:
    counts = Counter(case.archetype for case in spec.cases)
    if set(counts.values()) != {10} or len(counts) != 3:
        raise PrefreezeValidationError("benchmark requires exactly ten cases per archetype")
    split_counts = Counter(case.split for case in spec.cases)
    if split_counts != Counter({"train": 12, "development": 6, "test": 12}):
        raise PrefreezeValidationError(f"unexpected split counts: {dict(split_counts)}")
    family_splits: dict[str, set[str]] = defaultdict(set)
    for case in spec.cases:
        family_splits[case.fixture_family].add(case.split)
    crossing = {family: splits for family, splits in family_splits.items() if len(splits) != 1}
    if crossing:
        raise PrefreezeValidationError(f"fixture families cross splits: {crossing}")
    held_out = [case for case in spec.cases if case.split == "test"]
    class_counts = Counter(case.reference_decision for case in held_out)
    expected = Counter(
        {
            Decision.REUSE_WITH_NEW_CONTEXT: 4,
            Decision.REUSE_AS_LEGACY_REFERENCE: 4,
            Decision.HUMAN_REGULATORY_REVIEW: 4,
        }
    )
    if class_counts != expected:
        raise PrefreezeValidationError(f"held-out class balance must be 4/4/4: {class_counts}")
    if len({case.fixture_family for case in held_out}) != 6:
        raise PrefreezeValidationError(
            "held-out cases require six non-overlapping fixture families"
        )
    if {case.reference_decision for case in spec.cases} != REPRESENTED_DECISIONS:
        raise PrefreezeValidationError(
            "candidate labels must use exactly three represented classes"
        )
    if spec.controls.get("over_limit_behavior") != "fail-validation":
        raise PrefreezeValidationError("B0/B1 over-limit behavior must fail validation")
    if spec.controls.get("input_character_limit") != 16000:
        raise PrefreezeValidationError("B0/B1 character limit must be exactly 16000")
    if spec.controls.get("case_serialization") != "identical-for-b0-b1":
        raise PrefreezeValidationError("B0/B1 must use identical case serialization")


def build_prefreeze_ledger(path: Path | None = None) -> PrefreezeLedger:
    source = path or PREFREEZE_SPEC
    spec = load_prefreeze_spec(source)
    _validate_structure(spec)
    catalog = FixtureCatalog()
    available_fixtures = {item.id for item in catalog.list()}
    known_rules = {item.id for item in RuleRegistry().load()} | {
        item.id for item in MetadataRuleRegistry().load()
    }
    regulatory_evidence = {item.id for item in EvidenceRegistry().load()}
    inventories: dict[str, ApplicationInventory] = {}

    def inventory(fixture_id: str) -> ApplicationInventory:
        if fixture_id not in available_fixtures:
            raise PrefreezeValidationError(f"missing controlled fixture: {fixture_id}")
        if fixture_id not in inventories:
            inventories[fixture_id] = catalog.parse(fixture_id)
        return inventories[fixture_id]

    ledger_cases: list[LedgerCase] = []
    full_fingerprints: dict[str, str] = {}

    class _ValidationRepository:
        def save(self, result: Any, graph: Any) -> None:
            return None

    settings = Settings(llm_mode=LlmMode.FIXTURE)
    service = AnalysisService(settings=settings, repository=_ValidationRepository())  # type: ignore[arg-type]
    for case in spec.cases:
        parsed = inventory(case.fixture_id)
        leaf = _selected_leaf(parsed, case.selected_leaf_id)
        if leaf.modified_leaf_id and not any(
            item.id == leaf.modified_leaf_id for item in parsed.leaves
        ):
            raise PrefreezeValidationError(
                f"{case.case_id} names a missing predecessor {leaf.modified_leaf_id}"
            )
        target = spec.target_contexts[case.target_context_id]
        unknown_rules = set(case.required_rule_ids) - known_rules
        if unknown_rules:
            raise PrefreezeValidationError(
                f"{case.case_id} cites unknown rules: {sorted(unknown_rules)}"
            )
        dossier_evidence = {
            item.id for item in service._dossier_evidence(f"artifact-{leaf.id}", leaf)
        }
        unknown_evidence = set(case.acceptable_evidence_ids) - (
            regulatory_evidence | dossier_evidence
        )
        if unknown_evidence:
            raise PrefreezeValidationError(
                f"{case.case_id} cites unknown evidence: {sorted(unknown_evidence)}"
            )
        predicates = _leaf_predicates(parsed, leaf, target, include_input_hashes=True)
        predicate_only = _leaf_predicates(parsed, leaf, target, include_input_hashes=False)
        full_fingerprint = _digest(predicates)
        if prior := full_fingerprints.get(full_fingerprint):
            raise PrefreezeValidationError(
                f"cases {prior} and {case.case_id} have identical full fingerprints"
            )
        full_fingerprints[full_fingerprint] = case.case_id
        result = service.analyze(parsed, leaf.id, target)
        mismatches: list[str] = []
        if result.decision != case.reference_decision:
            mismatches.append(f"decision={result.decision.value}")
        if result.severity != case.reference_severity:
            mismatches.append(f"severity={result.severity.value}")
        if result.repair.type != case.action:
            mismatches.append(f"action={result.repair.type}")
        if result.human_approval_required != case.human_review_required:
            mismatches.append(f"human_review={result.human_approval_required}")
        if set(result.triggered_rule_ids) != set(case.required_rule_ids):
            mismatches.append(f"rules={list(result.triggered_rule_ids)}")
        if mismatches:
            raise PrefreezeValidationError(
                f"{case.case_id} production path differs from candidate reference: "
                + ", ".join(mismatches)
            )
        ledger_cases.append(
            LedgerCase(
                case_id=case.case_id,
                archetype=case.archetype,
                fixture_id=case.fixture_id,
                source_fixture_id=case.source_fixture_id,
                selected_leaf=_realized_leaf(parsed, leaf),
                target_context_id=case.target_context_id,
                target_context=target,
                fixture_family=case.fixture_family,
                split=case.split,
                mutation=case.mutation,
                input_hashes=InputHashes(
                    package_sha256=parsed.package_sha256,
                    selected_file_sha256=leaf.file_sha256,
                    target_context_sha256=_digest(target.model_dump(mode="json")),
                    decision_fingerprint_sha256=full_fingerprint,
                    decision_predicate_sha256=_digest(predicate_only),
                ),
                decision_relevant_predicates=predicates,
                reference_decision=case.reference_decision,
                reference_severity=case.reference_severity,
                action=case.action,
                action_mode=case.action_mode,
                required_rule_ids=case.required_rule_ids,
                acceptable_evidence_ids=case.acceptable_evidence_ids,
                human_review_required=case.human_review_required,
                rationale=case.rationale,
                production_path_validation="matched-candidate-reference",
            )
        )

    by_id = {case.case_id: case for case in ledger_cases}
    for case_id in REALIZED_CASE_IDS:
        realized = by_id[case_id]
        if not realized.source_fixture_id:
            raise PrefreezeValidationError(f"{case_id} lacks mutation lineage")
        source_inventory = inventory(realized.source_fixture_id)
        source_leaf = source_inventory.leaves[0]
        source_predicates = _leaf_predicates(
            source_inventory,
            source_leaf,
            realized.target_context,
            include_input_hashes=False,
        )
        if _digest(source_predicates) == realized.input_hashes.decision_predicate_sha256:
            raise PrefreezeValidationError(
                f"{case_id} mutation has no decision-relevant predicate change"
            )
        if source_inventory.package_sha256 == realized.input_hashes.package_sha256:
            raise PrefreezeValidationError(f"{case_id} package hash did not change")

    validation_summary = {
        "case_count": len(ledger_cases),
        "archetype_counts": dict(sorted(Counter(c.archetype for c in ledger_cases).items())),
        "split_counts": dict(sorted(Counter(c.split for c in ledger_cases).items())),
        "test_class_counts": dict(
            sorted(
                Counter(
                    c.reference_decision.value for c in ledger_cases if c.split == "test"
                ).items()
            )
        ),
        "test_fixture_family_count": len(
            {c.fixture_family for c in ledger_cases if c.split == "test"}
        ),
        "test_fixture_family_characterization": ("six non-overlapping held-out fixture families"),
        "realized_mutation_count": len(REALIZED_CASE_IDS),
        "unique_full_fingerprint_count": len(full_fingerprints),
        "production_path_matches": len(ledger_cases),
        "current_fda_operational_availability": "not_operational",
        "author_approval": "pending",
    }
    return PrefreezeLedger(
        benchmark_version=spec.version,
        snapshot_id=spec.snapshot_id,
        status="awaiting-explicit-author-01-approval",
        promotion_permitted=False,
        author_adjudication_events_created=False,
        expert_validated=False,
        generated_at="2026-08-30T00:00:00Z",
        specification_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        controls=spec.controls,
        validation_summary=validation_summary,
        cases=tuple(ledger_cases),
    )


def _render_markdown(ledger: PrefreezeLedger) -> str:
    lines = [
        "# M3 pre-freeze ledger",
        "",
        "> Status: **awaiting explicit `author-01` approval**. This ledger is not frozen, "
        "contains no benchmark adjudication event, is not expert validated, and cannot be "
        "promoted by this command.",
        "",
        "FDA operational availability remains `not_operational`. All labels below are candidate "
        "controlled prospective research labels until explicit author approval.",
        "",
        "## Validation summary",
        "",
        f"- Cases: {ledger.validation_summary['case_count']} (10 per archetype)",
        f"- Splits: `{ledger.validation_summary['split_counts']}`",
        f"- Held-out balance: `{ledger.validation_summary['test_class_counts']}`",
        "- Held-out grouping: six non-overlapping held-out fixture families",
        f"- Unique full fingerprints: {ledger.validation_summary['unique_full_fingerprint_count']}",
        (
            "- Realized mutations with changed package and decision predicates: "
            f"{ledger.validation_summary['realized_mutation_count']}"
        ),
        (
            "- Production-path candidate matches: "
            f"{ledger.validation_summary['production_path_matches']}"
        ),
        (
            "- B0/B1 input policy: identical serialization, fixed evidence-ID ordering, and "
            "fail validation above 16,000 characters (no silent truncation)"
        ),
        (
            "- B2 test policy: rule behavior and absence of semantic capability; no "
            "case-ID-specific expected-output mapping"
        ),
        "",
        "## Candidate cases",
        "",
        (
            "| Case | Split | Family | Fixture / selected leaf | Heading / operation / "
            "predecessor | Candidate decision | Severity | Action (mode) | Human | Package "
            "SHA-256 | File SHA-256 | Target SHA-256 | Decision fingerprint |"
        ),
        "|---|---|---|---|---|---|---|---|---:|---|---|---|---|",
    ]
    for case in ledger.cases:
        leaf = case.selected_leaf
        predecessor = leaf.modified_leaf_id or "—"
        lines.append(
            "| "
            + " | ".join(
                (
                    case.case_id,
                    case.split,
                    case.fixture_family,
                    f"{case.fixture_id} / {leaf.id}",
                    f"{leaf.heading} / {leaf.operation} / {predecessor}",
                    case.reference_decision.value,
                    case.reference_severity.value,
                    f"{case.action} ({case.action_mode})",
                    "yes" if case.human_review_required else "no",
                    case.input_hashes.package_sha256,
                    case.input_hashes.selected_file_sha256,
                    case.input_hashes.target_context_sha256,
                    case.input_hashes.decision_fingerprint_sha256,
                )
            )
            + " |"
        )
    lines.extend(
        (
            "",
            "## A005 operation and lineage",
            "",
            "A005 analyzes only `leaf-a005-selected`: `operation=append`, "
            "`modified-file=leaf-a005-predecessor`. The predecessor is present in the same "
            "package with `operation=new`. These exact predicates are included in the decision "
            "fingerprint.",
            "",
            "## Approval boundary",
            "",
            "The promotion command is intentionally absent at this checkpoint. Explicit "
            "`author-01` approval of this realized ledger is required before code may create "
            "benchmark adjudication events or atomically freeze the benchmark.",
            "",
        )
    )
    return "\n".join(lines)


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as temporary:
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
        Path(temporary_name).replace(path)
    finally:
        temporary_path = Path(temporary_name)
        if temporary_path.exists():
            temporary_path.unlink()


def write_prefreeze_ledger(
    json_path: Path | None = None, markdown_path: Path | None = None
) -> PrefreezeLedger:
    ledger = build_prefreeze_ledger()
    rendered_json = (
        json.dumps(ledger.model_dump(mode="json"), indent=2, sort_keys=True, ensure_ascii=False)
        + "\n"
    )
    _atomic_write(json_path or PREFREEZE_JSON, rendered_json)
    _atomic_write(markdown_path or PREFREEZE_MARKDOWN, _render_markdown(ledger))
    return ledger
