from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

import httpx

from app.config import settings
from app.models.github import CommitData, PRComment, PRData

logger = logging.getLogger(__name__)

_GITHUB_API_BASE = "https://api.github.com"
_RATE_LIMIT_WARNING_THRESHOLD = 20


class GitHubServiceError(Exception):
    """Raised when a GitHub API request fails with useful context."""


def _build_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "the-best-man-github-service",
    }
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"
    return headers


def _log_rate_limit(response: httpx.Response) -> None:
    remaining_value = response.headers.get("X-RateLimit-Remaining")
    reset_value = response.headers.get("X-RateLimit-Reset")
    if remaining_value is None:
        return

    try:
        remaining = int(remaining_value)
    except ValueError:
        logger.warning("GitHub rate limit header was not an integer: %s", remaining_value)
        return

    if remaining >= _RATE_LIMIT_WARNING_THRESHOLD:
        return

    logger.warning(
        "GitHub rate limit running low for %s: remaining=%s reset=%s",
        response.request.url,
        remaining,
        reset_value or "unknown",
    )


def _raise_github_error(response: httpx.Response, context: str) -> None:
    status = response.status_code
    detail = response.text.strip() or "No response body."

    if status == 401:
        raise GitHubServiceError(f"{context}: unauthorized (401). Check GITHUB_TOKEN.")
    if status == 403:
        raise GitHubServiceError(f"{context}: forbidden or rate limited (403). {detail}")
    if status == 404:
        raise GitHubServiceError(f"{context}: repository or resource not found (404).")

    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise GitHubServiceError(f"{context}: GitHub API returned {status}. {detail}") from exc


async def _get_json(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    context: str,
) -> Any:
    response = await client.get(url, params=params)
    _log_rate_limit(response)
    if response.is_error:
        _raise_github_error(response, context)
    return response.json()


def _parse_commit(item: dict[str, Any]) -> CommitData:
    commit_payload = item.get("commit") or {}
    author_payload = commit_payload.get("author") or {}
    message = commit_payload.get("message") or ""
    files_payload = item.get("files") or []
    files_changed = [
        file_item.get("filename")
        for file_item in files_payload
        if isinstance(file_item, dict) and file_item.get("filename")
    ]

    return CommitData(
        sha=item.get("sha") or "",
        message=message,
        author=(item.get("author") or {}).get("login") or author_payload.get("name"),
        date=author_payload.get("date"),
        files_changed=files_changed,
    )


def _parse_pr_comment(item: dict[str, Any]) -> PRComment:
    return PRComment(
        comment_id=str(item["id"]) if item.get("id") is not None else None,
        author=(item.get("user") or {}).get("login"),
        body=item.get("body") or "",
        created_at=item.get("created_at"),
    )


def _parse_pr(item: dict[str, Any], comments: Sequence[PRComment]) -> PRData:
    return PRData(
        number=item.get("number") or 0,
        title=item.get("title") or "",
        body=item.get("body"),
        state=item.get("state") or "",
        merged_at=item.get("merged_at"),
        comments=list(comments),
    )


async def fetch_commits(owner: str, repo: str, limit: int = 200) -> list[CommitData]:
    commits: list[CommitData] = []
    per_page = min(100, max(limit, 1))
    page = 1

    async with httpx.AsyncClient(headers=_build_headers(), timeout=30.0) as client:
        while len(commits) < limit:
            payload = await _get_json(
                client,
                f"{_GITHUB_API_BASE}/repos/{owner}/{repo}/commits",
                params={"per_page": per_page, "page": page},
                context=f"Fetching commits for {owner}/{repo}",
            )
            if not isinstance(payload, list) or not payload:
                break

            remaining_slots = limit - len(commits)
            commits.extend(_parse_commit(item) for item in payload[:remaining_slots])

            if len(payload) < per_page:
                break
            page += 1

    return commits


async def _fetch_pr_comments(client: httpx.AsyncClient, pr_item: dict[str, Any]) -> list[PRComment]:
    issue_comment_count = pr_item.get("comments") or 0
    review_comment_count = pr_item.get("review_comments") or 0

    if issue_comment_count > 0 and pr_item.get("comments_url"):
        payload = await _get_json(
            client,
            pr_item["comments_url"],
            params={"per_page": min(issue_comment_count, 100)},
            context=f"Fetching issue comments for PR #{pr_item.get('number')}",
        )
        return [_parse_pr_comment(item) for item in payload if isinstance(item, dict)]

    if review_comment_count > 0 and pr_item.get("review_comments_url"):
        payload = await _get_json(
            client,
            pr_item["review_comments_url"],
            params={"per_page": min(review_comment_count, 100)},
            context=f"Fetching review comments for PR #{pr_item.get('number')}",
        )
        return [_parse_pr_comment(item) for item in payload if isinstance(item, dict)]

    return []


async def fetch_pull_requests(owner: str, repo: str, limit: int = 100) -> list[PRData]:
    pull_requests: list[PRData] = []
    per_page = min(100, max(limit, 1))
    page = 1

    async with httpx.AsyncClient(headers=_build_headers(), timeout=30.0) as client:
        while len(pull_requests) < limit:
            payload = await _get_json(
                client,
                f"{_GITHUB_API_BASE}/repos/{owner}/{repo}/pulls",
                params={"state": "all", "per_page": per_page, "page": page},
                context=f"Fetching pull requests for {owner}/{repo}",
            )
            if not isinstance(payload, list) or not payload:
                break

            remaining_slots = limit - len(pull_requests)
            page_items = payload[:remaining_slots]

            for item in page_items:
                comments = await _fetch_pr_comments(client, item)
                pull_requests.append(_parse_pr(item, comments))

            if len(payload) < per_page:
                break
            page += 1

    return pull_requests
