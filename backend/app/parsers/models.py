from typing import Literal

from pydantic import Field, model_validator

from app.domain.enums import LifecycleOperation, StandardVersion
from app.domain.models import DomainModel, Sha256, StableId


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
    declared_checksum: Sha256 | None = None
    source_locator: str = Field(min_length=1)
    keywords: tuple[ParsedKeyword, ...] = ()
    text_span_count: int = Field(default=0, ge=0)
    hyperlink_count: int = Field(default=0, ge=0)
    extraction_status: Literal["completed", "failed", "bounded"] = "completed"
    text_spans: tuple[ParsedTextSpan, ...] = Field(default=(), exclude=True)
    hyperlinks: tuple[ParsedHyperlink, ...] = Field(default=(), exclude=True)

    @model_validator(mode="after")
    def validate_checksum(self) -> "ParsedLeaf":
        if self.declared_checksum and self.declared_checksum != self.file_sha256:
            raise ValueError(f"declared checksum does not match file content for leaf {self.id}")
        if self.operation == LifecycleOperation.REPLACE and not self.modified_leaf_id:
            raise ValueError("replace operations require modified_leaf_id")
        return self


class ApplicationInventory(DomainModel):
    id: StableId
    fixture_id: StableId | None = None
    source_standard: StandardVersion
    application_number: str | None = None
    submission_type: str | None = None
    applicant_name: str | None = None
    has_stf: bool
    package_sha256: Sha256
    leaves: tuple[ParsedLeaf, ...] = Field(min_length=1)
    warnings: tuple[ParseWarning, ...] = ()

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
