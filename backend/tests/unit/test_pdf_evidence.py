from pathlib import Path

from app.parsers.ectd322 import FixtureCatalog, parse_directory


def test_parser_normalizes_manufacturer_value_but_preserves_raw_value() -> None:
    leaf = FixtureCatalog().parse("case-b-unspecified-all").leaves[0]
    keyword = leaf.keywords[0]
    assert keyword.name == "manufacturer"
    assert keyword.raw_value == " ALL "
    assert keyword.normalized_value == "all"


def test_pdf_text_and_external_hyperlink_are_extracted_with_stable_ids() -> None:
    leaf = FixtureCatalog().parse("case-c-irrelevant-link").leaves[0]
    assert leaf.extraction_status == "completed"
    assert "legacy applicant portal" in leaf.text_spans[0].text.lower()
    assert leaf.hyperlinks[0].id == "leaf-c-irrelevant-link-link-p1-1"
    assert leaf.hyperlinks[0].target_type == "uri"
    assert not leaf.hyperlinks[0].author_verified_relevant


def test_author_verified_internal_hyperlink_target_exists() -> None:
    leaf = FixtureCatalog().parse("case-c-relevant-link").leaves[0]
    assert leaf.hyperlinks[0].target_type == "internal"
    assert leaf.hyperlinks[0].target_exists is True
    assert leaf.hyperlinks[0].author_verified_relevant is True


def test_malformed_pdf_becomes_explicit_incomplete_evidence_warning(tmp_path: Path) -> None:
    (tmp_path / "documents").mkdir()
    (tmp_path / "documents" / "broken.pdf").write_bytes(b"%PDF-1.7\nnot-a-valid-pdf")
    (tmp_path / "index.xml").write_text(
        """<ectd xmlns:xlink="http://www.w3.org/1999/xlink"><m3-2-s-1>
        <leaf ID="broken-leaf" xlink:href="documents/broken.pdf"><title>Broken</title></leaf>
        </m3-2-s-1></ectd>""",
        encoding="utf-8",
    )
    (tmp_path / "us-regional.xml").write_text(
        "<us-regional><application-number>123456</application-number></us-regional>",
        encoding="utf-8",
    )
    inventory = parse_directory(tmp_path)
    assert inventory.leaves[0].extraction_status == "failed"
    assert inventory.warnings[0].code == "pdf-evidence-incomplete"
