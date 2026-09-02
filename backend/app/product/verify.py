from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import date
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
from app.parsers.profile322 import parse_profile_zip
from app.product.models_registry import ProductFixtureModel
from app.product.services import CaptureRepository, canonical_digest

MANIFEST = REPOSITORY_ROOT / "data" / "product" / "m4-1" / "protected-artifacts.json"
COMPOSITE = REPOSITORY_ROOT / "data" / "demo-dossiers" / "m4-1" / "regbridge-m4-1-composite.zip"
GENERATION_MANIFEST = COMPOSITE.parent / "generation-manifest.json"


def _tree_digest(relative: str) -> tuple[int, str]:
    root = REPOSITORY_ROOT / relative
    digest = hashlib.sha256()
    files = sorted(path for path in root.rglob("*") if path.is_file())
    for path in files:
        digest.update(path.relative_to(REPOSITORY_ROOT).as_posix().encode())
        digest.update(path.read_bytes())
    return len(files), digest.hexdigest()


def verify_protected() -> dict[str, str]:
    expected = json.loads(MANIFEST.read_text(encoding="utf-8"))["trees"]
    results: dict[str, str] = {}
    for relative, record in expected.items():
        count, digest = _tree_digest(relative)
        if count != record["file_count"] or digest != record["sha256"]:
            raise RuntimeError(f"protected M3/M4 artifact tree changed: {relative}")
        results[relative] = digest
    return results


def verify_composite() -> dict[str, object]:
    manifest = json.loads(GENERATION_MANIFEST.read_text(encoding="utf-8"))
    digest = hashlib.sha256(COMPOSITE.read_bytes()).hexdigest()
    if digest != manifest["archive_sha256"]:
        raise RuntimeError("committed composite dossier digest mismatch")
    inventory = parse_profile_zip(COMPOSITE.read_bytes())
    if len(inventory.leaves) != 3 or inventory.package_profile_status != "passed":
        raise RuntimeError("composite dossier does not satisfy the controlled profile")
    return {"archive_sha256": digest, "document_candidates": len(inventory.leaves)}


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


async def _fixture_digest() -> str:
    inventory = parse_profile_zip(COMPOSITE.read_bytes())
    records: list[dict[str, object]] = []
    for leaf in inventory.leaves:
        capture = CaptureRepository()
        service = AnalysisService(
            model=ProductFixtureModel(),
            repository=cast(Any, capture),
            settings=Settings(llm_mode=LlmMode.FIXTURE),
        )
        result = await service.analyze_async(inventory, leaf.id, _target())
        if capture.neighborhood is None:
            raise RuntimeError("fixture analysis did not commit its graph")
        records.append(
            {
                "leaf_id": leaf.id,
                "decision": result.decision,
                "evidence": [item.model_dump(mode="json") for item in result.evidence],
                "graph": capture.neighborhood.model_dump(mode="json"),
                # UTC occurrence timestamps are audit metadata rather than decision content.
                "trace": [
                    item.model_dump(mode="json", exclude={"occurred_at"})
                    for item in result.trace
                ],
            }
        )
    return canonical_digest(records)


def verify_fixture_repetition() -> dict[str, object]:
    first = asyncio.run(_fixture_digest())
    second = asyncio.run(_fixture_digest())
    if first != second:
        raise RuntimeError("two fixture-mode dossier runs produced different content digests")
    return {"runs": 2, "decision_evidence_graph_trace_sha256": first}


def main() -> None:
    report = {
        "protected": verify_protected(),
        "composite": verify_composite(),
        "fixture_repetition": verify_fixture_repetition(),
    }
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
