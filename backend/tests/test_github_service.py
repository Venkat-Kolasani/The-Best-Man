from __future__ import annotations

import logging

import httpx
import pytest

from app.services import github_service


class MockAsyncClient:
    def __init__(self, *, headers=None, timeout=None, transport=None):
        self.headers = headers or {}
        self.timeout = timeout
        self._transport = transport
        self.requests: list[httpx.Request] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def get(self, url, params=None):
        request = httpx.Request("GET", url, params=params, headers=self.headers)
        self.requests.append(request)
        response = await self._transport.handle_async_request(request)
        return response


def install_mock_client(monkeypatch: pytest.MonkeyPatch, handler):
    client_holder: dict[str, MockAsyncClient] = {}

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        return handler(request)

    transport = httpx.MockTransport(mock_handler)

    def factory(*, headers=None, timeout=None):
        client = MockAsyncClient(headers=headers, timeout=timeout, transport=transport)
        client_holder["client"] = client
        return client

    monkeypatch.setattr(github_service.httpx, "AsyncClient", factory)
    return client_holder


@pytest.mark.asyncio
async def test_fetch_commits_parses_commit_data(monkeypatch: pytest.MonkeyPatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["page"] == "1"
        payload = [
            {
                "sha": "abc123",
                "commit": {
                    "message": "Initial commit",
                    "author": {"name": "Alice", "date": "2025-01-02T03:04:05Z"},
                },
                "author": {"login": "alice"},
            },
            {
                "sha": "def456",
                "commit": {
                    "message": "Add tests",
                    "author": {"name": "Bob", "date": "2025-01-03T03:04:05Z"},
                },
                "files": [{"filename": "app.py"}, {"filename": "tests/test_app.py"}],
            },
        ]
        return httpx.Response(
            200,
            json=payload,
            headers={"X-RateLimit-Remaining": "100", "X-RateLimit-Reset": "9999999999"},
            request=request,
        )

    install_mock_client(monkeypatch, handler)

    commits = await github_service.fetch_commits("acme", "widgets", limit=2)

    assert [commit.sha for commit in commits] == ["abc123", "def456"]
    assert commits[0].author == "alice"
    assert commits[0].date == "2025-01-02T03:04:05Z"
    assert commits[0].files_changed == []
    assert commits[1].files_changed == ["app.py", "tests/test_app.py"]


@pytest.mark.asyncio
async def test_fetch_pull_requests_parses_prs_with_comments(monkeypatch: pytest.MonkeyPatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/pulls"):
            return httpx.Response(
                200,
                json=[
                    {
                        "number": 7,
                        "title": "Improve parser",
                        "body": "Details",
                        "state": "closed",
                        "merged_at": "2025-02-01T00:00:00Z",
                        "comments": 1,
                        "review_comments": 0,
                        "comments_url": "https://api.github.com/repos/acme/widgets/issues/7/comments",
                    }
                ],
                headers={"X-RateLimit-Remaining": "100", "X-RateLimit-Reset": "9999999999"},
                request=request,
            )

        assert request.url.path.endswith("/issues/7/comments")
        return httpx.Response(
            200,
            json=[
                {
                    "user": {"login": "reviewer1"},
                    "body": "Looks good",
                    "created_at": "2025-01-31T00:00:00Z",
                }
            ],
            headers={"X-RateLimit-Remaining": "100", "X-RateLimit-Reset": "9999999999"},
            request=request,
        )

    install_mock_client(monkeypatch, handler)

    pull_requests = await github_service.fetch_pull_requests("acme", "widgets", limit=1)

    assert len(pull_requests) == 1
    pr = pull_requests[0]
    assert pr.number == 7
    assert pr.title == "Improve parser"
    assert pr.comments[0].author == "reviewer1"
    assert pr.comments[0].body == "Looks good"


@pytest.mark.asyncio
async def test_fetch_commits_respects_limit_across_pages(monkeypatch: pytest.MonkeyPatch):
    seen_pages: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_pages.append(request.url.params["page"])
        page = request.url.params["page"]
        if page == "1":
            payload = [
                {"sha": f"a{index}", "commit": {"message": f"m{index}", "author": {}}}
                for index in range(1, 101)
            ]
        else:
            payload = [
                {"sha": "a101", "commit": {"message": "m101", "author": {}}},
                {"sha": "a102", "commit": {"message": "m102", "author": {}}},
            ]

        return httpx.Response(
            200,
            json=payload,
            headers={"X-RateLimit-Remaining": "100", "X-RateLimit-Reset": "9999999999"},
            request=request,
        )

    install_mock_client(monkeypatch, handler)

    commits = await github_service.fetch_commits("acme", "widgets", limit=101)

    assert len(commits) == 101
    assert commits[0].sha == "a1"
    assert commits[-1].sha == "a101"
    assert seen_pages == ["1", "2"]


@pytest.mark.asyncio
async def test_rate_limit_warning_is_logged(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[],
            headers={"X-RateLimit-Remaining": "19", "X-RateLimit-Reset": "1700000000"},
            request=request,
        )

    install_mock_client(monkeypatch, handler)
    caplog.set_level(logging.WARNING)

    await github_service.fetch_commits("acme", "widgets", limit=1)

    assert "GitHub rate limit running low" in caplog.text
    assert "remaining=19" in caplog.text


@pytest.mark.asyncio
async def test_auth_header_is_set_when_github_token_exists(
    monkeypatch: pytest.MonkeyPatch,
):
    client_holder = {}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[],
            headers={"X-RateLimit-Remaining": "100", "X-RateLimit-Reset": "9999999999"},
            request=request,
        )

    client_holder = install_mock_client(monkeypatch, handler)
    monkeypatch.setattr(github_service.settings, "github_token", "test-token")

    await github_service.fetch_commits("acme", "widgets", limit=1)

    assert client_holder["client"].headers["Authorization"] == "Bearer test-token"
