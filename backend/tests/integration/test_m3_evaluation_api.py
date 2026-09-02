import shutil
from collections.abc import Generator
from pathlib import Path

import pytest
from app.api.routes import _evaluation_manager
from app.evaluation import jobs, runner
from app.evaluation.jobs import EvaluationBusyError, EvaluationManager
from app.evaluation.runner import CONFIGURATION_ID, RUN_ID
from app.main import create_app
from fastapi.testclient import TestClient


def _isolate_evaluation_artifacts(monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    result_directory = runner.REPOSITORY_ROOT / "results" / "validation" / ".pytest-m3-api"
    paper_directory = runner.REPOSITORY_ROOT / "paper" / "tables" / "validation" / ".pytest-m3-api"
    shutil.rmtree(result_directory, ignore_errors=True)
    shutil.rmtree(paper_directory, ignore_errors=True)
    monkeypatch.setattr(runner, "RESULT_DIRECTORY", result_directory)
    monkeypatch.setattr(runner, "PAPER_DIRECTORY", paper_directory)
    monkeypatch.setattr(runner, "PAPER_DETERMINISTIC_DIRECTORY", paper_directory / "deterministic")
    monkeypatch.setattr(runner, "PAPER_RETRIEVAL_DIRECTORY", paper_directory / "retrieval")
    return result_directory, paper_directory


@pytest.fixture
def client(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[TestClient]:
    result_directory, paper_directory = _isolate_evaluation_artifacts(monkeypatch)
    _evaluation_manager.reset_for_tests()
    with TestClient(create_app()) as test_client:
        yield test_client
    _evaluation_manager.reset_for_tests()
    shutil.rmtree(result_directory, ignore_errors=True)
    shutil.rmtree(paper_directory, ignore_errors=True)


def test_named_baseline_runs_only_frozen_cases(client: TestClient) -> None:
    response = client.post("/api/v1/baselines/run", json={"system": "B1", "case_id": "A002"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["run_type"] == "deterministic_fixture_validation"
    assert payload["empirical_model_run"] is False
    assert payload["eligible_for_performance_claims"] is False
    assert payload["current_fda_operational_availability"] == "not_operational"
    assert payload["prediction"]["case_id"] == "A002"
    assert len(payload["retrieval"]["hits"]) == 3


def test_baseline_api_rejects_paths_unknown_cases_and_unknown_systems(
    client: TestClient,
) -> None:
    path_response = client.post(
        "/api/v1/baselines/run",
        json={"system": "B0", "case_id": "A001", "path": "../../labels.json"},
    )
    assert path_response.status_code == 422
    assert (
        client.post(
            "/api/v1/baselines/run", json={"system": "B0", "case_id": "../../A001"}
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/v1/baselines/run", json={"system": "arbitrary", "case_id": "A001"}
        ).status_code
        == 422
    )


def test_evaluation_api_runs_allowlisted_configuration_and_returns_artifacts(
    client: TestClient,
) -> None:
    response = client.post("/api/v1/evaluations", json={"configuration_id": CONFIGURATION_ID})
    assert response.status_code == 202
    created = response.json()["evaluation"]
    assert created["state"] in {"queued", "completed"}
    status_response = client.get(f"/api/v1/evaluations/{RUN_ID}")
    assert status_response.status_code == 200
    completed = status_response.json()["evaluation"]
    assert completed["state"] == "completed"
    assert completed["artifacts"]["manifest_json"].startswith("results/validation/")
    assert (
        client.post(
            "/api/v1/evaluations",
            json={"configuration_id": CONFIGURATION_ID, "path": "C:/secret"},
        ).status_code
        == 422
    )


def test_evaluation_manager_enforces_one_active_evaluation() -> None:
    manager = EvaluationManager()
    queued = manager.create(CONFIGURATION_ID)
    assert queued.state == "queued"
    with pytest.raises(EvaluationBusyError):
        manager.create(CONFIGURATION_ID)
    assert manager.get(queued.id).state == "queued"


def test_evaluation_failure_is_redacted_and_releases_running_slot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = EvaluationManager()
    queued = manager.create(CONFIGURATION_ID)

    def fail(configuration_id: str) -> None:
        assert configuration_id == CONFIGURATION_ID
        assert manager.get(queued.id).state == "running"
        with pytest.raises(EvaluationBusyError):
            manager.create(CONFIGURATION_ID)
        raise RuntimeError("secret-token and private dossier text must never escape")

    monkeypatch.setattr(jobs, "run_evaluation", fail)
    manager.execute(queued.id)
    failed = manager.get(queued.id)
    assert failed.state == "failed"
    assert failed.error == "evaluation failed: RuntimeError"
    assert "secret-token" not in failed.model_dump_json()
    assert manager.create(CONFIGURATION_ID).state == "queued"
