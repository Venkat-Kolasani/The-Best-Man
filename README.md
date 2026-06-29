# The Best Man

**A decision-memory agent for codebases.**

Every engineering team has faced the same kind of "decision amnesia": a production incident is resolved, a dependency is swapped, an architecture is reconsidered — and six months later nobody remembers why. The Best Man ingests git commits, PR discussions, and manual decision logs into a Cognee knowledge graph, then lets you ask natural-language questions like *"why did we drop approach X?"* or *"what were the trade-offs when we chose Y over Z?"* and get answers traced back to the actual decisions.

## Setup

### Prerequisites

- Python 3.11+
- Node.js 20+
- pip

### Backend

```bash
cd backend
cp .env.example .env
# edit .env with your keys (see below)
pip install -e .
uvicorn app.main:app --reload
```

#### Environment variables

| Variable | Where to get it |
|---|---|
| `LLM_API_KEY` | [OpenAI API keys](https://platform.openai.com/api-keys) (or your preferred LLM provider's console) |
| `GITHUB_TOKEN` | [GitHub Tokens](https://github.com/settings/tokens) — needs `repo` or `public_repo` scope |
| `COGNEE_LLM_PROVIDER` | `"openai"` (default), `"anthropic"`, or any [litellm provider](https://docs.litellm.ai/docs/providers) |
| `COGNEE_LLM_MODEL` | Model name your provider supports, e.g. `"gpt-4o"`, `"claude-sonnet-4-20250514"` |

Cognee 1.2+ enables multi-user access control by default. For local dev, add `ENABLE_BACKEND_ACCESS_CONTROL=false` to `.env` to skip authentication.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Tests

```bash
cd backend
pip install -e ".[dev]"
pytest
```

## Project Structure

```
backend/          — FastAPI application
frontend/         — Vite + React UI
docs/             — Architecture & demo documentation
```
