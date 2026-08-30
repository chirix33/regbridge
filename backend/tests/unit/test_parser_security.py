from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import pytest
from app.parsers.ectd322 import EctdSecurityError, parse_directory, parse_zip


def archive(entries: dict[str, bytes]) -> bytes:
    payload = BytesIO()
    with ZipFile(payload, "w", ZIP_DEFLATED) as output:
        for name, content in entries.items():
            output.writestr(name, content)
    return payload.getvalue()


def test_zip_rejects_parent_traversal() -> None:
    with pytest.raises(EctdSecurityError, match="unsafe archive member"):
        parse_zip(archive({"../outside.pdf": b"%PDF-1.4"}))


def test_zip_rejects_absolute_windows_path() -> None:
    with pytest.raises(EctdSecurityError, match="unsafe archive member"):
        parse_zip(archive({"C:\\outside.pdf": b"%PDF-1.4"}))


def test_zip_rejects_symbolic_link() -> None:
    payload = BytesIO()
    with ZipFile(payload, "w") as output:
        member = ZipInfo("documents/link.pdf")
        member.external_attr = 0o120777 << 16
        output.writestr(member, b"target")
    with pytest.raises(EctdSecurityError, match="Symbolic|symbolic"):
        parse_zip(payload.getvalue())


def test_zip_rejects_duplicate_normalized_paths() -> None:
    with pytest.raises(EctdSecurityError, match="duplicate normalized"):
        parse_zip(archive({"Index.xml": b"<ectd />", "index.xml": b"<ectd />"}))


def test_zip_rejects_excessive_member_count() -> None:
    entries = {f"documents/{index}.pdf": b"%PDF-1.4" for index in range(201)}
    with pytest.raises(EctdSecurityError, match="too many members"):
        parse_zip(archive(entries))


def test_zip_rejects_high_compression_ratio() -> None:
    with pytest.raises(EctdSecurityError, match="compression-ratio"):
        parse_zip(archive({"documents/bomb.pdf": b"A" * 50_000}))


def test_zip_rejects_oversized_upload_before_opening() -> None:
    with pytest.raises(EctdSecurityError, match="upload-size"):
        parse_zip(b"x" * (10 * 1024 * 1024 + 1))


def test_xml_rejects_doctype_and_entity_declarations(tmp_path: Path) -> None:
    (tmp_path / "index.xml").write_text(
        '<!DOCTYPE x [<!ENTITY boom "unsafe">]><ectd><m3-2-s-1>'
        '<leaf ID="l" href="x.pdf"><title>&boom;</title></leaf>'
        "</m3-2-s-1></ectd>",
        encoding="utf-8",
    )
    (tmp_path / "us-regional.xml").write_text("<regional />", encoding="utf-8")
    (tmp_path / "x.pdf").write_bytes(b"%PDF-1.4")

    with pytest.raises(EctdSecurityError, match="DTD and entity"):
        parse_directory(tmp_path)


def test_referenced_pdf_requires_pdf_signature(tmp_path: Path) -> None:
    (tmp_path / "index.xml").write_text(
        '<ectd><m3-2-s-1><leaf ID="l" href="x.pdf"><title>x</title></leaf></m3-2-s-1></ectd>',
        encoding="utf-8",
    )
    (tmp_path / "us-regional.xml").write_text("<regional />", encoding="utf-8")
    (tmp_path / "x.pdf").write_bytes(b"not a pdf")

    with pytest.raises(EctdSecurityError, match="invalid file signature"):
        parse_directory(tmp_path)
