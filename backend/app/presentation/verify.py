import argparse
import asyncio
import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any

from app.analyzer.service import AnalysisService
from app.config import REPOSITORY_ROOT, Settings
from app.domain.enums import (
    ApplicationType,
    Authority,
    Center,
    LlmMode,
    ReuseOperation,
    ScenarioMode,
    StandardVersion,
)
from app.domain.models import MetadataPlan, TargetContext
from app.llm.fixture import FixtureModel
from app.parsers.ectd322 import FixtureCatalog
from app.presentation.repository import load_m4_snapshot

PROTECTED_PATHS = (
    "data/benchmark/frozen/benchmark-v1.0.0.json",
    "data/benchmark/frozen/benchmark-v1.0.0.sha256",
    "data/benchmark/phase2/benchmark-held-out-v1.0.0.json",
    "data/benchmark/phase2/benchmark-held-out-v1.0.0.sha256",
    "data/benchmark/PRE_FREEZE_LEDGER.md",
    "data/benchmark/pre-freeze-ledger.json",
    "results/validation/eval-m3-fixture-v2-graph-contract/manifest.json",
    "results/validation/eval-m3-fixture-v2-graph-contract/metrics.json",
    "results/validation/eval-m3-fixture-v2-graph-contract/predictions.jsonl",
    "results/live/m3-live-phase2-20260901T170811002109Z/manifest.json",
    "results/live/m3-live-phase2-20260901T170811002109Z/metrics.json",
    "results/live/m3-live-phase2-20260901T170811002109Z/completion-audit.json",
)
SCREENSHOT_MANIFEST = REPOSITORY_ROOT / "paper" / "figures" / "m4" / "manifest.json"
EXPECTED_SCREENSHOTS = frozenset(
    {
        "case-a-evidence-graph",
        "case-c-b2-regbridge-contrast",
        "case-b-metadata-behavior",
        "held-out-comparison-dashboard",
    }
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _protected_hashes() -> dict[str, str]:
    hashes: dict[str, str] = {}
    for relative in PROTECTED_PATHS:
        path = REPOSITORY_ROOT / relative
        if path.is_file():
            hashes[relative] = _sha256(path)
    return hashes


def _canonical_digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _verify_screenshot_manifest(snapshot_sha256: str) -> dict[str, Any]:
    if not SCREENSHOT_MANIFEST.is_file():
        raise RuntimeError("M4 screenshot manifest is missing")
    manifest = json.loads(SCREENSHOT_MANIFEST.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != "m4.screenshot-manifest.v1":
        raise RuntimeError("M4 screenshot manifest schema version mismatch")
    if manifest.get("snapshot_sha256") != snapshot_sha256:
        raise RuntimeError("M4 screenshot manifest snapshot digest mismatch")
    entries = manifest.get("entries")
    if not isinstance(entries, list):
        raise RuntimeError("M4 screenshot manifest entries are invalid")
    ids = {entry.get("id") for entry in entries if isinstance(entry, dict)}
    if ids != EXPECTED_SCREENSHOTS:
        raise RuntimeError("M4 screenshot manifest does not cover the required screenshots")
    verified: dict[str, str] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise RuntimeError("M4 screenshot manifest entry is invalid")
        filename = entry.get("file")
        if not isinstance(filename, str):
            raise RuntimeError("M4 screenshot filename is invalid")
        path = SCREENSHOT_MANIFEST.parent / filename
        if path.name != filename or path.suffix.lower() != ".png":
            raise RuntimeError("M4 screenshot filename is not a local PNG basename")
        if not path.is_file():
            raise RuntimeError(f"M4 screenshot is missing: {filename}")
        digest = _sha256(path)
        if digest != entry.get("image_sha256"):
            raise RuntimeError(f"M4 screenshot digest mismatch: {filename}")
        viewport = entry.get("viewport")
        if viewport != {"width": 1440, "height": 900}:
            raise RuntimeError(f"M4 screenshot viewport mismatch: {filename}")
        verified[str(entry["id"])] = digest
    return {
        "screenshot_manifest": SCREENSHOT_MANIFEST.relative_to(REPOSITORY_ROOT).as_posix(),
        "screenshot_count": len(verified),
        "screenshot_digests": verified,
    }


def _target(metadata_plan: dict[str, str | None] | None = None) -> TargetContext:
    return TargetContext(
        authority=Authority.FDA,
        center=Center.CDER,
        application_type=ApplicationType.NDA,
        source_standard=StandardVersion.ECTD_3_2_2,
        target_standard=StandardVersion.ECTD_4_0,
        analysis_date=date(2026, 8, 29),
        reuse_operation=ReuseOperation.REFERENCE_EXISTING_CONTENT,
        standards_snapshot_id="fda-cder-demo-v1",
        scenario_mode=ScenarioMode.PROSPECTIVE_FORWARD_COMPATIBILITY,
        metadata_plan=(
            MetadataPlan.model_validate(metadata_plan) if metadata_plan is not None else None
        ),
    )


async def _run_demo_once() -> dict[str, str]:
    snapshot = load_m4_snapshot()
    service = AnalysisService(
        model=FixtureModel(),
        settings=Settings(llm_mode=LlmMode.FIXTURE),
    )
    catalog = FixtureCatalog()
    digests: dict[str, str] = {}
    for preset in snapshot.demo_presets:
        inventory = catalog.parse(preset.fixture_id)
        leaf = inventory.leaves[0]
        analysis = await service.analyze_async(
            inventory,
            leaf.id,
            _target(preset.metadata_plan),
        )
        graph = service.graph(analysis.id)
        digests[preset.id] = _canonical_digest(
            {
                "decision": analysis.decision,
                "action": analysis.repair.type,
                "evidence_ids": [item.id for item in analysis.evidence],
                "graph": graph.model_dump(mode="json"),
                "trace": [
                    step.model_dump(mode="json", exclude={"occurred_at"})
                    for step in analysis.trace
                ],
            }
        )
    return digests


async def verify_m4() -> dict[str, Any]:
    before = _protected_hashes()
    snapshot = load_m4_snapshot()
    first = await _run_demo_once()
    second = await _run_demo_once()
    after = _protected_hashes()
    if before != after:
        raise RuntimeError("protected M3 bytes changed during M4 verification")
    if first != second:
        raise RuntimeError("fixture-mode demonstration digests are not reproducible")
    if snapshot.snapshot_sha256 is None:
        raise RuntimeError("M4 snapshot is missing its canonical digest")
    screenshots = _verify_screenshot_manifest(snapshot.snapshot_sha256)
    return {
        "snapshot_version": snapshot.snapshot_version,
        "snapshot_sha256": snapshot.snapshot_sha256,
        "protected_files_checked": len(before),
        "demo_run_count": 2,
        "demo_digests": first,
        "immutability": "passed",
        "fixture_mode_reproducibility": "passed",
        **screenshots,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify M4 presentation snapshot and demo.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    arguments = parser.parse_args()
    report = asyncio.run(verify_m4())
    if arguments.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print("M4 presentation verification passed.")
        print(f"Snapshot: {report['snapshot_version']} {report['snapshot_sha256']}")
        print(f"Protected files checked: {report['protected_files_checked']}")
        print(f"Screenshots checked: {report['screenshot_count']}")
        print("Two fixture-mode demo runs produced identical digests.")


if __name__ == "__main__":
    main()
