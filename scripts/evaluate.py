import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.evaluation.runner import CONFIGURATION_ID, run_evaluation  # noqa: E402


def main() -> None:
    run = run_evaluation(CONFIGURATION_ID)
    if not run.artifacts:
        raise SystemExit("evaluation did not produce artifacts")
    print(
        f"Completed {run.id}: {len(run.cases)} system-case outputs; "
        f"prediction digest={run.artifacts.prediction_content_sha256}; "
        f"metrics digest={run.artifacts.metrics_content_sha256}"
    )


if __name__ == "__main__":
    main()
