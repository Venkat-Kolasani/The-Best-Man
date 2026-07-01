from __future__ import annotations

import pytest

from app.models.github import CommitData, PRComment, PRData
from app.services import ingestion_service
from app.services.memory_service import RememberEntry


def _fake_commit(sha: str, message: str = "fix", files: list[str] | None = None) -> CommitData:
    return CommitData(
        sha=sha, message=message, author="dev1", date="2025-01-01", files_changed=files or []
    )


def _fake_pr(number: int, comments: list[PRComment] | None = None) -> PRData:
    return PRData(
        number=number,
        title=f"PR #{number}",
        body="desc",
        state="open",
        comments=comments or [],
    )


def _fake_comment(comment_id: str, body: str = "nice") -> PRComment:
    return PRComment(comment_id=comment_id, author="reviewer", body=body, created_at="2025-01-02")


# ── Success path ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ingest_repo_counts_and_batches(monkeypatch: pytest.MonkeyPatch):
    commits = [
        _fake_commit("c001", "Add auth"),
        _fake_commit("c002", "Fix bug", files=["app.py"]),
    ]
    pull_requests = [
        _fake_pr(1, comments=[_fake_comment("101"), _fake_comment("102")]),
    ]

    async def fake_fetch_commits(*a, **kw):
        return commits

    async def fake_fetch_prs(*a, **kw):
        return pull_requests

    monkeypatch.setattr(ingestion_service.github_service, "fetch_commits", fake_fetch_commits)
    monkeypatch.setattr(ingestion_service.github_service, "fetch_pull_requests", fake_fetch_prs)

    call_args: list[tuple] = []

    async def _fake_remember_batch(*, entries, dataset_name):
        call_args.append((entries, dataset_name))

    monkeypatch.setattr(
        ingestion_service.memory_service, "remember_decision_batch", _fake_remember_batch
    )
    monkeypatch.setattr(ingestion_service, "_INGEST_BATCH_SIZE", 100)

    summary = await ingestion_service.ingest_repo("acme", "widgets")

    assert summary.commits_ingested == 2
    assert summary.prs_ingested == 1
    assert summary.comments_ingested == 2
    assert summary.skipped == []

    # One batch call for all 5 entries (2 commits + 1 PR summary + 2 comments)
    assert len(call_args) == 1
    (entries, dataset_name) = call_args[0]
    assert dataset_name == "repo:acme/widgets"
    assert len(entries) == 5
    assert entries[0].source_type == "commit"
    assert entries[0].source_id == "c001"
    assert entries[1].source_type == "commit"
    assert entries[1].source_id == "c002"
    assert entries[2].source_type == "pr_comment"
    assert entries[2].source_id == "1:summary"


@pytest.mark.asyncio
async def test_ingest_repo_multiple_batches(monkeypatch: pytest.MonkeyPatch):
    commits = [_fake_commit(f"c{i:03d}") for i in range(5)]
    pull_requests = []

    async def fake_fetch_commits(*a, **kw):
        return commits

    async def fake_fetch_prs(*a, **kw):
        return pull_requests

    monkeypatch.setattr(ingestion_service.github_service, "fetch_commits", fake_fetch_commits)
    monkeypatch.setattr(ingestion_service.github_service, "fetch_pull_requests", fake_fetch_prs)

    call_args: list[tuple] = []

    async def _fake_remember_batch(*, entries, dataset_name):
        call_args.append((entries, dataset_name))

    monkeypatch.setattr(
        ingestion_service.memory_service, "remember_decision_batch", _fake_remember_batch
    )
    monkeypatch.setattr(ingestion_service, "_INGEST_BATCH_SIZE", 2)

    summary = await ingestion_service.ingest_repo("acme", "widgets")

    assert summary.commits_ingested == 5
    assert summary.prs_ingested == 0
    assert summary.comments_ingested == 0
    assert summary.skipped == []

    # 5 commits in batches of 2 = 3 batches (2 + 2 + 1)
    assert len(call_args) == 3


# ── Batch failure isolation ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ingest_repo_batch_failure_skips_and_continues(monkeypatch: pytest.MonkeyPatch):
    commits = [
        _fake_commit("good1"),
        _fake_commit("good2"),
        _fake_commit("bad1"),
        _fake_commit("good3"),
    ]
    pull_requests = []

    async def fake_fetch_commits(*a, **kw):
        return commits

    async def fake_fetch_prs(*a, **kw):
        return pull_requests

    monkeypatch.setattr(ingestion_service.github_service, "fetch_commits", fake_fetch_commits)
    monkeypatch.setattr(ingestion_service.github_service, "fetch_pull_requests", fake_fetch_prs)

    call_count = 0

    async def _fake_remember_batch(*, entries, dataset_name):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise RuntimeError("LLM quota exceeded")

    monkeypatch.setattr(
        ingestion_service.memory_service, "remember_decision_batch", _fake_remember_batch
    )
    monkeypatch.setattr(ingestion_service, "_INGEST_BATCH_SIZE", 2)

    summary = await ingestion_service.ingest_repo("acme", "widgets")

    # Batch 1 (good1, good2): success → 2 commits ingested
    # Batch 2 (bad1, good3): failure → 0 ingested, 2 skipped
    assert summary.commits_ingested == 2
    assert summary.prs_ingested == 0
    assert summary.comments_ingested == 0

    assert len(summary.skipped) == 2
    assert summary.skipped[0]["source_type"] == "commit"
    assert summary.skipped[0]["source_id"] == "bad1"
    assert summary.skipped[0]["reason"] == "LLM quota exceeded"
    assert summary.skipped[1]["source_id"] == "good3"

    # 3 batches total (2 processed, even though 2nd failed, the 3rd would
    # have been attempted — but after the 2nd batch consumed 2 entries,
    # only 0 remain, so only 2 calls total)
    assert call_count == 2


# ── Empty repos ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ingest_repo_empty(monkeypatch: pytest.MonkeyPatch):
    async def fake_fetch(*a, **kw):
        return []

    monkeypatch.setattr(ingestion_service.github_service, "fetch_commits", fake_fetch)
    monkeypatch.setattr(ingestion_service.github_service, "fetch_pull_requests", fake_fetch)
    monkeypatch.setattr(
        ingestion_service.memory_service,
        "remember_decision_batch",
        lambda *, entries, dataset_name: None,
    )
    monkeypatch.setattr(ingestion_service, "_INGEST_BATCH_SIZE", 20)

    summary = await ingestion_service.ingest_repo("acme", "empty-repo")

    assert summary.commits_ingested == 0
    assert summary.prs_ingested == 0
    assert summary.comments_ingested == 0
    assert summary.skipped == []


# ── add_manual_decision ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_add_manual_decision(monkeypatch: pytest.MonkeyPatch):
    call_kwargs: dict = {}

    async def _fake_remember(content, dataset_name, source_type, source_id):
        call_kwargs.update(
            content=content, dataset_name=dataset_name, source_type=source_type, source_id=source_id
        )

    monkeypatch.setattr(ingestion_service.memory_service, "remember_decision", _fake_remember)

    await ingestion_service.add_manual_decision("acme", "widgets", "We chose SQLite for the MVP.")

    assert "We chose SQLite for the MVP." in call_kwargs["content"]
    assert "acme/widgets" in call_kwargs["content"]
    assert call_kwargs["dataset_name"] == "repo:acme/widgets"
    assert call_kwargs["source_type"] == "manual_log"
    assert isinstance(call_kwargs["source_id"], str)
    assert len(call_kwargs["source_id"]) > 0


# ── Helper unit tests ────────────────────────────────────────────────────────


def test_normalize_text():
    assert ingestion_service._normalize_text(" hello ", "fallback") == "hello"
    assert ingestion_service._normalize_text(None, "fallback") == "fallback"
    assert ingestion_service._normalize_text("", "fallback") == "fallback"
    assert ingestion_service._normalize_text("   ", "fallback") == "fallback"


def test_dataset_name():
    assert ingestion_service._dataset_name("acme", "widgets") == "repo:acme/widgets"
    assert ingestion_service._dataset_name("a/b", "c") == "repo:a/b/c"


def test_format_commit_text():
    commit = _fake_commit("abc", "Add tests", files=["test_app.py"])
    text = ingestion_service._format_commit_text("acme", "widgets", commit)
    assert "abc" in text
    assert "acme/widgets" in text
    assert "Add tests" in text
    assert "test_app.py" in text


def test_format_commit_text_no_files():
    commit = _fake_commit("abc", "Initial")
    text = ingestion_service._format_commit_text("acme", "widgets", commit)
    assert "The changed files were not included" in text


def test_format_commit_text_none_fields():
    commit = CommitData(sha="abc", message="fix")
    text = ingestion_service._format_commit_text("acme", "w", commit)
    assert "unknown author" in text
    assert "unknown date" in text
    assert "make an undocumented change" not in text  # message is "fix"


def test_format_pr_text():
    pr = _fake_pr(5, comments=[])
    text = ingestion_service._format_pr_text("acme", "widgets", pr)
    assert "PR #5" in text
    assert "acme/widgets" in text
    assert "It has not been merged" in text


def test_format_pr_text_merged():
    pr = PRData(
        number=5, title="Merged PR", body="body", state="closed", merged_at="2025-02-01T00:00:00Z"
    )
    text = ingestion_service._format_pr_text("acme", "widgets", pr)
    assert "merged on 2025-02-01" in text


def test_format_pr_comment_text():
    pr = _fake_pr(3)
    comment = _fake_comment("99", "LGTM")
    text = ingestion_service._format_pr_comment_text("acme", "widgets", pr, comment)
    assert "PR #3" in text
    assert "LGTM" in text
    assert "reviewer" in text


def test_build_comment_source_id():
    pr = _fake_pr(3)
    comment = _fake_comment("99")
    assert ingestion_service._build_comment_source_id(pr, comment, 0) == "3:99"


def test_build_comment_source_id_fallback():
    pr = _fake_pr(3)
    comment = PRComment(comment_id=None, author="u", body="b", created_at="2025-01-02")
    result = ingestion_service._build_comment_source_id(pr, comment, 0)
    assert result.startswith("3:0:")


def test_skip_entry():
    entry = ingestion_service._skip_entry("commit", "abc", "error")
    assert entry == {"source_type": "commit", "source_id": "abc", "reason": "error"}


def test_batched_entries():
    entries = [RememberEntry(source_type="commit", source_id=str(i), content="x") for i in range(5)]
    batches = ingestion_service._batched_entries(entries, 2)
    assert len(batches) == 3
    assert len(batches[0]) == 2
    assert len(batches[1]) == 2
    assert len(batches[2]) == 1


def test_batched_entries_clamp_min():
    entries = [RememberEntry(source_type="commit", source_id="1", content="x")]
    batches = ingestion_service._batched_entries(entries, 0)
    assert len(batches) == 1
    assert len(batches[0]) == 1
