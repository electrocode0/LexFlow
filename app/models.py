from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ContractCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    contract_type: str | None = Field(default=None, max_length=100)
    counterparty: str | None = Field(default=None, max_length=500)

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        title = value.strip()
        if not title:
            raise ValueError("title must not be blank")
        return title


class ContractResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    contract_type: str | None
    status: str
    counterparty: str | None
    created_at: datetime
    updated_at: datetime


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    contract_id: UUID
    file_name: str
    mime_type: str | None
    storage_path: str | None
    raw_text: str | None
    created_at: datetime


class SearchResult(BaseModel):
    chunk_id: UUID
    document_id: UUID
    file_name: str
    mime_type: str | None
    contract_title: str
    contract_type: str | None
    chunk_index: int
    text: str
    start_offset: int
    end_offset: int
    similarity: float


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)

    @field_validator("question")
    @classmethod
    def validate_question(cls, value: str) -> str:
        question = value.strip()
        if not question:
            raise ValueError("question must not be blank")
        return question


class Citation(BaseModel):
    document_id: UUID
    chunk_id: UUID
    chunk_index: int
    text: str


class AskResponse(BaseModel):
    answer: str
    citations: list[Citation]