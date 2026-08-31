"""Case-independent output contracts, derived from existing repair semantics only."""

from typing import Literal, get_args

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
ACTION_VOCABULARY_VERSION = "2.0.0-proposed"


def output_vocabulary() -> dict[str, list[str]]:
    # No conditions, rule IDs, case IDs, examples, labels, or decision/action mappings.
    return {"decisions": [item.value for item in Decision], "actions": list(ACTION_CODES)}
