from pathlib import Path

import yaml

from app.config import REPOSITORY_ROOT
from app.rules.models import HeadingRule
from app.standards.evidence import EvidenceRegistry
from app.standards.registry import StandardsRegistry, StandardsRegistryError

APPROVED_M1_MAPPING = {
    "3.2.S.1.1": "3.2.S.1",
    "3.2.S.1.2": "3.2.S.1",
    "3.2.S.1.3": "3.2.S.1",
}


class RuleRegistry:
    def __init__(self, rules_path: Path | None = None) -> None:
        self.rules_path = rules_path or REPOSITORY_ROOT / "data" / "rules" / "heading-rules.yaml"

    def load(self) -> tuple[HeadingRule, ...]:
        payload = yaml.safe_load(self.rules_path.read_text(encoding="utf-8"))
        manifest = StandardsRegistry().load()
        if payload["snapshot_id"] != manifest.snapshot_id:
            raise StandardsRegistryError("rule snapshot does not match standards manifest")
        rules = tuple(HeadingRule.model_validate(item) for item in payload["rules"])
        known_evidence = {span.id for span in EvidenceRegistry().load()}
        for rule in rules:
            if unknown := set(rule.evidence_ids) - known_evidence:
                raise StandardsRegistryError(
                    f"rule {rule.id} cites unknown evidence: {', '.join(sorted(unknown))}"
                )
            if rule.explicit_heading_mapping != APPROVED_M1_MAPPING:
                raise StandardsRegistryError(
                    "M1 heading rule must use only the approved explicit mapping"
                )
            if set(rule.verified_available_target_headings) != {"3.2.S.1"}:
                raise StandardsRegistryError(
                    "M1 heading rule must retain only the source-verified 3.2.S.1 target heading"
                )
        return rules
