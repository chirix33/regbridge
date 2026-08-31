"""Request-local aliases; durable identifiers/provenance never belong in model input."""

import json
import re
from dataclasses import dataclass, field
from typing import Any

from app.domain.vocabulary import output_vocabulary
from app.llm.models import ModelRequest

UUID_PATTERN = re.compile(r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}", re.IGNORECASE)
CASE_PATTERN = re.compile(r"(?<![a-z0-9])[abc]\d{3}(?![a-z0-9])", re.IGNORECASE)


@dataclass
class RequestAliases:
    forbidden: tuple[str, ...] = ()
    replacements: dict[str, str] = field(default_factory=dict)

    def text(self, value: str) -> str:
        def alias(match: re.Match[str]) -> str:
            original = match.group(0).casefold()
            return self.replacements.setdefault(
                original, f"local-id-{len(self.replacements) + 1:03d}"
            )

        if self.forbidden:
            pattern = "|".join(re.escape(item) for item in sorted(
                set(self.forbidden), key=lambda item: (-len(item), item)
            ) if item)
            if pattern:
                value = re.sub(pattern, alias, value, flags=re.IGNORECASE)
        value = UUID_PATTERN.sub(alias, value)
        return CASE_PATTERN.sub(alias, value)

    def clean(self, value: Any) -> Any:
        if isinstance(value, str):
            return self.text(value)
        if isinstance(value, dict):
            return {self.text(str(key)): self.clean(item) for key, item in value.items()}
        if isinstance(value, list | tuple):
            return [self.clean(item) for item in value]
        return value


@dataclass(frozen=True)
class SemanticPacket:
    serialized: str
    alias_to_evidence_id: dict[str, str]


def serialize_semantic_request(request: ModelRequest) -> SemanticPacket:
    aliases = RequestAliases(forbidden=(request.fixture_lookup_key, *(
        value for evidence in request.evidence
        for value in (evidence.id, getattr(evidence, "artifact_id", ""), evidence.locator)
        if value
    )))
    evidence_map: dict[str, str] = {}
    records = []
    for index, evidence in enumerate(request.evidence, start=1):
        alias = f"case-evidence-{index:03d}"
        evidence_map[alias] = evidence.id
        records.append({
            "id": alias,
            "kind": getattr(evidence, "kind", "regulatory"),
            "text": aliases.text(evidence.text),
            # Original filenames, XML locators, leaf IDs, and hashes stay in the audit store.
            "locator": f"supplied span {index}",
        })
    packet = {
        "task": aliases.text(request.task),
        "context": aliases.clean(request.context),
        "evidence": records,
        "prompt_template_version": request.prompt_template_version,
        "output_vocabulary": output_vocabulary(),
    }
    return SemanticPacket(
        json.dumps(packet, sort_keys=True, separators=(",", ":"), ensure_ascii=False), evidence_map,
    )
