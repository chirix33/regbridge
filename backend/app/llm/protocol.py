from typing import Protocol, TypeVar

from pydantic import BaseModel

from app.llm.models import ModelCompletion, ModelRequest

ModelOutput = TypeVar("ModelOutput", bound=BaseModel)


class StructuredModel(Protocol):
    async def complete(
        self,
        request: ModelRequest,
        output_type: type[ModelOutput],
    ) -> ModelCompletion[ModelOutput]: ...
