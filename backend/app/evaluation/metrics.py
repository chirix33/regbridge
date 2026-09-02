import math
import random
from typing import Literal

from app.domain.enums import Decision, Severity
from app.evaluation.models import (
    BenchmarkCase,
    CaseEvaluation,
    ClassMetrics,
    FamilySensitivity,
    MetricsReport,
    RateMetric,
    RetrievalMetrics,
    RetrievalTrace,
    SystemPrediction,
    VocabularyDiagnostic,
)

REPRESENTED_CLASSES = (
    Decision.REUSE_WITH_NEW_CONTEXT,
    Decision.REUSE_AS_LEGACY_REFERENCE,
    Decision.HUMAN_REGULATORY_REVIEW,
)

MetricsScope = Literal[
    "held-out-test",
    "all-cases-secondary",
    "phase1-train",
    "phase1-development",
    "phase1-train-development",
]


def wilson_interval(numerator: int, denominator: int) -> tuple[float | None, float | None]:
    if denominator == 0:
        return None, None
    z = 1.959963984540054
    proportion = numerator / denominator
    denominator_term = 1 + z**2 / denominator
    center = (proportion + z**2 / (2 * denominator)) / denominator_term
    margin = (
        z
        * math.sqrt(proportion * (1 - proportion) / denominator + z**2 / (4 * denominator**2))
        / denominator_term
    )
    return max(0.0, center - margin), min(1.0, center + margin)


def _rate(numerator: int, denominator: int) -> RateMetric:
    low, high = wilson_interval(numerator, denominator)
    return RateMetric(
        numerator=numerator,
        denominator=denominator,
        rate=numerator / denominator if denominator else None,
        wilson_95_low=low,
        wilson_95_high=high,
    )


def _action_required(case: BenchmarkCase) -> bool:
    reference = case.reference
    return (
        reference.decision != Decision.REUSE_AS_LEGACY_REFERENCE
        or reference.action != "NO_MATERIAL_REPAIR"
        or reference.human_review_required
    )


def _cluster_bootstrap(
    family_counts: dict[str, tuple[int, int]], *, seed: int
) -> tuple[float, float] | None:
    families = sorted(family_counts)
    if not families or not sum(family_counts[item][1] for item in families):
        return None
    generator = random.Random(seed)
    estimates: list[float] = []
    for _ in range(2000):
        sample = [generator.choice(families) for _ in families]
        numerator = sum(family_counts[item][0] for item in sample)
        denominator = sum(family_counts[item][1] for item in sample)
        if denominator:
            estimates.append(numerator / denominator)
    if not estimates:
        return None
    estimates.sort()
    low_index = int(0.025 * (len(estimates) - 1))
    high_index = int(0.975 * (len(estimates) - 1))
    return estimates[low_index], estimates[high_index]


def score_system(
    *,
    cases: tuple[BenchmarkCase, ...],
    predictions: tuple[SystemPrediction, ...],
    retrieval_traces: tuple[RetrievalTrace, ...],
    scope: MetricsScope,
    seed: int,
    regulatory_evidence_ids: frozenset[str],
) -> tuple[MetricsReport, tuple[CaseEvaluation, ...]]:
    """Exact-match option (a); three-class benchmark, six permitted output decisions.

    Outside-class predictions are errors and false negatives for their true reference class.
    They enter no represented class's precision denominator. Macro-F1 is over the three
    fixed represented classes. Excluding outside predictions is sensitivity-only.
    """
    if not cases:
        raise ValueError("cannot score an empty benchmark scope")
    by_case = {item.case_id: item for item in predictions}
    if len(by_case) != len(predictions) or set(by_case) != {item.case_id for item in cases}:
        raise ValueError("predictions must cover every case exactly once")
    system = predictions[0].system
    if any(item.system != system for item in predictions):
        raise ValueError("a metrics report may contain only one system")
    if any(case.reference.decision not in REPRESENTED_CLASSES for case in cases):
        raise ValueError("this benchmark scorer instantiates only three reference classes")

    unsafe_numerator = unsafe_denominator = 0
    high_numerator = high_denominator = 0
    bypass_numerator = bypass_denominator = 0
    conservative_numerator = conservative_denominator = 0
    evaluations: list[CaseEvaluation] = []
    family_counts = {case.fixture_family: [0, 0] for case in cases}
    for case in cases:
        prediction = by_case[case.case_id]
        action_required = _action_required(case)
        unsafe = action_required and prediction.unconditional_reuse
        if action_required:
            unsafe_denominator += 1
            unsafe_numerator += int(unsafe)
            family_counts[case.fixture_family][1] += 1
            family_counts[case.fixture_family][0] += int(unsafe)
        if action_required and case.reference.severity in {Severity.HIGH, Severity.BLOCKING}:
            high_denominator += 1
            high_numerator += int(unsafe)
        is_human = case.reference.decision == Decision.HUMAN_REGULATORY_REVIEW
        review_bypass = (
            is_human
            and prediction.decision != Decision.HUMAN_REGULATORY_REVIEW
            and not prediction.human_review_required
        )
        if is_human:
            bypass_denominator += 1
            bypass_numerator += int(review_bypass)
        safe_reference = not action_required
        conservative = safe_reference and (
            prediction.decision != Decision.REUSE_AS_LEGACY_REFERENCE
            or prediction.action != "NO_MATERIAL_REPAIR"
            or prediction.human_review_required
        )
        if safe_reference:
            conservative_denominator += 1
            conservative_numerator += int(conservative)
        evaluations.append(
            CaseEvaluation(
                case_id=case.case_id,
                fixture_family=case.fixture_family,
                split=case.split,
                system=system,
                reference_decision=case.reference.decision,
                prediction_decision=prediction.decision,
                reference_action=case.reference.action,
                prediction_action=prediction.action,
                unsafe_false_negative=unsafe,
                review_bypass=review_bypass,
                conservative_false_positive=conservative,
                correct=prediction.decision == case.reference.decision,
            )
        )

    per_class: dict[str, ClassMetrics] = {}
    recalls: list[float] = []
    f1_values: list[float] = []
    for label in REPRESENTED_CLASSES:
        true_positive = sum(
            case.reference.decision == label and by_case[case.case_id].decision == label
            for case in cases
        )
        false_positive = sum(
            case.reference.decision != label and by_case[case.case_id].decision == label
            for case in cases
        )
        false_negative = sum(
            case.reference.decision == label and by_case[case.case_id].decision != label
            for case in cases
        )
        support = true_positive + false_negative
        precision = (
            true_positive / (true_positive + false_positive)
            if true_positive + false_positive
            else 0
        )
        recall = true_positive / support if support else 0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0
        per_class[label.value] = ClassMetrics(
            precision=precision, recall=recall, f1=f1, support=support
        )
        recalls.append(recall)
        f1_values.append(f1)

    evidence_correct = 0
    action_correct = 0
    abstention_correct = 0
    heading_correct = 0
    heading_total = 0
    for case in cases:
        prediction = by_case[case.case_id]
        acceptable = set(case.reference.acceptable_evidence_ids)
        predicted = set(prediction.evidence_ids)
        evidence_correct += int(bool(acceptable & predicted) if acceptable else not predicted)
        action_correct += int(case.reference.action == prediction.action)
        abstention_correct += int(
            (case.reference.decision == Decision.HUMAN_REGULATORY_REVIEW)
            == (prediction.decision == Decision.HUMAN_REGULATORY_REVIEW)
        )
        if case.archetype == "unavailable-heading":
            heading_total += 1
            heading_correct += int(case.reference.decision == prediction.decision)

    retrieval_metrics: RetrievalMetrics | None = None
    if system == "B1":
        traces = {trace.case_id: trace for trace in retrieval_traces}
        recall_values: list[float] = []
        precision_values: list[float] = []
        reciprocal_ranks: list[float] = []
        for case in cases:
            relevant = set(case.reference.acceptable_evidence_ids) & regulatory_evidence_ids
            if not relevant:
                continue
            hits = traces[case.case_id].hits
            hit_ids = [item.evidence_id for item in hits]
            found = relevant & set(hit_ids)
            recall_values.append(len(found) / len(relevant))
            precision_values.append(len(found) / 3)
            ranks = [index for index, item in enumerate(hit_ids, start=1) if item in relevant]
            reciprocal_ranks.append(1 / min(ranks) if ranks else 0)
        count = len(recall_values)
        retrieval_metrics = RetrievalMetrics(
            evaluated_cases=count,
            recall_at_3=sum(recall_values) / count if count else None,
            precision_at_3=sum(precision_values) / count if count else None,
            mrr=sum(reciprocal_ranks) / count if count else None,
        )

    family_sensitivity = tuple(
        FamilySensitivity(
            fixture_family=family,
            unsafe_misses=counts[0],
            eligible_cases=counts[1],
        )
        for family, counts in sorted(family_counts.items())
    )
    family_tuples = {family: (counts[0], counts[1]) for family, counts in family_counts.items()}
    outside_counts = {
        label.value: sum(item.decision == label for item in predictions)
        for label in Decision if label not in REPRESENTED_CLASSES
    }
    outside = sum(outside_counts.values())
    included = len(predictions) - outside
    legacy_count = sum(
        item.decision == Decision.REUSE_AS_LEGACY_REFERENCE for item in predictions
    )
    report = MetricsReport(
        system=system,
        result_status=(
            "genuine deterministic experimental output"
            if system == "B2" else "fixture validation only"
        ),
        interval_interpretation=(
            "exploratory only; no independence or significance claim"
            if system == "B2" else "scorer validation only; no statistical interpretation"
        ),
        scope=scope,
        represented_classes=REPRESENTED_CLASSES,
        unsafe_false_negative_rate=_rate(unsafe_numerator, unsafe_denominator),
        high_blocking_unsafe_false_negative_rate=_rate(high_numerator, high_denominator),
        review_bypass_rate=_rate(bypass_numerator, bypass_denominator),
        conservative_false_positive_rate=_rate(conservative_numerator, conservative_denominator),
        per_class=per_class,
        macro_f1=sum(f1_values) / len(f1_values),
        accuracy=sum(item.correct for item in evaluations) / len(evaluations),
        vocabulary_diagnostic=VocabularyDiagnostic(
            valid_prediction_count=len(predictions),
            outside_represented_count=outside,
            outside_represented_rate=outside / len(predictions),
            outside_counts_by_decision=outside_counts,
            outside_rates_by_decision={
                key: value / len(predictions) for key, value in outside_counts.items()
            },
            sensitivity_label="sensitivity only; not an alternative headline result",
            sensitivity_included_count=included,
            sensitivity_excluded_count=outside,
            accuracy_excluding_outside_predictions=(
                sum(item.correct for item in evaluations) / included if included else None
            ),
            legacy_reference_prediction_count=legacy_count,
            safety_caveat=(
                "Zero unsafe-FNR does not establish safety: no REUSE_AS_LEGACY_REFERENCE "
                "prediction occurred. Review-bypass must be considered alongside unsafe-FNR."
                if legacy_count == 0 else None
            ),
        ),
        balanced_accuracy=sum(recalls) / len(recalls),
        heading_mapping_accuracy=heading_correct / heading_total if heading_total else None,
        evidence_citation_accuracy=evidence_correct / len(cases),
        repair_action_accuracy=action_correct / len(cases),
        abstention_accuracy=abstention_correct / len(cases),
        retrieval=retrieval_metrics,
        latency_ms_total=sum(item.latency_ms for item in predictions),
        failures=sum(item.failure is not None for item in predictions),
        requests=sum(item.requests for item in predictions),
        input_tokens=sum(item.input_tokens for item in predictions),
        output_tokens=sum(item.output_tokens for item in predictions),
        cost_usd=None,
        calibration_status="not_applicable",
        calibration_not_applicable_reason=(
            "Deterministic contract fixtures and rule outputs do not provide empirically "
            "calibrated probabilities."
        ),
        family_sensitivity=family_sensitivity,
        action_required_family_count=sum(item.eligible_cases > 0 for item in family_sensitivity),
        families_with_unsafe_misses=sum(item.unsafe_misses > 0 for item in family_sensitivity),
        cluster_bootstrap_unsafe_fnr_95=_cluster_bootstrap(family_tuples, seed=seed),
        inference_claims="exploratory-only-no-independence-or-significance-claims",
    )
    return report, tuple(evaluations)
