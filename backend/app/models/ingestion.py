from __future__ import annotations

from pydantic import BaseModel, Field


class IngestionSummary(BaseModel):
    commits_ingested: int
    prs_ingested: int
    comments_ingested: int
    skipped: list[dict[str, str]] = Field(default_factory=list)
