"""One genuine rule-only B2 rescore for the frozen held-out Phase 2 bundle."""

from dataclasses import dataclass
from typing import Any

from app.domain.vocabulary import action_vocabulary_disclosure, output_vocabulary
from app.evaluation.live_configuration import configuration_material, content_digest
from app.evaluation.metrics import score_system
from app.evaluation.models import MetricsReport, SystemPrediction
from app.evaluation.phase1_b2 import B2_RESULT_STATUS, _predict
from app.evaluation.phase2_bundle import Phase2Bundle
from app.standards.evidence import EvidenceRegistry


def scoring_contract() -> dict[str, Any]:
    return {
        "output_vocabulary": output_vocabulary(),
        "action_vocabulary_disclosure": action_vocabulary_disclosure(),
        "decision_scoring_policy": "option-a-exact-match-three-represented-reference-classes",
    }


@dataclass(frozen=True)
class Phase2B2Rescore:
    configuration_sha256: str
    bundle_content_sha256: str
    contract: dict[str, Any]
    predictions: tuple[SystemPrediction, ...]
    report: MetricsReport

    def validate(self, bundle: Phase2Bundle, *, frozen_configuration_digest: str) -> None:
        if self.configuration_sha256 != frozen_configuration_digest:
            raise ValueError("Phase 2 B2 configuration digest mismatch")
        if self.contract != scoring_contract():
            raise ValueError("Phase 2 B2 scoring contract mismatch")
        if self.bundle_content_sha256 != content_digest(bundle.model_dump(mode="json")):
            raise ValueError("Phase 2 B2 bundle digest mismatch")
        expected = {item.case_id for item in bundle.case_inputs}
        if len(self.predictions) != len(expected) or {
            item.case_id for item in self.predictions
        } != expected:
            raise ValueError("Phase 2 B2 held-out coverage is incomplete")
        for prediction in self.predictions:
            if (
                prediction.system != "B2"
                or prediction.prediction_source != "genuine_rule_only"
                or prediction.requests
                or prediction.empirical_model_observation
            ):
                raise ValueError("Phase 2 B2 output is not a genuine rule-only result")

    def artifact(self) -> dict[str, Any]:
        return {
            "run_type": "deterministic_rule_only_rescore",
            "result_status": B2_RESULT_STATUS,
            "empirical_model_run": False,
            "eligible_for_performance_claims": True,
            "scope": "held-out-test",
            "current_fda_operational_availability": "not_operational",
            "expert_validated": False,
            "configuration_sha256": self.configuration_sha256,
            "bundle_content_sha256": self.bundle_content_sha256,
            "scoring_contract": self.contract,
            "model_calls": 0,
            "repetitions": 1,
            "predictions": [item.model_dump(mode="json") for item in self.predictions],
            "report": self.report.model_dump(mode="json"),
        }


async def rescore_phase2_b2(
    bundle: Phase2Bundle,
    *, seed: int,
    frozen_configuration_digest: str,
) -> Phase2B2Rescore:
    bundle = Phase2Bundle.model_validate(bundle.model_dump())
    current = content_digest(configuration_material(max_output_tokens=4000))
    if current != frozen_configuration_digest:
        raise ValueError("Phase 2 B2 aborted: frozen configuration digest mismatch")
    metadata = {item.fixture_id: item for item in bundle.fixture_metadata}
    predictions = tuple(
        [await _predict(case_input, metadata[case_input.fixture_id])
         for case_input in bundle.case_inputs]
    )
    report, _ = score_system(
        cases=bundle.cases,
        predictions=predictions,
        retrieval_traces=(),
        scope="held-out-test",
        seed=seed,
        regulatory_evidence_ids=frozenset(item.id for item in EvidenceRegistry().load()),
    )
    report = report.model_copy(update={
        "result_status": B2_RESULT_STATUS,
        "interval_interpretation": "exploratory only; no independence or significance claim",
    })
    result = Phase2B2Rescore(
        configuration_sha256=current,
        bundle_content_sha256=content_digest(bundle.model_dump(mode="json")),
        contract=scoring_contract(),
        predictions=predictions,
        report=report,
    )
    result.validate(bundle, frozen_configuration_digest=frozen_configuration_digest)
    return result
