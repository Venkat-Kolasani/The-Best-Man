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
# edit .env with your keys
pip install -e .
uvicorn app.main:app --reload
```

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
