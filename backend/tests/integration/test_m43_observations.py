from __future__ import annotations

from typing import Any

import pytest
from app.config import Settings
from app.domain.enums import LlmMode, MetadataMigrationIntent
from app.domain.models import MetadataPlan
from app.parsers.public322 import parse_public_profile_zip
from app.product.explanation import PlacementObservation, SemanticTopic
from app.product.models import DossierAnalysisRequest
from app.product.models_registry import ModelProfileRegistry
from app.product.repository import DossierRunRepository, InventoryRepository
from app.product.services import DossierAnalysisManager
from app.product.verify_m422 import PACKAGE, VerificationAbstentionModel, _target


@pytest.mark.parametrize("intent", list(MetadataMigrationIntent))
@pytest.mark.parametrize("abstain", [False, True])
async def test_observations_retain_actual_input_and_only_accepted_topics(
    intent: MetadataMigrationIntent,
    abstain: bool,
) -> None:
    class AbstentionRegistry(ModelProfileRegistry):
        def create(self, model_id: str) -> VerificationAbstentionModel:
            return VerificationAbstentionModel()

    options: dict[str, Any] = {"_env_file": None, "llm_mode": LlmMode.FIXTURE}
    settings = Settings(**options)
    inventory = parse_public_profile_zip(PACKAGE.read_bytes())
    inventories = InventoryRepository(capacity=2, ttl_seconds=60)
    envelope = inventories.put(inventory)
    manager = DossierAnalysisManager(
        inventories=inventories,
        runs=DossierRunRepository(capacity=2, ttl_seconds=60, prefix="dossier"),
        registry=AbstentionRegistry(settings) if abstain else ModelProfileRegistry(settings),
        settings=settings,
    )
    target = _target().model_copy(update={"metadata_plan": MetadataPlan(intent=intent)})
    run = manager.create(
        DossierAnalysisRequest(
            inventory_id=envelope.inventory_id,
            target_context=target,
        )
    )
    await manager.execute(run.run_id)
    result = manager.runs.get(run.run_id)
    assert result.state == "completed"
    placements: list[PlacementObservation] = []
    topics: list[SemanticTopic] = []
    for leaf_result in result.results:
        assert leaf_result.explanation is not None
        observed = leaf_result.explanation.observations
        assert observed is not None
        assert observed.metadata_plan == target.metadata_plan
        assert observed.package_applicant_name == inventory.applicant_name
        ids = {f.id for f in leaf_result.analysis.findings}
        assert all(t.finding_id in ids for t in observed.semantic_topics)
        assert all(p.finding_id in ids for p in observed.placements)
        placements.extend(observed.placements)
        topics.extend(observed.semantic_topics)
        for p in observed.placements:
            assert p.source_heading == leaf_result.analysis.source_artifact.source_heading
            assert p.target_heading == "3.2.S.1"
        if abstain:
            assert not observed.semantic_topics
    assert placements
    assert bool(topics) is not abstain


async def test_changed_manufacturer_does_not_project_previous_metadata_findings() -> None:
    options: dict[str, Any] = {"_env_file": None, "llm_mode": LlmMode.FIXTURE}
    settings = Settings(**options)
    inventory = parse_public_profile_zip(PACKAGE.read_bytes())
    leaves = tuple(
        leaf.model_copy(
            update={
                "keywords": tuple(
                    k.model_copy(
                        update={
                            "raw_value": "Named Manufacturer",
                            "normalized_value": "named manufacturer",
                        }
                    )
                    if k.name == "manufacturer"
                    else k
                    for k in leaf.keywords
                )
            }
        )
        for leaf in inventory.leaves
    )
    inventories = InventoryRepository(capacity=2, ttl_seconds=60)
    envelope = inventories.put(inventory.model_copy(update={"leaves": leaves}))
    manager = DossierAnalysisManager(
        inventories=inventories,
        runs=DossierRunRepository(capacity=2, ttl_seconds=60, prefix="dossier"),
        registry=ModelProfileRegistry(settings),
        settings=settings,
    )
    run = manager.create(
        DossierAnalysisRequest(
            inventory_id=envelope.inventory_id,
            target_context=_target(),
        )
    )
    await manager.execute(run.run_id)
    result = manager.runs.get(run.run_id)
    assert result.state == "completed"
    assert all(
        r.explanation and r.explanation.observations and not r.explanation.observations.keywords
        for r in result.results
    )
