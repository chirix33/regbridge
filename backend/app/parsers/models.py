from typing import Literal

from pydantic import Field, model_validator

from app.domain.enums import LifecycleOperation, StandardVersion
from app.domain.models import DomainModel, Sha256, StableId

PolicyCoverageStatus = Literal[
    "EVALUATED_WITH_APPROVED_POLICY",
    "NO_MIGRATION_CHANGE_DETECTED",
    "OUTSIDE_ENCODED_POLICY_COVERAGE",
    "INSUFFICIENT_APPLICATION_HISTORY",
    "DOCUMENT_INSPECTION_INCOMPLETE",
]


class ParseWarning(DomainModel):
    code: StableId
    message: str = Field(min_length=1)
    locator: str = Field(min_length=1)


class ParsedKeyword(DomainModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    raw_value: str = Field(min_length=1)
    normalized_value: str = Field(min_length=1)
    source_locator: str = Field(min_length=1)


class ParsedTextSpan(DomainModel):
    id: StableId
    page: int = Field(ge=1)
    text: str = Field(min_length=1, max_length=4000)
    locator: str = Field(min_length=1)


class ParsedHyperlink(DomainModel):
    id: StableId
    page: int = Field(ge=1)
    target_type: Literal["uri", "internal", "unsupported"]
    target: str = Field(min_length=1, max_length=2000)
    locator: str = Field(min_length=1)
    target_exists: bool | None = None
    author_verified_relevant: bool = False


class ParsedLeaf(DomainModel):
    id: StableId
    title: str = Field(min_length=1)
    heading: str = Field(pattern=r"^\d+(?:\.[A-Za-z0-9]+)+$")
    href: str = Field(min_length=1)
    operation: LifecycleOperation
    modified_leaf_id: StableId | None = None
    content_type: str = Field(pattern=r"^[a-z0-9][a-z0-9.+-]*/[a-z0-9][a-z0-9.+-]*$")
    file_sha256: Sha256
    declared_checksum_type: Literal["md5", "sha256"] | None = None
    declared_checksum: str | None = Field(
        default=None, pattern=r"^(?:[a-fA-F0-9]{32}|[a-f0-9]{64})$"
    )
    computed_declared_checksum: str | None = Field(
        default=None, pattern=r"^(?:[a-f0-9]{32}|[a-f0-9]{64})$"
    )
    declared_checksum_matches: bool | None = None
    raw_heading: str | None = None
    heading_status: Literal["recognized", "unsupported"] = "recognized"
    prior_reference_status: Literal["not_applicable", "resolved", "unresolved", "outside_scope"] = (
        "not_applicable"
    )
    source_locator: str = Field(min_length=1)
    keywords: tuple[ParsedKeyword, ...] = ()
    text_span_count: int = Field(default=0, ge=0)
    hyperlink_count: int = Field(default=0, ge=0)
    extraction_status: Literal["completed", "failed", "bounded"] = "completed"
    policy_coverage_status: PolicyCoverageStatus = "EVALUATED_WITH_APPROVED_POLICY"
    policy_coverage_basis: str = "Legacy controlled fixture policy coverage."
    covered_policy_ids: tuple[StableId, ...] = ()
    text_spans: tuple[ParsedTextSpan, ...] = Field(default=(), exclude=True)
    hyperlinks: tuple[ParsedHyperlink, ...] = Field(default=(), exclude=True)

    @model_validator(mode="after")
    def validate_checksum(self) -> "ParsedLeaf":
        checksum_fields = (
            self.declared_checksum_type,
            self.declared_checksum,
            self.computed_declared_checksum,
            self.declared_checksum_matches,
        )
        if any(value is not None for value in checksum_fields) and not all(
            value is not None for value in checksum_fields
        ):
            raise ValueError("declared checksum fields must be recorded together")
        if self.declared_checksum_matches is False:
            raise ValueError(f"declared checksum does not match file content for leaf {self.id}")
        if (
            self.operation
            in {
                LifecycleOperation.APPEND,
                LifecycleOperation.REPLACE,
                LifecycleOperation.DELETE,
            }
            and not self.modified_leaf_id
        ):
            raise ValueError(f"{self.operation.value} operations require modified_leaf_id")
        return self


class PackageFile(DomainModel):
    path: str = Field(min_length=1)
    member_type: Literal[
        "BACKBONE_XML",
        "REGIONAL_XML",
        "DOSSIER_DOCUMENT",
        "STUDY_TAGGING_FILE",
        "SUPPORT_FILE",
        "UNSUPPORTED",
    ]
    provenance_sha256: Sha256
    relationship: str = Field(min_length=1)
    declared_checksum_type: Literal["md5", "sha256"] | None = None
    declared_checksum: str | None = Field(
        default=None, pattern=r"^(?:[a-fA-F0-9]{32}|[a-f0-9]{64})$"
    )
    computed_declared_checksum: str | None = Field(
        default=None, pattern=r"^(?:[a-f0-9]{32}|[a-f0-9]{64})$"
    )
    declared_checksum_matches: bool | None = None


class ProfileCheck(DomainModel):
    id: StableId
    label: str = Field(min_length=1)
    status: Literal["passed", "warning", "unsupported", "failed"]
    detail: str = Field(min_length=1)


class XmlDeclarationRecord(DomainModel):
    path: str = Field(min_length=1)
    xml_version: str | None = None
    root_name: str = Field(min_length=1)
    namespace: str | None = None
    declared_doctype: str | None = None
    doctype_recognized: bool
    dtd_version_supported: bool
    dtd_validation_performed: bool = False
    dtd_validation_result: Literal["not_performed", "passed", "failed"] = "not_performed"
    dtd_asset_id: StableId | None = None
    effective_dtd_version: str | None = None
    version_source: Literal["declared", "inferred_from_catalog", "unsupported"] = "unsupported"


class LifecycleReference(DomainModel):
    leaf_id: StableId
    operation: LifecycleOperation
    href: str | None = None
    modified_file: str | None = None
    prior_reference_status: Literal["resolved", "unresolved", "outside_scope"]
    source_locator: str = Field(min_length=1)


class ApplicationInventory(DomainModel):
    id: StableId
    fixture_id: StableId | None = None
    source_standard: StandardVersion
    application_number: str | None = None
    submission_type: str | None = None
    application_type_code: str | None = None
    submission_id: str | None = None
    sequence_number: str | None = None
    applicant_name: str | None = None
    has_stf: bool
    package_sha256: Sha256
    leaves: tuple[ParsedLeaf, ...] = Field(min_length=1)
    warnings: tuple[ParseWarning, ...] = ()
    input_profile_id: StableId = "legacy-controlled-layout-v1"
    input_profile_version: str = "1.0.0"
    detected_sequence_root: str = "."
    layout: Literal["authentic_sequence_layout", "legacy_controlled_layout"] = (
        "legacy_controlled_layout"
    )
    parsing_extent: Literal["complete", "bounded"] = "complete"
    package_profile_status: Literal["passed", "warning", "unsupported", "failed"] = "warning"
    profile_checks: tuple[ProfileCheck, ...] = ()
    xml_declarations: tuple[XmlDeclarationRecord, ...] = ()
    package_files: tuple[PackageFile, ...] = ()
    lifecycle_references: tuple[LifecycleReference, ...] = ()
    policy_coverage_counts: dict[PolicyCoverageStatus, int] = Field(default_factory=dict)
    regional_xml_version: str | None = None
    regional_xml_sha256: Sha256 | None = None
    index_md5_declared: str | None = Field(default=None, pattern=r"^[a-fA-F0-9]{32}$")
    index_md5_computed: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")
    index_md5_matches: bool | None = None

    @model_validator(mode="after")
    def validate_leaf_ids(self) -> "ApplicationInventory":
        leaf_ids = [leaf.id for leaf in self.leaves]
        if len(leaf_ids) != len(set(leaf_ids)):
            raise ValueError("leaf identifiers must be unique")
        return self


class FixtureSummary(DomainModel):
    id: StableId
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    expected_class: str = Field(pattern=r"^(positive|negative|ambiguous)$")
    archetype: str = Field(
        pattern=r"^(unavailable-heading|legacy-metadata-tension|stale-content-or-hyperlink)$"
    )
    default_metadata_intent: str | None = Field(
        default=None,
        pattern=r"^(preserve-existing-lifecycle|normalize-metadata|unspecified)$",
    )
    manufacturer_partitioning: str | None = Field(
        default=None, pattern=r"^(unnecessary|required|unknown)$"
    )
    replacement_manufacturer_value: str | None = None
    author_verified_relevant_hyperlink_ids: tuple[StableId, ...] = ()
