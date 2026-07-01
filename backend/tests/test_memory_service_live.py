"""Integration tests that exercise real Cognee remember/recall/forget calls.

These tests communicate with the configured LLM and embedding provider and
will consume API credits.  They are **skipped by default** — run with::

    pytest -m live_cognee

The tests use a disposable dataset (``test:memory-service-live-<uuid>``) that
is cleaned up after the session.
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from app.services.memory_service import (
    recall_answer,
    remember_decision,
    forget_dataset,
)

pytestmark = pytest.mark.live_cognee

_DATASET_PREFIX = "test:memory-service-live"
_LOCK = asyncio.Lock()


def _dataset_name() -> str:
    return f"{_DATASET_PREFIX}-{uuid4().hex[:12]}"


@pytest.fixture
def dataset_name() -> str:
    return _dataset_name()


@pytest.mark.asyncio
async def test_remember_and_recall(dataset_name: str):
    async with _LOCK:
        try:
            await remember_decision(
                content="We chose SQLite over PostgreSQL for the MVP because "
                "SQLite requires zero infrastructure and the data model "
                "fits in a single file.",
                dataset_name=dataset_name,
                source_type="commit",
                source_id="live-abc123",
            )

            result = await recall_answer(
                query="Why did we choose SQLite over PostgreSQL?",
                dataset_name=dataset_name,
            )

            assert result.answer, "Expected a non-empty answer from the graph"
            assert result.source in ("graph", "multi", "unknown")
            assert "SQLite" in result.answer or "sqlite" in result.answer.lower()
        finally:
            await forget_dataset(dataset_name)


@pytest.mark.asyncio
async def test_recall_empty_dataset_returns_empty(dataset_name: str):
    async with _LOCK:
        try:
            result = await recall_answer(
                query="What decisions were made?",
                dataset_name=dataset_name,
            )
            assert result.answer == ""
            assert result.source == "empty"
        finally:
            await forget_dataset(dataset_name)
