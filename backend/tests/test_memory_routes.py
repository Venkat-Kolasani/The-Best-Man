from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers.memory import get_memory_service
from app.services.memory_service import (
    MemoryBusyError,
    MemoryServiceError,
    RecallResult,
)


def _make_recall_result(
    answer: str = "Use Postgres",
    source: str = "graph",
) -> RecallResult:
    return RecallResult(
        answer=answer,
        source=source,
        references=[{"node": "abc"}],
        graph_nodes=[{"id": "n1", "label": "Decision", "type": "Node", "properties": {}}],
        graph_edges=[{"id": "e1", "source": "n1", "target": "n2", "label": "leads_to"}],
        highlighted_node_ids=["n1"],
        highlighted_edge_ids=["e1"],
    )


class MockMemoryService:
    MemoryServiceError = MemoryServiceError
    MemoryBusyError = MemoryBusyError

    recall_result: RecallResult = _make_recall_result()
    recall_raise: type[Exception] | None = None
    improve_raise: type[Exception] | None = None
    forget_raise: type[Exception] | None = None

    async def recall_answer(self, query: str, dataset_name: str) -> RecallResult:
        if self.recall_raise is not None:
            raise self.recall_raise
        return self.recall_result

    async def improve_memory(self, feedback: str, dataset_name: str) -> None:
        if self.improve_raise is not None:
            raise self.improve_raise
        return None

    async def forget_dataset(self, dataset_name: str) -> None:
        if self.forget_raise is not None:
            raise self.forget_raise
        return None


@pytest.fixture()
def client():
    mock = MockMemoryService()
    app.dependency_overrides[get_memory_service] = lambda: mock
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class TestRecall:
    def test_returns_answer(self, client: TestClient) -> None:
        resp = client.post(
            "/repos/owner/repo/recall",
            json={"query": "Why Postgres?"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["answer"] == "Use Postgres"
        assert data["traversal"] == [{"node": "abc"}]
        assert data["sources"] == "graph"
        assert data["graph"]["nodes"] == [
            {"id": "n1", "label": "Decision", "type": "Node", "properties": {}}
        ]
        assert data["graph"]["edges"] == [
            {"id": "e1", "source": "n1", "target": "n2", "label": "leads_to"}
        ]
        assert data["highlighted"]["node_ids"] == ["n1"]
        assert data["highlighted"]["edge_ids"] == ["e1"]

    def test_rejects_empty_query(self, client: TestClient) -> None:
        resp = client.post(
            "/repos/owner/repo/recall",
            json={"query": ""},
        )
        assert resp.status_code == 422

    def test_returns_409_on_busy(self, client: TestClient) -> None:
        mock = app.dependency_overrides[get_memory_service]()
        mock.recall_raise = mock.MemoryBusyError("recall", "busy")
        resp = client.post(
            "/repos/owner/repo/recall",
            json={"query": "Why?"},
        )
        assert resp.status_code == 409
        mock.recall_raise = None

    def test_returns_503_on_service_error(self, client: TestClient) -> None:
        mock = app.dependency_overrides[get_memory_service]()
        mock.recall_raise = mock.MemoryServiceError("recall", "engine down")
        resp = client.post(
            "/repos/owner/repo/recall",
            json={"query": "Why?"},
        )
        assert resp.status_code == 503
        mock.recall_raise = None

    def test_empty_result_returns_empty_answer(self, client: TestClient) -> None:
        mock = app.dependency_overrides[get_memory_service]()
        mock.recall_result = _make_recall_result(answer="", source="empty")
        resp = client.post(
            "/repos/owner/repo/recall",
            json={"query": "Nothing"},
        )
        assert resp.status_code == 200
        assert resp.json()["answer"] == ""
        assert resp.json()["sources"] == "empty"
        mock.recall_result = _make_recall_result()


class TestImprove:
    def test_improves_memory(self, client: TestClient) -> None:
        resp = client.post(
            "/repos/owner/repo/improve",
            json={"feedback": "Great decision"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_rejects_empty_feedback(self, client: TestClient) -> None:
        resp = client.post(
            "/repos/owner/repo/improve",
            json={"feedback": ""},
        )
        assert resp.status_code == 422

    def test_returns_409_on_busy(self, client: TestClient) -> None:
        mock = app.dependency_overrides[get_memory_service]()

        mock.improve_raise = mock.MemoryBusyError("improve", "busy")
        resp = client.post(
            "/repos/owner/repo/improve",
            json={"feedback": "Good"},
        )
        assert resp.status_code == 409
        mock.improve_raise = None

    def test_returns_503_on_service_error(self, client: TestClient) -> None:
        mock = app.dependency_overrides[get_memory_service]()

        mock.improve_raise = mock.MemoryServiceError("improve", "engine down")
        resp = client.post(
            "/repos/owner/repo/improve",
            json={"feedback": "Good"},
        )
        assert resp.status_code == 503
        mock.improve_raise = None


class TestForget:
    def test_forgets_dataset(self, client: TestClient) -> None:
        resp = client.delete("/repos/owner/repo/memory")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_returns_409_on_busy(self, client: TestClient) -> None:
        mock = app.dependency_overrides[get_memory_service]()

        mock.forget_raise = mock.MemoryBusyError("forget", "busy")
        resp = client.delete("/repos/owner/repo/memory")
        assert resp.status_code == 409
        mock.forget_raise = None

    def test_returns_503_on_service_error(self, client: TestClient) -> None:
        mock = app.dependency_overrides[get_memory_service]()

        mock.forget_raise = mock.MemoryServiceError("forget", "engine down")
        resp = client.delete("/repos/owner/repo/memory")
        assert resp.status_code == 503
        mock.forget_raise = None
