#!/usr/bin/env python3
"""Smoke test for The Best Man's Cognee integration.

Ingests three fake-but-labeled decisions, queries across them, forgets
the dataset, and confirms the data is gone.

Usage:
    python scripts/smoke_test.py

WARNING: This makes real Cognee/LLM API calls and may cost money.
You will be prompted to confirm before anything executes.
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path
import os

# ---------------------------------------------------------------------------
# Add the parent directory so we can import app.services.memory_service
# when run as `python scripts/smoke_test.py` from the backend/ directory.
# ---------------------------------------------------------------------------
BACKEND_DIR = Path(__file__).resolve().parent.parent


def ensure_compatible_runtime() -> None:
    """Re-exec into a Python runtime that has Cognee and its compiled deps."""
    try:
        import cognee  # noqa: F401
        return
    except ImportError:
        pass

    if os.environ.get("TBM_SMOKE_REEXEC") == "1":
        return

    for candidate in ("/opt/anaconda3/bin/python", "/opt/anaconda3/bin/python3"):
        candidate_path = Path(candidate)
        if not candidate_path.exists() or Path(sys.executable).resolve() == candidate_path.resolve():
            continue

        os.environ["TBM_SMOKE_REEXEC"] = "1"
        os.execv(candidate, [candidate, str(Path(__file__).resolve()), *sys.argv[1:]])


def load_backend_env() -> None:
    """Load backend/.env without depending on python-dotenv at runtime."""
    env_path = BACKEND_DIR / ".env"

    try:
        from dotenv import load_dotenv
    except ImportError:
        if not env_path.exists():
            return

        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                value = value[1:-1]
            os.environ[key.strip()] = value
        return

    load_dotenv(env_path, override=True)


ensure_compatible_runtime()
load_backend_env()
sys.path.insert(0, str(BACKEND_DIR))

from app.services.memory_service import (
    MemoryServiceError,
    remember_decision,
    recall_answer,
    forget_dataset,
)

DATASET = "smoke_test"


def confirm() -> bool:
    """Prompt the user before making real API calls."""
    print("=" * 60)
    print("  Cognee Smoke Test")
    print("=" * 60)
    print()
    print(f"  Dataset : {DATASET}")
    print("  Actions : 3x remember_decision  ->  recall_answer")
    print("            -> forget_dataset     -> recall_answer")
    print()
    print("  WARNING: This will call the real Cognee/LLM API and")
    print("           may incur costs if your LLM_API_KEY is set.")
    print()
    resp = input("  Continue? [y/N] ").strip().lower()
    if resp != "y":
        print("  Aborted.")
        return False
    return True


async def main() -> None:
    if not confirm():
        sys.exit(0)

    # -----------------------------------------------------------------------
    # Phase 1: Ingest three labelled test decisions.
    # -----------------------------------------------------------------------
    print("\n--- Phase 1: remember_decision (3 items) ---\n")
    decisions = [
        (
            "TEST: the team chose Postgres over MongoDB for ACID guarantees",
            "commit",
            "abc123",
        ),
        (
            "TEST: the migration to Postgres was completed in Q2 2025",
            "commit",
            "def456",
        ),
        (
            "TEST: the ACID compliance requirement came from the finance team",
            "pr_comment",
            "ghi789",
        ),
    ]

    for i, (content, source_type, source_id) in enumerate(decisions, 1):
        t0 = time.perf_counter()
        try:
            await remember_decision(
                content=content,
                dataset_name=DATASET,
                source_type=source_type,
                source_id=source_id,
            )
            elapsed = time.perf_counter() - t0
            print(f"  [{i}/{len(decisions)}] OK  ({elapsed:.1f}s)  {source_type}:{source_id}")
        except MemoryServiceError as exc:
            print(f"  [{i}/{len(decisions)}] FAIL  {exc}")
            print("  Aborting — phase 1 must succeed before continuing.")
            sys.exit(1)

    # -----------------------------------------------------------------------
    # Phase 2: Recall — ask a question that needs at least two facts.
    # -----------------------------------------------------------------------
    print("\n--- Phase 2: recall_answer ---\n")
    query = (
        "Why did the team choose Postgres, and who required ACID compliance?"
    )
    print(f"  Query: {query}\n")

    t0 = time.perf_counter()
    try:
        result = await recall_answer(query=query, dataset_name=DATASET)
        elapsed = time.perf_counter() - t0
    except MemoryServiceError as exc:
        print(f"  FAIL  {exc}")
        sys.exit(1)

    print(f"  Elapsed : {elapsed:.1f}s")
    print(f"  Source  : {result.source}")
    print(f"  Refs    : {len(result.references)} reference(s)")
    print(f"  Answer  :")
    for line in result.answer.splitlines():
        print(f"           {line}")
    print()

    # -----------------------------------------------------------------------
    # Phase 3: Forget the dataset.
    # -----------------------------------------------------------------------
    print("--- Phase 3: forget_dataset ---\n")
    t0 = time.perf_counter()
    try:
        await forget_dataset(dataset_name=DATASET)
        elapsed = time.perf_counter() - t0
        print(f"  OK  ({elapsed:.1f}s)")
    except MemoryServiceError as exc:
        print(f"  FAIL  {exc}")
        sys.exit(1)

    # -----------------------------------------------------------------------
    # Phase 4: Recall again — must come back empty.
    # -----------------------------------------------------------------------
    print("\n--- Phase 4: recall_answer (after forget) ---\n")
    print(f"  Query: {query}\n")

    t0 = time.perf_counter()
    try:
        after_result = await recall_answer(query=query, dataset_name=DATASET)
        elapsed = time.perf_counter() - t0
    except MemoryServiceError as exc:
        print(f"  FAIL  {exc}")
        sys.exit(1)

    print(f"  Elapsed : {elapsed:.1f}s")
    print(f"  Source  : {after_result.source}")
    print(f"  Refs    : {len(after_result.references)} reference(s)")
    print(f"  Answer  :")
    for line in after_result.answer.splitlines():
        print(f"           {line}")
    print()

    # -----------------------------------------------------------------------
    # Phase 5: Comparison summary.
    # -----------------------------------------------------------------------
    print("--- Comparison ---\n")
    print(f"  Before forget — answer length: {len(result.answer)} chars")
    print(f"  Before forget — source:        {result.source}")
    print(f"  After forget  — answer length: {len(after_result.answer)} chars")
    print(f"  After forget  — source:        {after_result.source}")

    if after_result.answer and len(after_result.answer) > 0:
        print("\n  ⚠ WARNING: recall returned content after forget_dataset.")
        print("    The dataset may not have been fully cleaned up.")
        print("    Visually inspect both answers above.")
    else:
        print("\n  ✅ Empty response after forget — dataset was removed.")

    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
