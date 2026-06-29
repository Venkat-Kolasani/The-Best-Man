from __future__ import annotations

import logging
from uuid import uuid4

from app.models.github import CommitData, PRComment, PRData
from app.models.ingestion import IngestionSummary
from app.services import github_service, memory_service

logger = logging.getLogger(__name__)


def _dataset_name(owner: str, repo: str) -> str:
    return f"repo:{owner}/{repo}"


def _normalize_text(value: str | None, fallback: str) -> str:
    if value is None:
        return fallback

    stripped = value.strip()
    return stripped or fallback


def _format_commit_text(owner: str, repo: str, commit: CommitData) -> str:
    files_changed = ", ".join(commit.files_changed) if commit.files_changed else "Not provided."
    return (
        f"Repository {owner}/{repo} recorded commit {commit.sha}. "
        f"The author was {_normalize_text(commit.author, 'unknown')} and the commit date was "
        f"{_normalize_text(commit.date, 'unknown')}. "
        f"The commit message was: {_normalize_text(commit.message, 'No commit message provided.')}\n\n"
        f"Files changed: {files_changed}"
    )


def _format_pr_text(owner: str, repo: str, pr: PRData) -> str:
    return (
        f"Repository {owner}/{repo} has pull request #{pr.number} titled "
        f"\"{_normalize_text(pr.title, 'Untitled pull request')}\". "
        f"The pull request state is {_normalize_text(pr.state, 'unknown')} and it was merged at "
        f"{_normalize_text(pr.merged_at, 'not merged')}. "
        f"Pull request description: {_normalize_text(pr.body, 'No pull request description provided.')}"
    )


def _build_comment_source_id(pr: PRData, comment: PRComment, index: int) -> str:
    if comment.comment_id:
        return f"{pr.number}:{comment.comment_id}"
    return f"{pr.number}:{index}:{_normalize_text(comment.created_at, 'unknown')}"


def _format_pr_comment_text(owner: str, repo: str, pr: PRData, comment: PRComment) -> str:
    return (
        f"Repository {owner}/{repo} has a comment on pull request #{pr.number}, "
        f"\"{_normalize_text(pr.title, 'Untitled pull request')}\". "
        f"The comment author was {_normalize_text(comment.author, 'unknown')} and it was created at "
        f"{_normalize_text(comment.created_at, 'unknown')}. "
        f"Comment text: {_normalize_text(comment.body, 'No comment body provided.')}"
    )


def _format_manual_decision_text(owner: str, repo: str, content: str) -> str:
    return (
        f"Manual decision log entry for repository {owner}/{repo}. "
        f"Decision details: {_normalize_text(content, 'No decision details provided.')}"
    )


def _skip_entry(source_type: str, source_id: str, reason: str) -> dict[str, str]:
    return {
        "source_type": source_type,
        "source_id": source_id,
        "reason": reason,
    }


async def ingest_repo(owner: str, repo: str) -> IngestionSummary:
    dataset_name = _dataset_name(owner, repo)
    logger.warning(
        "Repo ingestion for %s may re-submit previously seen text; Cognee content hashing should "
        "dedupe identical entries.",
        dataset_name,
    )

    commits = await github_service.fetch_commits(owner, repo)
    pull_requests = await github_service.fetch_pull_requests(owner, repo)

    summary = IngestionSummary(
        commits_ingested=0,
        prs_ingested=0,
        comments_ingested=0,
    )

    for commit in commits:
        source_id = commit.sha
        try:
            await memory_service.remember_decision(
                content=_format_commit_text(owner, repo, commit),
                dataset_name=dataset_name,
                source_type="commit",
                source_id=source_id,
            )
            summary.commits_ingested += 1
        except Exception as exc:
            summary.skipped.append(_skip_entry("commit", source_id, str(exc)))

    for pr in pull_requests:
        pr_source_id = f"{pr.number}:summary"
        try:
            await memory_service.remember_decision(
                content=_format_pr_text(owner, repo, pr),
                dataset_name=dataset_name,
                source_type="pr_comment",
                source_id=pr_source_id,
            )
            summary.prs_ingested += 1
        except Exception as exc:
            summary.skipped.append(_skip_entry("pr_comment", pr_source_id, str(exc)))

        for index, comment in enumerate(pr.comments):
            comment_source_id = _build_comment_source_id(pr, comment, index)
            try:
                await memory_service.remember_decision(
                    content=_format_pr_comment_text(owner, repo, pr, comment),
                    dataset_name=dataset_name,
                    source_type="pr_comment",
                    source_id=comment_source_id,
                )
                summary.comments_ingested += 1
            except Exception as exc:
                summary.skipped.append(_skip_entry("pr_comment", comment_source_id, str(exc)))

    return summary


async def add_manual_decision(owner: str, repo: str, content: str) -> None:
    await memory_service.remember_decision(
        content=_format_manual_decision_text(owner, repo, content),
        dataset_name=_dataset_name(owner, repo),
        source_type="manual_log",
        source_id=str(uuid4()),
    )
