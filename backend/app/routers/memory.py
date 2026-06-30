from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.models.api import (
    ErrorResponse,
    ForgetResponse,
    ImproveRequest,
    ImproveResponse,
    RecallRequest,
    RecallResponse,
)
from app.services import memory_service

router = APIRouter(prefix="/repos/{owner}/{repo}", tags=["memory"])


def _dataset_name(owner: str, repo: str) -> str:
    return f"repo:{owner}/{repo}"


def _raise_memory_http_error(action: str, exc: memory_service.MemoryServiceError) -> None:
    if isinstance(exc, memory_service.MemoryBusyError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Memory is busy with another local Cognee operation. "
                f"Unable to {action} until the current ingest or write finishes."
            ),
        ) from exc

    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=f"Unable to {action} right now because the memory engine reported an error: {exc.detail}",
    ) from exc


@router.post(
    "/recall",
    response_model=RecallResponse,
    responses={409: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
)
async def recall_repo_memory(owner: str, repo: str, request: RecallRequest) -> RecallResponse:
    try:
        result = await memory_service.recall_answer(
            query=request.query,
            dataset_name=_dataset_name(owner, repo),
        )
    except memory_service.MemoryServiceError as exc:
        _raise_memory_http_error("recall from memory", exc)

    return RecallResponse(
        answer=result.answer,
        traversal=result.references or None,
        sources=result.source,
        graph={
            "nodes": result.graph_nodes,
            "edges": result.graph_edges,
        },
        highlighted={
            "node_ids": result.highlighted_node_ids,
            "edge_ids": result.highlighted_edge_ids,
        },
    )


@router.post(
    "/improve",
    response_model=ImproveResponse,
    responses={409: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
)
async def improve_repo_memory(owner: str, repo: str, request: ImproveRequest) -> ImproveResponse:
    try:
        await memory_service.improve_memory(
            feedback=request.feedback,
            dataset_name=_dataset_name(owner, repo),
        )
    except memory_service.MemoryServiceError as exc:
        _raise_memory_http_error("improve memory", exc)

    return ImproveResponse(status="ok")


@router.delete(
    "/memory",
    response_model=ForgetResponse,
    responses={409: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
)
async def forget_repo_memory(owner: str, repo: str) -> ForgetResponse:
    try:
        await memory_service.forget_dataset(dataset_name=_dataset_name(owner, repo))
    except memory_service.MemoryServiceError as exc:
        _raise_memory_http_error("forget repo memory", exc)

    return ForgetResponse(status="ok")
