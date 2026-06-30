from __future__ import annotations

import asyncio
import logging
import os
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException, status

from app.models.api import (
    ErrorResponse,
    IngestJobResponse,
    IngestJobStatusResponse,
    ManualDecisionRequest,
    ManualDecisionResponse,
)
from app.services import ingestion_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/repos/{owner}/{repo}", tags=["repos"])

# Hackathon demo only: this in-memory job store is lost on restart and is not
# safe for production multi-worker deployments because each worker would keep
# its own isolated copy of job state.
_INGEST_JOBS: dict[str, dict[str, object | None]] = {}
_INGEST_TIMEOUT_SECONDS = int(os.getenv("INGEST_JOB_TIMEOUT_SECONDS", "900"))


async def _run_ingestion_job(job_id: str, owner: str, repo: str) -> None:
    _INGEST_JOBS[job_id] = {
        "status": "running",
        "summary": None,
        "error": None,
        "owner": owner,
        "repo": repo,
    }
    try:
        summary = await asyncio.wait_for(
            ingestion_service.ingest_repo(owner, repo),
            timeout=_INGEST_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        message = (
            f"Ingestion timed out after {_INGEST_TIMEOUT_SECONDS} seconds. "
            "This demo job was marked failed after extended upstream retries or slow processing."
        )
        logger.warning(
            "Repository ingestion timed out for %s/%s (job_id=%s): %s",
            owner,
            repo,
            job_id,
            message,
        )
        _INGEST_JOBS[job_id] = {
            "status": "failed",
            "summary": None,
            "error": message,
            "owner": owner,
            "repo": repo,
        }
        return
    except Exception as exc:
        logger.exception("Repository ingestion failed for %s/%s (job_id=%s)", owner, repo, job_id)
        _INGEST_JOBS[job_id] = {
            "status": "failed",
            "summary": None,
            "error": str(exc),
            "owner": owner,
            "repo": repo,
        }
        return

    _INGEST_JOBS[job_id] = {
        "status": "done",
        "summary": summary,
        "error": None,
        "owner": owner,
        "repo": repo,
    }


@router.post(
    "/ingest",
    response_model=IngestJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={404: {"model": ErrorResponse}},
)
async def start_ingestion(
    owner: str,
    repo: str,
    background_tasks: BackgroundTasks,
) -> IngestJobResponse:
    job_id = str(uuid4())
    _INGEST_JOBS[job_id] = {
        "status": "queued",
        "summary": None,
        "error": None,
        "owner": owner,
        "repo": repo,
    }
    background_tasks.add_task(_run_ingestion_job, job_id, owner, repo)
    return IngestJobResponse(job_id=job_id, status="queued")


@router.get(
    "/ingest/{job_id}",
    response_model=IngestJobStatusResponse,
    responses={404: {"model": ErrorResponse}},
)
async def get_ingestion_status(owner: str, repo: str, job_id: str) -> IngestJobStatusResponse:
    job = _INGEST_JOBS.get(job_id)
    if job is None or job.get("owner") != owner or job.get("repo") != repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ingestion job '{job_id}' was not found for {owner}/{repo}.",
        )

    summary = job.get("summary")
    return IngestJobStatusResponse(
        job_id=job_id,
        status=str(job["status"]),
        summary=summary if summary is None else summary,
        error=job.get("error") if isinstance(job.get("error"), str) else None,
    )


@router.post(
    "/decisions",
    response_model=ManualDecisionResponse,
)
async def add_manual_decision(
    owner: str,
    repo: str,
    request: ManualDecisionRequest,
) -> ManualDecisionResponse:
    await ingestion_service.add_manual_decision(owner, repo, request.content)
    return ManualDecisionResponse(status="ok", source_id=None)
