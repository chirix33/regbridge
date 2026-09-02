from __future__ import annotations

import asyncio
import hashlib
import json
import sys
import time
import zipfile
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.analyzer.service import AnalysisService
from app.baselines.runner import OmittedSemanticModel
from app.config import Settings
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
from app.llm.responses import RetryableLiveModelError
from app.main import app
from app.parsers.ectd322 import EctdParseError, EctdSecurityError
from app.parsers.profile322 import PROFILE_ID, parse_profile_zip
from app.product.comparison import package_material
from app.product.models import DossierAnalysisRequest
from app.product.models_registry import ModelProfileRegistry, ProductFixtureModel
from app.product.repository import DossierRunRepository, InventoryRepository
from app.product.services import CaptureRepository, DossierAnalysisManager, stable_run_id
from scripts.generate_m4_1_dossier import APPLICANT, ZIP_PATH, build_package

client = TestClient(app)


def _rewrite_zip(source: Path, target: Path, changes: dict[str, bytes | None]) -> None:
    with zipfile.ZipFile(source) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    for name, payload in changes.items():
        if payload is None:
            members.pop(name, None)
        else:
            members[name] = payload
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in sorted(members.items()):
            if payload is not None:
                archive.writestr(name, payload)


def _manager_for_one_leaf(
    inventory: object, leaf_id: str
) -> tuple[DossierAnalysisManager, str]:
    settings = Settings(llm_mode=LlmMode.FIXTURE)
    inventories = InventoryRepository(capacity=2, ttl_seconds=60)
    envelope = inventories.put(inventory)  # type: ignore[arg-type]
    runs = DossierRunRepository(capacity=2, ttl_seconds=60, prefix="dossier")
    manager = DossierAnalysisManager(
        inventories=inventories,
        runs=runs,
        registry=ModelProfileRegistry(settings),
        settings=settings,
    )
    run = manager.create(
        DossierAnalysisRequest(
            inventory_id=envelope.inventory_id,
            model_id="gpt-5.5",
            target_context=_target(),
            leaf_ids=(leaf_id,),
        )
    )
    return manager, run.run_id


def _target() -> TargetContext:
    return TargetContext(
        authority=Authority.FDA,
        center=Center.CDER,
        application_type=ApplicationType.NDA,
        source_standard=StandardVersion.ECTD_3_2_2,
        target_standard=StandardVersion.ECTD_4_0,
        analysis_date=date(2026, 9, 2),
        reuse_operation=ReuseOperation.REFERENCE_EXISTING_CONTENT,
        standards_snapshot_id="fda-cder-demo-v1",
        scenario_mode=ScenarioMode.PROSPECTIVE_FORWARD_COMPATIBILITY,
        metadata_plan=MetadataPlan(
            intent=MetadataMigrationIntent.PRESERVE_EXISTING_LIFECYCLE,
            manufacturer_partitioning=ManufacturerPartitioning.UNKNOWN,
        ),
    )


def _analyze(payload: bytes) -> dict[str, str]:
    inventory = parse_profile_zip(payload)
    output: dict[str, str] = {}
    for leaf in inventory.leaves:
        repository = CaptureRepository()
        service = AnalysisService(
            model=ProductFixtureModel(),
            repository=repository,  # type: ignore[arg-type]
            settings=Settings(llm_mode=LlmMode.FIXTURE),
        )
        result = asyncio.run(service.analyze_async(inventory, leaf.id, _target()))
        output[leaf.id] = result.decision.value
    return output


def test_composite_profile_is_xml_pdf_and_checksum_derived() -> None:
    inventory = parse_profile_zip(ZIP_PATH.read_bytes())
    assert inventory.input_profile_id == PROFILE_ID
    assert inventory.detected_sequence_root == "synthetic-application/0000"
    assert inventory.layout == "authentic_sequence_layout"
    assert inventory.package_profile_status == "passed"
    assert inventory.index_md5_matches is True
    assert len(inventory.leaves) == 3
    assert all(leaf.declared_checksum_type == "md5" for leaf in inventory.leaves)
    assert all(leaf.declared_checksum_matches is True for leaf in inventory.leaves)
    assert inventory.regional_xml_sha256
    assert inventory.applicant_name == APPLICANT
    assert {item.member_type for item in inventory.package_files} >= {
        "BACKBONE_XML",
        "REGIONAL_XML",
        "DOSSIER_DOCUMENT",
    }


def test_composite_produces_three_archetypes_without_fixture_lookup() -> None:
    decisions = _analyze(ZIP_PATH.read_bytes())
    assert decisions == {
        "m41-leaf-a": "REUSE_WITH_NEW_CONTEXT",
        "m41-leaf-b": "REUSE_AS_LEGACY_REFERENCE",
        "m41-leaf-c": "HUMAN_REGULATORY_REVIEW",
    }


@pytest.mark.parametrize(
    ("kwargs", "leaf_id", "expected_not"),
    [
        ({"case_a_heading": "m3-2-s-1"}, "m41-leaf-a", "REUSE_WITH_NEW_CONTEXT"),
        ({"manufacturer": "synthetic-maker-001"}, "m41-leaf-b", "HUMAN_REGULATORY_REVIEW"),
        ({"case_c_applicant": APPLICANT}, "m41-leaf-c", "HUMAN_REGULATORY_REVIEW"),
    ],
)
def test_archetype_metamorphoses_change_pipeline_result(
    kwargs: dict[str, str], leaf_id: str, expected_not: str, tmp_path: Path
) -> None:
    path = tmp_path / "variant.zip"
    build_package(path, **kwargs)
    assert _analyze(path.read_bytes())[leaf_id] != expected_not


def test_ambiguous_or_missing_sequence_root_fails_closed(tmp_path: Path) -> None:
    missing = tmp_path / "missing.zip"
    with zipfile.ZipFile(missing, "w") as archive:
        archive.writestr("readme.txt", "none")
    with pytest.raises(EctdParseError, match="no supported sequence root"):
        parse_profile_zip(missing.read_bytes())
    ambiguous = tmp_path / "ambiguous.zip"
    with zipfile.ZipFile(ambiguous, "w") as archive:
        archive.writestr("a/0000/index.xml", "<ectd/>")
        archive.writestr("b/0000/index.xml", "<ectd/>")
    with pytest.raises(EctdParseError, match="multiple ambiguous"):
        parse_profile_zip(ambiguous.read_bytes())


def test_internal_entity_and_checksum_mutation_are_rejected(tmp_path: Path) -> None:
    extracted = tmp_path / "package"
    with zipfile.ZipFile(ZIP_PATH) as archive:
        archive.extractall(extracted)
    index = extracted / "synthetic-application" / "0000" / "index.xml"
    index.write_text(
        index.read_text(encoding="utf-8").replace(
            '<!DOCTYPE ectd SYSTEM "util/dtd/ich-ectd-3-2.dtd">',
            '<!DOCTYPE ectd [<!ENTITY xxe SYSTEM "file:///secret">]>',
        ),
        encoding="utf-8",
    )
    hostile = tmp_path / "hostile.zip"
    with zipfile.ZipFile(hostile, "w") as archive:
        for path in extracted.rglob("*"):
            if path.is_file():
                archive.write(path, path.relative_to(extracted).as_posix())
    with pytest.raises(EctdSecurityError, match="internal entity"):
        parse_profile_zip(hostile.read_bytes())


def test_sequence_root_may_be_archive_root_and_legacy_layout_is_explicit(
    tmp_path: Path,
) -> None:
    root_zip = tmp_path / "root.zip"
    with zipfile.ZipFile(ZIP_PATH) as source, zipfile.ZipFile(root_zip, "w") as target:
        for name in source.namelist():
            target.writestr(name.removeprefix("synthetic-application/0000/"), source.read(name))
    parsed = parse_profile_zip(root_zip.read_bytes())
    assert parsed.detected_sequence_root == "."
    assert parsed.layout == "authentic_sequence_layout"


def test_unrecognized_doctype_and_unsupported_version_fail_closed(tmp_path: Path) -> None:
    with zipfile.ZipFile(ZIP_PATH) as archive:
        index_name = "synthetic-application/0000/index.xml"
        source = archive.read(index_name)
    unknown = tmp_path / "unknown-doctype.zip"
    _rewrite_zip(
        ZIP_PATH,
        unknown,
        {index_name: source.replace(b"ich-ectd-3-2.dtd", b"unknown.dtd")},
    )
    with pytest.raises(EctdSecurityError, match="unrecognized DOCTYPE"):
        parse_profile_zip(unknown.read_bytes())
    unsupported = tmp_path / "unsupported-version.zip"
    changed = source.replace(b'dtd-version="3.2.2"', b'dtd-version="9.9"')
    index_md5 = hashlib.md5(changed, usedforsecurity=False).hexdigest().encode() + b"\n"
    _rewrite_zip(
        ZIP_PATH,
        unsupported,
        {index_name: changed, "synthetic-application/0000/index-md5.txt": index_md5},
    )
    with pytest.raises(EctdParseError, match="version is missing or unsupported"):
        parse_profile_zip(unsupported.read_bytes())


def test_leaf_and_index_md5_failures_are_distinct_from_sha256_provenance(
    tmp_path: Path,
) -> None:
    malformed = tmp_path / "malformed-leaf-md5.zip"
    with zipfile.ZipFile(ZIP_PATH) as archive:
        index_name = "synthetic-application/0000/index.xml"
        index = archive.read(index_name)
    changed = index.replace(
        b'checksum-type="md5" checksum="', b'checksum-type="md5" checksum="not-an-md5', 1
    )
    changed_index_md5 = hashlib.md5(changed, usedforsecurity=False).hexdigest().encode() + b"\n"
    _rewrite_zip(
        ZIP_PATH,
        malformed,
        {
            index_name: changed,
            "synthetic-application/0000/index-md5.txt": changed_index_md5,
        },
    )
    with pytest.raises(EctdParseError, match="malformed MD5"):
        parse_profile_zip(malformed.read_bytes())

    bad_index = tmp_path / "bad-index-md5.zip"
    _rewrite_zip(
        ZIP_PATH,
        bad_index,
        {"synthetic-application/0000/index-md5.txt": b"0" * 32 + b"\n"},
    )
    with pytest.raises(EctdParseError, match="does not match"):
        parse_profile_zip(bad_index.read_bytes())

    parsed = parse_profile_zip(ZIP_PATH.read_bytes())
    document = next(item for item in parsed.package_files if item.member_type == "DOSSIER_DOCUMENT")
    assert document.declared_checksum_type == "md5"
    assert document.provenance_sha256 != document.declared_checksum


@pytest.mark.parametrize("operation", ["append", "replace"])
def test_lifecycle_operations_require_safe_modified_file(
    operation: str, tmp_path: Path
) -> None:
    with zipfile.ZipFile(ZIP_PATH) as archive:
        index_name = "synthetic-application/0000/index.xml"
        source = archive.read(index_name)
    changed = source.replace(
        b'ID="m41-leaf-a" operation="new"',
        f'ID="m41-leaf-a" operation="{operation}" modified-file="prior-leaf-a"'.encode(),
    )
    index_md5 = hashlib.md5(changed, usedforsecurity=False).hexdigest().encode() + b"\n"
    path = tmp_path / f"{operation}.zip"
    _rewrite_zip(
        ZIP_PATH,
        path,
        {index_name: changed, "synthetic-application/0000/index-md5.txt": index_md5},
    )
    parsed = parse_profile_zip(path.read_bytes())
    reference = next(item for item in parsed.lifecycle_references if item.leaf_id == "m41-leaf-a")
    assert reference.operation.value == operation
    assert reference.prior_reference_status == "outside_scope"

    unsafe = tmp_path / f"{operation}-unsafe.zip"
    unsafe_xml = changed.replace(b"prior-leaf-a", b"../escape")
    unsafe_md5 = hashlib.md5(unsafe_xml, usedforsecurity=False).hexdigest().encode() + b"\n"
    _rewrite_zip(
        ZIP_PATH,
        unsafe,
        {index_name: unsafe_xml, "synthetic-application/0000/index-md5.txt": unsafe_md5},
    )
    with pytest.raises(EctdSecurityError):
        parse_profile_zip(unsafe.read_bytes())


def test_delete_records_lifecycle_without_treating_backbone_as_pdf(tmp_path: Path) -> None:
    with zipfile.ZipFile(ZIP_PATH) as archive:
        index_name = "synthetic-application/0000/index.xml"
        source = archive.read(index_name)
    leaf_start = source.index(b'<leaf ID="m41-leaf-a"')
    leaf_end = source.index(b">", leaf_start)
    replacement = (
        b'<leaf ID="m41-leaf-a" operation="delete" '
        b'modified-file="prior-leaf-a"'
    )
    changed = source[:leaf_start] + replacement + source[leaf_end:]
    index_md5 = hashlib.md5(changed, usedforsecurity=False).hexdigest().encode() + b"\n"
    path = tmp_path / "delete.zip"
    _rewrite_zip(
        ZIP_PATH,
        path,
        {index_name: changed, "synthetic-application/0000/index-md5.txt": index_md5},
    )
    parsed = parse_profile_zip(path.read_bytes())
    assert len(parsed.leaves) == 2
    assert any(item.operation.value == "delete" for item in parsed.lifecycle_references)
    assert all(
        item.member_type != "DOSSIER_DOCUMENT" or item.path.endswith(".pdf")
        for item in parsed.package_files
    )


def test_inventory_repository_is_opaque_bounded_and_expiring() -> None:
    parsed = parse_profile_zip(ZIP_PATH.read_bytes())
    repository = InventoryRepository(capacity=1, ttl_seconds=60)
    first = repository.put(parsed)
    second = repository.put(parsed)
    assert first.inventory_id.startswith("inv-") and first.inventory_id != second.inventory_id
    with pytest.raises(KeyError):
        repository.get(first.inventory_id)
    with pytest.raises(KeyError):
        repository.get("../inventory")
    repository._items[second.inventory_id].expires_at = time.monotonic() - 1
    with pytest.raises(KeyError):
        repository.get(second.inventory_id)


def test_package_input_is_label_and_identifier_free_and_identity_is_config_scoped() -> None:
    inventory = parse_profile_zip(ZIP_PATH.read_bytes())
    leaf = inventory.leaves[0]
    material, aliases = package_material(inventory, leaf, _target())
    serialized = json.dumps(material)
    assert leaf.id not in serialized
    assert inventory.id not in serialized
    assert "reference_decision" not in serialized and "fixture_id" not in serialized
    assert all(identifier not in serialized for identifier in aliases.values())
    profile_a = "a" * 64
    profile_b = "b" * 64
    identity_a = stable_run_id("dossier", inventory.package_sha256, profile_a)
    assert identity_a == stable_run_id("dossier", inventory.package_sha256, profile_a)
    assert identity_a != stable_run_id("dossier", inventory.package_sha256, profile_b)


def test_public_product_api_uses_real_zip_and_exposes_no_secrets() -> None:
    catalog = client.get("/api/v1/models")
    assert catalog.status_code == 200
    models = catalog.json()["models"]
    assert [item["model_id"] for item in models] == ["gpt-5.5", "qwen3.6-local"]
    assert models[1]["availability"] == "coming_soon"
    assert "api_key" not in catalog.text.casefold()

    parsed_response = client.post(
        "/api/v1/applications/parse",
        content=ZIP_PATH.read_bytes(),
        headers={"content-type": "application/zip"},
    )
    assert parsed_response.status_code == 200
    parsed = parsed_response.json()
    assert parsed["id"].startswith("inv-")
    assert client.get(f"/api/v1/applications/{parsed['id']}").status_code == 200

    request = {
        "inventory_id": parsed["id"],
        "model_id": "gpt-5.5",
        "target_context": _target().model_dump(mode="json"),
    }
    dossier = client.post("/api/v1/dossier-analyses", json=request)
    assert dossier.status_code == 202
    completed = client.get(f"/api/v1/dossier-analyses/{dossier.json()['run_id']}").json()
    assert completed["state"] == "completed"
    assert completed["expert_validated"] is False
    assert completed["operational_status"] == "not_operational"
    assert len(completed["results"]) == 3

    comparison = client.post("/api/v1/comparisons", json=request)
    assert comparison.status_code == 202
    result = client.get(f"/api/v1/comparisons/{comparison.json()['comparison_id']}").json()
    assert result["state"] == "completed"
    assert len(result["results"]) == 12
    assert all(
        item["model"]["model_profile_id"] == "model-free"
        for item in result["results"]
        if item["system"] == "B2"
    )
    assert "accuracy" not in json.dumps(result).casefold()


def test_b2_omitted_semantic_model_has_no_network_capability() -> None:
    model = OmittedSemanticModel()
    assert not hasattr(model, "base_url")


def test_transport_retries_twice_but_downstream_persistence_never_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inventory = parse_profile_zip(ZIP_PATH.read_bytes())
    original_complete = ProductFixtureModel.complete
    transport_calls = 0

    async def flaky_complete(self: ProductFixtureModel, request: object, output_type: object):
        nonlocal transport_calls
        transport_calls += 1
        if transport_calls < 3:
            raise RetryableLiveModelError("synthetic_transport_failure")
        return await original_complete(self, request, output_type)  # type: ignore[arg-type]

    monkeypatch.setattr(ProductFixtureModel, "complete", flaky_complete)
    manager, run_id = _manager_for_one_leaf(inventory, "m41-leaf-c")
    asyncio.run(manager.execute(run_id))
    completed = manager.runs.get(run_id)
    assert completed.state == "completed"
    assert completed.results[0].model.attempt_count == 3
    assert completed.results[0].model.retry_causes == (
        "synthetic_transport_failure",
        "synthetic_transport_failure",
    )

    persistence_calls = 0

    async def counted_complete(self: ProductFixtureModel, request: object, output_type: object):
        nonlocal persistence_calls
        persistence_calls += 1
        return await original_complete(self, request, output_type)  # type: ignore[arg-type]

    def fail_save(self: CaptureRepository, result: object, graph: object) -> None:
        raise ValueError("synthetic persistence failure")

    monkeypatch.setattr(ProductFixtureModel, "complete", counted_complete)
    monkeypatch.setattr(CaptureRepository, "save", fail_save)
    manager, run_id = _manager_for_one_leaf(inventory, "m41-leaf-c")
    asyncio.run(manager.execute(run_id))
    failed = manager.runs.get(run_id)
    assert failed.state == "failed"
    assert persistence_calls == 1
    assert failed.failures[0].stage == "persistence"
    assert failed.failures[0].cause == "AnalysisPipelineError"
    assert failed.failures[0].retryable is False
