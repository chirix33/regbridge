from pydantic import Field, model_validator

from app.domain.enums import LifecycleOperation, StandardVersion
from app.domain.models import DomainModel, Sha256, StableId


class ParseWarning(DomainModel):
    code: StableId
    message: str = Field(min_length=1)
    locator: str = Field(min_length=1)


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
