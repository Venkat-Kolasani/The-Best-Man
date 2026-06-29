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
