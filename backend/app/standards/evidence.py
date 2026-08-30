from pathlib import Path

import yaml
from pydantic import TypeAdapter

from app.config import REPOSITORY_ROOT
from app.domain.models import EvidenceSpan, ReviewEvent
from app.standards.registry import StandardsRegistry, StandardsRegistryError


class EvidenceRegistry:
    def __init__(self, evidence_path: Path | None = None) -> None:
        self.evidence_path = (
            evidence_path or REPOSITORY_ROOT / "data" / "standards" / "evidence.yaml"
        )

    def load(self) -> tuple[EvidenceSpan, ...]:
        payload = yaml.safe_load(self.evidence_path.read_text(encoding="utf-8"))
        manifest = StandardsRegistry().load()
        if payload["snapshot_id"] != manifest.snapshot_id:
            raise StandardsRegistryError("evidence snapshot does not match standards manifest")
        sources = {source.id: source for source in manifest.sources}
        events = TypeAdapter(tuple[ReviewEvent, ...]).validate_python(payload["review_events"])
        spans: list[EvidenceSpan] = []
        for item in payload["evidence"]:
            source = sources.get(item["source_id"])
            if not source:
                raise StandardsRegistryError(
                    f"evidence references unknown source: {item['source_id']}"
                )
            if item["source_sha256"] != source.sha256:
                raise StandardsRegistryError(f"evidence digest differs from source: {item['id']}")
            matching_events = tuple(
                event for event in events if event.source_sha256 == source.sha256
            )
            spans.append(
                EvidenceSpan.model_validate(
                    {
                        **item,
                        "applicability": source.scope.model_dump(mode="json"),
                        "review_events": [
                            event.model_dump(mode="json") for event in matching_events
                        ],
                    }
                )
            )
        ids = [span.id for span in spans]
        if len(ids) != len(set(ids)):
            raise StandardsRegistryError("evidence identifiers must be unique")
        return tuple(spans)
