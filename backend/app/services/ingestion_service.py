from __future__ import annotations

import logging
import os
from uuid import uuid4

from app.models.github import CommitData, PRComment, PRData
from app.models.ingestion import IngestionSummary
from app.services import github_service, memory_service

logger = logging.getLogger(__name__)
_INGEST_BATCH_SIZE = int(os.getenv("INGEST_BATCH_SIZE", "20"))


def _dataset_name(owner: str, repo: str) -> str:
    return f"repo:{owner}/{repo}"


def _normalize_text(value: str | None, fallback: str) -> str:
    if value is None:
        return fallback

    stripped = value.strip()
    return stripped or fallback


def _format_commit_text(owner: str, repo: str, commit: CommitData) -> str:
    author = _normalize_text(commit.author, "an unknown author")
    date = _normalize_text(commit.date, "an unknown date")
    message = _normalize_text(commit.message, "make an undocumented change")
    text = f"On {date}, {author} committed {commit.sha} in {owner}/{repo} to {message}."
    if commit.files_changed:
        text += f" The change touched {', '.join(commit.files_changed)}."
    else:
        text += " The changed files were not included in the GitHub response."
    return text


def _format_pr_text(owner: str, repo: str, pr: PRData) -> str:
    title = _normalize_text(pr.title, "Untitled pull request")
    body = _normalize_text(pr.body, "No pull request description was provided.")
    state = _normalize_text(pr.state, "unknown")
    outcome = (
        f"It was merged on {pr.merged_at}."
        if pr.merged_at
        else "It has not been merged."
    )
    return (
        f"In {owner}/{repo}, PR #{pr.number}, \"{title}\", proposed the following change: {body} "
        f"The pull request is currently {state}. {outcome}"
    )


def _build_comment_source_id(pr: PRData, comment: PRComment, index: int) -> str:
    if comment.comment_id:
        return f"{pr.number}:{comment.comment_id}"
    return f"{pr.number}:{index}:{_normalize_text(comment.created_at, 'unknown')}"


def _format_pr_comment_text(owner: str, repo: str, pr: PRData, comment: PRComment) -> str:
    author = _normalize_text(comment.author, "an unknown participant")
    created_at = _normalize_text(comment.created_at, "an unknown time")
    body = _normalize_text(comment.body, "No comment body was provided.")
    title = _normalize_text(pr.title, "Untitled pull request")
    return (
        f"In the discussion for {owner}/{repo} PR #{pr.number}, \"{title}\", {author} noted on "
        f"{created_at}: {body}"
    )


def _format_manual_decision_text(owner: str, repo: str, content: str) -> str:
    return f"A manual decision was recorded for {owner}/{repo}: {_normalize_text(content, 'No decision details were provided.')}"


def _skip_entry(source_type: str, source_id: str, reason: str) -> dict[str, str]:
    return {
        "source_type": source_type,
        "source_id": source_id,
        "reason": reason,
    }


def _batched_entries(
    entries: list[memory_service.RememberEntry],
    batch_size: int,
) -> list[list[memory_service.RememberEntry]]:
    if batch_size < 1:
        batch_size = 1
    return [entries[index : index + batch_size] for index in range(0, len(entries), batch_size)]


async def ingest_repo(owner: str, repo: str) -> IngestionSummary:
    dataset_name = _dataset_name(owner, repo)
    logger.warning(
        "Repo ingestion for %s may re-submit previously seen text; Cognee content hashing now "
        "dedupes at the batch-text level. Source-level dedup can be added later if needed.",
        dataset_name,
    )

    commits = await github_service.fetch_commits(owner, repo)
    pull_requests = await github_service.fetch_pull_requests(owner, repo)

    summary = IngestionSummary(
        commits_ingested=0,
        prs_ingested=0,
        comments_ingested=0,
    )

    # Batch entries so bulk repo ingestion triggers far fewer Cognee
    # add/cognify/improve pipeline runs, which reduces repeated embedding and
    # graph extraction pressure on Gemini quotas.
    entries_with_meta: list[tuple[str, str, memory_service.RememberEntry]] = []

    for commit in commits:
        source_id = commit.sha
        entries_with_meta.append(
            (
                "commit",
                source_id,
                memory_service.RememberEntry(
                    source_type="commit",
                    source_id=source_id,
                    content=_format_commit_text(owner, repo, commit),
                ),
            )
        )

    for pr in pull_requests:
        pr_source_id = f"{pr.number}:summary"
        entries_with_meta.append(
            (
                "pr_comment",
                pr_source_id,
                memory_service.RememberEntry(
                    source_type="pr_comment",
                    source_id=pr_source_id,
                    content=_format_pr_text(owner, repo, pr),
                ),
            )
        )

        for index, comment in enumerate(pr.comments):
            comment_source_id = _build_comment_source_id(pr, comment, index)
            entries_with_meta.append(
                (
                    "pr_comment",
                    comment_source_id,
                    memory_service.RememberEntry(
                        source_type="pr_comment",
                        source_id=comment_source_id,
                        content=_format_pr_comment_text(owner, repo, pr, comment),
                    ),
                )
            )

    for batch in _batched_entries(
        [entry for _, _, entry in entries_with_meta],
        _INGEST_BATCH_SIZE,
    ):
        batch_items = entries_with_meta[: len(batch)]
        entries_with_meta = entries_with_meta[len(batch) :]

        try:
            await memory_service.remember_decision_batch(
                entries=batch,
                dataset_name=dataset_name,
            )
            for source_type, _source_id, _entry in batch_items:
                if source_type == "commit":
                    summary.commits_ingested += 1
                elif _source_id.endswith(":summary"):
                    summary.prs_ingested += 1
                else:
                    summary.comments_ingested += 1
        except Exception as exc:
            reason = str(exc)
            for source_type, source_id, _entry in batch_items:
                summary.skipped.append(_skip_entry(source_type, source_id, reason))

    return summary


async def add_manual_decision(owner: str, repo: str, content: str) -> None:
    await memory_service.remember_decision(
        content=_format_manual_decision_text(owner, repo, content),
        dataset_name=_dataset_name(owner, repo),
        source_type="manual_log",
        source_id=str(uuid4()),
    )
