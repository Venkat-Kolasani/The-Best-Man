from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.models.ingestion import IngestionSummary


class ErrorResponse(BaseModel):
    detail: str


class IngestJobResponse(BaseModel):
    job_id: str
    status: str


class IngestJobStatusResponse(BaseModel):
    job_id: str
    status: str
    summary: IngestionSummary | None = None
    error: str | None = None


class ManualDecisionRequest(BaseModel):
    content: str = Field(min_length=1)


class ManualDecisionResponse(BaseModel):
    status: str
    source_id: str | None = None


class RecallRequest(BaseModel):
    query: str = Field(min_length=1)


class RecallResponse(BaseModel):
    answer: str
    traversal: list[dict[str, Any]] | None = None
    sources: str | None = None


class ImproveRequest(BaseModel):
    feedback: str = Field(min_length=1)


class ImproveResponse(BaseModel):
    status: str


class ForgetResponse(BaseModel):
    status: str
