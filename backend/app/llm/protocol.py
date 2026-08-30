from typing import Protocol, TypeVar

from pydantic import BaseModel

from app.llm.models import ModelRequest

ModelOutput = TypeVar("ModelOutput", bound=BaseModel)


class StructuredModel(Protocol):
    async def complete(
        self,
        request: ModelRequest,
        output_type: type[ModelOutput],
    ) -> ModelOutput: ...
