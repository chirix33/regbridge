import json
from dataclasses import dataclass
from typing import Any, cast

from app.baselines.prompts import DIRECT_DECISION_TASK
from app.domain.enums import Decision, Severity
from app.domain.models import EvidenceSpan
from app.domain.vocabulary import ActionCode, output_vocabulary
from app.evaluation.models import CaseInput, DirectDecisionOutput
from app.llm.serialization import RequestAliases

DIRECT_INPUT_CHARACTER_LIMIT = 16_000
DIRECT_OUTPUT_TOKEN_LIMIT = 800
DIRECT_TEMPERATURE = 0
DIRECT_MODEL_NAME = "contract-fixture-direct-decision-v1"


@dataclass(frozen=True)
class PreparedCase:
    material: dict[str, Any]
    serialized: str
    alias_to_evidence_id: dict[str, str]


def prepare_case(case_input: CaseInput) -> PreparedCase:
    request_aliases = RequestAliases(forbidden=(
        case_input.case_id, case_input.fixture_id, case_input.selected_leaf_id,
        case_input.target_context_id, *(
            value for item in case_input.dossier_evidence
            for value in (item.id, item.artifact_id, item.locator)
        ),
    ))
    selected = dict(case_input.material["selected_leaf"])
    aliases: dict[str, str] = {}
    sanitized_text: list[dict[str, Any]] = []
    sanitized_links: list[dict[str, Any]] = []
    sanitized_keywords: list[dict[str, Any]] = []
    for index, evidence in enumerate(case_input.dossier_evidence, start=1):
        alias = f"case-evidence-{index:03d}"
        aliases[alias] = evidence.id
        record = {"evidence_id": alias, "text": request_aliases.text(evidence.text)}
        if evidence.kind == "text":
            sanitized_text.append(record)
        elif evidence.kind == "hyperlink":
            sanitized_links.append(record)
        elif evidence.kind == "metadata":
            sanitized_keywords.append(record)
    selected.pop("href", None)
    selected.pop("modified_leaf_id", None)
    selected.pop("text_spans", None)
    selected.pop("hyperlinks", None)
    selected.pop("keywords", None)
    selected["text_evidence"] = sanitized_text
    selected["hyperlink_evidence"] = sanitized_links
    selected["metadata_evidence"] = sanitized_keywords
    material = {
        "source_standard": case_input.material["source_standard"],
        "application_type": case_input.target_context.application_type.value,
        "applicant_name": case_input.material["applicant_name"],
        "selected_leaf": selected,
        "target_context": case_input.target_context.model_dump(mode="json"),
        "operational_availability": case_input.material["operational_availability"],
    }
    material = request_aliases.clean(material)
    serialized = json.dumps(material, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    forbidden = (
        case_input.case_id,
        case_input.fixture_id,
        case_input.selected_leaf_id,
    )
    if any(value in serialized for value in forbidden):
        raise ValueError("case or fixture identifier leaked into direct-decision serialization")
    return PreparedCase(
        material=material,
        serialized=serialized,
        alias_to_evidence_id=aliases,
    )


def serialize_direct_request(prepared: PreparedCase, evidence: tuple[EvidenceSpan, ...]) -> str:
    ordered = tuple(sorted(evidence, key=lambda item: item.id))
    packet = {
        "task": DIRECT_DECISION_TASK,
        "case_material": prepared.material,
        "evidence": [
            {
                "id": item.id,
                "source_sha256": item.source_sha256,
                "locator": item.locator,
                "text": item.text,
            }
            for item in ordered
        ],
        "output_schema": "DirectDecisionOutput-v2",
        "output_vocabulary": output_vocabulary(),
    }
    serialized = json.dumps(packet, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    if len(serialized) > DIRECT_INPUT_CHARACTER_LIMIT:
        raise ValueError(
            f"direct-decision input has {len(serialized)} characters; limit is "
            f"{DIRECT_INPUT_CHARACTER_LIMIT}; silent truncation is forbidden"
        )
    return serialized


def _aliases(prepared: PreparedCase, kind: str) -> tuple[str, ...]:
    key = {
        "text": "text_evidence",
        "hyperlink": "hyperlink_evidence",
        "metadata": "metadata_evidence",
    }[kind]
    return tuple(item["evidence_id"] for item in prepared.material["selected_leaf"][key])


def contract_fixture_decision(
    prepared: PreparedCase, evidence: tuple[EvidenceSpan, ...]
) -> DirectDecisionOutput:
    """Offline schema fixture; this is deliberately not an empirical model observation."""

    evidence_ids = {item.id for item in evidence}
    selected = prepared.material["selected_leaf"]
    target = prepared.material["target_context"]
    text = " ".join(item["text"] for item in selected["text_evidence"]).casefold()
    metadata = " ".join(item["text"] for item in selected["metadata_evidence"]).casefold()
    link_text = " ".join(item["text"] for item in selected["hyperlink_evidence"]).casefold()
    text_aliases = _aliases(prepared, "text")
    link_aliases = _aliases(prepared, "hyperlink")
    metadata_aliases = _aliases(prepared, "metadata")

    def output(
        decision: Decision,
        severity: Severity,
        action: str,
        human: bool,
        rationale: str,
        cited: tuple[str, ...] = (),
    ) -> DirectDecisionOutput:
        return DirectDecisionOutput(
            decision=decision,
            severity=severity,
            action=cast(ActionCode, action),
            human_review_required=human,
            rationale=rationale,
            evidence_ids=cited,
            confidence=None,
        )

    if target["scenario_mode"] == "current_operational":
        return output(
            Decision.HUMAN_REGULATORY_REVIEW,
            Severity.UNRESOLVED,
            "WAIT_FOR_OPERATIONAL_AVAILABILITY",
            True,
            "Forward compatibility is recorded as not operational.",
        )
    if target["reuse_operation"] == "create-new-target-artifact":
        return output(
            Decision.HUMAN_REGULATORY_REVIEW,
            Severity.UNRESOLVED,
            "SELECT_SUPPORTED_REUSE_OPERATION",
            True,
            "The supplied evidence addresses identifier reuse, not new-artifact creation.",
        )
    heading = selected["heading"]
    if heading in {"3.2.S.1.1", "3.2.S.1.2", "3.2.S.1.3"}:
        required = {"ev-ctoc-3211-3213-removed", "ev-tcg-new-context-and-reuse"}
        if required <= evidence_ids:
            return output(
                Decision.REUSE_WITH_NEW_CONTEXT,
                Severity.BLOCKING,
                "CREATE_NEW_CONTEXT_GROUP_AND_SUSPEND_LEGACY_CONTENT",
                True,
                "The supplied spans identify the subheading as removed and require new context.",
                tuple(sorted(required)),
            )
        return output(
            Decision.HUMAN_REGULATORY_REVIEW,
            Severity.UNRESOLVED,
            "AUTHOR_REVIEW_HEADING_MAPPING",
            True,
            "Retrieved evidence is insufficient to support a heading mapping.",
            tuple(sorted(evidence_ids)),
        )
    if heading != "3.2.S.1":
        return output(
            Decision.HUMAN_REGULATORY_REVIEW,
            Severity.UNRESOLVED,
            "AUTHOR_REVIEW_HEADING_MAPPING",
            True,
            "No supplied evidence supports this exact heading mapping.",
            tuple(sorted(evidence_ids)),
        )
    if selected["hyperlink_evidence"] and "author-verified relevant" not in link_text:
        return output(
            Decision.HUMAN_REGULATORY_REVIEW,
            Severity.UNRESOLVED,
            "VERIFY_HYPERLINK_RELEVANCE",
            True,
            "Hyperlink relevance is not author verified.",
            link_aliases,
        )
    benign_history = "historical only" in text and "not current" in text
    stale_or_ambiguous = any(
        marker in text
        for marker in (
            "controlling description",
            "current controlling",
            "old applicant",
            "current responsible applicant",
            "confirm whether",
            "former dossier context",
        )
    )
    if stale_or_ambiguous and not benign_history:
        return output(
            Decision.HUMAN_REGULATORY_REVIEW,
            Severity.UNRESOLVED,
            "HUMAN_VERIFY_STALE_CONTENT",
            True,
            "Case text contains stale or ambiguous context requiring human review.",
            text_aliases,
        )
    manufacturer_all = "manufacturer=all" in metadata or "manufacturer= all " in metadata
    plan = target.get("metadata_plan")
    if manufacturer_all:
        if not plan or plan["intent"] == "unspecified":
            return output(
                Decision.HUMAN_REGULATORY_REVIEW,
                Severity.UNRESOLVED,
                "DECLARE_METADATA_MIGRATION_INTENT",
                True,
                "Manufacturer migration intent is absent.",
                metadata_aliases,
            )
        if plan["intent"] == "normalize-metadata":
            if plan["manufacturer_partitioning"] == "unknown":
                return output(
                    Decision.HUMAN_REGULATORY_REVIEW,
                    Severity.UNRESOLVED,
                    "DECLARE_MANUFACTURER_PARTITIONING",
                    True,
                    "Manufacturer partitioning is not declared.",
                    metadata_aliases,
                )
            if "ev-m4-manufacturer-general-values" in evidence_ids:
                return output(
                    Decision.REUSE_WITH_NEW_CONTEXT,
                    Severity.BLOCKING,
                    "CREATE_NEW_CONTEXT_GROUP_AND_SUSPEND_OLD",
                    True,
                    "Explicit manufacturer normalization changes the target context.",
                    ("ev-m4-manufacturer-general-values",),
                )
        if plan["intent"] == "preserve-existing-lifecycle":
            return output(
                Decision.REUSE_AS_LEGACY_REFERENCE,
                Severity.MEDIUM,
                "PRESERVE_EXACT_CONTEXT_GROUP_KEYWORDS",
                False,
                "Explicit preservation retains the exact legacy keyword with an advisory.",
                tuple(
                    item
                    for item in (
                        "ev-m4-manufacturer-general-values",
                        "ev-tcg-replacement-context-same",
                    )
                    if item in evidence_ids
                ),
            )
    cited = text_aliases or metadata_aliases or link_aliases
    return output(
        Decision.REUSE_AS_LEGACY_REFERENCE,
        Severity.INFORMATIONAL,
        "NO_MATERIAL_REPAIR",
        False,
        "No material issue is supported by the supplied packet.",
        cited,
    )


def translate_evidence_aliases(
    output: DirectDecisionOutput, prepared: PreparedCase
) -> DirectDecisionOutput:
    return output.model_copy(
        update={
            "evidence_ids": tuple(
                prepared.alias_to_evidence_id.get(item, item) for item in output.evidence_ids
            )
        }
    )
