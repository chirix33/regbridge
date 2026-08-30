from app.domain.enums import ScenarioMode
from app.domain.models import TargetContext
from app.parsers.models import ParsedLeaf
from app.rules.models import HeadingRule


def applicable_heading_rule(
    leaf: ParsedLeaf,
    target: TargetContext,
    rules: tuple[HeadingRule, ...],
) -> HeadingRule | None:
    if target.scenario_mode != ScenarioMode.PROSPECTIVE_FORWARD_COMPATIBILITY:
        return None
    for rule in rules:
        if (
            rule.scenario_mode == target.scenario_mode
            and target.authority == rule.scope.authority
            and target.center == rule.scope.center
            and target.application_type in rule.scope.application_types
            and target.source_standard == rule.scope.source_standard
            and target.target_standard == rule.scope.target_standard
            and leaf.heading in rule.explicit_heading_mapping
        ):
            return rule
    return None
