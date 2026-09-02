import argparse
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast
from uuid import uuid4

from app.config import REPOSITORY_ROOT
from app.domain.enums import ReviewDecision, ReviewStatus
from app.domain.models import ReviewEvent
from app.evaluation.models import BenchmarkCase, FrozenBenchmark, ReferenceLabel
from app.evaluation.prefreeze import PREFREEZE_JSON, PrefreezeLedger

FROZEN_DIRECTORY = REPOSITORY_ROOT / "data" / "benchmark" / "frozen"
FROZEN_BENCHMARK = FROZEN_DIRECTORY / "benchmark-v1.0.0.json"
FROZEN_DIGEST = FROZEN_DIRECTORY / "benchmark-v1.0.0.sha256"


class BenchmarkPromotionError(ValueError):
    """Raised when the approved ledger cannot be atomically promoted."""


def _file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_frozen_benchmark(path: Path | None = None) -> FrozenBenchmark:
    source = path or FROZEN_BENCHMARK
    benchmark = FrozenBenchmark.model_validate_json(source.read_text(encoding="utf-8"))
    if source == FROZEN_BENCHMARK:
        expected = FROZEN_DIGEST.read_text(encoding="utf-8").strip()
        if _file_digest(source) != expected:
            raise BenchmarkPromotionError("frozen benchmark digest does not match")
    return benchmark


def promote_approved_ledger(
    *,
    author_id: str,
    approved_ledger_sha256: str,
    reviewed_at: datetime | None = None,
) -> FrozenBenchmark:
    if author_id != "author-01":
        raise BenchmarkPromotionError("M3 promotion requires explicit author-01 approval")
    if not PREFREEZE_JSON.is_file():
        raise BenchmarkPromotionError("pre-freeze ledger is missing")
    actual_ledger_sha256 = _file_digest(PREFREEZE_JSON)
    if actual_ledger_sha256 != approved_ledger_sha256:
        raise BenchmarkPromotionError("approved ledger digest does not match the realized ledger")
    ledger = PrefreezeLedger.model_validate_json(PREFREEZE_JSON.read_text(encoding="utf-8"))
    if ledger.status != "awaiting-explicit-author-01-approval":
        raise BenchmarkPromotionError("ledger is not at the author-approval checkpoint")
    timestamp_value = (reviewed_at or datetime.now(UTC)).replace(microsecond=0)
    timestamp = timestamp_value.isoformat().replace("+00:00", "Z")
    cases: list[BenchmarkCase] = []
    for candidate in ledger.cases:
        event = ReviewEvent(
            id=f"adjudication-m3-{candidate.case_id.lower()}-author-01",
            reviewer_id="author-01",
            reviewer_role="research-author",
            reviewed_at=timestamp_value,
            object_id=candidate.case_id,
            object_version=ledger.benchmark_version,
            source_snapshot_id=ledger.snapshot_id,
            source_sha256=actual_ledger_sha256,
            decision=ReviewDecision.ACCEPTED,
            rationale=(
                "author-01 explicitly approved the realized M3 pre-freeze ledger, including "
                "this candidate label, split, fixture family, exact mutation, selected leaf, "
                "hashes, evidence, rules, action, and human-review requirement."
            ),
            unresolved_assumptions=(
                "Controlled prospective FDA/CDER research label only; not FDA acceptance or "
                "regulatory-expert ground truth.",
            ),
            independent_second_author_check=False,
            expert_validated=False,
        )
        cases.append(
            BenchmarkCase(
                case_id=candidate.case_id,
                archetype=candidate.archetype,
                fixture_id=candidate.fixture_id,
                source_fixture_id=candidate.source_fixture_id,
                selected_leaf_id=candidate.selected_leaf.id,
                target_context_id=candidate.target_context_id,
                target_context=candidate.target_context,
                fixture_family=candidate.fixture_family,
                split=cast(Literal["train", "development", "test"], candidate.split),
                mutation=candidate.mutation.model_dump(),
                package_sha256=candidate.input_hashes.package_sha256,
                selected_file_sha256=candidate.input_hashes.selected_file_sha256,
                target_context_sha256=candidate.input_hashes.target_context_sha256,
                decision_fingerprint_sha256=(candidate.input_hashes.decision_fingerprint_sha256),
                decision_predicate_sha256=candidate.input_hashes.decision_predicate_sha256,
                decision_relevant_predicates=candidate.decision_relevant_predicates,
                reference=ReferenceLabel(
                    decision=candidate.reference_decision,
                    severity=candidate.reference_severity,
                    action=candidate.action,
                    action_mode=cast(
                        Literal["required_condition", "suggested_check", "no_action"],
                        candidate.action_mode,
                    ),
                    required_rule_ids=candidate.required_rule_ids,
                    acceptable_evidence_ids=candidate.acceptable_evidence_ids,
                    human_review_required=candidate.human_review_required,
                    rationale=candidate.rationale,
                ),
                review_status=ReviewStatus.AUTHOR_ADJUDICATED_FOR_DEMO,
                review_event=event,
                expert_validated=False,
            )
        )
    benchmark = FrozenBenchmark(
        schema_version="1.0.0",
        benchmark_version=ledger.benchmark_version,
        snapshot_id=ledger.snapshot_id,
        status="frozen",
        frozen_at=timestamp,
        source_ledger_sha256=actual_ledger_sha256,
        frozen_by="author-01",
        expert_validated=False,
        operational_availability="not_operational",
        cases=tuple(cases),
    )
    rendered = (
        json.dumps(benchmark.model_dump(mode="json"), indent=2, sort_keys=True, ensure_ascii=False)
        + "\n"
    )
    if FROZEN_DIRECTORY.exists():
        existing = load_frozen_benchmark()
        if existing.source_ledger_sha256 != actual_ledger_sha256:
            raise BenchmarkPromotionError("a different frozen benchmark already exists")
        return existing
    parent = FROZEN_DIRECTORY.parent
    # mkdtemp uses mode 0700, which gives a protected DACL on recent Windows Python.
    # This public, synthetic artifact must inherit repository access after atomic rename.
    temporary = parent / f".frozen.{uuid4().hex}"
    temporary.mkdir(mode=0o755)
    try:
        temporary_benchmark = temporary / FROZEN_BENCHMARK.name
        temporary_benchmark.write_text(rendered, encoding="utf-8", newline="\n")
        rendered_digest = _file_digest(temporary_benchmark)
        (temporary / FROZEN_DIGEST.name).write_text(
            rendered_digest + "\n", encoding="utf-8", newline="\n"
        )
        os.replace(temporary, FROZEN_DIRECTORY)
    finally:
        if temporary.exists():
            for item in temporary.iterdir():
                item.unlink()
            temporary.rmdir()
    return load_frozen_benchmark()


def main() -> None:
    parser = argparse.ArgumentParser(description="Promote an explicitly approved M3 ledger.")
    parser.add_argument("--author-id", required=True)
    parser.add_argument("--approved-ledger-sha256", required=True)
    arguments = parser.parse_args()
    benchmark = promote_approved_ledger(
        author_id=arguments.author_id,
        approved_ledger_sha256=arguments.approved_ledger_sha256,
    )
    print(
        f"Frozen benchmark {benchmark.benchmark_version}: {len(benchmark.cases)} cases, "
        "expert_validated=false, operational_availability=not_operational"
    )


if __name__ == "__main__":
    main()
