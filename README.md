# The Best Man

**A decision-memory agent for codebases.**

Every engineering team has faced the same kind of "decision amnesia": a production incident is resolved, a dependency is swapped, an architecture is reconsidered — and six months later nobody remembers why. The Best Man ingests git commits, PR discussions, and manual decision logs into a Cognee knowledge graph, then lets you ask natural-language questions like *"why did we drop approach X?"* or *"what were the trade-offs when we chose Y over Z?"* and get answers traced back to the actual decisions.

## Setup

### Prerequisites

- Python 3.11+
- Node.js 20+
- pip
- [Ollama](https://ollama.com/)

### Backend

```bash
ollama pull nomic-embed-text
ollama serve

cd backend
cp .env.example .env
# fill in your required variables
pip install -e .
python -m uvicorn app.main:app --reload
```

#### Environment variables

| Variable | Value / where to get it |
|---|---|
| `LLM_PROVIDER` | `custom` |
| `LLM_MODEL` | `groq/llama-3.3-70b-versatile` |
| `LLM_API_KEY` | Create a Groq API key at [console.groq.com/keys](https://console.groq.com/keys) |
| `EMBEDDING_PROVIDER` | `ollama` |
| `EMBEDDING_MODEL` | `nomic-embed-text` |
| `EMBEDDING_ENDPOINT` | `http://localhost:11434/api/embed` |
| `EMBEDDING_DIMENSIONS` | `768` |
| `HUGGINGFACE_TOKENIZER` | `nomic-ai/nomic-embed-text-v1.5` |
| `EMBEDDING_BATCH_SIZE` | `8` |
| `GITHUB_TOKEN` | [GitHub Tokens](https://github.com/settings/tokens) — needs `repo` or `public_repo` scope |
| `COGNEE_DB_PATH` | Optional local storage path, default `data/cognee` |

Cognee 1.2+ enables multi-user access control by default. For local dev, add `ENABLE_BACKEND_ACCESS_CONTROL=false` to `.env` to skip authentication.

Current runtime architecture:
- LLM: Groq via LiteLLM
- Embeddings: Ollama with `nomic-embed-text`

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Tests

```bash
cd backend
pytest
```

Tests marked ``@pytest.mark.live_cognee`` exercise real Cognee API calls
(remember, recall, forget) against a disposable dataset and will consume
LLM / embedding credits. They are **skipped by default**. To run them:

```bash
pytest -m live_cognee
```

You must have a valid ``LLM_API_KEY`` and working LLM/embedding provider
configured in your ``.env`` for these integration tests to pass.

## Project Structure

```
backend/          — FastAPI application
frontend/         — Vite + React UI
docs/             — Architecture & demo documentation
```
