from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SessionCreate(StrictModel):
    language: Literal["en"] = "en"


class AnswerPatch(StrictModel):
    revision: int = Field(ge=0, strict=True)
    answers: dict[str, Any]


class GenerateRequest(StrictModel):
    request_id: UUID
    revision: int = Field(ge=0, strict=True)
    accepted_notes: list[str] = Field(default_factory=list, max_length=10)
