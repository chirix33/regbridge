"""Build the deterministic public-standards M4.2 synthetic dossier."""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import zipfile
from pathlib import Path
from typing import Final, Literal

from reportlab.pdfgen import canvas  # type: ignore[import-untyped]

from app.parsers.public322 import independent_validate_package, parse_public_profile_zip

REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[1]
OUTPUT_DIRECTORY: Final = REPOSITORY_ROOT / "data" / "demo-dossiers" / "m4-2"
ZIP_PATH: Final = OUTPUT_DIRECTORY / "regbridge-m4-2-public-standards.zip"
MANIFEST_PATH: Final = OUTPUT_DIRECTORY / "generation-manifest.json"
ZIP_TIMESTAMP: Final = (2026, 9, 3, 0, 0, 0)
APPLICANT: Final = "RegBridge Synthetic Therapeutics LLC"
XLINK: Final = "http://www.w3c.org/1999/xlink"


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
    drawing.setCreator("RegBridge deterministic M4.2 generator")
    drawing.setTitle(title)
    drawing.setSubject("Public synthetic FDA/CDER input-profile demonstration")
    drawing.setFont("Helvetica-Bold", 16)
    drawing.drawString(72, 720, title)
    drawing.setFont("Helvetica", 11)
    y = 680
    for line in lines:
        drawing.drawString(72, y, line)
        y -= 22
    drawing.showPage()
    drawing.save()


def _leaf(leaf_id: str, href: str, checksum: str, title: str) -> str:
    return (
        f'<leaf ID="{leaf_id}" operation="new" xlink:type="simple" '
        f'checksum-type="md5" checksum="{checksum}" xlink:href="{href}" '
        'application-version="PDF 1.4">\n'
        f"  <title>{title}</title>\n"
        "</leaf>"
    )


def _index_xml(checksums: dict[str, str], regional_md5: str) -> bytes:
    regional = _leaf(
        "m42-regional-backbone",
        "m1/us/us-regional.xml",
        regional_md5,
        "FDA Module 1 regional backbone",
    )
    case_a = _leaf(
        "m42-leaf-a",
        "m3/32-body-data/case-a.pdf",
        checksums["case-a.pdf"],
        "Synthetic molecular structure",
    )
    case_b = _leaf(
        "m42-leaf-b",
        "m3/32-body-data/case-b.pdf",
        checksums["case-b.pdf"],
        "Synthetic lifecycle metadata context",
    )
    case_c = _leaf(
        "m42-leaf-c",
        "m3/32-body-data/case-c.pdf",
        checksums["case-c.pdf"],
        "Synthetic applicant responsibility statement",
    )
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE ectd:ectd SYSTEM "util/dtd/ich-ectd-3-2.dtd">
<ectd:ectd xmlns:ectd="http://www.ich.org/ectd" xmlns:xlink="{XLINK}">
  <m1-administrative-information-and-prescribing-information>
    {regional}
  </m1-administrative-information-and-prescribing-information>
  <m3-quality>
    <m3-2-body-of-data>
      <m3-2-s-drug-substance substance="Synthetic Substance A" manufacturer="Synthetic Manufacturer A">
        <m3-2-s-1-general-information>
          <m3-2-s-1-2-structure>
            {case_a}
          </m3-2-s-1-2-structure>
        </m3-2-s-1-general-information>
      </m3-2-s-drug-substance>
      <m3-2-s-drug-substance substance="Synthetic Substance B" manufacturer="all">
        <m3-2-s-1-general-information>
          {case_b}
        </m3-2-s-1-general-information>
      </m3-2-s-drug-substance>
      <m3-2-s-drug-substance substance="Synthetic Substance C" manufacturer="Synthetic Manufacturer C">
        <m3-2-s-1-general-information>
          {case_c}
        </m3-2-s-1-general-information>
      </m3-2-s-drug-substance>
    </m3-2-body-of-data>
  </m3-quality>
</ectd:ectd>
'''.encode()


def _regional_xml() -> bytes:
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<!DOCTYPE fda-regional:fda-regional SYSTEM "https://www.accessdata.fda.gov/static/eCTD/us-regional-v3-3.dtd">
<fda-regional:fda-regional dtd-version="3.3" xml:lang="en" xmlns:fda-regional="http://www.ich.org/fda" xmlns:xlink="{XLINK}">
  <admin>
    <applicant-info>
      <id>123456789</id>
      <company-name>{APPLICANT}</company-name>
      <submission-description>Public synthetic original NDA sequence</submission-description>
      <applicant-contacts>
        <applicant-contact>
          <applicant-contact-name applicant-contact-type="fdaact1">Synthetic Contact</applicant-contact-name>
          <telephones><telephone telephone-number-type="fdatnt1">1-000-000-0000</telephone></telephones>
          <emails><email>synthetic@example.invalid</email></emails>
        </applicant-contact>
      </applicant-contacts>
    </applicant-info>
    <application-set>
      <application application-containing-files="true">
        <application-information>
          <application-number application-type="fdaat1">999999</application-number>
        </application-information>
        <submission-information>
          <submission-id submission-type="fdast1">0001</submission-id>
          <sequence-number submission-sub-type="fdasst1">0000</sequence-number>
        </submission-information>
      </application>
    </application-set>
  </admin>
</fda-regional:fda-regional>
'''.encode()


def build_package(
    output: Path = ZIP_PATH,
    *,
    wrapper: LiteralWrapper = "application",
    case_c_applicant: str = "Legacy Applicant Corporation",
) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="regbridge-m42-build-") as temporary:
        base = Path(temporary)
        if wrapper == "application":
            sequence = base / "synthetic-application" / "0000"
            archive_base = base
        elif wrapper == "sequence":
            sequence = base / "0000"
            archive_base = base
        else:
            sequence = base
            archive_base = base
        pdfs = {
            "case-a.pdf": sequence / "m3" / "32-body-data" / "case-a.pdf",
            "case-b.pdf": sequence / "m3" / "32-body-data" / "case-b.pdf",
            "case-c.pdf": sequence / "m3" / "32-body-data" / "case-c.pdf",
        }
        _pdf(
            pdfs["case-a.pdf"],
            "Synthetic molecular structure",
            (
                "Controlled public synthetic dossier document.",
                "This content is located under the authentic 3.2.S.1.2 structure element.",
            ),
        )
        _pdf(
            pdfs["case-b.pdf"],
            "Synthetic lifecycle metadata context",
            (
                "Controlled public synthetic dossier document.",
                "Existing lifecycle content is preserved by identifier for this demonstration.",
            ),
        )
        _pdf(
            pdfs["case-c.pdf"],
            "Synthetic applicant responsibility statement",
            (
                "Controlled public synthetic dossier document.",
                f"The responsible applicant for this content is {case_c_applicant}.",
            ),
        )
        checksums = {name: _md5(path.read_bytes()) for name, path in pdfs.items()}
        regional_path = sequence / "m1" / "us" / "us-regional.xml"
        regional_path.parent.mkdir(parents=True, exist_ok=True)
        regional_path.write_bytes(_regional_xml())
        index_path = sequence / "index.xml"
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_bytes(_index_xml(checksums, _md5(regional_path.read_bytes())))
        (sequence / "index-md5.txt").write_text(
            _md5(index_path.read_bytes()) + "\n", encoding="ascii", newline="\n"
        )
        notice = sequence / "util" / "PROFILE-NOTICE.txt"
        notice.parent.mkdir(parents=True, exist_ok=True)
        notice.write_text(
            "Parser validation uses repository-pinned DTDs, never archive-supplied DTDs.\n",
            encoding="utf-8",
            newline="\n",
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(
            output, "w", zipfile.ZIP_DEFLATED, compresslevel=9
        ) as archive:
            for path in sorted(item for item in sequence.rglob("*") if item.is_file()):
                info = zipfile.ZipInfo(
                    path.relative_to(archive_base).as_posix(), ZIP_TIMESTAMP
                )
                info.create_system = 0
                info.external_attr = 0o100644 << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(
                    info,
                    path.read_bytes(),
                    compress_type=zipfile.ZIP_DEFLATED,
                    compresslevel=9,
                )
    payload = output.read_bytes()
    independent = independent_validate_package(payload)
    if not all(item.valid for item in independent):
        raise RuntimeError(f"independent DTD validation failed: {independent}")
    inventory = parse_public_profile_zip(payload)
    return {
        "schema_version": "m4.2.public-standards-generation.v1",
        "profile_id": inventory.input_profile_id,
        "profile_version": inventory.input_profile_version,
        "package_id": "regbridge-m4-2-public-standards-synthetic-v1",
        "archive": output.name,
        "archive_sha256": hashlib.sha256(payload).hexdigest(),
        "inventory_sha256": hashlib.sha256(
            inventory.model_dump_json(exclude={"id"}).encode()
        ).hexdigest(),
        "generator": "scripts/generate_m4_2_dossier.py",
        "sequence_root": inventory.detected_sequence_root,
        "independent_dtd_validation": [item.__dict__ for item in independent],
        "warning_codes": [item.code for item in inventory.warnings],
        "policy_coverage_counts": inventory.policy_coverage_counts,
        "public_synthetic_data": True,
        "contains_personal_or_sponsor_confidential_data": False,
        "expected_decisions_embedded": False,
        "expert_validated": False,
        "operational_status": "not_operational",
    }


LiteralWrapper = Literal["application", "sequence", "root"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="regbridge-m42-check-") as temporary:
        target = Path(temporary) / ZIP_PATH.name if arguments.check else ZIP_PATH
        manifest = build_package(target)
        if arguments.check:
            committed = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
            for key in ("archive_sha256", "inventory_sha256"):
                if manifest[key] != committed[key]:
                    raise SystemExit(f"M4.2 {key} mismatch")
            print(json.dumps(manifest, indent=2, sort_keys=True))
            return
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
