"""Authenticity-hardened controlled FDA eCTD v3.2.2 package profile.

This is deliberately not a complete FDA or DTD validator. External declarations are recognized
but never resolved; the parser performs only the bounded checks represented in the inventory.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterator
from pathlib import Path, PurePosixPath
from typing import Literal
from xml.etree import ElementTree

from app.domain.enums import LifecycleOperation, StandardVersion
from app.parsers.ectd322 import (
    EctdParseError,
    EctdSecurityError,
    _attribute,
    _extract_pdf_evidence,
    _heading_from_tag,
    _local_name,
    _normalize_keyword,
    _package_digest,
    _resolve_leaf_file,
    _safe_relative_path,
    extracted_archive,
    parse_directory,
)
from app.parsers.models import (
    ApplicationInventory,
    LifecycleReference,
    PackageFile,
    ParsedKeyword,
    ParsedLeaf,
    ParseWarning,
    ProfileCheck,
    XmlDeclarationRecord,
)

PROFILE_ID = "fda-ectd-322-regbridge-demo-profile-v1"
PROFILE_VERSION = "1.0.0"
CAPABILITY_BOUNDARY = (
    "RegBridge securely parses and validates a controlled FDA eCTD v3.2.2 package profile "
    "for supported structural, lifecycle, metadata, checksum, and document-evidence "
    "predicates. It does not perform complete FDA submission validation."
)
_XML_DECLARATION = re.compile(rb"<\?xml\s+version=[\"']([^\"']+)[\"'][^?]*\?>", re.I)
_DOCTYPE = re.compile(
    rb"<!DOCTYPE\s+[^>]+?\s+(?:SYSTEM\s+[\"']([^\"']+)[\"']|PUBLIC\s+[\"'][^\"']+[\"']\s+[\"']([^\"']+)[\"'])\s*>",
    re.I,
)
_ALLOWED_DTD_BASENAMES = {"ich-ectd-3-2.dtd", "us-regional-2-01.dtd"}
_RECOGNIZED_ROOTS = {"ectd", "regional", "fda-regional"}
_SUPPORTED_CHECKSUM = re.compile(r"^[a-fA-F0-9]{32}$")
_KEYWORD_ATTRIBUTES = {"manufacturer", "substance", "product", "dosage-form"}


def compatibility_md5(payload: bytes) -> str:
    """Calculate legacy-format MD5 without treating it as a security hash."""
    try:
        digest = hashlib.md5(payload, usedforsecurity=False)
    except TypeError:  # pragma: no cover - compatibility for non-CPython implementations
        digest = hashlib.md5(payload)
    return digest.hexdigest()


def _xml_record(path: Path, relative: str) -> tuple[ElementTree.Element, XmlDeclarationRecord]:
    payload = path.read_bytes()
    lowered = payload.lower()
    if b"<!entity" in lowered or b"[" in (
        lowered.split(b"<!doctype", 1)[1].split(b">", 1)[0] if b"<!doctype" in lowered else b""
    ):
        raise EctdSecurityError(f"internal entity declarations are not permitted in {relative}")
    match = _DOCTYPE.search(payload)
    declared: str | None = None
    recognized = False
    if b"<!doctype" in lowered and match is None:
        raise EctdSecurityError(f"unrecognized DOCTYPE declaration in {relative}")
    if match:
        declared = (match.group(1) or match.group(2)).decode("utf-8", errors="strict")
        if "://" in declared or declared.startswith(("/", "\\")):
            raise EctdSecurityError(f"external DOCTYPE location is not permitted in {relative}")
        basename = PurePosixPath(declared.replace("\\", "/")).name.casefold()
        recognized = basename in _ALLOWED_DTD_BASENAMES
        if not recognized:
            raise EctdSecurityError(f"unrecognized DOCTYPE identifier in {relative}")
        payload = payload[: match.start()] + payload[match.end() :]
    try:
        root = ElementTree.fromstring(payload)
    except ElementTree.ParseError as error:
        raise EctdParseError(f"XML is not well formed: {relative}") from error
    root_name = _local_name(root.tag)
    if root_name.casefold() not in _RECOGNIZED_ROOTS:
        raise EctdParseError(f"unrecognized XML root in {relative}: {root_name}")
    namespace = root.tag.split("}", 1)[0].lstrip("{") if "}" in root.tag else None
    version_match = _XML_DECLARATION.search(path.read_bytes())
    xml_version = version_match.group(1).decode() if version_match else None
    declared_version = _attribute(root, "dtd-version") or _attribute(root, "version")
    dtd_supported = declared_version in {"3.2.2", "2.01"}
    return root, XmlDeclarationRecord(
        path=relative,
        xml_version=xml_version,
        root_name=root_name,
        namespace=namespace,
        declared_doctype=declared,
        doctype_recognized=recognized,
        dtd_version_supported=dtd_supported,
    )


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
    try:
        relative = root.relative_to(extraction_root.resolve()).as_posix()
    except ValueError as error:  # pragma: no cover - defense in depth
        raise EctdSecurityError("sequence root escapes extracted archive") from error
    depth = 0 if relative == "." else len(PurePosixPath(relative).parts)
    if depth not in {0, 2}:
        raise EctdParseError(
            "sequence root must be archive root or one application/sequence wrapper"
        )
    return root, relative


def _regional_value(root: ElementTree.Element, *names: str) -> str | None:
    for element in root.iter():
        if _local_name(element.tag).casefold() in {name.casefold() for name in names}:
            if element.text and element.text.strip():
                return " ".join(element.text.split())
    return None


def _iter_leaf_nodes(
    element: ElementTree.Element, ancestors: tuple[ElementTree.Element, ...] = ()
) -> Iterator[tuple[ElementTree.Element, tuple[ElementTree.Element, ...]]]:
    if _local_name(element.tag).casefold() == "leaf":
        yield element, ancestors
    for child in element:
        yield from _iter_leaf_nodes(child, (*ancestors, element))


def _heading_and_keywords(
    ancestors: tuple[ElementTree.Element, ...],
) -> tuple[str, str, tuple[ParsedKeyword, ...]]:
    recognized: str | None = None
    raw = "unsupported"
    keyword_values: dict[str, ParsedKeyword] = {}
    for node in ancestors:
        local = _local_name(node.tag)
        if local.casefold().startswith("m3-"):
            raw = local
            recognized = _heading_from_tag(local)
        for attr_name, attr_value in node.attrib.items():
            name = _local_name(attr_name).casefold()
            value = str(attr_value).strip()
            if name in _KEYWORD_ATTRIBUTES and value:
                keyword_values[name] = ParsedKeyword(
                    name=name,
                    raw_value=value,
                    normalized_value=_normalize_keyword(value),
                    source_locator=f"index.xml / {raw} / @{name}",
                )
    # The domain schema needs a stable syntactic heading even when the raw XML heading is outside
    # the supported heading recognizer. The raw value and unsupported status remain authoritative.
    return (
        recognized or "0.UNSUPPORTED",
        raw,
        tuple(keyword_values[name] for name in sorted(keyword_values)),
    )


def _leaf_title(element: ElementTree.Element, fallback: str) -> str:
    for child in element:
        if _local_name(child.tag).casefold() == "title" and child.text and child.text.strip():
            return " ".join(child.text.split())
    return fallback


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
    declared_checksum_type: Literal["md5", "sha256"] | None = None,
    declared_checksum: str | None = None,
    computed_declared_checksum: str | None = None,
    declared_checksum_matches: bool | None = None,
) -> PackageFile:
    return PackageFile(
        path=path.relative_to(root).as_posix(),
        member_type=member_type,
        provenance_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        relationship=relationship,
        declared_checksum_type=declared_checksum_type,
        declared_checksum=declared_checksum,
        computed_declared_checksum=computed_declared_checksum,
        declared_checksum_matches=declared_checksum_matches,
    )


def parse_profile_directory(directory: Path) -> ApplicationInventory:
    extraction_root = directory.resolve()
    sequence_root, sequence_relative = _sequence_root(extraction_root)
    index_path = sequence_root / "index.xml"
    regional_path = sequence_root / "m1" / "us" / "us-regional.xml"
    legacy_regional = sequence_root / "us-regional.xml"
    layout: Literal["authentic_sequence_layout", "legacy_controlled_layout"] = (
        "authentic_sequence_layout"
    )
    if not regional_path.is_file() and legacy_regional.is_file() and sequence_relative == ".":
        regional_path = legacy_regional
        layout = "legacy_controlled_layout"
    if not regional_path.is_file():
        raise EctdParseError("supported Module 1 regional XML is missing")

    index_root, index_decl = _xml_record(index_path, "index.xml")
    regional_relative = regional_path.relative_to(sequence_root).as_posix()
    regional_root, regional_decl = _xml_record(regional_path, regional_relative)
    checks: list[ProfileCheck] = [
        ProfileCheck(
            id="sequence-root", label="Sequence root", status="passed", detail=sequence_relative
        ),
        ProfileCheck(
            id="xml-well-formed",
            label="XML and version",
            status="passed",
            detail="Backbone and regional XML are well formed.",
        ),
        ProfileCheck(
            id="doctype",
            label="DOCTYPE recognition",
            status="passed"
            if index_decl.doctype_recognized and regional_decl.doctype_recognized
            else "warning",
            detail=(
                "Declarations were recognized without resolution; full DTD validation was "
                "not performed."
            ),
        ),
        ProfileCheck(
            id="regional-metadata",
            label="Regional metadata",
            status="passed",
            detail=f"Parsed {regional_relative}.",
        ),
    ]
    if not index_decl.dtd_version_supported or not regional_decl.dtd_version_supported:
        raise EctdParseError("declared eCTD or regional DTD version is missing or unsupported")

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
        if len(values) != 1 or not _SUPPORTED_CHECKSUM.fullmatch(values[0]):
            raise EctdParseError("index-md5.txt must contain exactly one valid MD5 value")
        index_md5_declared = values[0].casefold()
        index_md5_computed = compatibility_md5(index_path.read_bytes())
        index_md5_matches = index_md5_declared == index_md5_computed
        if not index_md5_matches:
            raise EctdParseError("index-md5.txt does not match index.xml")
        checks.append(
            ProfileCheck(
                id="index-md5",
                label="Index MD5",
                status="passed",
                detail="Legacy index MD5 matched.",
            )
        )
    else:
        checks.append(
            ProfileCheck(
                id="index-md5",
                label="Index MD5",
                status="warning",
                detail="index-md5.txt was not supplied.",
            )
        )

    leaves: list[ParsedLeaf] = []
    lifecycle: list[LifecycleReference] = []
    files: list[PackageFile] = [
        _file_record(index_path, sequence_root, "BACKBONE_XML", "eCTD backbone"),
        _file_record(regional_path, sequence_root, "REGIONAL_XML", "FDA Module 1 metadata"),
    ]
    if index_md5_path.is_file():
        files.append(
            _file_record(
                index_md5_path, sequence_root, "SUPPORT_FILE", "index.xml compatibility checksum"
            )
        )
    warnings: list[ParseWarning] = []
    seen_ids: set[str] = set()
    for element, ancestors in _iter_leaf_nodes(index_root):
        leaf_id = _attribute(element, "ID") or _attribute(element, "id")
        if not leaf_id or leaf_id in seen_ids:
            raise EctdParseError("leaf IDs must be present and unique within the backbone")
        seen_ids.add(leaf_id)
        operation_raw = (_attribute(element, "operation") or "new").casefold()
        try:
            operation = LifecycleOperation(operation_raw)
        except ValueError as error:
            raise EctdParseError(f"unsupported lifecycle operation: {operation_raw}") from error
        href = _attribute(element, "href")
        modified = _attribute(element, "modified-file")
        if (
            operation
            in {LifecycleOperation.APPEND, LifecycleOperation.REPLACE, LifecycleOperation.DELETE}
            and not modified
        ):
            raise EctdParseError(f"{operation.value} leaf {leaf_id} requires modified-file")
        if modified:
            _safe_relative_path(modified)
        prior_status: Literal["resolved", "outside_scope"] = (
            "outside_scope" if modified else "resolved"
        )
        lifecycle.append(
            LifecycleReference(
                leaf_id=leaf_id,
                operation=operation,
                href=href,
                modified_file=modified,
                prior_reference_status=prior_status,
                source_locator=f"index.xml / leaf[{leaf_id}]",
            )
        )
        if operation == LifecycleOperation.DELETE:
            if href:
                raise EctdParseError(
                    "delete leaves in this profile must not introduce a physical file"
                )
            continue
        if not href:
            raise EctdParseError(f"{operation.value} leaf {leaf_id} requires a file reference")
        leaf_path, content_type = _resolve_leaf_file(sequence_root, href)
        declared_type = (_attribute(element, "checksum-type") or "").casefold()
        declared = _attribute(element, "checksum")
        if declared_type != "md5":
            raise EctdParseError("controlled profile supports only checksum-type=md5")
        if not declared or not _SUPPORTED_CHECKSUM.fullmatch(declared):
            raise EctdParseError(f"leaf {leaf_id} has a malformed MD5 checksum")
        computed = compatibility_md5(leaf_path.read_bytes())
        if declared.casefold() != computed:
            raise EctdParseError(
                f"declared checksum does not match file content for leaf {leaf_id}"
            )
        heading, raw_heading, keywords = _heading_and_keywords((*ancestors, element))
        spans, links, extraction_status, extraction_warning = _extract_pdf_evidence(
            leaf_path, leaf_id, set()
        )
        if extraction_warning:
            warnings.append(
                ParseWarning(
                    code="pdf-evidence-incomplete",
                    message=extraction_warning,
                    locator=f"index.xml / leaf[{leaf_id}]",
                )
            )
        leaves.append(
            ParsedLeaf(
                id=leaf_id,
                title=_leaf_title(element, leaf_path.stem),
                heading=heading,
                raw_heading=raw_heading,
                heading_status="recognized" if heading != "0.UNSUPPORTED" else "unsupported",
                href=PurePosixPath(href.replace("\\", "/")).as_posix(),
                operation=operation,
                modified_leaf_id=modified,
                prior_reference_status=prior_status if modified else "not_applicable",
                content_type=content_type,
                file_sha256=hashlib.sha256(leaf_path.read_bytes()).hexdigest(),
                declared_checksum_type="md5",
                declared_checksum=declared.casefold(),
                computed_declared_checksum=computed,
                declared_checksum_matches=True,
                source_locator=f"index.xml / {raw_heading} / leaf[{leaf_id}]",
                keywords=keywords,
                text_span_count=len(spans),
                hyperlink_count=len(links),
                extraction_status=extraction_status,
                text_spans=spans,
                hyperlinks=links,
            )
        )
        files.append(
            _file_record(
                leaf_path,
                sequence_root,
                "DOSSIER_DOCUMENT",
                f"leaf {leaf_id}",
                declared_checksum_type="md5",
                declared_checksum=declared.casefold(),
                computed_declared_checksum=computed,
                declared_checksum_matches=True,
            )
        )
    if not leaves:
        raise EctdParseError("index.xml contains no supported dossier-document candidates")

    referenced_paths = {record.path.casefold() for record in files}
    for path in sorted(item for item in sequence_root.rglob("*") if item.is_file()):
        relative = path.relative_to(sequence_root).as_posix()
        if relative.casefold() in referenced_paths:
            continue
        suffix = path.suffix.casefold()
        kind: Literal["STUDY_TAGGING_FILE", "SUPPORT_FILE", "UNSUPPORTED"] = (
            "STUDY_TAGGING_FILE"
            if path.name.casefold() == "stf.xml"
            else ("SUPPORT_FILE" if suffix in {".dtd", ".txt"} else "UNSUPPORTED")
        )
        files.append(_file_record(path, sequence_root, kind, "unreferenced package member"))
        if kind == "UNSUPPORTED":
            warnings.append(
                ParseWarning(
                    code="unsupported-package-member",
                    message="Package member is not analyzed by the controlled profile.",
                    locator=relative,
                )
            )

    checks.extend(
        [
            ProfileCheck(
                id="leaf-checksums",
                label="Document checksums",
                status="passed",
                detail=(
                    f"Verified {len(leaves)} legacy MD5 declarations; SHA-256 provenance "
                    "recorded separately."
                ),
            ),
            ProfileCheck(
                id="referenced-files",
                label="Referenced files",
                status="passed",
                detail=f"Resolved {len(leaves)} dossier document references.",
            ),
            ProfileCheck(
                id="pdf-extraction",
                label="PDF extraction",
                status="passed"
                if all(leaf.extraction_status == "completed" for leaf in leaves)
                else "warning",
                detail=f"Inspected {len(leaves)} bounded PDF documents.",
            ),
        ]
    )
    if layout == "legacy_controlled_layout":
        warnings.append(
            ParseWarning(
                code="legacy-controlled-layout",
                message=(
                    "Root-level regional XML is a legacy regression layout, not the "
                    "audience-facing profile."
                ),
                locator=".",
            )
        )
    status: Literal["passed", "warning"] = (
        "warning" if warnings or layout == "legacy_controlled_layout" else "passed"
    )
    return ApplicationInventory(
        id=f"inventory-pending-{_package_digest(sequence_root)[:12]}",
        source_standard=StandardVersion.ECTD_3_2_2,
        application_number=_regional_value(
            regional_root, "application-number", "application-number-text"
        ),
        submission_type=_regional_value(regional_root, "submission-type", "application-type"),
        applicant_name=_regional_value(regional_root, "applicant-name", "applicant"),
        has_stf=any(path.name.casefold() == "stf.xml" for path in sequence_root.rglob("*")),
        package_sha256=_package_digest(sequence_root),
        leaves=tuple(leaves),
        warnings=tuple(warnings),
        input_profile_id=PROFILE_ID,
        input_profile_version=PROFILE_VERSION,
        detected_sequence_root=sequence_relative,
        layout=layout,
        parsing_extent="bounded"
        if any(leaf.extraction_status == "bounded" for leaf in leaves)
        else "complete",
        package_profile_status=status,
        profile_checks=tuple(checks),
        xml_declarations=(index_decl, regional_decl),
        package_files=tuple(sorted(files, key=lambda item: item.path)),
        lifecycle_references=tuple(lifecycle),
        regional_xml_version=_attribute(regional_root, "version")
        or _attribute(regional_root, "dtd-version"),
        regional_xml_sha256=hashlib.sha256(regional_path.read_bytes()).hexdigest(),
        index_md5_declared=index_md5_declared,
        index_md5_computed=index_md5_computed,
        index_md5_matches=index_md5_matches,
    )


def parse_profile_zip(payload: bytes) -> ApplicationInventory:
    with extracted_archive(payload) as directory:
        return parse_profile_directory(directory)


def parse_uploaded_zip(payload: bytes) -> ApplicationInventory:
    """Route public-standard uploads while retaining the explicit M4.1 regression profile."""
    with extracted_archive(payload) as directory:
        index_candidates = [
            path
            for path in directory.rglob("*")
            if path.is_file() and path.name.casefold() == "index.xml"
        ]
        public_standard = False
        if len(index_candidates) == 1:
            index_prefix = index_candidates[0].read_bytes()[:8192]
            public_standard = b"http://www.ich.org/ectd" in index_prefix
        if public_standard:
            from app.parsers.public322 import parse_public_profile_directory

            return parse_public_profile_directory(directory)
        legacy = (directory / "index.xml").is_file() and (directory / "us-regional.xml").is_file()
        if legacy and len(index_candidates) == 1:
            try:
                return parse_profile_directory(directory)
            except EctdParseError:
                parsed = parse_directory(directory)
                return parsed.model_copy(
                    update={
                        "layout": "legacy_controlled_layout",
                        "input_profile_id": "legacy-controlled-layout-v1",
                        "package_profile_status": "warning",
                    }
                )
        return parse_profile_directory(directory)
