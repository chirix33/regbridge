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


class MetadataMigrationIntent(StrEnum):
    PRESERVE_EXISTING_LIFECYCLE = "preserve-existing-lifecycle"
    NORMALIZE_METADATA = "normalize-metadata"
    UNSPECIFIED = "unspecified"


class ManufacturerPartitioning(StrEnum):
    UNNECESSARY = "unnecessary"
    REQUIRED = "required"
    UNKNOWN = "unknown"


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
    SOURCE_VERIFIED = "source_verified"
    AUTHOR_ADJUDICATED_FOR_DEMO = "author_adjudicated_for_demo"
    REJECTED = "rejected"


class ReviewDecision(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class VerificationBasis(StrEnum):
    DIRECT_STANDARD_ENCODING = "direct_standard_encoding"
    MECHANICAL_DERIVATION = "mechanical_derivation"
    AUTHOR_INTERPRETATION = "author_interpretation"
    SEMANTIC_INFERENCE = "semantic_inference"
    SYNTHETIC_ASSUMPTION = "synthetic_assumption"


class EnforcementMode(StrEnum):
    HARD = "hard"
    ADVISORY = "advisory"
    SEMANTIC_SIGNAL = "semantic_signal"
    DISABLED = "disabled"


class ScenarioMode(StrEnum):
    PROSPECTIVE_FORWARD_COMPATIBILITY = "prospective_forward_compatibility"
    CURRENT_OPERATIONAL = "current_operational"


class OperationalStatus(StrEnum):
    NOT_OPERATIONAL = "not_operational"


class LifecycleOperation(StrEnum):
    NEW = "new"
    REPLACE = "replace"
    APPEND = "append"
    DELETE = "delete"


class NodeType(StrEnum):
    ARTIFACT = "artifact"
    STANDARD = "standard"
    STANDARD_VERSION = "standard_version"
    HEADING = "heading"
    EVIDENCE = "evidence"
    RULE = "rule"
    REPAIR = "repair"
    DECISION = "decision"
    KEYWORD = "keyword"
    DOSSIER_EVIDENCE = "dossier_evidence"
    MODEL_FINDING = "model_finding"


class EdgeType(StrEnum):
    LOCATED_UNDER = "LOCATED_UNDER"
    AVAILABLE_IN = "AVAILABLE_IN"
    REMOVED_IN = "REMOVED_IN"
    MAPS_TO = "MAPS_TO"
    SUPPORTED_BY = "SUPPORTED_BY"
    REQUIRES_REPAIR = "REQUIRES_REPAIR"
    TRIGGERS_DECISION = "TRIGGERS_DECISION"
    HAS_KEYWORD = "HAS_KEYWORD"
    CITES = "CITES"
    ABOUT = "ABOUT"
    OBSERVES = "OBSERVES"


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
