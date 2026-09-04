from __future__ import annotations

import asyncio
import hashlib
import io
import json
import socket
import urllib.request
import zipfile
from datetime import date
from pathlib import Path
from typing import Any, cast

import pytest
from app.analyzer.service import AnalysisService
from app.config import REPOSITORY_ROOT, Settings
from app.domain.enums import (
    ApplicationType,
    Authority,
    Center,
    LlmMode,
    ManufacturerPartitioning,
    MetadataMigrationIntent,
    ReuseOperation,
    ScenarioMode,
    StandardVersion,
)
from app.domain.models import MetadataPlan, TargetContext
from app.main import app
from app.parsers.ectd322 import EctdParseError, EctdParserLimits, EctdSecurityError
from app.parsers.profile322 import parse_uploaded_zip
from app.parsers.public322 import (
    adjudicate_public_profile_zip,
    independent_validate_package,
    load_catalog,
    parse_public_profile_zip,
)
from app.product.models_registry import ProductFixtureModel
from app.product.services import CaptureRepository, canonical_digest
from fastapi.testclient import TestClient

PACKAGE = (
    REPOSITORY_ROOT / "data" / "demo-dossiers" / "m4-2" / "regbridge-m4-2-public-standards.zip"
)
ACCEPTANCE_PACKAGE = REPOSITORY_ROOT / "meridianvelacytenda217999seq0000ectd322spec.zip"


def _target() -> TargetContext:
    return TargetContext(
        authority=Authority.FDA,
        center=Center.CDER,
        application_type=ApplicationType.NDA,
        source_standard=StandardVersion.ECTD_3_2_2,
        target_standard=StandardVersion.ECTD_4_0,
        analysis_date=date(2026, 9, 3),
        reuse_operation=ReuseOperation.REFERENCE_EXISTING_CONTENT,
        standards_snapshot_id="fda-cder-demo-v1",
        scenario_mode=ScenarioMode.PROSPECTIVE_FORWARD_COMPATIBILITY,
        metadata_plan=MetadataPlan(
            intent=MetadataMigrationIntent.PRESERVE_EXISTING_LIFECYCLE,
            manufacturer_partitioning=ManufacturerPartitioning.UNKNOWN,
        ),
    )


def _members(payload: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        return {
            item.filename: archive.read(item) for item in archive.infolist() if not item.is_dir()
        }


def _zip(members: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, body in sorted(members.items()):
            info = zipfile.ZipInfo(name, (2026, 9, 3, 0, 0, 0))
            info.create_system = 0
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, body)
    return output.getvalue()


def _ending(members: dict[str, bytes], suffix: str) -> str:
    matches = [name for name in members if name == suffix or name.endswith("/" + suffix)]
    assert len(matches) == 1
    return matches[0]


def _with_archive_ich_dtd(payload: bytes, dtd_payload: bytes) -> bytes:
    members = _members(payload)
    prefix = _ending(members, "index.xml").removesuffix("index.xml")
    members[prefix + "util/dtd/ich-ectd-3-2.dtd"] = dtd_payload
    return _zip(members)


def _mutate(
    payload: bytes,
    *,
    index: tuple[bytes, bytes] | None = None,
    regional: tuple[bytes, bytes] | None = None,
) -> bytes:
    members = _members(payload)
    index_name = _ending(members, "index.xml")
    regional_name = _ending(members, "m1/us/us-regional.xml")
    index_body = members[index_name]
    if regional:
        old_regional = members[regional_name]
        members[regional_name] = old_regional.replace(*regional)
        old_md5 = hashlib.md5(old_regional, usedforsecurity=False).hexdigest().encode()
        new_md5 = hashlib.md5(members[regional_name], usedforsecurity=False).hexdigest().encode()
        index_body = index_body.replace(old_md5, new_md5)
    if index:
        index_body = index_body.replace(*index)
    members[index_name] = index_body
    index_md5_name = _ending(members, "index-md5.txt")
    members[index_md5_name] = (
        hashlib.md5(index_body, usedforsecurity=False).hexdigest() + "\n"
    ).encode()
    return _zip(members)


def test_generated_package_passes_both_independent_pinned_dtd_validations() -> None:
    results = independent_validate_package(PACKAGE.read_bytes())
    assert [(item.dtd_asset_id, item.valid) for item in results] == [
        ("ich-ectd-dtd-v3-2", True),
        ("fda-us-regional-dtd-v3-3", True),
    ]
    assert all(item.detail == "passed" for item in results)


def test_product_demo_preset_endpoint_serves_exact_committed_package() -> None:
    response = TestClient(app).get("/api/v1/product/demo-package")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert (
        "fda-cder-ectd-322-public-standards-profile-v1"
        in response.headers["x-regbridge-input-profile"]
    )
    assert (
        hashlib.sha256(response.content).hexdigest()
        == hashlib.sha256(PACKAGE.read_bytes()).hexdigest()
    )


def test_pinned_manifest_assets_exist_and_match_sha256() -> None:
    catalog = load_catalog()
    assert {"ich-ectd-dtd-v3-2", "fda-us-regional-dtd-v3-3"} <= set(catalog)
    assert all(
        hashlib.sha256(item.path.read_bytes()).hexdigest() == item.sha256
        for item in catalog.values()
    )
    ich = catalog["ich-ectd-dtd-v3-2"]
    assert ich.official_md5 == "1d6f631cc6b6357f0f4fe378e5f79a27"
    assert ich.byte_identity_required is True
    assert ich.byte_identity_basis and "criterion 1130" in ich.byte_identity_basis


def test_byte_identical_archive_dtd_is_recorded_and_accepted() -> None:
    pinned = load_catalog()["ich-ectd-dtd-v3-2"].path.read_bytes()
    payload = _with_archive_ich_dtd(PACKAGE.read_bytes(), pinned)
    adjudication = adjudicate_public_profile_zip(payload)
    comparison = adjudication.dtd_comparisons[0]
    assert adjudication.status == "accepted"
    assert comparison.archive_sha256 == comparison.pinned_sha256
    assert comparison.raw_bytes_equal is True
    assert comparison.normalized_text_equal is True
    assert comparison.semantic_text_equal is True
    assert comparison.difference_class == "byte_identical"
    assert comparison.first_substantive_differences == ()
    assert comparison.archive_copy_ignored is True
    inventory = parse_public_profile_zip(payload)
    assert "ARCHIVE_DTD_DIFFERS_FROM_PINNED_COPY" not in {
        item.code for item in inventory.warnings
    }


def test_line_ending_only_archive_dtd_is_distinguished_and_byte_policy_applies() -> None:
    pinned = load_catalog()["ich-ectd-dtd-v3-2"].path.read_bytes()
    text = pinned.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    line_ending_copy = text.replace("\n", "\r\n").encode("utf-8")
    if line_ending_copy == pinned:
        line_ending_copy = text.encode("utf-8")
    payload = _with_archive_ich_dtd(PACKAGE.read_bytes(), line_ending_copy)
    adjudication = adjudicate_public_profile_zip(payload)
    comparison = adjudication.dtd_comparisons[0]
    assert adjudication.status == "rejected_nonconforming"
    assert adjudication.byte_identity_required is True
    assert comparison.archive_sha256 != comparison.pinned_sha256
    assert comparison.normalized_text_equal is True
    assert comparison.semantic_text_equal is True
    assert comparison.difference_class == "non_substantive_text_only"
    assert comparison.first_substantive_differences == ()
    with pytest.raises(EctdParseError, match="criterion 1130"):
        parse_public_profile_zip(payload)

    accepted = parse_public_profile_zip(payload, enforce_official_byte_identity=False)
    warning = next(
        item
        for item in accepted.warnings
        if item.code == "ARCHIVE_DTD_DIFFERS_FROM_PINNED_COPY"
    )
    assert "archive copy was ignored" in warning.message


def test_bom_and_trailing_whitespace_are_excluded_from_substantive_differences() -> None:
    pinned = load_catalog()["ich-ectd-dtd-v3-2"].path.read_bytes()
    text = pinned.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    packaging_copy = b"\xef\xbb\xbf" + "\n".join(
        f"{line} \t" for line in text.split("\n")
    ).encode("utf-8")
    payload = _with_archive_ich_dtd(PACKAGE.read_bytes(), packaging_copy)
    adjudication = adjudicate_public_profile_zip(payload)
    comparison = adjudication.dtd_comparisons[0]
    assert adjudication.status == "rejected_nonconforming"
    assert comparison.raw_bytes_equal is False
    assert comparison.normalized_text_equal is True
    assert comparison.semantic_text_equal is True
    assert comparison.difference_class == "non_substantive_text_only"
    assert comparison.first_substantive_differences == ()


def test_comment_only_archive_dtd_difference_is_not_called_substantive() -> None:
    pinned = load_catalog()["ich-ectd-dtd-v3-2"].path.read_bytes()
    payload = _with_archive_ich_dtd(
        PACKAGE.read_bytes(), pinned + b"\n<!-- archive packaging note only -->\n"
    )
    adjudication = adjudicate_public_profile_zip(payload)
    comparison = adjudication.dtd_comparisons[0]
    assert adjudication.status == "rejected_nonconforming"
    assert comparison.normalized_text_equal is False
    assert comparison.semantic_text_equal is True
    assert comparison.difference_class == "comment_only"
    assert comparison.first_substantive_differences == ()
    accepted = parse_public_profile_zip(payload, enforce_official_byte_identity=False)
    assert "ARCHIVE_DTD_DIFFERS_FROM_PINNED_COPY" in {
        item.code for item in accepted.warnings
    }


def test_substantively_modified_archive_dtd_reports_first_semantic_difference() -> None:
    pinned = load_catalog()["ich-ectd-dtd-v3-2"].path.read_bytes()
    payload = _with_archive_ich_dtd(
        PACKAGE.read_bytes(), pinned + b"\n<!ELEMENT archive-only EMPTY>\n"
    )
    adjudication = adjudicate_public_profile_zip(payload)
    comparison = adjudication.dtd_comparisons[0]
    assert adjudication.status == "rejected_nonconforming"
    assert comparison.difference_class == "substantive"
    assert comparison.semantic_text_equal is False
    assert comparison.first_substantive_differences
    assert any(
        difference.archive_text == "<!ELEMENT archive-only EMPTY>"
        for difference in comparison.first_substantive_differences
    )
    accepted = parse_public_profile_zip(payload, enforce_official_byte_identity=False)
    assert "ARCHIVE_DTD_DIFFERS_FROM_PINNED_COPY" in {
        item.code for item in accepted.warnings
    }


def test_hostile_archive_dtd_is_hard_rejected_even_though_it_is_never_executed() -> None:
    pinned = load_catalog()["ich-ectd-dtd-v3-2"].path.read_bytes()
    payload = _with_archive_ich_dtd(
        PACKAGE.read_bytes(),
        pinned + b'\n<!ENTITY xxe SYSTEM "file:///etc/passwd">\n',
    )
    adjudication = adjudicate_public_profile_zip(payload)
    comparison = adjudication.dtd_comparisons[0]
    assert adjudication.status == "security_violation"
    assert comparison.hostile is True
    assert comparison.hostile_reasons == ("external entity declaration",)
    with pytest.raises(EctdSecurityError, match="external entity declaration"):
        parse_public_profile_zip(payload)


def test_official_absolute_and_ich_relative_doctypes_never_call_python_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def blocked(*args: object, **kwargs: object) -> None:
        raise AssertionError(f"outbound request attempted: {args!r} {kwargs!r}")

    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(urllib.request, "urlopen", blocked)
    inventory = parse_public_profile_zip(PACKAGE.read_bytes())
    assert [item.dtd_asset_id for item in inventory.xml_declarations] == [
        "ich-ectd-dtd-v3-2",
        "fda-us-regional-dtd-v3-3",
    ]
    assert all(item.dtd_validation_result == "passed" for item in inventory.xml_declarations)


def test_missing_index_version_is_inferred_with_warning() -> None:
    inventory = parse_public_profile_zip(PACKAGE.read_bytes())
    index = inventory.xml_declarations[0]
    assert index.effective_dtd_version == "3.2.2"
    assert index.version_source == "inferred_from_catalog"
    assert "index-dtd-version-inferred" in {item.code for item in inventory.warnings}


def test_regional_v33_is_accepted_and_conflicting_or_unknown_versions_fail_precisely() -> None:
    accepted = parse_public_profile_zip(PACKAGE.read_bytes())
    assert accepted.regional_xml_version == "3.3"
    conflict = _mutate(PACKAGE.read_bytes(), regional=(b'dtd-version="3.3"', b'dtd-version="3.2"'))
    with pytest.raises(EctdParseError, match="DTD validation failed.*dtd-version"):
        parse_public_profile_zip(conflict)
    unknown = _mutate(
        PACKAGE.read_bytes(),
        regional=(
            b"https://www.accessdata.fda.gov/static/eCTD/us-regional-v3-3.dtd",
            b"https://www.accessdata.fda.gov/static/eCTD/us-regional-v9-9.dtd",
        ),
    )
    with pytest.raises(EctdSecurityError, match="unknown DOCTYPE identifier"):
        parse_public_profile_zip(unknown)


def test_authentic_roots_and_namespaces_are_enforced() -> None:
    wrong_namespace = _mutate(
        PACKAGE.read_bytes(), index=(b"http://www.ich.org/ectd", b"urn:not-ich:ectd")
    )
    with pytest.raises(EctdParseError, match="DTD validation failed|root/namespace conflicts"):
        parse_public_profile_zip(wrong_namespace)
    wrong_root = _mutate(PACKAGE.read_bytes(), index=(b"DOCTYPE ectd:ectd", b"DOCTYPE ectd:wrong"))
    with pytest.raises(EctdParseError, match="DOCTYPE root"):
        parse_public_profile_zip(wrong_root)


def test_regional_backbone_relationship_is_not_a_dossier_pdf() -> None:
    inventory = parse_public_profile_zip(PACKAGE.read_bytes())
    assert len(inventory.leaves) == 3
    regional = next(item for item in inventory.package_files if item.member_type == "REGIONAL_XML")
    assert regional.path == "m1/us/us-regional.xml"
    assert regional.relationship == "ICH backbone leaf m42-regional-backbone"
    assert all(item.href != "m1/us/us-regional.xml" for item in inventory.leaves)


def test_referenced_stf_and_non_pdf_members_are_separated_without_analysis() -> None:
    members = _members(PACKAGE.read_bytes())
    index_name = _ending(members, "index.xml")
    prefix = index_name.removesuffix("index.xml")
    original_path = "m3/32-body-data/case-a.pdf"
    original_pdf = members[prefix + original_path]
    original_md5 = hashlib.md5(original_pdf, usedforsecurity=False).hexdigest().encode()
    stf = b'<?xml version="1.0" encoding="UTF-8"?><study id="synthetic"/>'
    stf_md5 = hashlib.md5(stf, usedforsecurity=False).hexdigest().encode()
    members[prefix + "stf.xml"] = stf
    members[index_name] = (
        members[index_name]
        .replace(original_path.encode(), b"stf.xml", 1)
        .replace(original_md5, stf_md5, 1)
    )
    members[_ending(members, "index-md5.txt")] = (
        hashlib.md5(members[index_name], usedforsecurity=False).hexdigest() + "\n"
    ).encode()

    inventory = parse_public_profile_zip(_zip(members))
    assert len(inventory.leaves) == 2
    assert any(item.member_type == "STUDY_TAGGING_FILE" for item in inventory.package_files)
    assert any(
        item.path == original_path and item.member_type == "UNSUPPORTED"
        for item in inventory.package_files
    )
    assert all(item.href != "stf.xml" for item in inventory.leaves)


@pytest.mark.parametrize(
    ("source", "replacement", "heading"),
    [
        (b"m3-2-s-1-2-structure", b"m3-2-s-1-1-nomenclature", "3.2.S.1.1"),
        (b"m3-2-s-1-2-structure", b"m3-2-s-1-2-structure", "3.2.S.1.2"),
        (b"m3-2-s-1-2-structure", b"m3-2-s-1-3-general-properties", "3.2.S.1.3"),
    ],
)
def test_descriptive_module3_elements_do_not_create_fake_heading_segments(
    source: bytes, replacement: bytes, heading: str
) -> None:
    inventory = parse_public_profile_zip(_mutate(PACKAGE.read_bytes(), index=(source, replacement)))
    assert next(item for item in inventory.leaves if item.id == "m42-leaf-a").heading == heading


def test_drug_substance_keywords_and_module1_fields_are_parsed_from_standard_locations() -> None:
    inventory = parse_public_profile_zip(PACKAGE.read_bytes())
    leaf = next(item for item in inventory.leaves if item.id == "m42-leaf-b")
    keywords = {item.name: item.raw_value for item in leaf.keywords}
    assert keywords == {"manufacturer": "all", "substance": "Synthetic Substance B"}
    assert inventory.applicant_name == "RegBridge Synthetic Therapeutics LLC"
    assert inventory.application_number == "999999"
    assert inventory.application_type_code == "fdaat1"
    assert inventory.submission_type == "fdast1"
    assert inventory.submission_id == "0001"
    assert inventory.sequence_number == "0000"


def test_modified_file_is_lifecycle_history_not_archive_traversal() -> None:
    payload = _mutate(
        PACKAGE.read_bytes(),
        index=(
            b'ID="m42-leaf-c" operation="new"',
            b'ID="m42-leaf-c" operation="replace" modified-file="../0001/index.xml#m42-prior-c"',
        ),
    )
    inventory = parse_public_profile_zip(payload)
    leaf = next(item for item in inventory.leaves if item.id == "m42-leaf-c")
    lifecycle = next(item for item in inventory.lifecycle_references if item.leaf_id == leaf.id)
    assert leaf.modified_leaf_id == "m42-prior-c"
    assert lifecycle.modified_file == "../0001/index.xml#m42-prior-c"
    assert leaf.policy_coverage_status == "INSUFFICIENT_APPLICATION_HISTORY"


def test_root_sequence_and_application_wrappers_are_accepted(tmp_path: Path) -> None:
    from scripts.generate_m4_2_dossier import build_package

    for wrapper, expected in (
        ("root", "."),
        ("sequence", "0000"),
        ("application", "synthetic-application/0000"),
    ):
        output = tmp_path / f"{wrapper}.zip"
        build_package(output, wrapper=cast(Any, wrapper))
        assert parse_public_profile_zip(output.read_bytes()).detected_sequence_root == expected


def test_security_boundaries_fail_closed() -> None:
    internal_subset = _mutate(
        PACKAGE.read_bytes(),
        index=(
            b'<!DOCTYPE ectd:ectd SYSTEM "util/dtd/ich-ectd-3-2.dtd">',
            b'<!DOCTYPE ectd:ectd SYSTEM "util/dtd/ich-ectd-3-2.dtd" [<!ENTITY xxe SYSTEM "https://example.invalid/x">]>',
        ),
    )
    with pytest.raises(EctdSecurityError, match="entity declarations|internal subsets"):
        parse_public_profile_zip(internal_subset)

    hostile = _members(PACKAGE.read_bytes())
    prefix = _ending(hostile, "index.xml").removesuffix("index.xml")
    hostile[prefix + "util/dtd/ich-ectd-3-2.dtd"] = b'<!ENTITY xxe SYSTEM "file:///etc/passwd">'
    with pytest.raises(EctdSecurityError, match="security violation.*external entity"):
        parse_public_profile_zip(_zip(hostile))

    escaped = _members(PACKAGE.read_bytes())
    escaped["../escape.pdf"] = b"%PDF-hostile"
    with pytest.raises(EctdSecurityError, match="unsafe archive member path"):
        parse_public_profile_zip(_zip(escaped))

    ambiguous = _members(PACKAGE.read_bytes())
    index_name = _ending(ambiguous, "index.xml")
    ambiguous["0000/index.xml"] = ambiguous[index_name]
    with pytest.raises(EctdParseError, match="multiple ambiguous sequence roots"):
        parse_public_profile_zip(_zip(ambiguous))

    bomb = io.BytesIO()
    with zipfile.ZipFile(bomb, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("bomb.txt", b"0" * (EctdParserLimits.max_member_bytes + 1))
    with pytest.raises(EctdSecurityError, match="per-file limit|compression-ratio"):
        parse_public_profile_zip(bomb.getvalue())


def test_outside_policy_coverage_never_becomes_unconditional_reuse() -> None:
    payload = _mutate(
        PACKAGE.read_bytes(),
        index=(b"m3-2-s-1-2-structure", b"m3-2-s-2-1-manufacturer"),
    )
    payload = _mutate(
        payload,
        index=(b"m3-2-s-1-general-information", b"m3-2-s-2-manufacture"),
    )
    inventory = parse_public_profile_zip(payload)
    leaf = next(item for item in inventory.leaves if item.id == "m42-leaf-a")
    assert leaf.heading == "3.2.S.2.1"
    assert leaf.policy_coverage_status == "OUTSIDE_ENCODED_POLICY_COVERAGE"
    service = AnalysisService(
        model=ProductFixtureModel(),
        repository=cast(Any, CaptureRepository()),
        settings=Settings(llm_mode=LlmMode.FIXTURE),
    )
    result = service.analyze(inventory, leaf.id, _target())
    assert result.decision.value == "HUMAN_REGULATORY_REVIEW"
    assert result.human_approval_required is True


def test_clean_negative_requires_the_explicit_encoded_condition() -> None:
    payload = _mutate(
        PACKAGE.read_bytes(),
        index=(b'manufacturer="all"', b'manufacturer="Synthetic Manufacturer B"'),
    )
    inventory = parse_public_profile_zip(payload)
    leaf = next(item for item in inventory.leaves if item.id == "m42-leaf-b")
    assert leaf.heading == "3.2.S.1"
    assert leaf.policy_coverage_status == "NO_MIGRATION_CHANGE_DETECTED"
    assert "Explicit encoded clean-negative" in leaf.policy_coverage_basis


def test_analyzer_and_all_comparison_systems_use_same_inventory_without_label_leakage() -> None:
    client = TestClient(app)
    parsed = client.post(
        "/api/v1/applications/parse",
        content=PACKAGE.read_bytes(),
        headers={"Content-Type": "application/zip"},
    )
    assert parsed.status_code == 200, parsed.text
    inventory = parsed.json()
    target = _target().model_dump(mode="json")
    dossier = client.post(
        "/api/v1/dossier-analyses",
        json={"inventory_id": inventory["id"], "model_id": "gpt-5.5", "target_context": target},
    )
    assert dossier.status_code == 202, dossier.text
    dossier_run = client.get(f"/api/v1/dossier-analyses/{dossier.json()['run_id']}").json()
    assert dossier_run["state"] == "completed"
    comparison = client.post(
        "/api/v1/comparisons",
        json={"inventory_id": inventory["id"], "model_id": "gpt-5.5", "target_context": target},
    )
    assert comparison.status_code == 202, comparison.text
    run = client.get(f"/api/v1/comparisons/{comparison.json()['comparison_id']}").json()
    assert run["state"] == "completed"
    for leaf in inventory["leaves"]:
        cells = [item for item in run["results"] if item["leaf_id"] == leaf["id"]]
        assert {item["system"] for item in cells} == {"B0", "B1", "B2", "RegBridge"}
        assert {item["package_sha256"] for item in cells} == {inventory["package_sha256"]}
        assert {item["selected_file_sha256"] for item in cells} == {leaf["file_sha256"]}
        assert len({item["package_input_digest"] for item in cells}) == 1
    serialized = json.dumps(run, sort_keys=True).casefold()
    assert "reference_decision" not in serialized
    assert "benchmark_id" not in serialized
    assert "fixture_id" not in serialized
    assert "adjudication_rationale" not in serialized


def test_two_parse_and_analysis_runs_are_digest_reproducible() -> None:
    payload = PACKAGE.read_bytes()
    inventories = [parse_public_profile_zip(payload) for _ in range(2)]
    inventory_digests = [canonical_digest(item.model_dump(mode="json")) for item in inventories]
    assert len(set(inventory_digests)) == 1

    async def analyze(inventory: Any) -> str:
        records: list[dict[str, object]] = []
        for leaf in inventory.leaves:
            capture = CaptureRepository()
            result = await AnalysisService(
                model=ProductFixtureModel(),
                repository=cast(Any, capture),
                settings=Settings(llm_mode=LlmMode.FIXTURE),
            ).analyze_async(inventory, leaf.id, _target())
            records.append(
                {
                    "result": result.model_dump(
                        mode="json",
                        exclude={
                            "trace": {"__all__": {"occurred_at"}},
                            "model_run": {"latency_ms"},
                        },
                    ),
                    "graph": capture.neighborhood.model_dump(mode="json")
                    if capture.neighborhood
                    else None,
                }
            )
        return canonical_digest(records)

    assert asyncio.run(analyze(inventories[0])) == asyncio.run(analyze(inventories[1]))


def test_user_acceptance_zip_is_tested_against_profile_without_spelling_exceptions() -> None:
    if not ACCEPTANCE_PACKAGE.is_file():
        pytest.skip(f"acceptance package missing: {ACCEPTANCE_PACKAGE}")
    payload = ACCEPTANCE_PACKAGE.read_bytes()
    adjudication = adjudicate_public_profile_zip(payload)
    assert adjudication.status == "rejected_nonconforming"
    comparison = adjudication.dtd_comparisons[0]
    assert comparison.archive_sha256 == (
        "f28d7c22d0ebccff6176058926ed7b956744c20942929676bcc1345cf6104134"
    )
    assert comparison.pinned_sha256 == (
        "c094aa2bded99564ade8ac78ae1540f95e518461b8eebe9a3063f67a165c2731"
    )
    assert comparison.archive_size == 149
    assert comparison.pinned_size == 31_400
    assert comparison.raw_bytes_equal is False
    assert comparison.normalized_text_equal is False
    assert comparison.semantic_text_equal is False
    assert comparison.difference_class == "substantive"
    assert comparison.hostile is False
    assert comparison.archive_copy_ignored is True
    assert comparison.first_substantive_differences[0].archive_text is None
    assert comparison.first_substantive_differences[0].pinned_line == 56
    first_pinned_text = comparison.first_substantive_differences[0].pinned_text
    assert first_pinned_text is not None
    assert first_pinned_text.startswith("<!ENTITY % att")
    assert len(adjudication.xml_validations) == 2
    assert all(not result.valid for result in adjudication.xml_validations)
    assert all(
        "namespace name for xlink does not match the DTD" in result.detail
        for result in adjudication.xml_validations
    )
    with pytest.raises(EctdParseError) as captured:
        parse_uploaded_zip(payload)
    error = str(captured.value)
    assert "index.xml:" in error
    assert "m1/us/us-regional.xml:" in error
    assert error.count("namespace name for xlink does not match the DTD") == 2
