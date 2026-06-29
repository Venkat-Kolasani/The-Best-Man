from __future__ import annotations

from fastapi import APIRouter

from app.models.api import (
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


@router.post("/recall", response_model=RecallResponse)
async def recall_repo_memory(owner: str, repo: str, request: RecallRequest) -> RecallResponse:
    result = await memory_service.recall_answer(
        query=request.query,
        dataset_name=_dataset_name(owner, repo),
    )
    return RecallResponse(
        answer=result.answer,
        traversal=result.references or None,
        sources=result.source,
    )


@router.post("/improve", response_model=ImproveResponse)
async def improve_repo_memory(owner: str, repo: str, request: ImproveRequest) -> ImproveResponse:
    await memory_service.improve_memory(
        feedback=request.feedback,
        dataset_name=_dataset_name(owner, repo),
    )
    return ImproveResponse(status="ok")


@router.delete("/memory", response_model=ForgetResponse)
async def forget_repo_memory(owner: str, repo: str) -> ForgetResponse:
    await memory_service.forget_dataset(dataset_name=_dataset_name(owner, repo))
    return ForgetResponse(status="ok")
