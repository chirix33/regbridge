import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.evaluation.prefreeze import write_prefreeze_ledger  # noqa: E402


def main() -> None:
    ledger = write_prefreeze_ledger()
    summary = ledger.validation_summary
    print(
        "Validated pre-freeze ledger: "
        f"{summary['case_count']} cases, "
        f"{summary['unique_full_fingerprint_count']} unique fingerprints, "
        "author approval pending; no adjudication event or frozen benchmark created."
    )


if __name__ == "__main__":
    main()
