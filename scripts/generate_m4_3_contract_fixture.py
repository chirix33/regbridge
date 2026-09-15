"""Network-free product contracts from the production synthetic ZIP path (not evaluation)."""
import asyncio
import json

from app.config import REPOSITORY_ROOT, Settings
from app.domain.enums import LlmMode
from app.parsers.public322 import parse_public_profile_zip
from app.product.comparison import ComparisonManager
from app.product.models import ComparisonRequest, DossierAnalysisRequest
from app.product.models_registry import ModelProfileRegistry
from app.product.repository import ComparisonRunRepository, DossierRunRepository, InventoryRepository
from app.product.services import DossierAnalysisManager
from app.product.verify_m422 import PACKAGE, VerificationAbstentionModel, _target


async def main() -> None:
    settings = Settings(_env_file=None, llm_mode=LlmMode.FIXTURE)
    registry = ModelProfileRegistry(settings)
    inventories = InventoryRepository(capacity=2, ttl_seconds=60)
    envelope = inventories.put(parse_public_profile_zip(PACKAGE.read_bytes()))
    runs = DossierRunRepository(capacity=2, ttl_seconds=60, prefix="dossier")
    manager = DossierAnalysisManager(
        inventories=inventories, runs=runs, registry=registry, settings=settings,
    )
    run = manager.create(DossierAnalysisRequest(
        inventory_id=envelope.inventory_id, target_context=_target(),
    ))
    await manager.execute(run.run_id)
    comparisons = ComparisonRunRepository(capacity=2, ttl_seconds=60, prefix="comparison")
    comparison_manager = ComparisonManager(
        inventories=inventories, runs=comparisons, registry=registry, settings=settings,
    )
    comparison = comparison_manager.create(ComparisonRequest(
        inventory_id=envelope.inventory_id, target_context=_target(),
    ))
    await comparison_manager.execute(comparison.comparison_id)
    class AbstentionRegistry(ModelProfileRegistry):
        def create(self, model_id: str) -> VerificationAbstentionModel:
            self.require(model_id)
            return VerificationAbstentionModel()

    abstention_manager = DossierAnalysisManager(
        inventories=inventories, runs=DossierRunRepository(capacity=2, ttl_seconds=60, prefix="dossier"),
        registry=AbstentionRegistry(settings), settings=settings,
    )
    abstention = abstention_manager.create(DossierAnalysisRequest(
        inventory_id=envelope.inventory_id, target_context=_target(),
    ))
    await abstention_manager.execute(abstention.run_id)
    output = {
        "abstention": abstention_manager.runs.get(abstention.run_id).model_dump(mode="json"),
        "origin": "M4.3 network-free production ZIP contract example, not experimental output",
        "inventory": envelope.inventory.model_dump(mode="json"),
        "configuration": registry.active_configuration().model_dump(mode="json"),
        "run": runs.get(run.run_id).model_dump(mode="json"),
        "comparison": comparisons.get(comparison.comparison_id).model_dump(mode="json"),
    }
    path = REPOSITORY_ROOT / "frontend/src/test/fixtures/m43-product.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote production contract fixture: {path}")


if __name__ == "__main__":
    asyncio.run(main())
