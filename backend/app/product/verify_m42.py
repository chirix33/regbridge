from __future__ import annotations

import asyncio
import hashlib
import json
import tempfile
from datetime import date
from pathlib import Path
from typing import Any, cast

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
from app.parsers.ectd322 import EctdParseError
from app.parsers.profile322 import parse_uploaded_zip
from app.parsers.public322 import (
    independent_validate_package,
    load_catalog,
    parse_public_profile_zip,
)
from app.product.models_registry import ProductFixtureModel
from app.product.services import CaptureRepository, canonical_digest

PROTECTED_MANIFEST = REPOSITORY_ROOT / "data" / "product" / "m4-2" / "protected-artifacts.json"
PACKAGE = (
    REPOSITORY_ROOT / "data" / "demo-dossiers" / "m4-2" / "regbridge-m4-2-public-standards.zip"
)
GENERATION_MANIFEST = PACKAGE.parent / "generation-manifest.json"
ACCEPTANCE_PACKAGE = REPOSITORY_ROOT / "meridianvelacytenda217999seq0000ectd322spec.zip"


def _tree_digest(relative: str) -> tuple[int, str]:
    root = REPOSITORY_ROOT / relative
    digest = hashlib.sha256()
    files = sorted(path for path in root.rglob("*") if path.is_file())
    for path in files:
        digest.update(path.relative_to(REPOSITORY_ROOT).as_posix().encode())
        digest.update(path.read_bytes())
    return len(files), digest.hexdigest()


def verify_protected() -> dict[str, dict[str, object]]:
    expected = json.loads(PROTECTED_MANIFEST.read_text(encoding="utf-8"))
    result: dict[str, dict[str, object]] = {}
    for relative, record in expected["trees"].items():
        count, digest = _tree_digest(relative)
        if count != record["file_count"] or digest != record["sha256"]:
            raise RuntimeError(f"protected artifact tree changed: {relative}")
        result[relative] = {"file_count": count, "pre_sha256": digest, "post_sha256": digest}
    for relative, expected_digest in expected["files"].items():
        digest = hashlib.sha256((REPOSITORY_ROOT / relative).read_bytes()).hexdigest()
        if digest != expected_digest:
            raise RuntimeError(f"protected artifact file changed: {relative}")
        result[relative] = {"file_count": 1, "pre_sha256": digest, "post_sha256": digest}
    return result


def verify_assets() -> dict[str, str]:
    return {asset_id: asset.sha256 for asset_id, asset in sorted(load_catalog().items())}


def verify_package() -> dict[str, object]:
    manifest = json.loads(GENERATION_MANIFEST.read_text(encoding="utf-8"))
    payload = PACKAGE.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    if digest != manifest["archive_sha256"]:
        raise RuntimeError("committed M4.2 package digest mismatch")
    validation = independent_validate_package(payload)
    if not all(item.valid for item in validation):
        raise RuntimeError("M4.2 package failed independent pinned DTD validation")
    inventory = parse_public_profile_zip(payload)
    if len(inventory.leaves) != 3:
        raise RuntimeError("M4.2 package must expose exactly three dossier PDFs")
    return {
        "package_id": manifest["package_id"],
        "archive_sha256": digest,
        "inventory_sha256": manifest["inventory_sha256"],
        "profile_id": inventory.input_profile_id,
        "profile_version": inventory.input_profile_version,
        "warnings": [item.code for item in inventory.warnings],
        "coverage": inventory.policy_coverage_counts,
        "independent_dtd_validation": [item.__dict__ for item in validation],
    }


def verify_acceptance_package() -> dict[str, object]:
    if not ACCEPTANCE_PACKAGE.is_file():
        return {"status": "missing", "path": str(ACCEPTANCE_PACKAGE)}
    payload = ACCEPTANCE_PACKAGE.read_bytes()
    try:
        inventory = parse_uploaded_zip(payload)
    except EctdParseError as error:
        return {
            "status": "rejected_nonconforming",
            "path": str(ACCEPTANCE_PACKAGE),
            "archive_sha256": hashlib.sha256(payload).hexdigest(),
            "profile_error": str(error),
        }
    return {
        "status": "accepted",
        "path": str(ACCEPTANCE_PACKAGE),
        "archive_sha256": hashlib.sha256(payload).hexdigest(),
        "profile_id": inventory.input_profile_id,
        "warnings": [item.code for item in inventory.warnings],
    }


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


async def _result_digest(payload: bytes) -> str:
    inventory = parse_public_profile_zip(payload)
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


def verify_reproducibility() -> dict[str, object]:
    from scripts.generate_m4_2_dossier import build_package

    runs: list[dict[str, str]] = []
    with tempfile.TemporaryDirectory(prefix="regbridge-m42-repro-") as temporary:
        for index in range(2):
            path = Path(temporary) / f"run-{index}.zip"
            manifest = build_package(path)
            payload = path.read_bytes()
            inventory = parse_public_profile_zip(payload)
            runs.append(
                {
                    "package_sha256": hashlib.sha256(payload).hexdigest(),
                    "inventory_sha256": hashlib.sha256(
                        inventory.model_dump_json(exclude={"id"}).encode()
                    ).hexdigest(),
                    "result_sha256": asyncio.run(_result_digest(payload)),
                    "manifest_inventory_sha256": str(manifest["inventory_sha256"]),
                }
            )
    if runs[0] != runs[1]:
        raise RuntimeError("two M4.2 generation/parse/analysis runs were not reproducible")
    return {"runs": 2, **runs[0]}


def main() -> None:
    report = {
        "protected_artifacts": verify_protected(),
        "pinned_assets": verify_assets(),
        "package": verify_package(),
        "acceptance_package": verify_acceptance_package(),
        "reproducibility": verify_reproducibility(),
    }
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
