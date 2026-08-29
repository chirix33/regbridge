from pathlib import Path

import pytest
import yaml
from app.config import REPOSITORY_ROOT
from app.domain.enums import ReviewStatus
from app.standards.registry import SourceDigestMismatchError, StandardsRegistry


def test_reviewed_manifest_loads_and_verifies_frozen_source() -> None:
    manifest = StandardsRegistry().load()

    assert manifest.snapshot_id == "fda-cder-demo-v1"
    assert len(manifest.sources) == 1
    assert manifest.sources[0].review_status == ReviewStatus.REVIEWED
    assert manifest.sources[0].sha256 == (
        "dccd247940cdf5bc7cbf6a5e31b8f2547ad7f61650ae1a138113feb315f8002e"
    )


def test_registry_rejects_digest_drift(tmp_path: Path) -> None:
    source_manifest = REPOSITORY_ROOT / "data" / "standards" / "manifest.yaml"
    payload = yaml.safe_load(source_manifest.read_text(encoding="utf-8"))
    standards_directory = tmp_path / "standards"
    snapshot_directory = standards_directory / "snapshots"
    snapshot_directory.mkdir(parents=True)
    snapshot_path = snapshot_directory / "fda-ectd-v4-technical-conformance-guide-v1.5.pdf"
    snapshot_path.write_bytes(b"not the reviewed source")
    manifest_path = standards_directory / "manifest.yaml"
    manifest_path.write_text(yaml.safe_dump(payload), encoding="utf-8")

    with pytest.raises(SourceDigestMismatchError, match="source digest mismatch"):
        StandardsRegistry(manifest_path).load()

