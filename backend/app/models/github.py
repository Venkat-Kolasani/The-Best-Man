from __future__ import annotations

from pydantic import BaseModel, Field


class CommitData(BaseModel):
    sha: str
    message: str
    author: str | None = None
    date: str | None = None
    files_changed: list[str] = Field(default_factory=list)


class PRComment(BaseModel):
    author: str | None = None
    body: str
    created_at: str | None = None


class PRData(BaseModel):
    number: int
    title: str
    body: str | None = None
    state: str
    merged_at: str | None = None
    comments: list[PRComment] = Field(default_factory=list)
