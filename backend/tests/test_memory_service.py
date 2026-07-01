from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import memory_service
from app.services.memory_service import (
    MemoryBusyError,
    MemoryServiceError,
    RecallResult,
    RememberEntry,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _mock_infra(monkeypatch):
    """Prevent real Cognee init and keep the async lock well-behaved."""
    monkeypatch.setattr(memory_service, "initialize_cognee", lambda: None)
    # Use a fresh lock per test so acquire/release always pair correctly
    monkeypatch.setattr(memory_service, "_MEMORY_OPERATION_LOCK", asyncio.Lock())


def _mock_cognee(**funcs) -> tuple[dict[str, MagicMock], dict[str, MagicMock]]:
    """Patch ``memory_service.cognee.<name>`` with an AsyncMock.

    Returns ``(patchers, mocks)`` so caller can start/stop or just index
    the mock by function name.
    """
    patchers: dict[str, object] = {}
    mocks: dict[str, MagicMock] = {}
    for name, return_value in funcs.items():
        mock = AsyncMock(return_value=return_value)
        patchers[name] = patch.object(memory_service, "cognee", **{name: mock})
        patchers[name].start()
        mocks[name] = mock
    return patchers, mocks


def _stop_patchers(patchers: dict) -> None:
    for p in patchers.values():
        p.stop()


# ── remember_decision ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_remember_decision_calls_cognee_remember(monkeypatch: pytest.MonkeyPatch):
    cognee_mock = AsyncMock()
    monkeypatch.setattr(memory_service.cognee, "remember", cognee_mock)

    await memory_service.remember_decision(
        content="Dropped Redis for in-memory cache",
        dataset_name="repo:acme/widgets",
        source_type="commit",
        source_id="abc123",
    )

    cognee_mock.assert_awaited_once()
    call_data = cognee_mock.call_args.kwargs["data"]
    assert "[source: commit | id: abc123]" in call_data
    assert "Dropped Redis" in call_data
    assert cognee_mock.call_args.kwargs["dataset_name"] == "repo:acme/widgets"


@pytest.mark.asyncio
async def test_remember_decision_rejects_invalid_source_type():
    with pytest.raises(MemoryServiceError, match="source_type must be one of"):
        await memory_service.remember_decision(
            content="x", dataset_name="d", source_type="invalid", source_id="1"
        )


@pytest.mark.asyncio
async def test_remember_decision_wraps_cognee_error(monkeypatch: pytest.MonkeyPatch):
    cognee_mock = AsyncMock(side_effect=RuntimeError("API failure"))
    monkeypatch.setattr(memory_service.cognee, "remember", cognee_mock)

    with pytest.raises(MemoryServiceError) as excinfo:
        await memory_service.remember_decision(
            content="x", dataset_name="d", source_type="commit", source_id="1"
        )

    assert "API failure" in str(excinfo.value)
    assert excinfo.value.operation == "remember"


# ── remember_decision_batch ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_remember_decision_batch_calls_cognee_remember(monkeypatch: pytest.MonkeyPatch):
    cognee_mock = AsyncMock()
    monkeypatch.setattr(memory_service.cognee, "remember", cognee_mock)
    entries = [
        RememberEntry(source_type="commit", source_id="s1", content="fix: login bug"),
        RememberEntry(source_type="pr_comment", source_id="s2", content="LGTM"),
    ]

    await memory_service.remember_decision_batch(entries, dataset_name="repo:acme/widgets")

    cognee_mock.assert_awaited_once()
    call_data = cognee_mock.call_args.kwargs["data"]
    assert "Repository ingestion batch." in call_data
    assert "fix: login bug" in call_data
    assert "LGTM" in call_data
    assert cognee_mock.call_args.kwargs["dataset_name"] == "repo:acme/widgets"


@pytest.mark.asyncio
async def test_remember_decision_batch_empty_entries(monkeypatch: pytest.MonkeyPatch):
    """Empty batch returns immediately without calling Cognee."""
    cognee_mock = AsyncMock()
    monkeypatch.setattr(memory_service.cognee, "remember", cognee_mock)

    await memory_service.remember_decision_batch([], dataset_name="d")

    cognee_mock.assert_not_called()


@pytest.mark.asyncio
async def test_remember_decision_batch_rejects_invalid_source_type():
    with pytest.raises(MemoryServiceError, match="source_type must be one of"):
        await memory_service.remember_decision_batch(
            [RememberEntry(source_type="bad", source_id="1", content="x")],
            dataset_name="d",
        )


@pytest.mark.asyncio
async def test_remember_decision_batch_wraps_error(monkeypatch: pytest.MonkeyPatch):
    cognee_mock = AsyncMock(side_effect=ValueError("bad data"))
    monkeypatch.setattr(memory_service.cognee, "remember", cognee_mock)

    with pytest.raises(MemoryServiceError) as excinfo:
        await memory_service.remember_decision_batch(
            [RememberEntry(source_type="commit", source_id="1", content="x")],
            dataset_name="d",
        )

    assert excinfo.value.operation == "remember_batch"


# ── recall_answer ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_recall_answer_calls_search_and_returns_result(monkeypatch: pytest.MonkeyPatch):
    search_mock = AsyncMock(
        return_value=[
            MagicMock(source="graph", content="We chose SQLite for the MVP."),
        ]
    )
    monkeypatch.setattr(memory_service.cognee, "search", search_mock)

    # Mock the internal graph helpers so they return empty lists
    monkeypatch.setattr(
        memory_service, "_load_highlighted_graph_elements", AsyncMock(return_value=([], []))
    )
    monkeypatch.setattr(
        memory_service, "_load_graph_evidence_snapshot", AsyncMock(return_value=([], []))
    )

    # Mock SearchType.GRAPH_COMPLETION so _check_params passes
    monkeypatch.setattr(
        "cognee.modules.search.types.SearchType",
        MagicMock(GRAPH_COMPLETION="graph_completion"),
    )

    result = await memory_service.recall_answer(
        query="Why SQLite?", dataset_name="repo:acme/widgets"
    )

    assert isinstance(result, RecallResult)
    assert "We chose SQLite" in result.answer
    assert result.source == "graph"


@pytest.mark.asyncio
async def test_recall_answer_empty_on_missing_dataset(monkeypatch: pytest.MonkeyPatch):
    search_mock = AsyncMock(side_effect=Exception("DatasetNotFoundError"))
    monkeypatch.setattr(memory_service.cognee, "search", search_mock)
    monkeypatch.setattr(
        "cognee.modules.search.types.SearchType",
        MagicMock(GRAPH_COMPLETION="graph_completion"),
    )

    result = await memory_service.recall_answer(query="Why?", dataset_name="repo:missing/repo")

    assert result.answer == ""
    assert result.source == "empty"


@pytest.mark.asyncio
async def test_recall_answer_wraps_unexpected_error(monkeypatch: pytest.MonkeyPatch):
    search_mock = AsyncMock(side_effect=RuntimeError("unexpected"))
    monkeypatch.setattr(memory_service.cognee, "search", search_mock)
    monkeypatch.setattr(
        "cognee.modules.search.types.SearchType",
        MagicMock(GRAPH_COMPLETION="graph_completion"),
    )

    with pytest.raises(MemoryServiceError) as excinfo:
        await memory_service.recall_answer(query="Why?", dataset_name="repo:acme/x")

    assert excinfo.value.operation == "recall"


# ── improve_memory ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_improve_memory_calls_remember_then_improve(monkeypatch: pytest.MonkeyPatch):
    remember_mock = AsyncMock()
    improve_mock = AsyncMock()
    monkeypatch.setattr(memory_service.cognee, "remember", remember_mock)
    monkeypatch.setattr(memory_service.cognee, "improve", improve_mock)

    await memory_service.improve_memory(
        feedback="SQLite was the right call for the MVP.",
        dataset_name="repo:acme/widgets",
    )

    remember_mock.assert_awaited_once()
    improve_mock.assert_awaited_once_with(dataset="repo:acme/widgets")


@pytest.mark.asyncio
async def test_improve_memory_wraps_error(monkeypatch: pytest.MonkeyPatch):
    improve_mock = AsyncMock(side_effect=KeyError("no such dataset"))
    monkeypatch.setattr(memory_service.cognee, "remember", AsyncMock())
    monkeypatch.setattr(memory_service.cognee, "improve", improve_mock)

    with pytest.raises(MemoryServiceError) as excinfo:
        await memory_service.improve_memory(feedback="x", dataset_name="d")

    assert excinfo.value.operation == "improve_memory"


# ── forget_dataset ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_forget_dataset_calls_cognee_forget(monkeypatch: pytest.MonkeyPatch):
    forget_mock = AsyncMock()
    monkeypatch.setattr(memory_service.cognee, "forget", forget_mock)

    await memory_service.forget_dataset("repo:acme/widgets")

    forget_mock.assert_awaited_once_with(dataset="repo:acme/widgets")


@pytest.mark.asyncio
async def test_forget_dataset_wraps_error(monkeypatch: pytest.MonkeyPatch):
    forget_mock = AsyncMock(side_effect=Exception("forget failed"))
    monkeypatch.setattr(memory_service.cognee, "forget", forget_mock)

    with pytest.raises(MemoryServiceError) as excinfo:
        await memory_service.forget_dataset("d")

    assert excinfo.value.operation == "forget"


# ── Error classification ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_lock_error_classified_as_memory_busy(monkeypatch: pytest.MonkeyPatch):
    cognee_mock = AsyncMock(side_effect=Exception("Could not set lock on file"))
    monkeypatch.setattr(memory_service.cognee, "remember", cognee_mock)

    with pytest.raises(MemoryBusyError) as excinfo:
        await memory_service.remember_decision(
            content="x", dataset_name="d", source_type="commit", source_id="1"
        )

    assert "busy" in str(excinfo.value).lower()


# ── _check_params ────────────────────────────────────────────────────────────


def test_check_params_rejects_bad_key():
    def dummy_func(a, b):
        pass

    with pytest.raises(MemoryServiceError, match="Parameter 'c' is not accepted"):
        memory_service._check_params(dummy_func, "op", a=1, b=2, c=3)


def test_check_params_passes_with_var_keyword():
    def dummy_func(**kw):
        pass

    memory_service._check_params(dummy_func, "op", a=1, b=2)


# ── Helper: _build_recall_session_id ─────────────────────────────────────────


def test_build_recall_session_id():
    sid = memory_service._build_recall_session_id("repo:acme/widgets")
    assert sid.startswith("recall-")
    assert len(sid) == 7 + 12  # "recall-" + 12 hex chars
