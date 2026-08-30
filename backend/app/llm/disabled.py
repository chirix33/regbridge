import hashlib
from typing import TypeVar

from pydantic import BaseModel

from app.domain.models import ModelRunRecord
from app.llm.models import ModelCompletion, ModelRequest, SemanticRiskOutput

ModelOutput = TypeVar("ModelOutput", bound=BaseModel)


class DisabledModel:
    async def complete(
        self, request: ModelRequest, output_type: type[ModelOutput]
    ) -> ModelCompletion[ModelOutput]:
        if output_type is not SemanticRiskOutput:
            raise TypeError("disabled model supports only SemanticRiskOutput")
        output = SemanticRiskOutput(
            fixture_version="1.0.0",
            abstained=True,
            abstain_reason="semantic model is disabled",
            findings=(),
            confidence=0,
        )
        digest = hashlib.sha256(request.model_dump_json().encode()).hexdigest()
        return ModelCompletion(
            output=output_type.model_validate(output.model_dump()),
            run=ModelRunRecord(
                mode="disabled",
                status="abstained",
                prompt_template_version=request.prompt_template_version,
                model_name="disabled",
                request_digest=digest,
                latency_ms=0,
            ),
        )
