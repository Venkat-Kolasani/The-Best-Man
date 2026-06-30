from __future__ import annotations

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


class RecallGraphNode(BaseModel):
    id: str
    label: str
    type: str
    properties: dict[str, object] = Field(default_factory=dict)


class RecallGraphEdge(BaseModel):
    id: str | None = None
    source: str
    target: str
    label: str


class RecallGraph(BaseModel):
    nodes: list[RecallGraphNode] = Field(default_factory=list)
    edges: list[RecallGraphEdge] = Field(default_factory=list)


class RecallHighlighted(BaseModel):
    node_ids: list[str] = Field(default_factory=list)
    edge_ids: list[str] = Field(default_factory=list)


class RecallResponse(BaseModel):
    answer: str
    traversal: list[dict[str, object]] | None = None
    sources: str | None = None
    graph: RecallGraph = Field(default_factory=RecallGraph)
    highlighted: RecallHighlighted = Field(default_factory=RecallHighlighted)


class ImproveRequest(BaseModel):
    feedback: str = Field(min_length=1)


class ImproveResponse(BaseModel):
    status: str


class ForgetResponse(BaseModel):
    status: str
