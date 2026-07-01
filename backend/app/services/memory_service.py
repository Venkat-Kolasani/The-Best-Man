"""Memory service wrapping Cognee's API for The Best Man.

Provides a typed, project-specific interface over Cognee's
remember/recall/improve/forget lifecycle. All functions are async because
every Cognee call is async (see .cursorrules ground rule #3).

All signatures below are confirmed against cognee 1.2.2 installed in
/opt/anaconda3/lib/python3.13/site-packages/cognee/.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import os
from hashlib import sha1
from dataclasses import dataclass, field
from typing import Any

import cognee
from app.config import initialize_cognee

logger = logging.getLogger(__name__)

_VALID_SOURCE_TYPES = frozenset({"commit", "pr_comment", "manual_log"})
_MEMORY_OPERATION_LOCK = asyncio.Lock()
_MEMORY_BUSY_TIMEOUT_SECONDS = float(os.getenv("MEMORY_BUSY_TIMEOUT_SECONDS", "1.0"))
_LOCK_ERROR_MARKERS = (
    "Could not set lock on file",
    "Lock is held by PID",
    ".lbug",
)


class MemoryServiceError(Exception):
    """Raised when a Cognee operation fails or receives unexpected arguments.

    Attributes:
        operation: Name of the Cognee operation that failed.
        detail: Human-readable explanation of what went wrong.
    """

    def __init__(self, operation: str, detail: str):
        self.operation = operation
        self.detail = detail
        super().__init__(f"[{operation}] {detail}")


class MemoryBusyError(MemoryServiceError):
    """Raised when the local Cognee/Ladybug store is already in use."""


@dataclass
class RecallResult:
    """Typed result from a recall operation.

    Wraps Cognee's raw ``list[RecallResponse]`` so the API layer never
    needs to import or understand Cognee internals.

    Attributes:
        answer: Concatenated answer text from the result set.
        source: Where the result came from ("graph", "session", "multi",
            "empty", or "unknown").
        references: Graph traversal / reference metadata for UI
            visualization. Populated when Cognee's recall exposes
            references (via ``include_references=True``).
        raw: Raw Cognee response objects, preserved for debugging or
            advanced downstream use.
    """

    answer: str
    source: str
    references: list[dict] = field(default_factory=list)
    graph_nodes: list[dict[str, Any]] = field(default_factory=list)
    graph_edges: list[dict[str, Any]] = field(default_factory=list)
    highlighted_node_ids: list[str] = field(default_factory=list)
    highlighted_edge_ids: list[str] = field(default_factory=list)
    raw: list[Any] = field(default_factory=list)


@dataclass(frozen=True)
class RememberEntry:
    """One source-tracked text entry for batch ingestion."""

    source_type: str
    source_id: str
    content: str


def _check_params(func: Any, operation: str, **kwargs: Any) -> None:
    """Validate that *func* accepts *kwargs* before calling it.

    If the function has a ``**kwargs`` catch-all (``VAR_KEYWORD``), the
    check passes since any keyword is accepted. Otherwise every key in
    *kwargs* must appear in the function's signature.

    Args:
        func: The callable to inspect.
        operation: Label used in the error message if validation fails.
        **kwargs: Parameter names and values we intend to pass.

    Raises:
        MemoryServiceError: If a parameter is not accepted and the
            function has no ``**kwargs`` catch-all.
    """
    try:
        sig = inspect.signature(func)
    except (ValueError, TypeError) as exc:
        raise MemoryServiceError(operation, f"Cannot inspect signature: {exc}") from exc

    has_var_keyword = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
    if has_var_keyword:
        return

    accepted = set(sig.parameters.keys())
    for key in kwargs:
        if key not in accepted:
            raise MemoryServiceError(
                operation,
                f"Parameter '{key}' is not accepted by {func.__qualname__}. "
                f"Accepted: {sorted(accepted)}",
            )


def _normalize_exception(operation: str, exc: Exception) -> MemoryServiceError:
    detail = str(exc)
    if any(marker in detail for marker in _LOCK_ERROR_MARKERS):
        return MemoryBusyError(
            operation,
            "Memory is busy with another operation against the local Cognee store. "
            "Please retry once the current ingest or write finishes.",
        )
    return MemoryServiceError(operation, detail)


async def _acquire_memory_lock(operation: str) -> None:
    try:
        await asyncio.wait_for(
            _MEMORY_OPERATION_LOCK.acquire(),
            timeout=_MEMORY_BUSY_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError as exc:
        raise MemoryBusyError(
            operation,
            "Memory is busy with another operation against the local Cognee store. "
            "Please retry once the current ingest or write finishes.",
        ) from exc


async def remember_decision(
    content: str,
    dataset_name: str,
    source_type: str,
    source_id: str,
) -> None:
    """Store a decision or event in Cognee's knowledge graph.

    Wraps ``cognee.remember(data, dataset_name=...)`` (v1.2.2 confirmed).

    Provenance is embedded directly in the ingested text because
    Cognee's ``remember`` has no dedicated metadata parameter in 1.2.2.
    The graph extractor can then surface ``source_type`` and ``source_id``
    as entities during cognify, letting us trace any graph node back to
    its origin.

    ``remember`` with ``self_improvement=True`` (the default) runs
    add + cognify + improve in sequence, so a single call ingests the
    text, builds graph nodes/edges, and enriches with triplet embeddings.

    Args:
        content: The decision text, commit message, PR comment, etc.
        dataset_name: Target Cognee dataset. Per project convention this
            is ``f"repo:{owner}/{repo}"`` so all commits, PR comments,
            and manual logs for a repo share one graph.
        source_type: Provenance label. Must be one of "commit",
            "pr_comment", "manual_log".
        source_id: Unique identifier for the source (e.g. commit SHA,
            PR comment ID, or a manual entry UUID).

    Returns:
        None. Awaits the full add+cognify+improve pipeline to completion.

    Raises:
        MemoryServiceError: If ``source_type`` is invalid, or if Cognee
            rejects the call, or if a parameter is not supported by the
            installed version.

    Example::

        await remember_decision(
            content="Dropped Redis in favor of in-memory cache for v2",
            dataset_name="repo:acme/widgets",
            source_type="commit",
            source_id="a1b2c3d",
        )
    """
    if source_type not in _VALID_SOURCE_TYPES:
        raise MemoryServiceError(
            "remember_decision",
            f"source_type must be one of {sorted(_VALID_SOURCE_TYPES)}, got '{source_type}'.",
        )

    initialize_cognee()
    await _acquire_memory_lock("remember")

    try:
        formatted = f"[source: {source_type} | id: {source_id}]\n{content}"

        _check_params(
            cognee.remember,
            "remember",
            data=formatted,
            dataset_name=dataset_name,
        )

        result = await cognee.remember(
            data=formatted,
            dataset_name=dataset_name,
        )
        # remember returns RememberResult, a promise-like object.
        # With run_in_background=False (default) the pipeline has already
        # completed, but awaiting the result is a safe no-op if so.
        if inspect.isawaitable(result):
            await result
    except MemoryServiceError:
        raise
    except Exception as exc:
        raise _normalize_exception("remember", exc) from exc
    finally:
        _MEMORY_OPERATION_LOCK.release()


async def remember_decision_batch(
    entries: list[RememberEntry],
    dataset_name: str,
) -> None:
    """Store multiple decision-log entries in one Cognee remember call.

    Batching reduces the number of Cognee add/cognify/improve pipeline runs,
    which in turn reduces repeated embedding, indexing, and graph-extraction
    work during large repository ingestions.

    The trade-off is that Cognee content hashing now dedupes at the batch-text
    level rather than at a single-source-entry level. If stricter per-source
    deduplication is needed later, we can add explicit source tracking outside
    of the batch payload.
    """
    if not entries:
        return

    for entry in entries:
        if entry.source_type not in _VALID_SOURCE_TYPES:
            raise MemoryServiceError(
                "remember_decision_batch",
                f"source_type must be one of {sorted(_VALID_SOURCE_TYPES)}, got '{entry.source_type}'.",
            )

    initialize_cognee()
    await _acquire_memory_lock("remember_batch")

    try:
        formatted_entries: list[str] = [
            "Repository ingestion batch.",
            "",
        ]
        for index, entry in enumerate(entries, start=1):
            formatted_entries.extend(
                [
                    f"Entry {index}:",
                    f"Source: {entry.source_type} {entry.source_id}",
                    entry.content,
                    "",
                ]
            )
        batch_text = "\n".join(formatted_entries).rstrip()

        _check_params(
            cognee.remember,
            "remember_batch",
            data=batch_text,
            dataset_name=dataset_name,
        )

        result = await cognee.remember(
            data=batch_text,
            dataset_name=dataset_name,
        )
        if inspect.isawaitable(result):
            await result
    except MemoryServiceError:
        raise
    except Exception as exc:
        raise _normalize_exception("remember_batch", exc) from exc
    finally:
        _MEMORY_OPERATION_LOCK.release()


async def recall_answer(query: str, dataset_name: str) -> RecallResult:
    """Query the knowledge graph for an answer.

    Uses ``cognee.search(..., query_type=SearchType.GRAPH_COMPLETION)`` so we
    get the graph-oriented retriever path in the installed Cognee 1.2.2 API.
    If Cognee session/cache metadata exposes ``used_graph_element_ids``, those
    node and edge ids are returned as highlighted graph evidence for the UI.

    Args:
        query: Natural-language question.
        dataset_name: Dataset to search within.

    Returns:
        RecallResult containing the answer text, source label, any
        any reference metadata preserved for compatibility, the dataset graph
        evidence snapshot when available, highlighted graph-element ids from
        Cognee session metadata when available, and the raw Cognee response
        objects.

    Raises:
        MemoryServiceError: If Cognee rejects the call or a parameter
            is not supported by the installed version.

    Example::

        result = await recall_answer(
            query="Why did we drop the Redis caching approach?",
            dataset_name="repo:acme/widgets",
        )
        print(result.answer)
        print(result.source)
        print(len(result.references))
    """
    initialize_cognee()
    await _acquire_memory_lock("recall")

    highlighted_node_ids: list[str] = []
    highlighted_edge_ids: list[str] = []
    graph_nodes: list[dict[str, Any]] = []
    graph_edges: list[dict[str, Any]] = []

    try:
        from cognee.modules.search.types import SearchType

        _check_params(
            cognee.search,
            "recall.search",
            query_text=query,
            query_type=SearchType.GRAPH_COMPLETION,
            datasets=[dataset_name],
            session_id=_build_recall_session_id(dataset_name),
            include_references=True,
            verbose=True,
        )

        results = await cognee.search(
            query_text=query,
            query_type=SearchType.GRAPH_COMPLETION,
            datasets=[dataset_name],
            session_id=_build_recall_session_id(dataset_name),
            include_references=True,
            verbose=True,
        )

        highlighted_node_ids, highlighted_edge_ids = await _load_highlighted_graph_elements(
            dataset_name=dataset_name,
            session_id=_build_recall_session_id(dataset_name),
            query=query,
        )
        graph_nodes, graph_edges = await _load_graph_evidence_snapshot(
            dataset_name=dataset_name,
            target_node_ids=highlighted_node_ids,
        )
    except MemoryServiceError:
        raise
    except Exception as exc:
        if "DatasetNotFoundError" in str(exc):
            return RecallResult(answer="", source="empty")
        raise _normalize_exception("recall", exc) from exc
    finally:
        _MEMORY_OPERATION_LOCK.release()

    if not results:
        return RecallResult(answer="", source="empty")

    answers: list[str] = []
    sources: set[str] = set()
    references: list[dict] = []

    for item in results:
        # recall tags each result with a source label so callers can
        # tell whether it came from the session cache or the permanent graph.
        item_source = getattr(item, "source", None)
        if item_source is None and isinstance(item, dict):
            item_source = item.get("_source") or item.get("source")
        if item_source:
            sources.add(item_source)

        text = (
            getattr(item, "content", None)
            or getattr(item, "text_result", None)
            or getattr(item, "text", None)
            or getattr(item, "answer", None)
            or (item.get("text_result") if isinstance(item, dict) else None)
            or (item.get("content") if isinstance(item, dict) else None)
            or ""
        )
        if text:
            if isinstance(text, list):
                answers.extend(str(entry) for entry in text if entry)
            else:
                answers.append(str(text))

        refs = getattr(item, "references", None)
        if refs is None and isinstance(item, dict):
            refs = item.get("references")
        if refs:
            for ref in refs:
                references.append(
                    ref if isinstance(ref, dict) else getattr(ref, "model_dump", lambda: ref)()
                )

    if len(sources) == 1:
        source_label = sources.pop()
    elif sources:
        source_label = "multi"
    elif answers:
        source_label = "graph"
    else:
        source_label = "unknown"

    return RecallResult(
        answer="\n\n".join(answers),
        source=source_label,
        references=references,
        graph_nodes=graph_nodes,
        graph_edges=graph_edges,
        highlighted_node_ids=highlighted_node_ids,
        highlighted_edge_ids=highlighted_edge_ids,
        raw=list(results),
    )


def _build_recall_session_id(dataset_name: str) -> str:
    digest = sha1(dataset_name.encode("utf-8")).hexdigest()[:12]
    return f"recall-{digest}"


async def _load_highlighted_graph_elements(
    dataset_name: str,
    session_id: str,
    query: str,
) -> tuple[list[str], list[str]]:
    try:
        from cognee.infrastructure.session.get_session_manager import get_session_manager
        from cognee.modules.users.methods import get_default_user
    except Exception as exc:  # pragma: no cover - installed package dependency guard
        logger.debug("Unable to import Cognee session helpers for recall evidence: %s", exc)
        return [], []

    session_manager = get_session_manager()
    if not session_manager.is_available:
        return [], []

    try:
        user = await get_default_user()
        entries = await session_manager.get_session(
            user_id=str(user.id),
            session_id=session_id,
            formatted=False,
        )
    except Exception as exc:
        logger.debug("Unable to read Cognee session metadata for recall evidence: %s", exc)
        return [], []

    if not isinstance(entries, list) or not entries:
        return [], []

    for entry in reversed(entries):
        if getattr(entry, "question", None) != query:
            continue
        used = getattr(entry, "used_graph_element_ids", None) or {}
        node_ids = used.get("node_ids") or []
        edge_ids = used.get("edge_ids") or []
        return [str(node_id) for node_id in node_ids], [str(edge_id) for edge_id in edge_ids]

    return [], []


async def _load_graph_evidence_snapshot(
    dataset_name: str,
    target_node_ids: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    try:
        from cognee.context_global_variables import set_database_global_context_variables
        from cognee.infrastructure.databases.graph import get_graph_engine
        from cognee.modules.data.methods import get_authorized_existing_datasets
        from cognee.modules.users.methods import get_default_user
    except Exception as exc:  # pragma: no cover - installed package dependency guard
        logger.debug("Unable to import Cognee graph helpers for recall evidence: %s", exc)
        return [], []

    try:
        user = await get_default_user()
        datasets = await get_authorized_existing_datasets([dataset_name], "read", user)
        if not datasets:
            return [], []

        dataset = datasets[0]
        async with set_database_global_context_variables(dataset.id, dataset.owner_id):
            graph_engine = await get_graph_engine()
            get_filtered = getattr(graph_engine, "get_id_filtered_graph_data", None)
            if target_node_ids and callable(get_filtered):
                nodes_data, edges_data = await get_filtered(target_ids=target_node_ids)
                if not nodes_data and not edges_data:
                    nodes_data, edges_data = await graph_engine.get_graph_data()
            else:
                nodes_data, edges_data = await graph_engine.get_graph_data()
    except Exception as exc:
        logger.debug("Unable to load Cognee graph evidence snapshot: %s", exc)
        return [], []

    return _format_graph_nodes(nodes_data), _format_graph_edges(edges_data)


def _format_graph_nodes(nodes_data: list[Any]) -> list[dict[str, Any]]:
    formatted_nodes: list[dict[str, Any]] = []
    for node_id, properties in nodes_data or []:
        props = dict(properties or {})
        label = props.get("name") or props.get("label") or f"{props.get('type', 'Node')}_{node_id}"
        formatted_nodes.append(
            {
                "id": str(node_id),
                "label": str(label),
                "type": str(props.get("type", "Node")),
                "properties": {
                    key: value
                    for key, value in props.items()
                    if key not in {"id", "name", "label", "type", "created_at", "updated_at"}
                    and value is not None
                },
            }
        )
    return formatted_nodes


def _format_graph_edges(edges_data: list[Any]) -> list[dict[str, Any]]:
    formatted_edges: list[dict[str, Any]] = []
    for edge in edges_data or []:
        source_id, target_id, relation, properties = edge
        props = dict(properties or {})
        formatted_edges.append(
            {
                "id": str(props["edge_object_id"])
                if props.get("edge_object_id") is not None
                else None,
                "source": str(source_id),
                "target": str(target_id),
                "label": str(relation),
            }
        )
    return formatted_edges


async def improve_memory(feedback: str, dataset_name: str) -> None:
    """Enrich the knowledge graph with feedback.

    Cognee's ``improve(dataset=...)`` (v1.2.2 confirmed) enriches the
    graph with triplet embeddings and, when ``session_ids`` are provided,
    bridges session feedback scores into node weights. Our interface
    receives a free-form feedback string rather than session-bound
    feedback, so we first ``remember`` the feedback into the dataset
    (making it a graph node) and then call ``improve`` to enrich.

    This is a deliberate design choice: Cognee 1.2.2 has no
    ``improve(feedback="...")`` parameter. Bridging free-form feedback
    through remember+improve ensures the text enters the graph and
    receives enrichment rather than being silently dropped.

    Args:
        feedback: Free-form feedback text to incorporate into the graph.
        dataset_name: Dataset to improve.

    Returns:
        None.

    Raises:
        MemoryServiceError: If Cognee rejects either the remember or
            improve call.

    Example::

        await improve_memory(
            feedback="The decision to use SQLite was correct for the MVP.",
            dataset_name="repo:acme/widgets",
        )
    """
    initialize_cognee()
    await _acquire_memory_lock("improve_memory")

    try:
        formatted = f"[source: feedback | id: manual]\n{feedback}"

        _check_params(
            cognee.remember,
            "improve_memory.remember",
            data=formatted,
            dataset_name=dataset_name,
        )

        result = await cognee.remember(
            data=formatted,
            dataset_name=dataset_name,
        )
        if inspect.isawaitable(result):
            await result

        _check_params(
            cognee.improve,
            "improve_memory.improve",
            dataset=dataset_name,
        )

        await cognee.improve(dataset=dataset_name)
    except MemoryServiceError:
        raise
    except Exception as exc:
        raise _normalize_exception("improve_memory", exc) from exc
    finally:
        _MEMORY_OPERATION_LOCK.release()


async def forget_dataset(dataset_name: str) -> None:
    """Remove an entire dataset from Cognee's knowledge graph.

    Wraps ``cognee.forget(dataset=dataset_name)`` (v1.2.2 confirmed).
    This deletes all data items, graph nodes/edges, and vector entries
    for the dataset. Raw files are also removed (use ``memory_only=True``
    via Cognee directly if you need to preserve raw data for re-cognify).

    Args:
        dataset_name: Name of the dataset to forget.

    Returns:
        None.

    Raises:
        MemoryServiceError: If Cognee rejects the call.

    Example::

        await forget_dataset("repo:acme/widgets")
    """
    initialize_cognee()
    await _acquire_memory_lock("forget")

    try:
        _check_params(
            cognee.forget,
            "forget",
            dataset=dataset_name,
        )

        await cognee.forget(dataset=dataset_name)
    except MemoryServiceError:
        raise
    except Exception as exc:
        raise _normalize_exception("forget", exc) from exc
    finally:
        _MEMORY_OPERATION_LOCK.release()
