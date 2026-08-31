from threading import Lock

from app.evaluation.models import EvaluationRun
from app.evaluation.runner import (
    CONFIGURATION_ID,
    FIXED_TIMESTAMP,
    RUN_ID,
    SEED,
    SYSTEMS,
    run_evaluation,
)


class EvaluationBusyError(RuntimeError):
    """Raised when the single evaluation slot is occupied."""


class EvaluationManager:
    def __init__(self) -> None:
        self._lock = Lock()
        self._runs: dict[str, EvaluationRun] = {}
        self._active_id: str | None = None

    def create(self, configuration_id: str) -> EvaluationRun:
        if configuration_id != CONFIGURATION_ID:
            raise ValueError("evaluation configuration is not allowlisted")
        with self._lock:
            if self._active_id is not None:
                raise EvaluationBusyError("one evaluation is already queued or running")
            run = EvaluationRun(
                id=RUN_ID,
                configuration_id=configuration_id,
                state="queued",
                run_type="deterministic_fixture_validation",
                empirical_model_run=False,
                eligible_for_performance_claims=False,
                current_fda_operational_availability="not_operational",
                systems=SYSTEMS,
                seed=SEED,
                created_at=FIXED_TIMESTAMP,
                updated_at=FIXED_TIMESTAMP,
            )
            self._runs[run.id] = run
            self._active_id = run.id
            return run

    def execute(self, run_id: str) -> None:
        with self._lock:
            queued = self._runs.get(run_id)
            if queued is None:
                return
            self._runs[run_id] = queued.model_copy(update={"state": "running"})
        try:
            completed = run_evaluation(queued.configuration_id)
        except Exception as error:
            failed = queued.model_copy(
                update={
                    "state": "failed",
                    "error": f"evaluation failed: {type(error).__name__}",
                }
            )
            with self._lock:
                self._runs[run_id] = failed
                self._active_id = None
            return
        with self._lock:
            self._runs[run_id] = completed
            self._active_id = None

    def get(self, run_id: str) -> EvaluationRun:
        with self._lock:
            try:
                return self._runs[run_id]
            except KeyError as error:
                raise KeyError(f"evaluation not found: {run_id}") from error

    def reset_for_tests(self) -> None:
        with self._lock:
            self._runs.clear()
            self._active_id = None
