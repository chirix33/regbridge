from pathlib import Path

import pytest
import yaml
from app.config import REPOSITORY_ROOT
from app.domain.enums import ReviewStatus
from app.standards.operational import OperationalStatusRegistry
from app.standards.registry import SourceDigestMismatchError, StandardsRegistry


def test_source_verified_manifest_loads_and_verifies_frozen_sources() -> None:
    manifest = StandardsRegistry().load()

    assert manifest.snapshot_id == "fda-cder-demo-v1"
    assert len(manifest.sources) == 2
    assert all(source.review_status == ReviewStatus.SOURCE_VERIFIED for source in manifest.sources)
    assert all(source.expert_validated is False for source in manifest.sources)


def test_registry_rejects_digest_drift(tmp_path: Path) -> None:
    source_manifest = REPOSITORY_ROOT / "data" / "standards" / "manifest.yaml"
    payload = yaml.safe_load(source_manifest.read_text(encoding="utf-8"))
    standards_directory = tmp_path / "standards"
    snapshot_directory = standards_directory / "snapshots"
    snapshot_directory.mkdir(parents=True)
    for source in payload["sources"]:
        snapshot_path = snapshot_directory / Path(source["local_path"]).name
        snapshot_path.write_bytes(b"not the reviewed source")
    manifest_path = standards_directory / "manifest.yaml"
    manifest_path.write_text(yaml.safe_dump(payload), encoding="utf-8")

    with pytest.raises(SourceDigestMismatchError, match="source digest mismatch"):
        StandardsRegistry(manifest_path).load()


def test_operational_status_is_recorded_and_not_expert_validated() -> None:
    record = OperationalStatusRegistry().load()
    assert record.status.value == "not_operational"
    assert record.recorded_by == "author-01"
    assert record.review_status.value == "author_adjudicated_for_demo"
    assert record.enforcement_mode.value == "disabled"
    assert record.expert_validated is False
