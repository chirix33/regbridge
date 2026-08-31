import argparse
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
from app.domain.models import DomainModel, Sha256, StableId
from app.evaluation.benchmark import FROZEN_BENCHMARK, load_frozen_benchmark
from app.evaluation.models import BenchmarkCase, CaseInput
from app.parsers.models import FixtureSummary

PHASE1_BUNDLE_VERSION = "1.0.0"
PHASE1_EXPORTER_VERSION = "1.0.0"
PHASE1_ALLOWED_SPLITS = ("train", "development")
PHASE1_CASE_COUNT = 18
PHASE1_TRAIN_COUNT = 12
PHASE1_DEVELOPMENT_COUNT = 6
PHASE1_DIRECTORY = REPOSITORY_ROOT / "data" / "benchmark" / "phase1"
PHASE1_BUNDLE = PHASE1_DIRECTORY / "benchmark-train-dev-v1.0.0.json"
PHASE1_BUNDLE_DIGEST = PHASE1_DIRECTORY / "benchmark-train-dev-v1.0.0.sha256"


class Phase1FixtureMetadata(DomainModel):
    fixture_id: StableId
    relative_path: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
    author_verified_relevant_hyperlink_ids: tuple[StableId, ...] = ()


class Phase1Bundle(DomainModel):
    schema_version: Literal["1.0.0"]
    exporter_version: str
    benchmark_sha256: Sha256
    source_benchmark: str
    operational_availability: Literal["not_operational"]
    expert_validated: Literal[False]
    allowed_splits: tuple[Literal["train", "development"], ...]
    cases: tuple[BenchmarkCase, ...] = Field(min_length=18, max_length=18)
    case_inputs: tuple[CaseInput, ...] = Field(min_length=18, max_length=18)
    fixture_metadata: tuple[Phase1FixtureMetadata, ...] = Field(min_length=1)
    selected_input_hashes: dict[StableId, Sha256]

    @model_validator(mode="after")
    def validate_phase1_boundary(self) -> "Phase1Bundle":
        case_ids = [case.case_id for case in self.cases]
        input_ids = [case.case_id for case in self.case_inputs]
        if len(set(case_ids)) != PHASE1_CASE_COUNT or len(set(input_ids)) != PHASE1_CASE_COUNT:
            raise ValueError("Phase 1 bundle requires 18 unique cases and inputs")
        if set(case_ids) != set(input_ids):
            raise ValueError("Phase 1 case labels and inference inputs must align")
        if any(case.split not in PHASE1_ALLOWED_SPLITS for case in self.cases):
            raise ValueError("Phase 1 bundle contains a disallowed split")
        counts = {
            split: sum(case.split == split for case in self.cases)
            for split in PHASE1_ALLOWED_SPLITS
        }
        if (
            counts["train"] != PHASE1_TRAIN_COUNT
            or counts["development"] != PHASE1_DEVELOPMENT_COUNT
        ):
            raise ValueError("Phase 1 bundle split counts are not 12 train and 6 development")
        paired = zip(self.cases, self.case_inputs, strict=True)
        if any(case.case_id != case_input.case_id for case, case_input in paired):
            raise ValueError("Phase 1 cases and inputs must be sorted identically")
        return self


def _digest_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _file_digest(path: Path) -> str:
    return _digest_bytes(path.read_bytes())


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


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


def build_phase1_bundle() -> Phase1Bundle:
    benchmark = load_frozen_benchmark()
    benchmark_digest = _file_digest(FROZEN_BENCHMARK)
    if benchmark.operational_availability != "not_operational" or benchmark.expert_validated:
        raise ValueError("Phase 1 requires not_operational and expert_validated=false")
    selected = tuple(
        sorted(
            (case for case in benchmark.cases if case.split in PHASE1_ALLOWED_SPLITS),
            key=lambda item: item.case_id,
        )
    )
    if len(selected) != PHASE1_CASE_COUNT:
        raise ValueError("Phase 1 source selection did not produce 18 records")
    if any(case.split == "test" for case in selected):
        raise ValueError("Phase 1 source selection includes a disallowed split")
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
    return Phase1Bundle(
        schema_version="1.0.0",
        exporter_version=PHASE1_EXPORTER_VERSION,
        benchmark_sha256=benchmark_digest,
        source_benchmark=FROZEN_BENCHMARK.relative_to(REPOSITORY_ROOT).as_posix(),
        operational_availability="not_operational",
        expert_validated=False,
        allowed_splits=("train", "development"),
        cases=selected,
        case_inputs=case_inputs,
        fixture_metadata=fixture_metadata,
        selected_input_hashes=selected_input_hashes,
    )


def write_phase1_bundle(path: Path = PHASE1_BUNDLE) -> Phase1Bundle:
    bundle = build_phase1_bundle()
    rendered = (
        json.dumps(bundle.model_dump(mode="json"), indent=2, sort_keys=True, ensure_ascii=False)
        + "\n"
    )
    digest = _digest_bytes(rendered.encode("utf-8"))
    _atomic_write(path, rendered)
    _atomic_write(path.with_suffix(".sha256"), digest + "\n")
    return load_phase1_bundle(path)


def load_phase1_bundle(path: Path = PHASE1_BUNDLE) -> Phase1Bundle:
    bundle = Phase1Bundle.model_validate_json(path.read_text(encoding="utf-8"))
    digest_path = path.with_suffix(".sha256")
    expected_digest = (
        digest_path.read_text(encoding="utf-8").strip() if digest_path.is_file() else None
    )
    if expected_digest is not None and _file_digest(path) != expected_digest:
        raise ValueError("Phase 1 bundle digest does not match")
    return bundle


def phase1_bundle_sha256(path: Path = PHASE1_BUNDLE) -> str:
    return _file_digest(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Export the immutable train/development bundle.")
    parser.add_argument("--output", type=Path, default=PHASE1_BUNDLE)
    args = parser.parse_args()
    bundle = write_phase1_bundle(args.output)
    counts = {
        split: sum(case.split == split for case in bundle.cases)
        for split in PHASE1_ALLOWED_SPLITS
    }
    print(
        "Exported Phase 1 bundle: "
        f"{counts['train']} train, {counts['development']} development; "
        "operational_availability=not_operational; expert_validated=false"
    )


if __name__ == "__main__":
    main()
