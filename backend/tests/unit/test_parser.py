import hashlib
from pathlib import Path

from app.parsers.ectd322 import FixtureCatalog, parse_directory


def test_parser_resolves_namespaces_heading_metadata_and_digest() -> None:
    inventory = FixtureCatalog().parse("case-a-removed-3211")

    assert inventory.source_standard.value == "eCTD-3.2.2"
    assert inventory.application_number == "999001"
    assert inventory.applicant_name == "Synthetic Research Sponsor"
    assert inventory.has_stf is False
    assert inventory.leaves[0].heading == "3.2.S.1.1"
    assert inventory.leaves[0].href == "documents/substance-name.pdf"
    assert len(inventory.leaves[0].file_sha256) == 64


def test_all_controlled_variants_parse_without_case_specific_parser_logic() -> None:
    catalog = FixtureCatalog()
    headings = {catalog.parse(fixture.id).leaves[0].heading for fixture in catalog.list()}

    assert headings == {
        "3.2.S.1",
        "3.2.S.1.1",
        "3.2.S.1.2",
        "3.2.S.1.3",
        "3.2.S.1.4",
        "3.2.S.1.5",
    }


def test_parser_preserves_replace_lifecycle_reference(tmp_path: Path) -> None:
    pdf = b"%PDF-1.4\nreplacement"
    checksum = hashlib.sha256(pdf).hexdigest()
    (tmp_path / "index.xml").write_text(
        '<ectd><m3-2-s-1><leaf ID="replacement" operation="replace" '
        f'modified-file="legacy" href="x.pdf" checksum="{checksum}">'
        "<title>Replacement</title></leaf></m3-2-s-1></ectd>",
        encoding="utf-8",
    )
    (tmp_path / "us-regional.xml").write_text("<regional />", encoding="utf-8")
    (tmp_path / "x.pdf").write_bytes(pdf)

    leaf = parse_directory(tmp_path).leaves[0]
    assert leaf.operation.value == "replace"
    assert leaf.modified_leaf_id == "legacy"
    assert leaf.declared_checksum == checksum
