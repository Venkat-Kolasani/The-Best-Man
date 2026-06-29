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
| `LLM_API_KEY` | **Free**: [Google AI Studio](https://aistudio.google.com/apikey) (Gemini 3.1 Flash Lite — free tier, no CC needed). **Paid**: [OpenAI](https://platform.openai.com/api-keys) or [Anthropic](https://console.anthropic.com/) |
| `LLM_PROVIDER` | `"gemini"` (Gemini default), `"openai"`, or `"anthropic"` |
| `LLM_MODEL` | `"gemini/gemini-3.1-flash-lite"` (default), `"gpt-4o"`, or `"claude-sonnet-4-20250514"` |
| `GITHUB_TOKEN` | [GitHub Tokens](https://github.com/settings/tokens) — needs `repo` or `public_repo` scope |

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
