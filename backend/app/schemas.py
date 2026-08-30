import argparse
import json

from pydantic import BaseModel

from app.api.contracts import (
    AnalysisRequest,
    AnalysisResponse,
    FixtureListResponse,
    GraphResponse,
    ScopeResponse,
    StandardsSnapshotResponse,
)
from app.config import REPOSITORY_ROOT
from app.domain.models import AnalysisResult, StandardsManifest, TargetContext
from app.graph.models import GraphNeighborhood
from app.llm.models import ModelRequest, SemanticRiskOutput
from app.main import create_app
from app.parsers.models import ApplicationInventory
from app.rules.models import HeadingRule
from app.standards.operational import OperationalAvailability

SCHEMA_MODELS: dict[str, type[BaseModel]] = {
    "analysis-result.schema.json": AnalysisResult,
    "analysis-request.schema.json": AnalysisRequest,
    "analysis-response.schema.json": AnalysisResponse,
    "application-inventory.schema.json": ApplicationInventory,
    "fixture-list-response.schema.json": FixtureListResponse,
    "graph-neighborhood.schema.json": GraphNeighborhood,
    "graph-response.schema.json": GraphResponse,
    "heading-rule.schema.json": HeadingRule,
    "model-request.schema.json": ModelRequest,
    "operational-availability.schema.json": OperationalAvailability,
    "scope-response.schema.json": ScopeResponse,
    "semantic-risk-output.schema.json": SemanticRiskOutput,
    "standards-manifest.schema.json": StandardsManifest,
    "standards-snapshot-response.schema.json": StandardsSnapshotResponse,
    "target-context.schema.json": TargetContext,
}
SCHEMA_DIRECTORY = REPOSITORY_ROOT / "schemas"


def rendered_schemas() -> dict[str, str]:
    schemas = {
        filename: json.dumps(model.model_json_schema(), indent=2, sort_keys=True) + "\n"
        for filename, model in SCHEMA_MODELS.items()
    }
    schemas["openapi.json"] = json.dumps(create_app().openapi(), indent=2, sort_keys=True) + "\n"
    return schemas


def export_schemas() -> None:
    SCHEMA_DIRECTORY.mkdir(parents=True, exist_ok=True)
    for filename, rendered in rendered_schemas().items():
        (SCHEMA_DIRECTORY / filename).write_text(rendered, encoding="utf-8")


def check_schemas() -> list[str]:
    stale: list[str] = []
    for filename, rendered in rendered_schemas().items():
        path = SCHEMA_DIRECTORY / filename
        if not path.is_file() or path.read_text(encoding="utf-8") != rendered:
            stale.append(filename)
    return stale


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export or verify RegBridge JSON Schemas.")
    parser.add_argument("action", choices=("export", "check"))
    return parser.parse_args()


def main() -> None:
    arguments = parse_arguments()
    if arguments.action == "export":
        export_schemas()
        return
    stale = check_schemas()
    if stale:
        raise SystemExit(f"schema artifacts are missing or stale: {', '.join(stale)}")


if __name__ == "__main__":
    main()
