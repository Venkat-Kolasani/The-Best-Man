"""Memory service wrapping Cognee's API for The Best Man.

Provides a typed, project-specific interface over Cognee's
remember/recall/improve/forget lifecycle. All functions are async because
every Cognee call is async (see .cursorrules ground rule #3).

All signatures below are confirmed against cognee 1.2.2 installed in
/opt/anaconda3/lib/python3.13/site-packages/cognee/.
"""

from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass, field
from typing import Any

import cognee
from app.config import initialize_cognee

logger = logging.getLogger(__name__)

_VALID_SOURCE_TYPES = frozenset({"commit", "pr_comment", "manual_log"})


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
    raw: list[Any] = field(default_factory=list)


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

    formatted = f"[source: {source_type} | id: {source_id}]\n{content}"

    _check_params(
        cognee.remember,
        "remember",
        data=formatted,
        dataset_name=dataset_name,
    )

    try:
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
        raise MemoryServiceError("remember", str(exc)) from exc


async def recall_answer(query: str, dataset_name: str) -> RecallResult:
    """Query the knowledge graph for an answer.

    Wraps ``cognee.recall(query_text, datasets=[...], include_references=True)``
    (v1.2.2 confirmed).

    ``include_references=True`` is passed so that graph traversal metadata
    is included in the response for UI visualization (per .cursorrules
    ground rule #7). ``auto_route`` is left at its default (True) so
    Cognee's lightweight classifier picks the best search strategy
    (GRAPH_COMPLETION, GRAPH_COMMUNITIES, etc.) for the query.

    Args:
        query: Natural-language question.
        dataset_name: Dataset to search within.

    Returns:
        RecallResult containing the answer text, source label, any
        reference metadata for visualization, and the raw Cognee
        response objects.

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

    _check_params(
        cognee.recall,
        "recall",
        query_text=query,
        datasets=[dataset_name],
        include_references=True,
    )

    try:
        results = await cognee.recall(
            query_text=query,
            datasets=[dataset_name],
            include_references=True,
        )
    except MemoryServiceError:
        raise
    except Exception as exc:
        if "DatasetNotFoundError" in str(exc):
            return RecallResult(answer="", source="empty")
        raise MemoryServiceError("recall", str(exc)) from exc

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
            or getattr(item, "text", None)
            or getattr(item, "answer", None)
            or (item.get("content") if isinstance(item, dict) else None)
            or ""
        )
        if text:
            answers.append(text)

        # Collect graph references for visualization (ground rule #7).
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
    else:
        source_label = "unknown"

    return RecallResult(
        answer="\n\n".join(answers),
        source=source_label,
        references=references,
        raw=list(results),
    )


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

    formatted = f"[source: feedback | id: manual]\n{feedback}"

    _check_params(
        cognee.remember,
        "improve_memory.remember",
        data=formatted,
        dataset_name=dataset_name,
    )

    try:
        result = await cognee.remember(
            data=formatted,
            dataset_name=dataset_name,
        )
        if inspect.isawaitable(result):
            await result
    except MemoryServiceError:
        raise
    except Exception as exc:
        raise MemoryServiceError("improve_memory.remember", str(exc)) from exc

    _check_params(
        cognee.improve,
        "improve_memory.improve",
        dataset=dataset_name,
    )

    try:
        await cognee.improve(dataset=dataset_name)
    except MemoryServiceError:
        raise
    except Exception as exc:
        raise MemoryServiceError("improve_memory.improve", str(exc)) from exc


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

    _check_params(
        cognee.forget,
        "forget",
        dataset=dataset_name,
    )

    try:
        await cognee.forget(dataset=dataset_name)
    except MemoryServiceError:
        raise
    except Exception as exc:
        raise MemoryServiceError("forget", str(exc)) from exc
