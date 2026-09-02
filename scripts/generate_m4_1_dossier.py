"""Build the deterministic public M4.1 controlled-profile dossier."""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import zipfile
from pathlib import Path
from typing import Final

from reportlab.pdfgen import canvas  # type: ignore[import-untyped]

REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[1]
OUTPUT_DIRECTORY: Final = REPOSITORY_ROOT / "data" / "demo-dossiers" / "m4-1"
ZIP_PATH: Final = OUTPUT_DIRECTORY / "regbridge-m4-1-composite.zip"
MANIFEST_PATH: Final = OUTPUT_DIRECTORY / "generation-manifest.json"
ZIP_TIMESTAMP: Final = (2026, 9, 2, 0, 0, 0)
APPLICANT: Final = "RegBridge Synthetic Biologics LLC"


def _md5(payload: bytes) -> str:
    try:
        return hashlib.md5(payload, usedforsecurity=False).hexdigest()
    except TypeError:  # pragma: no cover
        return hashlib.md5(payload).hexdigest()


def _pdf(path: Path, title: str, lines: tuple[str, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    drawing = canvas.Canvas(
        str(path),
        pagesize=(612, 792),
        invariant=1,
        pageCompression=0,
        pdfVersion=(1, 4),
    )
    drawing.setAuthor("RegBridge research team")
    drawing.setCreator("RegBridge deterministic M4.1 generator")
    drawing.setTitle(title)
    drawing.setSubject("Public synthetic controlled dossier content")
    drawing.setFont("Helvetica-Bold", 16)
    drawing.drawString(72, 720, title)
    drawing.setFont("Helvetica", 11)
    y = 680
    for line in lines:
        drawing.drawString(72, y, line)
        y -= 22
    drawing.showPage()
    drawing.save()


def _index_xml(
    checksums: dict[str, str], *, case_a_heading: str, manufacturer: str
) -> bytes:
    xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE ectd SYSTEM "util/dtd/ich-ectd-3-2.dtd">
<ectd xmlns="urn:ich-org:ectd" xmlns:xlink="http://www.w3.org/1999/xlink" dtd-version="3.2.2">
  <m3>
    <m3-2-s>
      <m3-2-s-1>
        <{case_a_heading}>
          <leaf ID="m41-leaf-a" operation="new" xlink:href="m3/32s1/case-a.pdf" checksum-type="md5" checksum="{checksums["case-a.pdf"]}">
            <title>Synthetic substance properties</title>
          </leaf>
        </{case_a_heading}>
        <leaf ID="m41-leaf-b" operation="new" xlink:href="m3/32s1/case-b.pdf" checksum-type="md5" checksum="{checksums["case-b.pdf"]}" manufacturer="{manufacturer}">
          <title>Synthetic manufacturing overview</title>
        </leaf>
        <leaf ID="m41-leaf-c" operation="new" xlink:href="m3/32s1/case-c.pdf" checksum-type="md5" checksum="{checksums["case-c.pdf"]}">
          <title>Synthetic applicant responsibility statement</title>
        </leaf>
      </m3-2-s-1>
    </m3-2-s>
  </m3>
</ectd>
'''
    return xml.encode("utf-8")


def _regional_xml() -> bytes:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE regional SYSTEM "../../util/dtd/us-regional-2-01.dtd">
<regional xmlns="urn:fda:regional" version="2.01" dtd-version="2.01">
  <application-number>999999</application-number>
  <application-type>NDA</application-type>
  <submission-type>ORIGINAL</submission-type>
  <applicant-name>{APPLICANT}</applicant-name>
</regional>
""".encode("utf-8")


def build_package(
    output: Path = ZIP_PATH,
    *,
    case_a_heading: str = "m3-2-s-1-2",
    manufacturer: str = "all",
    case_c_applicant: str = "Legacy Applicant Corporation",
) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="regbridge-m41-build-") as temporary:
        sequence = Path(temporary) / "synthetic-application" / "0000"
        pdf_paths = {
            "case-a.pdf": sequence / "m3" / "32s1" / "case-a.pdf",
            "case-b.pdf": sequence / "m3" / "32s1" / "case-b.pdf",
            "case-c.pdf": sequence / "m3" / "32s1" / "case-c.pdf",
        }
        _pdf(
            pdf_paths["case-a.pdf"],
            "Synthetic substance properties",
            (
                "Controlled public synthetic dossier document.",
                "The document describes physicochemical properties without confidential data.",
            ),
        )
        _pdf(
            pdf_paths["case-b.pdf"],
            "Synthetic manufacturing overview",
            (
                "Controlled public synthetic dossier document.",
                "Existing lifecycle content is preserved by identifier for this demonstration.",
            ),
        )
        _pdf(
            pdf_paths["case-c.pdf"],
            "Synthetic applicant responsibility statement",
            (
                "Controlled public synthetic dossier document.",
                f"The responsible applicant for this content is {case_c_applicant}.",
            ),
        )
        checksums = {name: _md5(path.read_bytes()) for name, path in pdf_paths.items()}
        index_path = sequence / "index.xml"
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_bytes(
            _index_xml(
                checksums, case_a_heading=case_a_heading, manufacturer=manufacturer
            )
        )
        regional_path = sequence / "m1" / "us" / "us-regional.xml"
        regional_path.parent.mkdir(parents=True, exist_ok=True)
        regional_path.write_bytes(_regional_xml())
        index_md5 = sequence / "index-md5.txt"
        index_md5.write_text(
            _md5(index_path.read_bytes()) + "\n", encoding="ascii", newline="\n"
        )
        support = sequence / "util" / "dtd" / "PROFILE-NOTICE.txt"
        support.parent.mkdir(parents=True, exist_ok=True)
        support.write_text(
            "Declarations are recognized only. Full DTD validation is not performed.\n",
            encoding="utf-8",
            newline="\n",
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(
            output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
        ) as archive:
            base = sequence.parents[1]
            for path in sorted(item for item in sequence.rglob("*") if item.is_file()):
                relative = path.relative_to(base).as_posix()
                info = zipfile.ZipInfo(relative, ZIP_TIMESTAMP)
                info.create_system = 0
                info.external_attr = 0o100644 << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(
                    info,
                    path.read_bytes(),
                    compress_type=zipfile.ZIP_DEFLATED,
                    compresslevel=9,
                )
    package_sha256 = hashlib.sha256(output.read_bytes()).hexdigest()
    return {
        "schema_version": "m4.1.composite-generation.v1",
        "profile_id": "fda-ectd-322-regbridge-demo-profile-v1",
        "public_synthetic_data": True,
        "contains_personal_or_sponsor_confidential_data": False,
        "archive": output.name,
        "archive_sha256": package_sha256,
        "generator": "scripts/generate_m4_1_dossier.py",
        "sequence_root": "synthetic-application/0000",
        "source_signals": {
            "structural_heading": case_a_heading,
            "manufacturer_attribute": manufacturer,
            "regional_applicant": APPLICANT,
            "document_applicant": case_c_applicant,
        },
        "legacy_md5_purpose": "eCTD v3.2.2 compatibility only",
        "provenance_hash": "SHA-256",
        "expected_decisions_embedded": False,
        "expert_validated": False,
        "operational_status": "not_operational",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="regbridge-m41-check-") as temporary:
        target = Path(temporary) / ZIP_PATH.name if arguments.check else ZIP_PATH
        manifest = build_package(target)
        if arguments.check:
            committed = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
            if manifest["archive_sha256"] != committed["archive_sha256"]:
                raise SystemExit("composite dossier digest mismatch")
            print(manifest["archive_sha256"])
            return
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(manifest["archive_sha256"])


if __name__ == "__main__":
    main()
