import json
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from app.config import REPOSITORY_ROOT
from app.llm.models import ModelRequest, SemanticRiskOutput

ModelOutput = TypeVar("ModelOutput", bound=BaseModel)


class FixtureNotFoundError(LookupError):
    """Raised when an explicitly requested offline response is absent."""


class UnsupportedCitationError(ValueError):
    """Raised when a model fixture cites evidence outside its request packet."""


class FixtureModel:
    """Deterministic structured model backed by versioned JSON responses."""

    def __init__(self, fixture_directory: Path | None = None) -> None:
        self._fixture_directory = fixture_directory or REPOSITORY_ROOT / "data" / "model-fixtures"

    async def complete(
        self,
        request: ModelRequest,
        output_type: type[ModelOutput],
    ) -> ModelOutput:
        fixture_path = self._fixture_directory / f"{request.fixture_id}.json"
        if not fixture_path.is_file():
            raise FixtureNotFoundError(f"offline model fixture not found: {request.fixture_id}")

        with fixture_path.open(encoding="utf-8") as fixture_file:
            payload = json.load(fixture_file)

        result = output_type.model_validate(payload)
        if isinstance(result, SemanticRiskOutput):
            supplied_ids = {span.id for span in request.evidence}
            cited_ids = {
                evidence_id
                for finding in result.findings
                for evidence_id in finding.evidence_ids
            }
            unsupported_ids = cited_ids - supplied_ids
            if unsupported_ids:
                unsupported = ", ".join(sorted(unsupported_ids))
                raise UnsupportedCitationError(
                    f"fixture cited evidence not supplied in request: {unsupported}"
                )

        return result
