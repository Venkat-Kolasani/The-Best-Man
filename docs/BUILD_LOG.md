# Build Log

## 2026-06-29 — Initial Scaffold

### What we did
- Set up the repo structure: FastAPI backend, Vite+React frontend, docs stubs
- Installed and verified Cognee v1.2.2 (had to fix a broken editable install from `/private/tmp/cognee`)
- Pushed to GitHub

### API surface verified (cognee 1.2.2)
We checked the actual installed `__init__.py` and function signatures. Key findings:

**V2 API (high-level):**
- `remember(data, dataset_name="main_dataset", session_id=None, ...) -> RememberResult` — combined add+cognify (permanent) or session cache + improve (session mode)
- `recall(query_text, query_type=None, datasets=None, session_id=None, ...) -> list[RecallResponse]` — searches session first, falls through to graph; results tagged with `_source`
- `improve(dataset="main_dataset", session_ids=None, ...) — enriches graph, bridges session feedback
- `forget(data_id=None, dataset=None, everything=False, ...) -> dict` — unified deletion

**V1 API (still supported):**
- `add(data, dataset_name="main_dataset", ...)` — ingest raw data
- `cognify(datasets=None, ...)` — build knowledge graph from added data
- `search(query_text, query_type=GRAPH_COMPLETION, ...) -> list[SearchResult]` — lower-level search
- `memify(extraction_tasks=None, enrichment_tasks=None, ...)` — enrichment pipeline

**Key config flags discovered:**
- Multi-user access control is ON by default → set `ENABLE_BACKEND_ACCESS_CONTROL=false` to disable
- Session memory enabled by default → set `CACHING=false` to disable

### Decisions
- Using `pip` (not `uv`) — it's what was available and working
- Dataset naming convention: `f"repo:{owner}/{repo}"` per cursorrules
- `dataset_name` param in `remember`/`add` is the primary scoping mechanism; `session_id` is ephemeral only
- Using V2 API (`remember`/`recall`/`improve`/`forget`) as primary interface since it's the recommended 1.0+ path

## 2026-06-29 — Switched to Gemini (free tier)

### Why
User doesn't have OpenAI credits. Gemini 1.5 Flash via Google AI Studio has a generous free tier (60 req/min, no credit card needed).

### Changes
- `config.py`: default provider changed from `openai` → `litellm`, model from `gpt-4o` → `gemini/gemini-1.5-flash`
- `.env.example`: updated with Gemini setup instructions + link to get free API key
- `README.md`: env var table updated to show Gemini as the recommended free option

### How Cognee routes to Gemini
Cognee uses litellm internally. With `provider="litellm"` and `model="gemini/gemini-1.5-flash"`, litellm handles the API routing. The `LLM_API_KEY` is a Google AI Studio API key.

## 2026-06-29 — Smoke Test Script

### What we built
- `backend/scripts/smoke_test.py` — standalone script (not pytest) that exercises the full Cognee lifecycle

### Design
- Phase 1: 3x `remember_decision` with TEST-prefixed, clearly fake content about a Postgres decision
- Phase 2: `recall_answer` with a question that requires combining at least 2 of the 3 facts
- Phase 3: `forget_dataset` to clean up
- Phase 4: `recall_answer` again — expects empty result
- Phase 5: comparison summary printed for visual confirmation

### Notes
- Has a confirmation prompt before executing any API calls (credit-cost awareness)
- Adds `backend/` to `sys.path` so it can be run as `python scripts/smoke_test.py` from the `backend/` directory
- Not run yet — user will run it once they add their `LLM_API_KEY`

## 2026-06-29 — Memory Service Layer

### What we built
- `backend/app/services/memory_service.py` — typed Cognee wrapper for the project

### Design decisions

**Why `remember_decision` embeds provenance in the content string**
Cognee 1.2.2's `remember()` has no dedicated `metadata` parameter. To trace any graph node back to its origin (commit SHA, PR comment ID, etc.), we embed `[source: <type> | id: <id>]\n<content>` in the text itself. The graph extractor naturally picks up these tokens as entities during cognify.

**Why `improve_memory` does remember+improve, not just improve**
Cognee's `improve()` enriches the existing graph (triplet embeddings, indexing) but doesn't accept free-form feedback as input. So we first `remember()` the feedback (which runs add+cognify+improve by default), then call `improve()` again to ensure enrichment. This guarantees the feedback text enters the graph as nodes and receives full processing.

**Why `recall_answer` passes `include_references=True`**
Per .cursorrules ground rule #7: graph traversal visualization is a first-class feature. Passing `include_references=True` ensures Cognee returns traversal metadata that the UI can render alongside the answer.

**Error defense pattern**
Every wrapper function calls `_check_params()` before invoking Cognee — inspects the installed function's signature to fail fast with a clear `MemoryServiceError` if a parameter doesn't exist, rather than letting Cognee fail with a confusing traceback.

**Return types**
`RecallResult` is a project-specific dataclass (`answer`, `source`, `references`, `raw`) — the API layer never needs to import Cognee directly.
