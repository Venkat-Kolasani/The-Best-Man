from __future__ import annotations

import asyncio
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.ingestion import IngestionSummary
from app.routers.repos import get_ingestion_service, get_memory_service
from app.services.memory_service import MemoryBusyError, MemoryServiceError


class MockIngestionService:
    MemoryBusyError = MemoryBusyError
    MemoryServiceError = MemoryServiceError

    ingest_repo_raise: type[Exception] | None = None
    add_manual_decision_raise: type[Exception] | None = None

    async def ingest_repo(self, owner: str, repo: str) -> IngestionSummary:
        if self.ingest_repo_raise is not None:
            raise self.ingest_repo_raise
        return IngestionSummary(
            commits_ingested=3,
            prs_ingested=1,
            comments_ingested=5,
            skipped=[],
        )

    async def add_manual_decision(self, owner: str, repo: str, content: str) -> None:
        if self.add_manual_decision_raise is not None:
            raise self.add_manual_decision_raise
        return None


@pytest.fixture()
def client():
    mock = MockIngestionService()
    app.dependency_overrides[get_ingestion_service] = lambda: mock
    app.dependency_overrides[get_memory_service] = lambda: mock
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _poll_job(
    client: TestClient, owner: str, repo: str, job_id: str, max_retries: int = 10
) -> dict[str, Any]:
    for _ in range(max_retries):
        resp = client.get(f"/repos/{owner}/{repo}/ingest/{job_id}")
        if resp.status_code != 200:
            return {"error": f"unexpected status {resp.status_code}", "body": resp.json()}
        data = resp.json()
        if data["status"] in ("done", "failed", "cancelled"):
            return data
        asyncio.sleep(0.01)
    return {"error": "poll timeout"}


class TestStartIngest:
    def test_returns_202_with_job_id(self, client: TestClient) -> None:
        resp = client.post("/repos/owner/repo/ingest")
        assert resp.status_code == 202
        data = resp.json()
        assert data["status"] == "queued"
        assert len(data["job_id"]) > 0

    def test_job_eventually_completes(self, client: TestClient) -> None:
        resp = client.post("/repos/owner/repo/ingest")
        assert resp.status_code == 202
        job_id = resp.json()["job_id"]

        result = _poll_job(client, "owner", "repo", job_id)
        assert result.get("error") is None, result
        assert result["status"] == "done"
        assert result["summary"]["commits_ingested"] == 3
        assert result["summary"]["prs_ingested"] == 1
        assert result["summary"]["comments_ingested"] == 5


class TestGetIngestStatus:
    def test_returns_job_status(self, client: TestClient) -> None:
        resp = client.post("/repos/owner/repo/ingest")
        job_id = resp.json()["job_id"]
        result = _poll_job(client, "owner", "repo", job_id)
        assert result["status"] == "done"

    def test_returns_404_for_missing_job(self, client: TestClient) -> None:
        resp = client.get("/repos/owner/repo/ingest/nonexistent")
        assert resp.status_code == 404

    def test_returns_404_if_owner_repo_mismatch(self, client: TestClient) -> None:
        resp = client.post("/repos/owner/repo/ingest")
        job_id = resp.json()["job_id"]
        resp = client.get(f"/repos/wrong/repo/ingest/{job_id}")
        assert resp.status_code == 404

    def test_shows_failed_status_on_error(self, client: TestClient) -> None:
        mock = app.dependency_overrides[get_ingestion_service]()
        mock.ingest_repo_raise = ValueError("something broke")
        resp = client.post("/repos/owner/repo/ingest")
        assert resp.status_code == 202
        job_id = resp.json()["job_id"]

        result = _poll_job(client, "owner", "repo", job_id)
        assert result["status"] == "failed"
        assert "something broke" in result["error"]
        mock.ingest_repo_raise = None


class TestCancelIngestion:
    def test_cancel_queued_job(self, client: TestClient) -> None:
        resp = client.post("/repos/owner/repo/ingest")
        assert resp.status_code == 202
        job_id = resp.json()["job_id"]

        resp = client.post(f"/repos/owner/repo/ingest/{job_id}/cancel")
        assert resp.status_code == 200
        assert resp.json()["job_id"] == job_id

    def test_cancel_returns_404_for_missing_job(self, client: TestClient) -> None:
        resp = client.post("/repos/owner/repo/ingest/nonexistent/cancel")
        assert resp.status_code == 404

    def test_cancel_returns_404_for_mismatch(self, client: TestClient) -> None:
        resp = client.post("/repos/owner/repo/ingest")
        job_id = resp.json()["job_id"]
        resp = client.post(f"/repos/wrong/repo/ingest/{job_id}/cancel")
        assert resp.status_code == 404


class TestManualDecision:
    def test_logs_decision(self, client: TestClient) -> None:
        resp = client.post(
            "/repos/owner/repo/decisions",
            json={"content": "Chose SQLite for MVP"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_rejects_empty_content(self, client: TestClient) -> None:
        resp = client.post(
            "/repos/owner/repo/decisions",
            json={"content": ""},
        )
        assert resp.status_code == 422

    def test_returns_409_on_memory_busy(self, client: TestClient) -> None:
        mock = app.dependency_overrides[get_memory_service]()
        mock.add_manual_decision_raise = mock.MemoryBusyError("remember", "busy")
        resp = client.post(
            "/repos/owner/repo/decisions",
            json={"content": "Should conflict"},
        )
        assert resp.status_code == 409
        mock.add_manual_decision_raise = None

    def test_returns_503_on_memory_error(self, client: TestClient) -> None:
        mock = app.dependency_overrides[get_memory_service]()
        mock.add_manual_decision_raise = mock.MemoryServiceError("remember", "engine down")
        resp = client.post(
            "/repos/owner/repo/decisions",
            json={"content": "Should fail"},
        )
        assert resp.status_code == 503
        mock.add_manual_decision_raise = None
