"""Isolated held-out bundle, created only behind the frozen Phase 2 loading gate."""

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field, model_validator

from app.baselines.runner import BaselineRunner
from app.config import REPOSITORY_ROOT
from app.domain.enums import Decision
from app.domain.models import DomainModel, Sha256, StableId
from app.evaluation.benchmark import FROZEN_BENCHMARK, load_frozen_benchmark
from app.evaluation.models import BenchmarkCase, CaseInput
from app.evaluation.phase1_bundle import Phase1FixtureMetadata
from app.parsers.models import FixtureSummary

PHASE2_BUNDLE_VERSION: Literal["1.0.0"] = "1.0.0"
PHASE2_EXPORTER_VERSION = "1.0.0"
PHASE2_CASE_COUNT = 12
PHASE2_FAMILY_COUNT = 6
PHASE2_DIRECTORY = REPOSITORY_ROOT / "data" / "benchmark" / "phase2"
PHASE2_BUNDLE = PHASE2_DIRECTORY / "benchmark-held-out-v1.0.0.json"
PHASE2_BUNDLE_DIGEST = PHASE2_DIRECTORY / "benchmark-held-out-v1.0.0.sha256"


class Phase2Bundle(DomainModel):
    schema_version: Literal["1.0.0"]
    exporter_version: str
    benchmark_sha256: Sha256
    source_benchmark: str
    operational_availability: Literal["not_operational"]
    expert_validated: Literal[False]
    allowed_split: Literal["test"]
    cases: tuple[BenchmarkCase, ...] = Field(min_length=12, max_length=12)
    case_inputs: tuple[CaseInput, ...] = Field(min_length=12, max_length=12)
    fixture_metadata: tuple[Phase1FixtureMetadata, ...] = Field(min_length=1)
    selected_input_hashes: dict[StableId, Sha256]

    @model_validator(mode="after")
    def validate_held_out_boundary(self) -> "Phase2Bundle":
        case_ids = [case.case_id for case in self.cases]
        input_ids = [case.case_id for case in self.case_inputs]
        if len(set(case_ids)) != PHASE2_CASE_COUNT or len(set(input_ids)) != PHASE2_CASE_COUNT:
            raise ValueError("Phase 2 bundle requires 12 unique cases and inputs")
        if set(case_ids) != set(input_ids) or any(case.split != "test" for case in self.cases):
            raise ValueError("Phase 2 bundle may contain only aligned held-out test cases")
        if len({case.fixture_family for case in self.cases}) != PHASE2_FAMILY_COUNT:
            raise ValueError("Phase 2 bundle requires six non-overlapping held-out families")
        counts = {
            decision: sum(case.reference.decision == decision for case in self.cases)
            for decision in (
                Decision.REUSE_WITH_NEW_CONTEXT,
                Decision.REUSE_AS_LEGACY_REFERENCE,
                Decision.HUMAN_REGULATORY_REVIEW,
            )
        }
        if any(count != 4 for count in counts.values()):
            raise ValueError("Phase 2 held-out class balance must remain exactly 4/4/4")
        if any(
            case.case_id != case_input.case_id
            for case, case_input in zip(self.cases, self.case_inputs, strict=True)
        ):
            raise ValueError("Phase 2 cases and inputs must be sorted identically")
        return self


def _digest_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _file_digest(path: Path) -> str:
    return _digest_bytes(path.read_bytes())


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        Path(temporary_name).replace(path)
    finally:
        temporary = Path(temporary_name)
        if temporary.exists():
            temporary.unlink()


def _fixture_summaries() -> dict[str, FixtureSummary]:
    catalog_path = REPOSITORY_ROOT / "data" / "demo-cases" / "catalog.yaml"
    payload = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
    return {
        item.id: item
        for item in (FixtureSummary.model_validate(raw) for raw in payload["fixtures"])
    }


def build_phase2_bundle() -> Phase2Bundle:
    benchmark = load_frozen_benchmark()
    if benchmark.operational_availability != "not_operational" or benchmark.expert_validated:
        raise ValueError("Phase 2 requires not_operational and expert_validated=false")
    selected = tuple(sorted(
        (case for case in benchmark.cases if case.split == "test"),
        key=lambda item: item.case_id,
    ))
    if len(selected) != PHASE2_CASE_COUNT:
        raise ValueError("Phase 2 source selection did not produce exactly 12 records")
    runner = BaselineRunner()
    case_inputs = tuple(runner.case_input(case) for case in selected)
    summaries = _fixture_summaries()
    fixture_metadata = tuple(
        Phase1FixtureMetadata(
            fixture_id=fixture_id,
            relative_path=fixture_id,
            author_verified_relevant_hyperlink_ids=(
                summaries[fixture_id].author_verified_relevant_hyperlink_ids
            ),
        )
        for fixture_id in sorted({case.fixture_id for case in selected})
    )
    selected_input_hashes = {
        case_input.case_id: _digest_bytes(case_input.model_dump_json().encode("utf-8"))
        for case_input in case_inputs
    }
    return Phase2Bundle(
        schema_version=PHASE2_BUNDLE_VERSION,
        exporter_version=PHASE2_EXPORTER_VERSION,
        benchmark_sha256=_file_digest(FROZEN_BENCHMARK),
        source_benchmark=FROZEN_BENCHMARK.relative_to(REPOSITORY_ROOT).as_posix(),
        operational_availability="not_operational",
        expert_validated=False,
        allowed_split="test",
        cases=selected,
        case_inputs=case_inputs,
        fixture_metadata=fixture_metadata,
        selected_input_hashes=selected_input_hashes,
    )


def write_phase2_bundle(path: Path = PHASE2_BUNDLE) -> Phase2Bundle:
    bundle = build_phase2_bundle()
    rendered = json.dumps(
        bundle.model_dump(mode="json"), indent=2, sort_keys=True, ensure_ascii=False
    ) + "\n"
    digest = _digest_bytes(rendered.encode("utf-8"))
    _atomic_write(path, rendered)
    _atomic_write(path.with_suffix(".sha256"), digest + "\n")
    return load_phase2_bundle(path)


def load_phase2_bundle(path: Path = PHASE2_BUNDLE) -> Phase2Bundle:
    digest_path = path.with_suffix(".sha256")
    if not path.is_file() or not digest_path.is_file():
        raise ValueError("Phase 2 bundle and digest are required")
    if _file_digest(path) != digest_path.read_text(encoding="utf-8").strip():
        raise ValueError("Phase 2 bundle digest does not match")
    bundle = Phase2Bundle.model_validate_json(path.read_text(encoding="utf-8"))
    for case, case_input in zip(bundle.cases, bundle.case_inputs, strict=True):
        if (
            _digest_bytes(case_input.model_dump_json().encode("utf-8"))
            != bundle.selected_input_hashes.get(case.case_id)
            or case.fixture_id != case_input.fixture_id
            or case.selected_leaf_id != case_input.selected_leaf_id
            or case.target_context != case_input.target_context
        ):
            raise ValueError("Phase 2 selected input provenance mismatch")
    return bundle


def phase2_bundle_sha256(path: Path = PHASE2_BUNDLE) -> str:
    return _file_digest(path)
