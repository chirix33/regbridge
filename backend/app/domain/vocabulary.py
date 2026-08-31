"""Case-independent output contracts, derived from existing repair semantics only."""

from typing import Literal, TypedDict, get_args

from app.domain.enums import Decision

ActionCode = Literal[
    "AUTHOR_REVIEW_HEADING_MAPPING",
    "CREATE_NEW_CONTEXT_GROUP_AND_SUSPEND_LEGACY_CONTENT",
    "CREATE_NEW_CONTEXT_GROUP_AND_SUSPEND_OLD",
    "DECLARE_MANUFACTURER_PARTITIONING",
    "DECLARE_METADATA_MIGRATION_INTENT",
    "HUMAN_VERIFY_STALE_CONTENT",
    "NO_MATERIAL_REPAIR",
    "PRESERVE_EXACT_CONTEXT_GROUP_KEYWORDS",
    "SELECT_SUPPORTED_REUSE_OPERATION",
    "VERIFY_HYPERLINK_RELEVANCE",
    "WAIT_FOR_OPERATIONAL_AVAILABILITY",
]
ACTION_CODES: tuple[str, ...] = get_args(ActionCode)
ACTION_VOCABULARY_VERSION = "2.1.0"

# Effect-only definitions. Alphabetical code order is unrelated to benchmark frequency.
# Keep placement change and metadata change distinct without supplying trigger predicates.
ACTION_DEFINITIONS: dict[str, str] = {
    "AUTHOR_REVIEW_HEADING_MAPPING":
        "Have an author review a proposed content-placement mapping and its supporting evidence.",
    "CREATE_NEW_CONTEXT_GROUP_AND_SUSPEND_LEGACY_CONTENT":
        "Change content placement through a new context group, suspend the legacy placement, "
        "and reuse the unchanged document by identifier without resubmitting its file or element.",
    "CREATE_NEW_CONTEXT_GROUP_AND_SUSPEND_OLD":
        "Change context-group metadata through a new context group, suspend the previous group, "
        "and reuse the unchanged document by identifier without resubmitting its file or element.",
    "DECLARE_MANUFACTURER_PARTITIONING":
        "Record the manufacturer's content-partitioning requirements and distinguishing values.",
    "DECLARE_METADATA_MIGRATION_INTENT":
        "Record the intended preservation or modification of context-group metadata.",
    "HUMAN_VERIFY_STALE_CONTENT":
        "Have a human review cited content and references against the target context "
        "and document any corrections needed.",
    "NO_MATERIAL_REPAIR":
        "Retain the document and its context without material changes.",
    "PRESERVE_EXACT_CONTEXT_GROUP_KEYWORDS":
        "Retain the existing context-group keyword codes and values unchanged.",
    "SELECT_SUPPORTED_REUSE_OPERATION":
        "Select and record an identifier-based content-reuse operation or obtain human "
        "review of new-artifact creation.",
    "VERIFY_HYPERLINK_RELEVANCE":
        "Have a human check hyperlink targets and relevance to the target context "
        "and document any corrections needed.",
    "WAIT_FOR_OPERATIONAL_AVAILABILITY":
        "Defer operational submission activity pending availability of the submission pathway.",
}


class OutputVocabulary(TypedDict):
    decisions: list[str]
    actions: list[str]
    action_definitions: dict[str, str]


def action_vocabulary_disclosure() -> dict[str, str | bool]:
    return {
        "version": ACTION_VOCABULARY_VERSION,
        "derived_from": "RegBridge's existing analyzer and rule repair semantics",
        "b0_b1_receive_taxonomy_in_input": True,
        "baseline_interpretation": (
            "B0 and B1 are evaluated with the proposed system's action taxonomy supplied; "
            "they are not naive generic-LLM baselines."
        ),
        "ordering": "alphabetical by action code; no frequency implication",
    }


def output_vocabulary() -> OutputVocabulary:
    # No conditions, rule IDs, case IDs, examples, labels, or decision/action mappings.
    return {
        "decisions": [item.value for item in Decision], "actions": list(ACTION_CODES),
        "action_definitions": {code: ACTION_DEFINITIONS[code] for code in ACTION_CODES},
    }
