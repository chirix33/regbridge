import hashlib
import json
from functools import lru_cache

from app.config import REPOSITORY_ROOT
from app.presentation.models import M4PresentationSnapshot

SNAPSHOT_VERSION = "m4-phase2-20260901T170811002109Z-v1"
SNAPSHOT_PATH = (
    REPOSITORY_ROOT / "data" / "presentation" / "m4" / SNAPSHOT_VERSION / "snapshot.json"
)


def _canonical_bytes(snapshot: M4PresentationSnapshot) -> bytes:
    payload = snapshot.model_dump(mode="json")
    payload["snapshot_sha256"] = None
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def compute_snapshot_sha256(snapshot: M4PresentationSnapshot) -> str:
    return hashlib.sha256(_canonical_bytes(snapshot)).hexdigest()


@lru_cache
def load_m4_snapshot() -> M4PresentationSnapshot:
    if not SNAPSHOT_PATH.is_file():
        raise FileNotFoundError(f"M4 presentation snapshot is missing: {SNAPSHOT_PATH}")
    snapshot = M4PresentationSnapshot.model_validate_json(
        SNAPSHOT_PATH.read_text(encoding="utf-8")
    )
    expected = compute_snapshot_sha256(snapshot)
    if snapshot.snapshot_sha256 != expected:
        raise ValueError("M4 presentation snapshot digest mismatch")
    return snapshot

