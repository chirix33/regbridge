"""Pinned-public-standards FDA/CDER eCTD v3.2.2 input profile.

The parser validates only the declared M4.2 profile. It is not a complete FDA validator.
Every external DTD request is resolved by an exact immutable local catalog; network and ambient
filesystem fallback are prohibited.
"""

from __future__ import annotations

import difflib
import hashlib
import re
from collections import Counter
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal, cast

import yaml
from lxml import etree  # type: ignore[import-untyped]

from app.config import REPOSITORY_ROOT
from app.domain.enums import LifecycleOperation, StandardVersion
from app.parsers.ectd322 import (
    EctdParseError,
    EctdSecurityError,
    _extract_pdf_evidence,
    _normalize_keyword,
    _package_digest,
    _safe_relative_path,
    extracted_archive,
)
from app.parsers.models import (
    ApplicationInventory,
    LifecycleReference,
    PackageFile,
    ParsedKeyword,
    ParsedLeaf,
    ParseWarning,
    PolicyCoverageStatus,
    ProfileCheck,
    XmlDeclarationRecord,
)

PROFILE_ID = "fda-cder-ectd-322-public-standards-profile-v1"
PROFILE_VERSION = "1.0.0"
PROFILE_ROOT = REPOSITORY_ROOT / "data" / "input-profiles" / "fda-cder-ectd-322-public-standards-v1"
MANIFEST_PATH = PROFILE_ROOT / "manifest.yaml"
INDEX_DTD_ASSET_ID = "ich-ectd-dtd-v3-2"
REGIONAL_DTD_ASSET_ID = "fda-us-regional-dtd-v3-3"
INDEX_ROOT = "ectd:ectd"
INDEX_NAMESPACE = "http://www.ich.org/ectd"
REGIONAL_ROOT = "fda-regional:fda-regional"
REGIONAL_NAMESPACE = "http://www.ich.org/fda"
CASE_A_HEADINGS = {"3.2.S.1.1", "3.2.S.1.2", "3.2.S.1.3"}
_DOCTYPE = re.compile(
    rb"<!DOCTYPE\s+(?P<root>[A-Za-z_][\w:.-]*)\s+(?:SYSTEM\s+[\"'](?P<system>[^\"']+)[\"']|PUBLIC\s+[\"'][^\"']+[\"']\s+[\"'](?P<public_system>[^\"']+)[\"'])\s*>",
    re.IGNORECASE,
)
_XML_DECLARATION = re.compile(rb"<\?xml\s+version=[\"']([^\"']+)[\"'][^?]*\?>", re.I)
_MD5 = re.compile(r"^[a-fA-F0-9]{32}$")
_KEYWORD_ATTRIBUTES = {"manufacturer", "substance", "product-name", "dosageform"}
_STABLE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


@dataclass(frozen=True)
class CatalogAsset:
    asset_id: str
    version: str
    path: Path
    sha256: str
    system_identifiers: tuple[str, ...]
    official_md5: str | None = None
    byte_identity_required: bool = False
    byte_identity_basis: str | None = None


@dataclass(frozen=True)
class IndependentValidationResult:
    path: str
    dtd_asset_id: str
    valid: bool
    detail: str


@dataclass(frozen=True)
class DtdTextDifference:
    archive_line: int | None
    archive_text: str | None
    pinned_line: int | None
    pinned_text: str | None


@dataclass(frozen=True)
class ArchiveDtdComparison:
    archive_path: str
    pinned_asset_id: str
    archive_sha256: str
    pinned_sha256: str
    archive_size: int
    pinned_size: int
    raw_bytes_equal: bool
    normalized_text_equal: bool
    semantic_text_equal: bool
    difference_class: Literal[
        "byte_identical", "non_substantive_text_only", "comment_only", "substantive"
    ]
    first_substantive_differences: tuple[DtdTextDifference, ...]
    hostile: bool
    hostile_reasons: tuple[str, ...]
    archive_copy_ignored: bool = True


@dataclass(frozen=True)
class IndependentPackageAdjudication:
    status: Literal["accepted", "rejected_nonconforming", "security_violation"]
    dtd_comparisons: tuple[ArchiveDtdComparison, ...]
    xml_validations: tuple[IndependentValidationResult, ...]
    byte_identity_required: bool
    byte_identity_basis: str | None
    warning_codes: tuple[str, ...]
    errors: tuple[str, ...]


class _ExactLocalResolver(etree.Resolver):
    def __init__(self, mapping: Mapping[str, Path]) -> None:
        super().__init__()
        self._mapping = dict(mapping)

    def resolve(self, url: str, public_id: str | None, context: object) -> object:
        del public_id
        target = self._mapping.get(url)
        if target is None:
            raise OSError(f"external resource is outside the approved local catalog: {url}")
        return self.resolve_filename(str(target), context)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _compatibility_md5(payload: bytes) -> str:
    try:
        return hashlib.md5(payload, usedforsecurity=False).hexdigest()
    except TypeError:  # pragma: no cover
        return hashlib.md5(payload).hexdigest()


def _normalize_dtd_text(payload: bytes) -> str:
    if b"\x00" in payload:
        raise ValueError("NUL byte is not permitted in a bundled DTD")
    text = payload.decode("utf-8-sig", "strict").replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in text.split("\n"))


def _without_xml_comments(text: str) -> str:
    return re.sub(
        r"<!--.*?-->",
        lambda match: "\n" * match.group(0).count("\n"),
        text,
        flags=re.DOTALL,
    )


def _semantic_dtd_lines(text: str) -> tuple[tuple[int, str], ...]:
    comment_free = _without_xml_comments(text)
    declaration_free = re.sub(
        r"<\?xml\s+[^?]*\?>",
        lambda match: "\n" * match.group(0).count("\n"),
        comment_free,
        flags=re.IGNORECASE,
    )
    return tuple(
        (number, line)
        for number, line in enumerate(declaration_free.split("\n"), start=1)
        if line.strip()
    )


def _first_dtd_differences(
    archive: tuple[tuple[int, str], ...],
    pinned: tuple[tuple[int, str], ...],
    *,
    limit: int = 5,
) -> tuple[DtdTextDifference, ...]:
    matcher = difflib.SequenceMatcher(
        a=[line for _, line in archive],
        b=[line for _, line in pinned],
        autojunk=False,
    )
    differences: list[DtdTextDifference] = []
    for tag, archive_start, archive_end, pinned_start, pinned_end in matcher.get_opcodes():
        if tag == "equal":
            continue
        width = max(archive_end - archive_start, pinned_end - pinned_start)
        for offset in range(width):
            archive_item = (
                archive[archive_start + offset]
                if archive_start + offset < archive_end
                else None
            )
            pinned_item = (
                pinned[pinned_start + offset]
                if pinned_start + offset < pinned_end
                else None
            )
            differences.append(
                DtdTextDifference(
                    archive_line=archive_item[0] if archive_item else None,
                    archive_text=archive_item[1][:500] if archive_item else None,
                    pinned_line=pinned_item[0] if pinned_item else None,
                    pinned_text=pinned_item[1][:500] if pinned_item else None,
                )
            )
            if len(differences) == limit:
                return tuple(differences)
    return tuple(differences)


def _hostile_dtd_reasons(normalized_text: str) -> tuple[str, ...]:
    comment_free = _without_xml_comments(normalized_text)
    reasons: list[str] = []
    if re.search(
        r"<!ENTITY\s+(?:%\s+)?[A-Za-z_:][\w:.-]*\s+(?:SYSTEM|PUBLIC)\b",
        comment_free,
        re.IGNORECASE,
    ):
        reasons.append("external entity declaration")
    if re.search(r"<!DOCTYPE\b", comment_free, re.IGNORECASE):
        reasons.append("nested DOCTYPE declaration")
    if re.search(r"<!\[(?:INCLUDE|IGNORE)\[", comment_free, re.IGNORECASE):
        reasons.append("conditional DTD section")
    return tuple(reasons)


def load_catalog() -> dict[str, CatalogAsset]:
    payload = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))
    if payload.get("profile_id") != PROFILE_ID or payload.get("profile_version") != PROFILE_VERSION:
        raise EctdParseError("M4.2 input-profile manifest identity is invalid")
    if payload.get("runtime_network_access") != "prohibited":
        raise EctdParseError("M4.2 input-profile manifest must prohibit runtime network access")
    assets: dict[str, CatalogAsset] = {}
    for record in payload.get("assets", []):
        relative = PurePosixPath(str(record["local_path"]))
        if relative.is_absolute() or ".." in relative.parts:
            raise EctdSecurityError("input-profile asset path escapes the profile directory")
        path = (PROFILE_ROOT / Path(*relative.parts)).resolve()
        try:
            path.relative_to(PROFILE_ROOT.resolve())
        except ValueError as error:
            raise EctdSecurityError(
                "input-profile asset path escapes the profile directory"
            ) from error
        expected = str(record["sha256"])
        if not path.is_file() or _sha256(path) != expected:
            raise EctdParseError(f"pinned input-profile asset digest mismatch: {record['id']}")
        official_md5 = str(record["official_md5"]) if record.get("official_md5") else None
        if official_md5 and _compatibility_md5(path.read_bytes()) != official_md5:
            raise EctdParseError(
                f"pinned input-profile asset official MD5 mismatch: {record['id']}"
            )
        byte_identity = record.get("byte_identity_requirement") or {}
        assets[str(record["id"])] = CatalogAsset(
            asset_id=str(record["id"]),
            version=str(record["version"]),
            path=path,
            sha256=expected,
            system_identifiers=tuple(
                str(item) for item in record.get("approved_system_identifiers", [])
            ),
            official_md5=official_md5,
            byte_identity_required=bool(byte_identity.get("required", False)),
            byte_identity_basis=str(byte_identity["basis"])
            if byte_identity.get("basis")
            else None,
        )
    for required in (INDEX_DTD_ASSET_ID, REGIONAL_DTD_ASSET_ID):
        if required not in assets:
            raise EctdParseError(f"required DTD asset is absent: {required}")
    return assets


def compare_archive_dtd(
    archive_dtd: Path, sequence_root: Path, pinned_asset: CatalogAsset
) -> ArchiveDtdComparison:
    """Compare an untrusted archive DTD without parsing or resolving through it."""
    archive_payload = archive_dtd.read_bytes()
    pinned_payload = pinned_asset.path.read_bytes()
    archive_sha256 = hashlib.sha256(archive_payload).hexdigest()
    raw_equal = archive_payload == pinned_payload
    hostile_reasons: tuple[str, ...] = ()
    try:
        archive_text = _normalize_dtd_text(archive_payload)
        pinned_text = _normalize_dtd_text(pinned_payload)
        normalized_equal = archive_text == pinned_text
        archive_semantic = _semantic_dtd_lines(archive_text)
        pinned_semantic = _semantic_dtd_lines(pinned_text)
        semantic_equal = tuple(line for _, line in archive_semantic) == tuple(
            line for _, line in pinned_semantic
        )
        hostile_reasons = _hostile_dtd_reasons(archive_text)
        differences = _first_dtd_differences(archive_semantic, pinned_semantic)
    except UnicodeDecodeError:
        archive_text = ""
        normalized_equal = False
        semantic_equal = False
        differences = ()
        hostile_reasons = ("bundled DTD is not valid UTF-8",)
    except ValueError as error:
        archive_text = ""
        normalized_equal = False
        semantic_equal = False
        differences = ()
        hostile_reasons = (str(error),)
    if raw_equal:
        difference_class: Literal[
            "byte_identical", "non_substantive_text_only", "comment_only", "substantive"
        ] = "byte_identical"
    elif normalized_equal:
        difference_class = "non_substantive_text_only"
    elif semantic_equal:
        difference_class = "comment_only"
    else:
        difference_class = "substantive"
    return ArchiveDtdComparison(
        archive_path=archive_dtd.relative_to(sequence_root).as_posix(),
        pinned_asset_id=pinned_asset.asset_id,
        archive_sha256=archive_sha256,
        pinned_sha256=pinned_asset.sha256,
        archive_size=len(archive_payload),
        pinned_size=len(pinned_payload),
        raw_bytes_equal=raw_equal,
        normalized_text_equal=normalized_equal,
        semantic_text_equal=semantic_equal,
        difference_class=difference_class,
        first_substantive_differences=differences,
        hostile=bool(hostile_reasons),
        hostile_reasons=hostile_reasons,
    )


def _doctype(payload: bytes, relative: str) -> tuple[str, str]:
    lowered = payload.lower()
    if lowered.count(b"<!doctype") != 1:
        raise EctdSecurityError(f"{relative} requires exactly one approved DOCTYPE declaration")
    if b"<!entity" in lowered:
        raise EctdSecurityError(f"entity declarations are not permitted in {relative}")
    match = _DOCTYPE.search(payload)
    if match is None:
        raise EctdSecurityError(
            f"internal subsets or malformed DOCTYPE declarations are not permitted in {relative}"
        )
    declaration = lowered[lowered.index(b"<!doctype") : match.end()]
    if b"[" in declaration or b"]" in declaration:
        raise EctdSecurityError(f"internal subsets are not permitted in {relative}")
    system = (match.group("system") or match.group("public_system")).decode("utf-8", "strict")
    return match.group("root").decode("ascii"), system


def _validated_xml(
    path: Path,
    relative: str,
    *,
    asset: CatalogAsset,
    expected_doctype_root: str,
    expected_namespace: str,
    expected_local_root: str,
    expected_declared_version: str,
    inferred_source_version: str,
) -> tuple[etree._Element, XmlDeclarationRecord, bool]:
    payload = path.read_bytes()
    doctype_root, system_id = _doctype(payload, relative)
    if doctype_root != expected_doctype_root:
        raise EctdParseError(
            f"{relative} DOCTYPE root {doctype_root!r} conflicts with {expected_doctype_root!r}"
        )
    if system_id not in asset.system_identifiers:
        raise EctdSecurityError(f"unknown DOCTYPE identifier for {relative}: {system_id}")
    parser = etree.XMLParser(
        load_dtd=True,
        dtd_validation=True,
        attribute_defaults=False,
        resolve_entities=False,
        no_network=True,
        recover=False,
        huge_tree=False,
        remove_comments=False,
        remove_pis=False,
    )
    parser.resolvers.add(_ExactLocalResolver({system_id: asset.path}))
    try:
        root = etree.fromstring(payload, parser=parser)
    except (etree.XMLSyntaxError, OSError) as error:
        detail = str(error).splitlines()[0]
        raise EctdParseError(f"pinned DTD validation failed for {relative}: {detail}") from error
    qname = etree.QName(root)
    if qname.localname != expected_local_root or qname.namespace != expected_namespace:
        raise EctdParseError(
            f"{relative} root/namespace conflicts with the approved {asset.asset_id} profile"
        )
    root_start = re.search(
        rb"<\s*" + re.escape(expected_doctype_root.encode("ascii")) + rb"\b(?P<attrs>[^>]*)>",
        payload,
        re.IGNORECASE,
    )
    explicit_version = (
        re.search(rb"\bdtd-version\s*=\s*[\"']([^\"']+)[\"']", root_start.group("attrs"), re.I)
        if root_start is not None
        else None
    )
    declared_version = explicit_version.group(1).decode("utf-8") if explicit_version else None
    inferred = declared_version is None
    if declared_version is not None and declared_version != expected_declared_version:
        raise EctdParseError(
            f"{relative} declares unsupported dtd-version {declared_version!r}; "
            f"expected {expected_declared_version}"
        )
    declaration_match = _XML_DECLARATION.search(payload)
    return (
        root,
        XmlDeclarationRecord(
            path=relative,
            xml_version=declaration_match.group(1).decode() if declaration_match else None,
            root_name=expected_doctype_root,
            namespace=qname.namespace,
            declared_doctype=system_id,
            doctype_recognized=True,
            dtd_version_supported=True,
            dtd_validation_performed=True,
            dtd_validation_result="passed",
            dtd_asset_id=asset.asset_id,
            effective_dtd_version=inferred_source_version if inferred else declared_version,
            version_source="inferred_from_catalog" if inferred else "declared",
        ),
        inferred,
    )


def _without_doctype(payload: bytes, relative: str) -> bytes:
    _doctype(payload, relative)
    match = _DOCTYPE.search(payload)
    if match is None:  # pragma: no cover - checked by _doctype
        raise EctdSecurityError(f"missing approved DOCTYPE in {relative}")
    return payload[: match.start()] + payload[match.end() :]


def independent_validate_xml(
    xml_path: Path, relative: str, dtd_asset_id: str
) -> IndependentValidationResult:
    """Validate by directly applying the pinned DTD, independently of parser resolution."""
    asset = load_catalog()[dtd_asset_id]
    safe_payload = _without_doctype(xml_path.read_bytes(), relative)
    parser = etree.XMLParser(
        load_dtd=False, resolve_entities=False, no_network=True, huge_tree=False
    )
    try:
        root = etree.fromstring(safe_payload, parser=parser)
        with asset.path.open("rb") as stream:
            dtd = etree.DTD(stream)
        valid = dtd.validate(root)
        validation_errors = tuple(str(item) for item in dtd.error_log.filter_from_errors())
        detail = "passed" if valid else " | ".join(validation_errors)
        if not valid and not detail:
            detail = "pinned DTD validation failed without a detailed libxml error"
    except (etree.XMLSyntaxError, etree.DTDParseError) as error:
        valid = False
        detail = f"{type(error).__name__}: {error}"
    return IndependentValidationResult(relative, dtd_asset_id, valid, detail)


def _sequence_root(extraction_root: Path) -> tuple[Path, str]:
    candidates = sorted(
        path
        for path in extraction_root.rglob("*")
        if path.is_file() and path.name.casefold() == "index.xml"
    )
    if not candidates:
        raise EctdParseError("no supported sequence root containing index.xml was found")
    if len(candidates) != 1:
        raise EctdParseError("multiple ambiguous sequence roots containing index.xml were found")
    root = candidates[0].parent.resolve()
    relative = root.relative_to(extraction_root.resolve()).as_posix()
    parts = () if relative == "." else PurePosixPath(relative).parts
    valid = not parts or parts == ("0000",) or (len(parts) == 2 and parts[-1] == "0000")
    if not valid:
        raise EctdParseError(
            "sequence root must be archive root, 0000/, or one application/0000 wrapper"
        )
    return root, relative


def adjudicate_public_profile_directory(
    directory: Path,
    *,
    enforce_official_byte_identity: bool | None = None,
) -> IndependentPackageAdjudication:
    """Adjudicate archive DTD data and validate both XML files only with pinned DTDs."""
    catalog = load_catalog()
    sequence_root, _ = _sequence_root(directory.resolve())
    index_path = sequence_root / "index.xml"
    regional_path = sequence_root / "m1" / "us" / "us-regional.xml"
    if not regional_path.is_file():
        return IndependentPackageAdjudication(
            status="rejected_nonconforming",
            dtd_comparisons=(),
            xml_validations=(),
            byte_identity_required=catalog[INDEX_DTD_ASSET_ID].byte_identity_required,
            byte_identity_basis=catalog[INDEX_DTD_ASSET_ID].byte_identity_basis,
            warning_codes=(),
            errors=("supported profile requires m1/us/us-regional.xml",),
        )
    validations = (
        independent_validate_xml(index_path, "index.xml", INDEX_DTD_ASSET_ID),
        independent_validate_xml(
            regional_path,
            "m1/us/us-regional.xml",
            REGIONAL_DTD_ASSET_ID,
        ),
    )
    pinned_ich = catalog[INDEX_DTD_ASSET_ID]
    archive_dtds = sorted(
        path
        for path in sequence_root.rglob("*")
        if path.is_file() and path.name.casefold() == pinned_ich.path.name.casefold()
    )
    comparisons = tuple(
        compare_archive_dtd(path, sequence_root, pinned_ich) for path in archive_dtds
    )
    required = (
        pinned_ich.byte_identity_required
        if enforce_official_byte_identity is None
        else enforce_official_byte_identity
    )
    hostile_errors = tuple(
        f"{item.archive_path}: {reason}"
        for item in comparisons
        for reason in item.hostile_reasons
    )
    if hostile_errors:
        return IndependentPackageAdjudication(
            status="security_violation",
            dtd_comparisons=comparisons,
            xml_validations=validations,
            byte_identity_required=required,
            byte_identity_basis=pinned_ich.byte_identity_basis if required else None,
            warning_codes=(),
            errors=hostile_errors,
        )
    validation_errors = tuple(
        f"{item.path}: {item.detail}" for item in validations if not item.valid
    )
    if validation_errors:
        return IndependentPackageAdjudication(
            status="rejected_nonconforming",
            dtd_comparisons=comparisons,
            xml_validations=validations,
            byte_identity_required=required,
            byte_identity_basis=pinned_ich.byte_identity_basis if required else None,
            warning_codes=(),
            errors=validation_errors,
        )
    differing = tuple(item for item in comparisons if not item.raw_bytes_equal)
    if differing and required:
        basis = pinned_ich.byte_identity_basis or "exact official byte-identity requirement"
        return IndependentPackageAdjudication(
            status="rejected_nonconforming",
            dtd_comparisons=comparisons,
            xml_validations=validations,
            byte_identity_required=True,
            byte_identity_basis=basis,
            warning_codes=(),
            errors=(f"archive ICH DTD checksum differs from the pinned official copy; {basis}",),
        )
    warning_codes = (
        ("ARCHIVE_DTD_DIFFERS_FROM_PINNED_COPY",) if differing else ()
    )
    return IndependentPackageAdjudication(
        status="accepted",
        dtd_comparisons=comparisons,
        xml_validations=validations,
        byte_identity_required=required,
        byte_identity_basis=pinned_ich.byte_identity_basis if required else None,
        warning_codes=warning_codes,
        errors=(),
    )


def adjudicate_public_profile_zip(
    payload: bytes,
    *,
    enforce_official_byte_identity: bool | None = None,
) -> IndependentPackageAdjudication:
    with extracted_archive(payload) as directory:
        return adjudicate_public_profile_directory(
            directory,
            enforce_official_byte_identity=enforce_official_byte_identity,
        )


def _local_name(tag: object) -> str:
    return etree.QName(cast(str, tag)).localname


def _attribute(element: etree._Element, name: str) -> str | None:
    for raw_name, raw_value in element.attrib.items():
        if etree.QName(raw_name).localname == name:
            return str(raw_value).strip()
    return None


def _structural_heading(tag: object) -> str | None:
    local = _local_name(tag).casefold()
    match = re.fullmatch(r"m(?P<module>\d+)(?P<tail>(?:-[a-z0-9]+)+)", local)
    if not match:
        return None
    parts = [match.group("module")]
    for token in match.group("tail").strip("-").split("-"):
        if token.isdigit() or (len(token) == 1 and token in {"s", "p", "a", "r"}):
            parts.append(token.upper() if token.isalpha() else token)
        else:
            break
    return ".".join(parts) if len(parts) > 1 else None


def _iter_leaves(
    element: etree._Element, ancestors: tuple[etree._Element, ...] = ()
) -> Iterator[tuple[etree._Element, tuple[etree._Element, ...]]]:
    if _local_name(element.tag).casefold() == "leaf":
        yield element, ancestors
    for child in element:
        if isinstance(child.tag, str):
            yield from _iter_leaves(child, (*ancestors, element))


def _heading_and_keywords(
    ancestors: tuple[etree._Element, ...], source_xml: str
) -> tuple[str, str, tuple[ParsedKeyword, ...]]:
    heading: str | None = None
    raw_heading = "unsupported"
    keywords: dict[str, ParsedKeyword] = {}
    for node in ancestors:
        candidate = _structural_heading(node.tag)
        if candidate:
            heading = candidate
            raw_heading = _local_name(node.tag)
        for raw_name, raw_value in node.attrib.items():
            name = etree.QName(raw_name).localname.casefold()
            value = str(raw_value).strip()
            if name in _KEYWORD_ATTRIBUTES and value:
                keywords[name] = ParsedKeyword(
                    name=name,
                    raw_value=value,
                    normalized_value=_normalize_keyword(value),
                    source_locator=f"{source_xml} / {_local_name(node.tag)} / @{name}",
                )
    return (
        heading or "0.UNSUPPORTED",
        raw_heading,
        tuple(keywords[name] for name in sorted(keywords)),
    )


def _title(element: etree._Element, fallback: str) -> str:
    for child in element:
        if _local_name(child.tag).casefold() == "title" and child.text and child.text.strip():
            return " ".join(child.text.split())
    return fallback


def _safe_document_path(sequence_root: Path, href: str) -> Path:
    relative = _safe_relative_path(href)
    target = (sequence_root / Path(*relative.parts)).resolve()
    try:
        target.relative_to(sequence_root)
    except ValueError as error:
        raise EctdSecurityError("leaf reference escapes package root") from error
    if not target.is_file():
        raise EctdParseError(f"referenced leaf file is missing: {href}")
    return target


def _file_record(
    path: Path,
    root: Path,
    member_type: Literal[
        "BACKBONE_XML",
        "REGIONAL_XML",
        "DOSSIER_DOCUMENT",
        "STUDY_TAGGING_FILE",
        "SUPPORT_FILE",
        "UNSUPPORTED",
    ],
    relationship: str,
    *,
    declared_checksum: str | None = None,
    computed_checksum: str | None = None,
) -> PackageFile:
    return PackageFile(
        path=path.relative_to(root).as_posix(),
        member_type=member_type,
        provenance_sha256=_sha256(path),
        relationship=relationship,
        declared_checksum_type="md5" if declared_checksum else None,
        declared_checksum=declared_checksum,
        computed_declared_checksum=computed_checksum,
        declared_checksum_matches=True if declared_checksum else None,
    )


def _lifecycle_reference(
    raw: str, leaf_id: str
) -> tuple[str, Literal["resolved", "unresolved", "outside_scope"]]:
    if "#" not in raw:
        raise EctdParseError(f"modified-file for {leaf_id} must include an index.xml fragment")
    location, fragment = raw.rsplit("#", 1)
    if not fragment or not _STABLE_ID.fullmatch(fragment):
        raise EctdParseError(f"modified-file for {leaf_id} has an invalid leaf fragment")
    normalized = location.replace("\\", "/")
    if not re.fullmatch(r"(?:\.\./\d{4}/)?index\.xml", normalized, re.I):
        raise EctdParseError(f"modified-file for {leaf_id} is outside supported lifecycle syntax")
    return fragment, "unresolved" if normalized.startswith("../") else "resolved"


def _coverage(
    heading: str,
    keywords: tuple[ParsedKeyword, ...],
    extraction_status: str,
    prior_status: str,
    text: str,
) -> tuple[PolicyCoverageStatus, str, tuple[str, ...]]:
    if extraction_status != "completed":
        return "DOCUMENT_INSPECTION_INCOMPLETE", "Bounded PDF inspection did not complete.", ()
    if prior_status == "unresolved":
        return (
            "INSUFFICIENT_APPLICATION_HISTORY",
            "The selected sequence lacks referenced prior history.",
            (),
        )
    manufacturer_all = any(
        item.name == "manufacturer" and item.normalized_value == "all" for item in keywords
    )
    if heading in CASE_A_HEADINGS:
        return (
            "EVALUATED_WITH_APPROVED_POLICY",
            "Exact approved Case A heading mapping applies.",
            ("FDA-CDER-M1-REMOVED-SUBHEADING-001",),
        )
    if manufacturer_all:
        return (
            "EVALUATED_WITH_APPROVED_POLICY",
            "Approved manufacturer metadata policy applies.",
            ("FDA-CDER-M2-MANUFACTURER-GENERAL-001",),
        )
    if "responsible applicant" in text.casefold():
        return (
            "EVALUATED_WITH_APPROVED_POLICY",
            "Bounded applicant-reference semantic policy applies.",
            ("FDA-CDER-M2-STALE-CONTENT-001",),
        )
    if heading == "3.2.S.1":
        return (
            "NO_MIGRATION_CHANGE_DETECTED",
            "Explicit encoded clean-negative 3.2.S.1 placement condition applies.",
            (),
        )
    return (
        "OUTSIDE_ENCODED_POLICY_COVERAGE",
        f"No encoded v4 migration policy covers heading {heading}.",
        (),
    )


def _regional_field(root: etree._Element, name: str) -> etree._Element | None:
    return next((item for item in root.iter() if _local_name(item.tag).casefold() == name), None)


def parse_public_profile_directory(
    directory: Path,
    *,
    enforce_official_byte_identity: bool | None = None,
) -> ApplicationInventory:
    catalog = load_catalog()
    extraction_root = directory.resolve()
    sequence_root, sequence_relative = _sequence_root(extraction_root)
    index_path = sequence_root / "index.xml"
    regional_path = sequence_root / "m1" / "us" / "us-regional.xml"
    if not regional_path.is_file():
        raise EctdParseError("supported profile requires m1/us/us-regional.xml")
    pinned_dtd_by_name = {
        asset.path.name.casefold(): asset for asset in catalog.values() if asset.system_identifiers
    }
    archive_ich_dtds: list[Path] = []
    for archive_dtd in sequence_root.rglob("*.dtd"):
        pinned = pinned_dtd_by_name.get(archive_dtd.name.casefold())
        if pinned is None:
            continue
        if pinned.asset_id == INDEX_DTD_ASSET_ID:
            archive_ich_dtds.append(archive_dtd)
        elif _sha256(archive_dtd) != pinned.sha256:
            raise EctdSecurityError(
                f"archive-supplied DTD conflicts with pinned catalog asset: {archive_dtd.name}"
            )

    adjudication: IndependentPackageAdjudication | None = None
    if archive_ich_dtds:
        adjudication = adjudicate_public_profile_directory(
            directory,
            enforce_official_byte_identity=enforce_official_byte_identity,
        )
        if adjudication.status == "security_violation":
            raise EctdSecurityError(
                "archive-supplied ICH DTD security violation: "
                + "; ".join(adjudication.errors)
            )
        if adjudication.status == "rejected_nonconforming":
            raise EctdParseError(
                "independent package adjudication rejected_nonconforming: "
                + "; ".join(adjudication.errors)
            )

    index_root, index_record, inferred_index = _validated_xml(
        index_path,
        "index.xml",
        asset=catalog[INDEX_DTD_ASSET_ID],
        expected_doctype_root=INDEX_ROOT,
        expected_namespace=INDEX_NAMESPACE,
        expected_local_root="ectd",
        expected_declared_version="3.2",
        inferred_source_version="3.2.2",
    )
    regional_root, regional_record, _ = _validated_xml(
        regional_path,
        "m1/us/us-regional.xml",
        asset=catalog[REGIONAL_DTD_ASSET_ID],
        expected_doctype_root=REGIONAL_ROOT,
        expected_namespace=REGIONAL_NAMESPACE,
        expected_local_root="fda-regional",
        expected_declared_version="3.3",
        inferred_source_version="3.3",
    )

    warnings: list[ParseWarning] = []
    if adjudication is not None:
        for comparison in adjudication.dtd_comparisons:
            if comparison.raw_bytes_equal:
                continue
            warnings.append(
                ParseWarning(
                    code="ARCHIVE_DTD_DIFFERS_FROM_PINNED_COPY",
                    message=(
                        f"Archive DTD {comparison.archive_sha256} differs from pinned "
                        f"{comparison.pinned_sha256} ({comparison.difference_class}); the "
                        "archive copy was ignored and the pinned local DTD was used."
                    ),
                    locator=comparison.archive_path,
                )
            )
    if inferred_index:
        warnings.append(
            ParseWarning(
                code="index-dtd-version-inferred",
                message=(
                    "index.xml omitted dtd-version; eCTD v3.2.2 was inferred from the "
                    "approved DTD/root/namespace profile."
                ),
                locator="index.xml / ectd:ectd",
            )
        )
    files: list[PackageFile] = [
        _file_record(index_path, sequence_root, "BACKBONE_XML", "ICH eCTD backbone"),
        _file_record(
            regional_path, sequence_root, "REGIONAL_XML", "FDA Module 1 regional backbone"
        ),
    ]
    lifecycle: list[LifecycleReference] = []
    leaves: list[ParsedLeaf] = []
    seen_ids: set[str] = set()
    regional_relationship_found = False

    def consume(root: etree._Element, source_xml: str) -> None:
        nonlocal regional_relationship_found
        for element, ancestors in _iter_leaves(root):
            leaf_id = _attribute(element, "ID") or _attribute(element, "id")
            if not leaf_id or not _STABLE_ID.fullmatch(leaf_id) or leaf_id in seen_ids:
                raise EctdParseError("leaf IDs must be valid and unique across both backbones")
            seen_ids.add(leaf_id)
            operation_raw = (_attribute(element, "operation") or "").casefold()
            try:
                operation = LifecycleOperation(operation_raw)
            except ValueError as error:
                raise EctdParseError(f"unsupported lifecycle operation: {operation_raw}") from error
            href = _attribute(element, "href")
            modified_raw = _attribute(element, "modified-file")
            modified_id: str | None = None
            prior_status: Literal["resolved", "unresolved", "outside_scope"] = "resolved"
            if modified_raw:
                modified_id, prior_status = _lifecycle_reference(modified_raw, leaf_id)
            if (
                operation
                in {
                    LifecycleOperation.APPEND,
                    LifecycleOperation.REPLACE,
                    LifecycleOperation.DELETE,
                }
                and not modified_raw
            ):
                raise EctdParseError(f"{operation.value} leaf {leaf_id} requires modified-file")
            lifecycle.append(
                LifecycleReference(
                    leaf_id=leaf_id,
                    operation=operation,
                    href=href,
                    modified_file=modified_raw,
                    prior_reference_status=prior_status,
                    source_locator=f"{source_xml} / leaf[{leaf_id}]",
                )
            )
            if operation == LifecycleOperation.DELETE:
                continue
            if not href:
                raise EctdParseError(f"{operation.value} leaf {leaf_id} requires a file reference")
            target = _safe_document_path(sequence_root, href)
            declared_type = (_attribute(element, "checksum-type") or "").casefold()
            declared = _attribute(element, "checksum")
            if declared_type != "md5" or not declared or not _MD5.fullmatch(declared):
                raise EctdParseError(
                    f"leaf {leaf_id} requires a valid checksum-type=md5 declaration"
                )
            computed = _compatibility_md5(target.read_bytes())
            if declared.casefold() != computed:
                raise EctdParseError(
                    f"declared checksum does not match file content for leaf {leaf_id}"
                )
            normalized_href = PurePosixPath(href.replace("\\", "/")).as_posix()
            if source_xml == "index.xml" and normalized_href.casefold() == "m1/us/us-regional.xml":
                if operation != LifecycleOperation.NEW:
                    raise EctdParseError(
                        "the Module 1 backbone relationship must use operation=new"
                    )
                regional_relationship_found = True
                files[1] = _file_record(
                    regional_path,
                    sequence_root,
                    "REGIONAL_XML",
                    f"ICH backbone leaf {leaf_id}",
                    declared_checksum=declared.casefold(),
                    computed_checksum=computed,
                )
                continue
            if target.name.casefold() == "stf.xml":
                files.append(
                    _file_record(
                        target,
                        sequence_root,
                        "STUDY_TAGGING_FILE",
                        f"{source_xml} leaf {leaf_id}; STF content is inventoried but not executed",
                        declared_checksum=declared.casefold(),
                        computed_checksum=computed,
                    )
                )
                continue
            if target.suffix.casefold() != ".pdf" or not target.read_bytes().startswith(b"%PDF-"):
                files.append(
                    _file_record(
                        target,
                        sequence_root,
                        "UNSUPPORTED",
                        f"{source_xml} leaf {leaf_id}; not eligible for semantic analysis",
                        declared_checksum=declared.casefold(),
                        computed_checksum=computed,
                    )
                )
                warnings.append(
                    ParseWarning(
                        code="unsupported-dossier-member",
                        message=(
                            "Referenced member is structurally inventoried but is not a bounded "
                            "PDF and receives no migration decision."
                        ),
                        locator=f"{source_xml} / leaf[{leaf_id}] / {normalized_href}",
                    )
                )
                continue
            heading, raw_heading, keywords = _heading_and_keywords(
                (*ancestors, element), source_xml
            )
            spans, links, extraction_status, extraction_warning = _extract_pdf_evidence(
                target, leaf_id, set()
            )
            if extraction_warning:
                warnings.append(
                    ParseWarning(
                        code="pdf-evidence-incomplete",
                        message=extraction_warning,
                        locator=f"{source_xml} / leaf[{leaf_id}]",
                    )
                )
            text = " ".join(item.text for item in spans)
            coverage, basis, policy_ids = _coverage(
                heading, keywords, extraction_status, prior_status, text
            )
            leaves.append(
                ParsedLeaf(
                    id=leaf_id,
                    title=_title(element, target.stem),
                    heading=heading,
                    raw_heading=raw_heading,
                    heading_status="recognized" if heading != "0.UNSUPPORTED" else "unsupported",
                    href=normalized_href,
                    operation=operation,
                    modified_leaf_id=modified_id,
                    prior_reference_status=prior_status if modified_raw else "not_applicable",
                    content_type="application/pdf",
                    file_sha256=_sha256(target),
                    declared_checksum_type="md5",
                    declared_checksum=declared.casefold(),
                    computed_declared_checksum=computed,
                    declared_checksum_matches=True,
                    source_locator=f"{source_xml} / {raw_heading} / leaf[{leaf_id}]",
                    keywords=keywords,
                    text_span_count=len(spans),
                    hyperlink_count=len(links),
                    extraction_status=extraction_status,
                    policy_coverage_status=coverage,
                    policy_coverage_basis=basis,
                    covered_policy_ids=policy_ids,
                    text_spans=spans,
                    hyperlinks=links,
                )
            )
            files.append(
                _file_record(
                    target,
                    sequence_root,
                    "DOSSIER_DOCUMENT",
                    f"{source_xml} leaf {leaf_id}",
                    declared_checksum=declared.casefold(),
                    computed_checksum=computed,
                )
            )

    consume(index_root, "index.xml")
    consume(regional_root, "m1/us/us-regional.xml")
    if not regional_relationship_found:
        raise EctdParseError(
            "index.xml is missing the required leaf relationship to m1/us/us-regional.xml"
        )
    if not leaves:
        raise EctdParseError("package contains no bounded PDF dossier documents")

    index_md5_path = sequence_root / "index-md5.txt"
    index_md5_declared: str | None = None
    index_md5_computed: str | None = None
    index_md5_matches: bool | None = None
    if index_md5_path.is_file():
        values = [
            line.strip()
            for line in index_md5_path.read_text(encoding="ascii").splitlines()
            if line.strip()
        ]
        if len(values) != 1 or not _MD5.fullmatch(values[0]):
            raise EctdParseError("index-md5.txt must contain exactly one valid MD5 value")
        index_md5_declared = values[0].casefold()
        index_md5_computed = _compatibility_md5(index_path.read_bytes())
        index_md5_matches = index_md5_declared == index_md5_computed
        if not index_md5_matches:
            raise EctdParseError("index-md5.txt does not match index.xml")
        files.append(
            _file_record(
                index_md5_path, sequence_root, "SUPPORT_FILE", "index.xml compatibility checksum"
            )
        )
    else:
        warnings.append(
            ParseWarning(
                code="index-md5-missing",
                message="index-md5.txt was not supplied.",
                locator="index.xml",
            )
        )

    referenced = {item.path.casefold() for item in files}
    for path in sorted(item for item in sequence_root.rglob("*") if item.is_file()):
        relative = path.relative_to(sequence_root).as_posix()
        if relative.casefold() in referenced:
            continue
        if path.name.casefold() == "stf.xml":
            kind: Literal["STUDY_TAGGING_FILE", "SUPPORT_FILE", "UNSUPPORTED"] = (
                "STUDY_TAGGING_FILE"
            )
            relationship = "unvalidated optional STF"
        elif path.suffix.casefold() in {".dtd", ".xsl", ".xml", ".txt"}:
            kind = "SUPPORT_FILE"
            relationship = "archive support file; never trusted for parser validation"
        else:
            kind = "UNSUPPORTED"
            relationship = "unsupported unreferenced package member"
            warnings.append(
                ParseWarning(
                    code="unsupported-package-member",
                    message="Package member is outside the supported analysis profile.",
                    locator=relative,
                )
            )
        files.append(_file_record(path, sequence_root, kind, relationship))

    application_number = _regional_field(regional_root, "application-number")
    submission_id = _regional_field(regional_root, "submission-id")
    sequence_number = _regional_field(regional_root, "sequence-number")
    company = _regional_field(regional_root, "company-name")
    coverage_counts = cast(
        dict[PolicyCoverageStatus, int],
        dict(Counter(item.policy_coverage_status for item in leaves)),
    )
    status: Literal["passed", "warning"] = "warning" if warnings else "passed"
    checks = (
        ProfileCheck(
            id="sequence-root", label="Sequence root", status="passed", detail=sequence_relative
        ),
        ProfileCheck(
            id="pinned-dtd-validation",
            label="Pinned DTD validation",
            status="passed",
            detail=(
                "index.xml and m1/us/us-regional.xml passed offline validation through the "
                "exact local catalog."
            ),
        ),
        ProfileCheck(
            id="regional-relationship",
            label="Module 1 backbone relationship",
            status="passed",
            detail="index.xml references m1/us/us-regional.xml with operation=new.",
        ),
        ProfileCheck(
            id="document-checksums",
            label="Document checksums",
            status="passed",
            detail=(
                f"Verified {len(leaves) + 1} MD5 declarations separately from SHA-256 provenance."
            ),
        ),
        ProfileCheck(
            id="policy-coverage",
            label="Migration-policy coverage",
            status="warning" if "OUTSIDE_ENCODED_POLICY_COVERAGE" in coverage_counts else "passed",
            detail=f"Recorded explicit coverage for {len(leaves)} dossier documents.",
        ),
    )
    return ApplicationInventory(
        id=f"inventory-pending-{_package_digest(sequence_root)[:12]}",
        source_standard=StandardVersion.ECTD_3_2_2,
        application_number=" ".join(application_number.text.split())
        if application_number is not None and application_number.text
        else None,
        submission_type=_attribute(submission_id, "submission-type")
        if submission_id is not None
        else None,
        application_type_code=_attribute(application_number, "application-type")
        if application_number is not None
        else None,
        submission_id=" ".join(submission_id.text.split())
        if submission_id is not None and submission_id.text
        else None,
        sequence_number=" ".join(sequence_number.text.split())
        if sequence_number is not None and sequence_number.text
        else None,
        applicant_name=" ".join(company.text.split())
        if company is not None and company.text
        else None,
        has_stf=any(path.name.casefold() == "stf.xml" for path in sequence_root.rglob("*")),
        package_sha256=_package_digest(sequence_root),
        leaves=tuple(leaves),
        warnings=tuple(warnings),
        input_profile_id=PROFILE_ID,
        input_profile_version=PROFILE_VERSION,
        detected_sequence_root=sequence_relative,
        layout="authentic_sequence_layout",
        parsing_extent="bounded"
        if any(item.extraction_status == "bounded" for item in leaves)
        else "complete",
        package_profile_status=status,
        profile_checks=checks,
        xml_declarations=(index_record, regional_record),
        package_files=tuple(sorted(files, key=lambda item: item.path)),
        lifecycle_references=tuple(lifecycle),
        policy_coverage_counts=coverage_counts,
        regional_xml_version=regional_record.effective_dtd_version,
        regional_xml_sha256=_sha256(regional_path),
        index_md5_declared=index_md5_declared,
        index_md5_computed=index_md5_computed,
        index_md5_matches=index_md5_matches,
    )


def parse_public_profile_zip(
    payload: bytes,
    *,
    enforce_official_byte_identity: bool | None = None,
) -> ApplicationInventory:
    with extracted_archive(payload) as directory:
        return parse_public_profile_directory(
            directory,
            enforce_official_byte_identity=enforce_official_byte_identity,
        )


def independent_validate_package(payload: bytes) -> tuple[IndependentValidationResult, ...]:
    with extracted_archive(payload) as directory:
        sequence_root, _ = _sequence_root(directory)
        return (
            independent_validate_xml(sequence_root / "index.xml", "index.xml", INDEX_DTD_ASSET_ID),
            independent_validate_xml(
                sequence_root / "m1" / "us" / "us-regional.xml",
                "m1/us/us-regional.xml",
                REGIONAL_DTD_ASSET_ID,
            ),
        )
