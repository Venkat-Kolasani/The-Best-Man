from __future__ import annotations

import logging

import httpx
import pytest

from app.services import github_service
from app.services.github_service import GitHubServiceError


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


def _ok_response(request: httpx.Request, json_body: list) -> httpx.Response:
    return httpx.Response(
        200,
        json=json_body,
        headers={"X-RateLimit-Remaining": "100", "X-RateLimit-Reset": "9999999999"},
        request=request,
    )


# ── Error cases ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_commits_raises_on_403(monkeypatch: pytest.MonkeyPatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            text='{"message": "rate limit exceeded"}',
            headers={"X-RateLimit-Remaining": "0"},
            request=request,
        )

    install_mock_client(monkeypatch, handler)

    with pytest.raises(GitHubServiceError) as excinfo:
        await github_service.fetch_commits("acme", "widgets", limit=1)

    assert "forbidden or rate limited (403)" in str(excinfo.value)


@pytest.mark.asyncio
async def test_fetch_pull_requests_raises_on_403(monkeypatch: pytest.MonkeyPatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            text='{"message": "rate limit exceeded"}',
            headers={"X-RateLimit-Remaining": "0"},
            request=request,
        )

    install_mock_client(monkeypatch, handler)

    with pytest.raises(GitHubServiceError) as excinfo:
        await github_service.fetch_pull_requests("acme", "widgets", limit=1)

    assert "forbidden or rate limited (403)" in str(excinfo.value)


@pytest.mark.asyncio
async def test_fetch_commits_raises_on_401(monkeypatch: pytest.MonkeyPatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            text="Bad credentials",
            headers={"X-RateLimit-Remaining": "100"},
            request=request,
        )

    install_mock_client(monkeypatch, handler)

    with pytest.raises(GitHubServiceError) as excinfo:
        await github_service.fetch_commits("acme", "widgets", limit=1)

    assert "unauthorized (401)" in str(excinfo.value)


@pytest.mark.asyncio
async def test_fetch_commits_raises_on_404(monkeypatch: pytest.MonkeyPatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404,
            text="Not Found",
            headers={"X-RateLimit-Remaining": "100"},
            request=request,
        )

    install_mock_client(monkeypatch, handler)

    with pytest.raises(GitHubServiceError) as excinfo:
        await github_service.fetch_commits("acme", "widgets", limit=1)

    assert "repository or resource not found (404)" in str(excinfo.value)


@pytest.mark.asyncio
async def test_fetch_commits_raises_on_500(monkeypatch: pytest.MonkeyPatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            500,
            text="Internal Server Error",
            headers={"X-RateLimit-Remaining": "100"},
            request=request,
        )

    install_mock_client(monkeypatch, handler)

    with pytest.raises(GitHubServiceError) as excinfo:
        await github_service.fetch_commits("acme", "widgets", limit=1)

    assert "GitHub API returned 500" in str(excinfo.value)


# ── Rate limit edge cases ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_rate_limit_non_integer_header_logs_warning(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[],
            headers={"X-RateLimit-Remaining": "not-a-number"},
            request=request,
        )

    install_mock_client(monkeypatch, handler)
    caplog.set_level(logging.WARNING)

    await github_service.fetch_commits("acme", "widgets", limit=1)

    assert "rate limit header was not an integer" in caplog.text
    assert "not-a-number" in caplog.text


@pytest.mark.asyncio
async def test_rate_limit_missing_headers_does_not_warn(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[], request=request)

    install_mock_client(monkeypatch, handler)
    caplog.set_level(logging.WARNING)

    await github_service.fetch_commits("acme", "widgets", limit=1)

    assert "rate limit" not in caplog.text.lower()


@pytest.mark.asyncio
async def test_rate_limit_above_threshold_does_not_warn(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[],
            headers={"X-RateLimit-Remaining": "500", "X-RateLimit-Reset": "9999999999"},
            request=request,
        )

    install_mock_client(monkeypatch, handler)
    caplog.set_level(logging.WARNING)

    await github_service.fetch_commits("acme", "widgets", limit=1)

    assert "rate limit" not in caplog.text.lower()


# ── PR comment variants ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_pull_requests_without_comments(monkeypatch: pytest.MonkeyPatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return _ok_response(
            request,
            [
                {
                    "number": 42,
                    "title": "Silent PR",
                    "body": None,
                    "state": "open",
                    "merged_at": None,
                    "comments": 0,
                    "review_comments": 0,
                }
            ],
        )

    install_mock_client(monkeypatch, handler)

    pull_requests = await github_service.fetch_pull_requests("acme", "widgets", limit=1)

    assert len(pull_requests) == 1
    assert pull_requests[0].number == 42
    assert pull_requests[0].comments == []


@pytest.mark.asyncio
async def test_fetch_pull_requests_with_review_comments(monkeypatch: pytest.MonkeyPatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/pulls"):
            return _ok_response(
                request,
                [
                    {
                        "number": 8,
                        "title": "Review comments only",
                        "body": "desc",
                        "state": "open",
                        "comments": 0,
                        "review_comments": 2,
                        "review_comments_url": (
                            "https://api.github.com/repos/acme/widgets/pulls/8/comments"
                        ),
                    }
                ],
            )

        assert "pulls/8/comments" in request.url.path
        return _ok_response(
            request,
            [
                {
                    "id": 201,
                    "user": {"login": "coder1"},
                    "body": "Nice fix",
                    "created_at": "2025-03-01T00:00:00Z",
                }
            ],
        )

    install_mock_client(monkeypatch, handler)

    pull_requests = await github_service.fetch_pull_requests("acme", "widgets", limit=1)

    assert len(pull_requests) == 1
    assert len(pull_requests[0].comments) == 1
    assert pull_requests[0].comments[0].author == "coder1"


# ── Parser edge cases ────────────────────────────────────────────────────────


def test_parse_commit_minimal_fields():
    result = github_service._parse_commit({"sha": "abc"})
    assert result.sha == "abc"
    assert result.message == ""
    assert result.author is None
    assert result.date is None
    assert result.files_changed == []


def test_parse_commit_nested_none():
    result = github_service._parse_commit(
        {"sha": "abc", "commit": None, "files": None}
    )
    assert result.sha == "abc"
    assert result.message == ""
    assert result.author is None
    assert result.files_changed == []


def test_parse_pr_comment_minimal():
    result = github_service._parse_pr_comment({"body": "hello"})
    assert result.body == "hello"
    assert result.comment_id is None
    assert result.author is None
    assert result.created_at is None


def test_parse_pr_comment_with_id():
    result = github_service._parse_pr_comment({"id": 42, "body": "hello"})
    assert result.comment_id == "42"


# ── Header helper ────────────────────────────────────────────────────────────


def test_build_headers_without_token():
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(github_service.settings, "github_token", "")
    try:
        headers = github_service._build_headers()
        assert headers["Accept"] == "application/vnd.github+json"
        assert headers["User-Agent"] == "the-best-man-github-service"
        assert "Authorization" not in headers
    finally:
        monkeypatch.undo()


# ── Existing tests (retained) ─────────────────────────────────────────────────


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
        return _ok_response(request, payload)

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
            return _ok_response(
                request,
                [
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
            )

        assert request.url.path.endswith("/issues/7/comments")
        return _ok_response(
            request,
            [
                {
                    "user": {"login": "reviewer1"},
                    "body": "Looks good",
                    "created_at": "2025-01-31T00:00:00Z",
                }
            ],
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

        return _ok_response(request, payload)

    install_mock_client(monkeypatch, handler)

    commits = await github_service.fetch_commits("acme", "widgets", limit=101)

    assert len(commits) == 101
    assert commits[0].sha == "a1"
    assert commits[-1].sha == "a101"
    assert seen_pages == ["1", "2"]


@pytest.mark.asyncio
async def test_rate_limit_warning_is_logged(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
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
async def test_auth_header_is_set_when_github_token_exists(monkeypatch: pytest.MonkeyPatch):
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
