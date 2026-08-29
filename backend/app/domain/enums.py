from enum import StrEnum


class Authority(StrEnum):
    FDA = "FDA"


class Center(StrEnum):
    CDER = "CDER"


class ApplicationType(StrEnum):
    NDA = "NDA"
    ANDA = "ANDA"
    IND = "IND"
    DMF = "DMF"


class StandardVersion(StrEnum):
    ECTD_3_2_2 = "eCTD-3.2.2"
    ECTD_4_0 = "eCTD-4.0"


class ReuseOperation(StrEnum):
    REFERENCE_EXISTING_CONTENT = "reference-existing-content"
    CREATE_NEW_TARGET_ARTIFACT = "create-new-target-artifact"


class Decision(StrEnum):
    REUSE_AS_LEGACY_REFERENCE = "REUSE_AS_LEGACY_REFERENCE"
    REUSE_WITH_NEW_CONTEXT = "REUSE_WITH_NEW_CONTEXT"
    REUSE_AFTER_METADATA_REPAIR = "REUSE_AFTER_METADATA_REPAIR"
    BREAK_LIFECYCLE_AND_RESUBMIT = "BREAK_LIFECYCLE_AND_RESUBMIT"
    DO_NOT_REUSE = "DO_NOT_REUSE"
    HUMAN_REGULATORY_REVIEW = "HUMAN_REGULATORY_REVIEW"


class Severity(StrEnum):
    INFORMATIONAL = "informational"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    BLOCKING = "blocking"
    UNRESOLVED = "unresolved"


class Bindingness(StrEnum):
    REQUIREMENT = "requirement"
    VALIDATION = "validation"
    RECOMMENDATION = "recommendation"
    INFORMATIVE = "informative"


class ReviewStatus(StrEnum):
    CANDIDATE = "candidate"
    REVIEWED = "reviewed"
    AUTHORITATIVE_FOR_DEMO = "authoritative_for_demo"
    REJECTED = "rejected"


class ExtractionMethod(StrEnum):
    MANUAL = "manual"
    DETERMINISTIC = "deterministic"
    MODEL_CANDIDATE = "model_candidate"


class TraceStepKind(StrEnum):
    DETERMINISTIC = "deterministic"
    MODEL_ASSISTED = "model_assisted"
    SYNTHESIS = "synthesis"


class LlmMode(StrEnum):
    FIXTURE = "fixture"
    LIVE = "live"
    DISABLED = "disabled"

