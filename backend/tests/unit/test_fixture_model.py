import json
from pathlib import Path

import pytest
from app.domain.enums import (
    ApplicationType,
    Bindingness,
    EnforcementMode,
    ExtractionMethod,
    ReviewStatus,
    StandardVersion,
    VerificationBasis,
)
from app.domain.models import EvidenceSpan, SourceScope
from app.llm.fixture import FixtureModel, FixtureNotFoundError, UnsupportedCitationError
from app.llm.models import ModelRequest, SemanticRiskOutput


def evidence_span() -> EvidenceSpan:
    return EvidenceSpan(
        id="evidence-001",
        source_id="source-001",
        locator="synthetic fixture line 1",
        text="A synthetic, non-regulatory evidence span.",
        bindingness=Bindingness.INFORMATIVE,
        applicability=SourceScope(
            application_types=(ApplicationType.NDA,),
            source_standards=(StandardVersion.ECTD_3_2_2,),
            target_standards=(StandardVersion.ECTD_4_0,),
        ),
        source_sha256="a" * 64,
        extraction_method=ExtractionMethod.MANUAL,
        review_status=ReviewStatus.CANDIDATE,
        verification_basis=VerificationBasis.SYNTHETIC_ASSUMPTION,
        enforcement_mode=EnforcementMode.DISABLED,
    )


def request(fixture_id: str) -> ModelRequest:
    return ModelRequest(
        fixture_id=fixture_id,
        task="Classify semantic risk using only supplied evidence.",
        context={"artifact_id": "artifact-001"},
        evidence=(evidence_span(),),
        prompt_template_version="1.0.0",
    )


@pytest.mark.asyncio
async def test_fixture_model_is_deterministic_and_network_free() -> None:
    model = FixtureModel()

    first = await model.complete(request("semantic-clean-v1"), SemanticRiskOutput)
    second = await model.complete(request("semantic-clean-v1"), SemanticRiskOutput)

    assert first == second
    assert first.confidence == 1.0
    assert not first.abstained


@pytest.mark.asyncio
async def test_fixture_model_fails_closed_for_unknown_fixture() -> None:
    with pytest.raises(FixtureNotFoundError, match="offline model fixture not found"):
        await FixtureModel().complete(request("missing-fixture"), SemanticRiskOutput)


@pytest.mark.asyncio
async def test_fixture_model_rejects_unsupported_citation(tmp_path: Path) -> None:
    payload = {
        "fixture_version": "1.0.0",
        "abstained": False,
        "abstain_reason": None,
        "findings": [
            {
                "id": "finding-001",
                "basis": "inference",
                "summary": "Unsupported synthetic claim.",
                "severity": "high",
                "evidence_ids": ["evidence-not-supplied"],
            }
        ],
        "confidence": 0.4,
    }
    (tmp_path / "unsupported.json").write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(UnsupportedCitationError, match="evidence-not-supplied"):
        await FixtureModel(tmp_path).complete(request("unsupported"), SemanticRiskOutput)
