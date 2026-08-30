import hashlib
import mimetypes
import re
import shutil
import stat
import tempfile
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path, PurePosixPath, PureWindowsPath
from xml.etree import ElementTree

import yaml

from app.config import REPOSITORY_ROOT
from app.domain.enums import LifecycleOperation, StandardVersion
from app.parsers.models import ApplicationInventory, FixtureSummary, ParsedLeaf, ParseWarning

_HEADING_TAG = re.compile(r"^m(?P<module>\d+)(?P<parts>(?:-[a-z0-9]+)+)$", re.IGNORECASE)
_SUPPORTED_LEAF_TYPES = {".pdf": "application/pdf"}


class EctdParseError(ValueError):
    """Raised when a legacy package cannot be parsed safely and deterministically."""


class EctdSecurityError(EctdParseError):
    """Raised when an archive or XML security boundary is violated."""


class EctdParserLimits:
    max_upload_bytes = 10 * 1024 * 1024
    max_expanded_bytes = 25 * 1024 * 1024
    max_member_bytes = 10 * 1024 * 1024
    max_members = 200
    max_compression_ratio = 100


def _local_name(name: str) -> str:
    return name.rsplit("}", 1)[-1]


def _attribute(element: ElementTree.Element, name: str) -> str | None:
    attributes = getattr(element, "attrib", {})
    for key, value in attributes.items():
        if _local_name(key) == name:
            return str(value).strip()
    return None


def _heading_from_tag(tag: str) -> str | None:
    match = _HEADING_TAG.fullmatch(_local_name(tag))
    if not match:
        return None
    tokens = match.group("parts").strip("-").split("-")
    rendered = [match.group("module")]
    rendered.extend(token.upper() if token.isalpha() else token for token in tokens)
    return ".".join(rendered)


def _package_digest(directory: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in directory.rglob("*") if item.is_file()):
        relative = path.relative_to(directory).as_posix().encode()
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _safe_relative_path(raw_name: str) -> PurePosixPath:
    normalized = raw_name.replace("\\", "/")
    posix = PurePosixPath(normalized)
    windows = PureWindowsPath(raw_name)
    if (
        not normalized
        or posix.is_absolute()
        or windows.is_absolute()
        or windows.drive
        or any(part in {"", ".", ".."} for part in posix.parts)
    ):
        raise EctdSecurityError(f"unsafe archive member path: {raw_name!r}")
    return posix


@contextmanager
def extracted_archive(payload: bytes) -> Iterator[Path]:
    if len(payload) > EctdParserLimits.max_upload_bytes:
        raise EctdSecurityError("archive exceeds the upload-size limit")
    with tempfile.TemporaryDirectory(prefix="regbridge-m1-") as temporary_directory:
        root = Path(temporary_directory).resolve()
        try:
            from io import BytesIO

            with zipfile.ZipFile(BytesIO(payload)) as archive:
                members = archive.infolist()
                if len(members) > EctdParserLimits.max_members:
                    raise EctdSecurityError("archive contains too many members")
                expanded = 0
                seen: set[str] = set()
                for member in members:
                    relative = _safe_relative_path(member.filename)
                    key = relative.as_posix().casefold()
                    if key in seen:
                        raise EctdSecurityError("archive contains duplicate normalized paths")
                    seen.add(key)
                    mode = member.external_attr >> 16
                    if stat.S_ISLNK(mode):
                        raise EctdSecurityError("symbolic links are not permitted in uploads")
                    expanded += member.file_size
                    if member.file_size > EctdParserLimits.max_member_bytes:
                        raise EctdSecurityError("archive member exceeds the per-file limit")
                    if expanded > EctdParserLimits.max_expanded_bytes:
                        raise EctdSecurityError("archive exceeds the expanded-size limit")
                    compressed = max(member.compress_size, 1)
                    if member.file_size / compressed > EctdParserLimits.max_compression_ratio:
                        raise EctdSecurityError(
                            "archive member exceeds the compression-ratio limit"
                        )
                    target = (root / Path(*relative.parts)).resolve()
                    try:
                        target.relative_to(root)
                    except ValueError as error:
                        raise EctdSecurityError("archive member escapes extraction root") from error
                    if member.is_dir():
                        target.mkdir(parents=True, exist_ok=True)
                        continue
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(member) as source, target.open("wb") as destination:
                        shutil.copyfileobj(source, destination)
        except zipfile.BadZipFile as error:
            raise EctdParseError("upload is not a valid ZIP archive") from error
        yield root


def _parse_xml(path: Path) -> ElementTree.Element:
    payload = path.read_bytes()
    lowered = payload.lower()
    if b"<!doctype" in lowered or b"<!entity" in lowered:
        raise EctdSecurityError(f"DTD and entity declarations are not permitted in {path.name}")
    try:
        return ElementTree.fromstring(payload)
    except ElementTree.ParseError as error:
        raise EctdSecurityError(f"unsafe or invalid XML in {path.name}") from error


def _regional_value(root: ElementTree.Element, *names: str) -> str | None:
    for element in root.iter():
        if _local_name(element.tag) in names and element.text and element.text.strip():
            return element.text.strip()
    return None


def _iter_leaves(
    element: ElementTree.Element,
    heading: str | None = None,
) -> Iterator[tuple[ElementTree.Element, str]]:
    current_heading = _heading_from_tag(element.tag) or heading
    if _local_name(element.tag) == "leaf":
        if not current_heading:
            raise EctdParseError("leaf is not located beneath a recognized CTD heading")
        yield element, current_heading
    for child in element:
        yield from _iter_leaves(child, current_heading)


def _resolve_leaf_file(root: Path, href: str) -> tuple[Path, str]:
    relative = _safe_relative_path(href)
    target = (root / Path(*relative.parts)).resolve()
    try:
        target.relative_to(root)
    except ValueError as error:
        raise EctdSecurityError("leaf reference escapes package root") from error
    if not target.is_file():
        raise EctdParseError(f"referenced leaf file is missing: {href}")
    content_type = _SUPPORTED_LEAF_TYPES.get(target.suffix.lower())
    if not content_type:
        guessed, _ = mimetypes.guess_type(target.name)
        raise EctdSecurityError(f"unsupported referenced file type: {guessed or target.suffix}")
    if not target.read_bytes().startswith(b"%PDF-"):
        raise EctdSecurityError(f"referenced PDF has an invalid file signature: {href}")
    return target, content_type


def parse_directory(directory: Path, *, fixture_id: str | None = None) -> ApplicationInventory:
    root = directory.resolve()
    index_path = root / "index.xml"
    regional_path = root / "us-regional.xml"
    if not index_path.is_file() or not regional_path.is_file():
        raise EctdParseError("package requires index.xml and us-regional.xml at its root")

    index_root = _parse_xml(index_path)
    regional_root = _parse_xml(regional_path)
    leaves: list[ParsedLeaf] = []
    warnings: list[ParseWarning] = []
    for element, heading in _iter_leaves(index_root):
        leaf_id = _attribute(element, "ID") or _attribute(element, "id")
        href = _attribute(element, "href")
        operation_raw = (_attribute(element, "operation") or "new").lower()
        if not leaf_id or not href:
            raise EctdParseError("each leaf requires an identifier and href")
        try:
            operation = LifecycleOperation(operation_raw)
        except ValueError as error:
            raise EctdParseError(f"unsupported lifecycle operation: {operation_raw}") from error
        leaf_path, content_type = _resolve_leaf_file(root, href)
        title = next(
            (
                child.text.strip()
                for child in element
                if _local_name(child.tag) == "title" and child.text and child.text.strip()
            ),
            leaf_path.stem,
        )
        checksum = hashlib.sha256(leaf_path.read_bytes()).hexdigest()
        declared_checksum = _attribute(element, "checksum")
        leaves.append(
            ParsedLeaf(
                id=leaf_id,
                title=title,
                heading=heading,
                href=PurePosixPath(href.replace("\\", "/")).as_posix(),
                operation=operation,
                modified_leaf_id=_attribute(element, "modified-file"),
                content_type=content_type,
                file_sha256=checksum,
                declared_checksum=declared_checksum,
                source_locator=f"index.xml / {heading} / leaf[{leaf_id}]",
            )
        )
    if not leaves:
        raise EctdParseError("index.xml contains no parseable leaves")
    if (root / "stf.xml").is_file():
        _parse_xml(root / "stf.xml")
    return ApplicationInventory(
        id=f"inventory-{fixture_id or _package_digest(root)[:12]}",
        fixture_id=fixture_id,
        source_standard=StandardVersion.ECTD_3_2_2,
        application_number=_regional_value(
            regional_root, "application-number", "application-number-text"
        ),
        submission_type=_regional_value(regional_root, "submission-type"),
        applicant_name=_regional_value(regional_root, "applicant-name"),
        has_stf=(root / "stf.xml").is_file(),
        package_sha256=_package_digest(root),
        leaves=tuple(leaves),
        warnings=tuple(warnings),
    )


def parse_zip(payload: bytes) -> ApplicationInventory:
    with extracted_archive(payload) as directory:
        return parse_directory(directory)


class FixtureCatalog:
    def __init__(self, catalog_path: Path | None = None) -> None:
        self.catalog_path = catalog_path or REPOSITORY_ROOT / "data" / "demo-cases" / "catalog.yaml"
        self.root = self.catalog_path.parent.resolve()

    def list(self) -> tuple[FixtureSummary, ...]:
        payload = yaml.safe_load(self.catalog_path.read_text(encoding="utf-8"))
        return tuple(FixtureSummary.model_validate(item) for item in payload["fixtures"])

    def parse(self, fixture_id: str) -> ApplicationInventory:
        known = {fixture.id for fixture in self.list()}
        if fixture_id not in known:
            raise EctdParseError(f"unknown controlled fixture: {fixture_id}")
        fixture_path = (self.root / fixture_id).resolve()
        try:
            fixture_path.relative_to(self.root)
        except ValueError as error:
            raise EctdSecurityError("fixture path escapes fixture catalog") from error
        return parse_directory(fixture_path, fixture_id=fixture_id)
