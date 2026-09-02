import json
from pathlib import Path

import pytest
from app.presentation import generate
from app.presentation.repository import SNAPSHOT_PATH, compute_snapshot_sha256, load_m4_snapshot


def _walk_strings(value: object) -> list[str]:
    if isinstance(value, dict):
        return [item for child in value.values() for item in _walk_strings(child)]
    if isinstance(value, list):
        return [item for child in value for item in _walk_strings(child)]
    if isinstance(value, str):
        return [value]
    return []


def test_snapshot_loads_and_preserves_m3_disclosures() -> None:
    snapshot = load_m4_snapshot()

    assert snapshot.source_run_id == "m3-live-phase2-20260901T170811002109Z"
    assert snapshot.current_fda_operational_availability == "not_operational"
    assert snapshot.expert_validated is False
    assert snapshot.eligible_for_performance_claims is True
    assert snapshot.completion_audit["integrity_audit_passed"] is True
    assert len(snapshot.cases) == 12
    assert {case.split for case in snapshot.cases} == {"test"}
    assert snapshot.snapshot_sha256 == compute_snapshot_sha256(snapshot)


def test_snapshot_excludes_raw_provider_and_prompt_material() -> None:
    snapshot_path = Path(SNAPSHOT_PATH)
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    rendered_strings = "\n".join(_walk_strings(payload)).casefold()

    prohibited = (
        "response_id",
        "resp_",
        "final_json_text",
        "request_digest",
        "api_key",
        "llm_api_key",
        "prompt",
        "reasoning",
        "c:\\",
    )
    for item in prohibited:
        assert item not in rendered_strings


def test_source_hash_mismatch_fails_before_snapshot_build(monkeypatch: pytest.MonkeyPatch) -> None:
    tampered = dict(generate.EXPECTED_SOURCE_HASHES)
    first_key = next(iter(tampered))
    tampered[first_key] = "0" * 64
    monkeypatch.setattr(generate, "EXPECTED_SOURCE_HASHES", tampered)

    with pytest.raises(ValueError, match="source artifact changed"):
        generate.build_snapshot()


def test_build_snapshot_is_byte_reproducible() -> None:
    first = generate.build_snapshot()
    second = generate.build_snapshot()

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert compute_snapshot_sha256(first) == compute_snapshot_sha256(second)
